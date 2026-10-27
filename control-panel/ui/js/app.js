/* Control Panel shell: routing, focus, gamepad input, settings mutations and
 * the Bun Bun overlay stream. Views are pure markup; every action funnels
 * through the small action map at the bottom of this file. */

import { PanelApi } from './api.js';
import { FocusNav } from './nav.js';
import { startGamepad } from './gamepad.js';
import { createQuickMenu } from './quickmenu.js';
import { createCompanion } from './companion.js';
import { esc, platformLabel } from './util.js';
import { RECOMMENDED } from './views/tweaks.js';
import * as home from './views/home.js';
import * as platforms from './views/platforms.js';
import * as tweaks from './views/tweaks.js';
import * as bunbun from './views/bunbun.js';
import * as settings from './views/settings.js';

const VIEWS = { home, platforms, tweaks, bunbun, settings };
const VIEW_ORDER = ['home', 'platforms', 'tweaks', 'bunbun', 'settings'];
const NUMERIC = new Set([
  'performance.fps_cap',
  'performance.tdp_watts',
  'display.refresh_hz',
  'audio.latency_ms',
  'audio.bunbun_volume',
]);
const CONSENT = {
  'ai.coop_opt_in': 'I understand Bun Bun may join multiplayer lobbies',
  'ai.screen_vision': 'Screen vision is a reserved feature and does nothing in v0.1. Continue?',
  'performance.allow_overclock': 'I understand overclocking can damage hardware',
};

const api = new PanelApi();
const state = {
  view: 'home',
  status: null,
  settings: {},
  library: null,
  libraryFilter: 'all',
  bunbun: { online: false, status: null, line: '' },
  connection: { mode: 'mock', label: 'Offline preview' },
  busy: false,
};
const ctx = { state, api };

const $ = (id) => document.getElementById(id);
const viewEl = (name = state.view) => document.querySelector(`[data-view-panel="${name}"]`);
let modalClose = null;
let unsubscribe = () => {};

// ---------------------------------------------------------------------------
// Focus and input
// ---------------------------------------------------------------------------
const nav = new FocusNav({
  onBack: () => {
    if (modalClose) {
      modalClose();
      return;
    }
    if (state.view !== 'home') navigate('home');
  },
  onMenu: () => {
    if (!modalClose) navigate('settings');
  },
  onTab: (direction) => {
    if (!modalClose) cycle(direction);
  },
});

// Quick access (carrot button / C / LB+RB) and the Bun Bun companion invite
// themselves into the shell rather than the other way around, so views stay
// pure markup.
const quickMenu = createQuickMenu({ nav, viewEl });
const companion = createCompanion({ onOpen: () => navigate('bunbun') });

// #quickaccess is deferred until the first navigate() lands, otherwise the boot
// sequence repaints focus onto Home and the menu opens with no focus inside it.
let pendingQuick = location.hash === '#quickaccess';

function onAction(action) {
  if (action === 'quick-menu') {
    if (!modalClose) quickMenu.toggle();
    return;
  }
  if (action === 'accept') {
    nav.activate();
    return;
  }
  if (action === 'back') {
    if (modalClose) modalClose();
    else if (state.view !== 'home') navigate('home');
    return;
  }
  if (action === 'tab-left' || action === 'tab-right') {
    if (!modalClose) cycle(action === 'tab-left' ? -1 : 1);
    return;
  }
  if (action === 'menu') {
    if (!modalClose) navigate('settings');
    return;
  }
  nav.move(action);
}

// ---------------------------------------------------------------------------
// Chrome
// ---------------------------------------------------------------------------
function tickClock() {
  const clock = $('clock');
  if (clock) clock.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function paintChrome() {
  const mode = state.status?.mode || 'gaming';
  const online = Boolean(state.bunbun.online);

  if ($('mode-label')) $('mode-label').textContent = mode === 'gaming' ? 'Gaming Mode' : 'Desktop Mode';
  const chip = $('agent-chip');
  if (chip) chip.dataset.state = online ? 'online' : 'offline';
  if ($('agent-label')) $('agent-label').textContent = online ? 'Bun Bun online' : 'Bun Bun offline';
  if ($('runtime-label')) $('runtime-label').textContent = state.connection.label || 'local-only';

  const version = state.status?.version || '0.1.0';
  const channel = state.settings?.updates?.channel || 'dev';
  if ($('build-label')) $('build-label').textContent = `v${version} · ${channel}`;

  if ($('hint-status')) {
    const count = state.library?.games?.length;
    $('hint-status').textContent = state.library?.error
      ? 'Library unavailable'
      : `${count ?? 0} games · ${state.connection.label}`;
  }

  // Screen-aware companion: session mode + panel view + the title the
  // perception watcher currently reports. No camera, no microphone.
  companion.setScreen({
    mode,
    view: state.view,
    title: state.bunbun.status?.watcher?.title || '',
    online,
  });
}

// ---------------------------------------------------------------------------
// Toasts and modals
// ---------------------------------------------------------------------------
function toast(message, { title = 'Bunny OS', kind = 'info', bunbun: isBunBun = false, timeout = 5600 } = {}) {
  const host = $('toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast${isBunBun ? ' toast--bunbun' : ''}${kind === 'warn' ? ' toast--warn' : ''}`;
  el.innerHTML = `${isBunBun ? '<span class="toast__avatar"><img src="assets/bunny.svg" alt=""></span>' : ''}
    <div class="toast__body"><strong>${esc(title)}</strong>${esc(message)}</div>
    <button class="toast__close" aria-label="Dismiss" type="button">&times;</button>`;
  el.querySelector('.toast__close')?.addEventListener('click', () => el.remove());
  host.appendChild(el);
  window.setTimeout(() => el.remove(), timeout);
  while (host.children.length > 4) host.firstElementChild?.remove();
}

function modal({
  eyebrow = 'Confirm',
  title,
  text = '',
  body = '',
  confirmLabel = 'Continue',
  cancelLabel = 'Cancel',
  danger = false,
}) {
  return new Promise((resolve) => {
    const root = $('modal-root');
    if (!root) {
      resolve(null);
      return;
    }
    root.innerHTML = `<div class="modal-backdrop">
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="modal__eyebrow">${esc(eyebrow)}</div>
        <h2 class="modal__title" id="modal-title">${esc(title)}</h2>
        ${text ? `<p class="modal__text">${text}</p>` : ''}
        ${body}
        <div class="modal__actions">
          <button class="btn btn--ghost" type="button" data-modal="cancel" data-focusable>${esc(cancelLabel)}</button>
          <button class="btn ${danger ? 'btn--danger' : 'btn--primary'}" type="button" data-modal="ok" data-focusable>${esc(confirmLabel)}</button>
        </div>
      </div>
    </div>`;

    const previous = nav.scope;
    nav.setScope(root);
    nav.refresh();

    const finish = (value) => {
      if (!root.firstElementChild) return;
      root.innerHTML = '';
      modalClose = null;
      nav.setScope(previous === document.body ? viewEl() : previous);
      nav.refresh();
      resolve(value);
    };

    modalClose = () => finish(null);
    root.querySelector('[data-modal="cancel"]')?.addEventListener('click', () => finish(null));
    root.querySelector('[data-modal="ok"]')?.addEventListener('click', () => {
      const field = root.querySelector('[data-modal-form]');
      finish({ ok: true, value: field ? field.value : null });
    });
    root.querySelector('.modal-backdrop')?.addEventListener('click', (event) => {
      if (event.target === event.currentTarget) finish(null);
    });

    const field = root.querySelector('[data-modal-form]');
    if (field) window.setTimeout(() => field.focus({ preventScroll: true }), 40);
  });
}

const confirmModal = async (options) => Boolean((await modal(options))?.ok);

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadStatus({ quiet = false } = {}) {
  try {
    const status = await api.status();
    state.status = status;
    state.settings = status?.settings || state.settings || {};
    paintChrome();
    return true;
  } catch (err) {
    if (!quiet) toast(String(err?.message || err), { title: 'Session daemon', kind: 'warn' });
    return false;
  }
}

async function loadLibrary({ force = false, quiet = false } = {}) {
  try {
    const library = await api.library(force);
    state.library = library && typeof library === 'object' ? library : { games: [], platforms: [] };
  } catch (err) {
    state.library = { games: [], platforms: [], error: String(err?.message || err) };
    if (!quiet) toast(String(err?.message || err), { title: 'Library scan', kind: 'warn' });
  }
  paintChrome();
  renderView();
}

async function loadAgent({ quiet = true } = {}) {
  const health = await api.agentHealth();
  if (!health) {
    state.bunbun.online = false;
    paintChrome();
    return;
  }
  const status = await api.agentStatus();
  state.bunbun.online = Boolean(status || health);
  if (status) state.bunbun.status = status;
  if (!state.bunbun.line) {
    state.bunbun.line = 'Hi hi! I am Bun Bun. Ask me for a hint whenever you like.';
  }
  paintChrome();
  if (!quiet && state.view === 'bunbun') renderView();
}

function onAgentEvent(event) {
  const payload = event.payload || {};
  const text = payload.line || payload.text || payload.message || '';
  state.bunbun.online = true;
  if (text) {
    state.bunbun.line = text;
    if (/hint|commentary|coop|consent/i.test(event.topic)) {
      toast(text, { title: 'Bun Bun', bunbun: true });
    }
    if (state.view === 'bunbun' || state.view === 'home') renderView();
  }
  if (event.topic === 'coop.consent_request') {
    toast('A friend invited you. Open Bun Bun to confirm before joining.', {
      title: 'Lobby invite', kind: 'warn',
    });
  }
  if (event.topic === 'coop.refused') {
    toast(payload.reason || 'Bun Bun refused to join this lobby.', { title: 'Co-op', kind: 'warn' });
  }
  companion.react(event.topic, payload);
  paintChrome();
}

// ---------------------------------------------------------------------------
// Routing and rendering
// ---------------------------------------------------------------------------
function renderView() {
  const el = viewEl();
  const view = VIEWS[state.view];
  if (!el || !view) return;
  view.render(el, ctx);
}

function navigate(view, { focus = true } = {}) {
  if (!VIEWS[view]) return;
  state.view = view;
  const app = $('app');
  if (app) app.dataset.view = view;
  document.querySelectorAll('[data-view-panel]').forEach((panel) => {
    panel.hidden = panel.dataset.viewPanel !== view;
  });
  document.querySelectorAll('.rail__item').forEach((item) => {
    item.classList.toggle('is-active', item.dataset.view === view);
  });
  renderView();
  companion.setScreen({ view });
  if (focus) {
    nav.setScope(viewEl());
    nav.refresh();
    viewEl()?.scrollTo?.({ top: 0 });
  }
  // After the focus reset above, so the menu actually owns the D-pad.
  if (pendingQuick) {
    pendingQuick = false;
    quickMenu.open();
  }
}

function cycle(direction) {
  const index = VIEW_ORDER.indexOf(state.view);
  const next = (index + direction + VIEW_ORDER.length) % VIEW_ORDER.length;
  navigate(VIEW_ORDER[next]);
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
function readSetting(key) {
  return String(key).split('.').reduce((node, part) => (node == null ? undefined : node[part]), state.settings);
}

function coerce(key, raw) {
  if (NUMERIC.has(key)) return Number(raw);
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  return raw;
}

async function applySetting(key, raw, { consent = false } = {}) {
  if (state.busy) return;
  const value = coerce(key, raw);

  if (key === 'session.default_mode') {
    state.busy = true;
    try {
      const result = await api.setMode(value);
      state.settings = { ...state.settings, session: { ...state.settings.session, default_mode: value } };
      toast(`Default session saved: ${result?.session || value}. Applies at next login.`);
      renderView();
    } catch (err) {
      toast(String(err?.message || err), { title: 'Session mode', kind: 'warn' });
      renderView();
    } finally {
      state.busy = false;
    }
    return;
  }

  if (consent && value === true) {
    const warning = CONSENT[key] || 'This setting has privacy or safety implications.';
    const agreed = await confirmModal({
      eyebrow: 'Consent required',
      title: 'Turn this on?',
      text: `${esc(warning)}. You can switch it off again at any time.`,
      confirmLabel: 'I understand',
    });
    if (!agreed) {
      renderView();
      return;
    }
  }

  state.busy = true;
  try {
    const patch = {};
    let node = patch;
    const parts = key.split('.');
    for (const part of parts.slice(0, -1)) node = node[part] = node[part] || {};
    node[parts.at(-1)] = value;
    const result = await api.setSettings(patch, consent && value === true ? 'I AGREE' : null);
    state.settings = result?.settings || state.settings;
    if (result?.repairs?.length) {
      toast(result.repairs.join(' · '), { title: 'Adjusted for safety', kind: 'warn' });
    }
    renderView();
    paintChrome();
  } catch (err) {
    toast(String(err?.message || err), { title: 'Setting rejected', kind: 'warn' });
    renderView();
  } finally {
    state.busy = false;
  }
}

async function toggleSetting(el) {
  const key = el.dataset.key;
  const next = !Boolean(readSetting(key));
  await applySetting(key, next, { consent: el.dataset.consent === '1' });
}

// ---------------------------------------------------------------------------
// Games and agents
// ---------------------------------------------------------------------------
async function launchPlatform(platform, { game = '', title = '' } = {}) {
  try {
    await api.launch(platform, game);
    toast(`${title || platformLabel(platform)} is starting…`, { title: 'Launch' });
  } catch (err) {
    toast(String(err?.message || err), { title: platformLabel(platform), kind: 'warn' });
  }
}

async function askHint(secret) {
  if (secret) {
    const agreed = await confirmModal({
      eyebrow: 'Spoiler warning',
      title: 'Ask for a secret?',
      text: 'Secret hints can reveal puzzles, endings or hidden areas. This one is on you.',
      confirmLabel: 'Tell me',
    });
    if (!agreed) return;
  }
  const result = await api.hint(secret);
  const hint = result?.hint;
  if (!hint) {
    toast(state.bunbun.online ? 'No hint ready yet — play a little longer!' : 'Bun Bun is offline right now.', {
      title: 'Bun Bun', kind: 'warn',
    });
    return;
  }
  state.bunbun.line = hint.text;
  toast(hint.text, { title: 'Bun Bun', bunbun: true });
  if (state.view === 'bunbun' || state.view === 'home') renderView();
}

async function sayHi() {
  const result = await api.say('Hi hi! I missed you.');
  if (!result) {
    toast('Bun Bun is offline right now.', { title: 'Bun Bun', kind: 'warn' });
    return;
  }
  state.bunbun.line = result.text || 'Hi hi!';
  toast(result.text || 'Hi hi!', { title: 'Bun Bun', bunbun: true });
  renderView();
}

async function joinLobby() {
  const invite = await modal({
    eyebrow: 'Multiplayer co-op',
    title: "Join a friend's lobby",
    text: 'Bun Bun checks the allowlist and anti-cheat policy, then opens the game. You still accept the invite in-game.',
    body: `<label class="field"><span>Lobby link or code</span>
      <input class="text-input" data-modal-form data-focusable
             placeholder="steam://joinlobby/… or lobby code" aria-label="Lobby link or code"></label>`,
    confirmLabel: 'Check invite',
  });
  if (!invite?.ok) return;

  const raw = String(invite.value || '').trim();
  if (!raw) {
    toast('Paste a lobby link or code first.', { kind: 'warn' });
    return;
  }

  let payload = { platform: 'steam', game_id: raw, title: raw, allowlisted: false };
  const deepLink = raw.match(/^steam:\/\/joinlobby\/(\d+)\/(\w+)/i);
  if (deepLink) {
    payload = {
      platform: 'steam',
      game_id: `steam:${deepLink[1]}`,
      app_id: deepLink[1],
      lobby_id: deepLink[2],
      title: `Steam app ${deepLink[1]}`,
      allowlisted: false,
    };
  }

  const result = await api.join({ invite: payload, confirmed: true });
  if (!result) {
    toast('Bun Bun is offline.', { title: 'Co-op', kind: 'warn' });
    return;
  }
  if (result.status === 'joined') {
    toast('Lobby opened — have fun, and be nice to the strangers!', { title: 'Bun Bun', bunbun: true });
  } else if (result.status === 'manual' || result.status === 'dry-run') {
    toast(result.message || 'Follow the invite steps in-game.', { title: 'Bun Bun', bunbun: true });
  } else {
    toast(result.reason || result.message || `Could not join (${result.status || 'refused'}).`, {
      title: 'Co-op', kind: 'warn',
    });
  }
  await loadAgent();
  if (state.view === 'bunbun') renderView();
}

// ---------------------------------------------------------------------------
// System actions
// ---------------------------------------------------------------------------
async function switchMode(target) {
  const current = state.status?.mode || 'gaming';
  const wanted = target || (current === 'gaming' ? 'desktop' : 'gaming');
  if (wanted === current) {
    toast(`Already in ${wanted === 'gaming' ? 'Gaming' : 'Desktop'} Mode.`);
    return;
  }
  const agreed = await confirmModal({
    eyebrow: 'Session switch',
    title: `Switch to ${wanted === 'gaming' ? 'Gaming' : 'Desktop'} Mode?`,
    text: 'Bunny OS restarts the display manager. Save your game and close anything unsaved first.',
    confirmLabel: 'Switch now',
  });
  if (!agreed) return;
  try {
    await api.switchMode(wanted);
    toast('Display manager is restarting…', { title: 'Session' });
  } catch (err) {
    toast(String(err?.message || err), { title: 'Session switch', kind: 'warn' });
  }
}

async function power(action) {
  const labels = { reboot: 'Restart', poweroff: 'Shut down', logout: 'Log out', suspend: 'Suspend' };
  const agreed = await confirmModal({
    eyebrow: 'Power',
    title: `${labels[action] || action}?`,
    text: action === 'poweroff' || action === 'reboot'
      ? 'Any unsaved game progress will be lost.'
      : 'The session will end and return to the display manager.',
    confirmLabel: labels[action] || action,
    danger: action === 'poweroff',
  });
  if (!agreed) return;
  try {
    await api.power(action);
    toast(`${labels[action] || action} requested.`, { title: 'Power' });
  } catch (err) {
    toast(String(err?.message || err), { title: 'Power', kind: 'warn' });
  }
}

async function purgeMemory() {
  const agreed = await confirmModal({
    eyebrow: 'Privacy',
    title: 'Purge Bun Bun memory?',
    text: 'Deletes the local journal of hints, discoveries and preferences. This cannot be undone.',
    confirmLabel: 'Purge',
    danger: true,
  });
  if (!agreed) return;
  const result = await api.purgeMemory();
  if (!result) {
    toast('Bun Bun is offline; nothing was purged.', { title: 'Privacy', kind: 'warn' });
    return;
  }
  toast('Local memory purged.');
  await loadAgent();
  if (state.view === 'bunbun' || state.view === 'settings') renderView();
}

async function checkUpdate(apply = false) {
  if (apply) {
    const agreed = await confirmModal({
      eyebrow: 'Updates',
      title: 'Stage this update?',
      text: 'The image-based core downloads in the background and keeps the previous deployment for rollback. You choose when to reboot.',
      confirmLabel: 'Stage update',
    });
    if (!agreed) return;
  }
  try {
    const result = await api.update(apply ? 'apply' : 'check');
    const output = String(result?.output || '').trim().split('\n').slice(0, 2).join(' · ');
    toast(output || (apply ? 'Update staged.' : 'Everything is up to date.'), {
      title: 'Updates', timeout: 8000,
    });
  } catch (err) {
    toast(String(err?.message || err), { title: 'Updates', kind: 'warn' });
  }
}

async function showAudit() {
  try {
    const result = await api.audit(25);
    const lines = result?.lines || [];
    await modal({
      eyebrow: 'Audit log',
      title: 'Recent privileged actions',
      text: lines.length ? 'Newest last. Written by bunny-sessiond, not by the UI.' : 'No privileged actions recorded yet.',
      body: lines.length
        ? `<ul class="modal__list audit">${lines.map((line) => `<li><code>${esc(line)}</code></li>`).join('')}</ul>`
        : '',
      confirmLabel: 'Close',
      cancelLabel: 'Back',
    });
  } catch (err) {
    toast(String(err?.message || err), { title: 'Audit log', kind: 'warn' });
  }
}

// ---------------------------------------------------------------------------
// Event wiring
// ---------------------------------------------------------------------------
const ACTIONS = {
  navigate: (el) => navigate(el.dataset.view),
  'quick-menu': () => { if (!modalClose) quickMenu.toggle(); },
  'toggle-mode': () => switchMode(),
  'switch-mode': (el) => switchMode(el.dataset.mode),
  'launch-platform': (el) => launchPlatform(el.dataset.platform),
  'launch-game': (el) => launchPlatform(el.dataset.platform, {
    game: el.dataset.game || '',
    title: el.dataset.title || '',
  }),
  'refresh-library': () => loadLibrary({ force: true }),
  'filter-library': (el) => {
    state.libraryFilter = el.dataset.platform || 'all';
    renderView();
  },
  'set-setting': (el) => applySetting(el.dataset.key, el.dataset.value, {
    consent: el.dataset.consent === '1',
  }),
  'toggle-setting': (el) => toggleSetting(el),
  'ask-hint': (el) => askHint(el.dataset.secret === '1'),
  'say-hi': () => sayHi(),
  'join-lobby': () => joinLobby(),
  'leave-lobby': async () => {
    await api.leaveCoop();
    toast('Left the lobby.');
    await loadAgent();
    renderView();
  },
  'purge-memory': () => purgeMemory(),
  'check-update': () => checkUpdate(false),
  'apply-update': () => checkUpdate(true),
  'show-audit': () => showAudit(),
  installer: async () => {
    try {
      const result = await api.installer();
      toast(result?.dry_run ? 'Installer is unavailable in preview mode.' : 'Installer opened in a terminal.');
    } catch (err) {
      toast(String(err?.message || err), { title: 'Installer', kind: 'warn' });
    }
  },
  power: (el) => power(el.dataset.op),
  'reset-tweaks': async () => {
    const agreed = await confirmModal({
      eyebrow: 'Tweaks',
      title: 'Reset to recommended?',
      text: 'Performance, display and audio return to Bunny OS defaults. Bun Bun preferences are untouched.',
      confirmLabel: 'Reset',
    });
    if (!agreed) return;
    try {
      const result = await api.setSettings(RECOMMENDED);
      state.settings = result?.settings || state.settings;
      toast('Tweaks reset to recommended.');
      renderView();
    } catch (err) {
      toast(String(err?.message || err), { title: 'Tweaks', kind: 'warn' });
    }
  },
};

document.addEventListener('click', (event) => {
  const target = event.target.closest('[data-action]');
  if (!target || target.disabled || target.getAttribute('aria-disabled') === 'true') return;
  const handler = ACTIONS[target.dataset.action];
  if (!handler) return;
  event.preventDefault();
  Promise.resolve(handler(target)).catch((err) => {
    toast(String(err?.message || err), { kind: 'warn' });
  });
});

document.addEventListener('keydown', (event) => {
  const invite = event.target.closest?.('[data-invite-input]');
  if (invite && event.key === 'Enter') {
    event.preventDefault();
    ACTIONS['join-lobby']();
  }
});

document.addEventListener('input', (event) => {
  const slider = event.target.closest?.('[data-setting-range]');
  if (!slider) return;
  const min = Number(slider.min);
  const max = Number(slider.max);
  const pct = ((Number(slider.value) - min) / (max - min || 1)) * 100;
  slider.style.setProperty('--fill', `${Math.max(0, Math.min(100, pct))}%`);
  const output = slider.parentElement?.querySelector('output');
  if (output) {
    const key = slider.dataset.settingRange;
    const suffix = key === 'performance.fps_cap' ? ' fps'
      : key === 'performance.tdp_watts' ? ' W'
        : key === 'display.refresh_hz' ? ' Hz'
          : key === 'audio.latency_ms' ? ' ms'
            : '';
    const value = Number(slider.value);
    output.textContent = key === 'audio.bunbun_volume' ? `${Math.round(value * 100)}%` : `${value}${suffix}`;
  }
});

document.addEventListener('change', (event) => {
  const slider = event.target.closest?.('[data-setting-range]');
  if (!slider) return;
  applySetting(slider.dataset.settingRange, slider.value);
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------
async function boot() {
  tickClock();
  window.setInterval(tickClock, 15000);

  startGamepad({
    onAction,
    onGamepad: (pad) => {
      document.body.classList.toggle('has-gamepad', Boolean(pad));
      if (pad) toast(`Controller ready: ${pad.id}`, { title: 'Input' });
    },
  });

  api.connect().then(async () => {
    state.connection = { mode: api.mode, label: api.label };
    if (api.error) {
      toast(`${api.error} — falling back to ${api.label.toLowerCase()}.`, { title: 'Daemon', kind: 'warn' });
    }
    await Promise.all([loadStatus({ quiet: true }), loadLibrary({ quiet: true })]);
    await loadAgent();
    navigate('home');
    unsubscribe = api.openEvents(onAgentEvent, (online) => {
      state.bunbun.online = online || state.bunbun.online;
      paintChrome();
    });
    window.setInterval(() => loadAgent(), 30000);
  }).catch((err) => {
    toast(String(err?.message || err), { title: 'Startup', kind: 'warn' });
    navigate('home');
  });

  window.addEventListener('beforeunload', () => unsubscribe());
}

boot();
