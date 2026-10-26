/* Data access for the Control Panel.
 *
 * Three transports, in order of preference:
 *   1. native  — the Tauri shell calls bunny-sessiond over its unix socket.
 *   2. bridge  — a loopback HTTP bridge proxies the same command vocabulary.
 *   3. mock    — deterministic demo data so the UI still renders offline.
 *
 * The UI never talks to the daemon directly: every call goes through one of the
 * three backends above, and the daemon re-authorises every privileged command.
 */

import { createMockBackend } from './mock.js';

const DEFAULT_BRIDGE = 'http://127.0.0.1:8421';
const DEFAULT_AGENT = 'http://127.0.0.1:8422';

const query = new URLSearchParams(window.location.search);
const bridgeUrl = (query.get('bridge') || DEFAULT_BRIDGE).replace(/\/+$/, '');
const agentUrl = (query.get('agent') || DEFAULT_AGENT).replace(/\/+$/, '');

function nativeInvoke() {
  const tauri = globalThis.__TAURI__;
  if (tauri?.core?.invoke) {
    return (cmd, args) => tauri.core.invoke('bunny_call', { cmd, args });
  }
  if (typeof globalThis.__BUNNY_NATIVE__?.call === 'function') {
    return (cmd, args) => globalThis.__BUNNY_NATIVE__.call(cmd, args);
  }
  return null;
}

function unwrapNative(res) {
  if (res && typeof res === 'object' && 'ok' in res) {
    if (!res.ok) throw new Error(res.error || 'native command failed');
    return res.result;
  }
  return res;
}

export class PanelApi {
  constructor() {
    this.mode = 'mock';
    this.label = 'Offline preview';
    this.error = null;
    this.agentReachable = false;
    this.bridgeUrl = bridgeUrl;
    this.agentUrl = agentUrl;
    this._invoke = nativeInvoke();
    this.backend = createMockBackend();
  }

  get isMock() {
    return this.mode === 'mock';
  }

  async connect() {
    if (this._invoke) {
      try {
        const pong = unwrapNative(await this._invoke('ping', {}));
        if (pong && (pong.pong || pong.version)) {
          this.mode = 'native';
          this.label = 'Native shell';
          this.error = null;
          return this;
        }
      } catch (err) {
        this.error = `native shell: ${err?.message || err}`;
      }
    }

    try {
      const health = await this._fetchJson(`${this.bridgeUrl}/api/health`, { timeout: 1400 });
      if (health?.ok) {
        this.mode = 'bridge';
        this.label = 'Local bridge';
        this.error = null;
        return this;
      }
    } catch (err) {
      this.bridgeError = `bridge: ${err?.message || err}`;
    }

    this.mode = 'mock';
    this.label = 'Offline preview';
    this.backend = createMockBackend();
    return this;
  }

  async _fetchJson(url, { method = 'GET', body = null, timeout = 8000 } = {}) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {
        method,
        headers: body ? { 'Content-Type': 'application/json' } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      const text = await response.text();
      let data = null;
      if (text) {
        try { data = JSON.parse(text); } catch { data = null; }
      }
      if (!response.ok) {
        throw new Error(data?.error || `${response.status} ${response.statusText}`);
      }
      return data;
    } finally {
      window.clearTimeout(timer);
    }
  }

  async call(cmd, args = {}) {
    if (this.mode === 'native') {
      // nativeInvoke() already wraps the Tauri command; do not nest it again.
      return unwrapNative(await this._invoke(cmd, args));
    }
    if (this.mode === 'bridge') {
      const data = await this._fetchJson(`${this.bridgeUrl}/api/call`, {
        method: 'POST',
        body: { cmd, args },
        timeout: 40000,
      });
      if (!data?.ok) throw new Error(data?.error || 'bridge rejected the command');
      return data.result;
    }
    return this.backend.call(cmd, args);
  }

  // -- sessiond -----------------------------------------------------------
  status() { return this.call('status'); }

  getSettings() { return this.call('get-settings'); }

  setSettings(patch, confirm = null) {
    return this.call('set-settings', { patch, confirm });
  }

  setMode(mode) { return this.call('set-mode', { mode }); }

  switchMode(mode) { return this.call('switch-mode', { mode }); }

  library(refresh = false) { return this.call('library', { refresh }); }

  launch(platform, gameId = '') { return this.call('launch', { platform, game_id: gameId || null }); }

  agent(action = 'status') { return this.call('agent', { action }); }

  inputAgent(enable, confirm = null) { return this.call('input-agent', { enable, confirm }); }

  installer() { return this.call('installer', {}); }

  power(action) { return this.call('power', { action }); }

  update(action = 'check') { return this.call('update', { action }); }

  audit(lines = 40) { return this.call('audit-tail', { lines }); }

  // -- Bun Bun agent ------------------------------------------------------
  async _agent(path, { method = 'GET', body = null, timeout = 7000 } = {}) {
    try {
      const data = await this._fetchJson(`${this.agentUrl}${path}`, { method, body, timeout });
      this.agentReachable = true;
      return data;
    } catch (err) {
      this.agentReachable = false;
      this.agentError = String(err?.message || err);
      return null;
    }
  }

  agentHealth() {
    if (this.isMock) return this.backend.agent.health();
    return this._agent('/health');
  }

  agentStatus() {
    if (this.isMock) return this.backend.agent.status();
    return this._agent('/v1/status');
  }

  hint(secret = false) {
    if (this.isMock) return this.backend.agent.hint(secret);
    return this._agent('/v1/hint', { method: 'POST', body: { secret } });
  }

  say(text) {
    if (this.isMock) return this.backend.agent.say(text);
    return this._agent('/v1/say', { method: 'POST', body: { text } });
  }

  join(payload) {
    if (this.isMock) return this.backend.agent.join(payload);
    return this._agent('/v1/coop/join', { method: 'POST', body: payload });
  }

  leaveCoop(reason = 'player request') {
    if (this.isMock) return this.backend.agent.leave();
    return this._agent('/v1/coop/leave', { method: 'POST', body: { reason } });
  }

  purgeMemory() {
    if (this.isMock) return this.backend.agent.purgeMemory();
    return this._agent('/v1/memory/purge', { method: 'POST', body: {} });
  }

  /** Subscribe to the overlay SSE stream. Returns an unsubscribe function. */
  openEvents(onEvent, onState) {
    if (this.isMock) {
      this.agentReachable = true;
      onState?.(true);
      return () => {};
    }
    let source = null;
    try {
      source = new EventSource(`${this.agentUrl}/v1/stream`);
    } catch {
      onState?.(false);
      return () => {};
    }
    source.onopen = () => {
      this.agentReachable = true;
      onState?.(true);
    };
    source.onerror = () => {
      this.agentReachable = false;
      onState?.(false);
    };
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data);
        if (event && event.topic) onEvent?.(event);
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => {
      try { source.close(); } catch { /* already closed */ }
    };
  }
}
