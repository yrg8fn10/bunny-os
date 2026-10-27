/* Offline demo backend.
 *
 * Used when neither the native shell nor the local bridge is reachable, for
 * example when the UI is opened in a normal browser for design work.  It
 * mirrors the daemon's command vocabulary and its validation rules closely
 * enough that the UI can be exercised without pretending to touch the system.
 */

import { DEMO_GAMES, DEMO_PLATFORMS } from './util.js';

const clone = (value) => JSON.parse(JSON.stringify(value));
const wait = (ms = 200) => new Promise((resolve) => setTimeout(resolve, ms));

const DEFAULT_SETTINGS = {
  session: {
    default_mode: 'gaming',
    autologin: true,
    desktop_session: 'bunny-desktop',
    gaming_session: 'bunny-gaming',
  },
  performance: {
    profile: 'balanced',
    fps_cap: 60,
    tdp_watts: 15,
    gpu_driver: 'auto',
    allow_overclock: false,
    mangohud: false,
  },
  audio: {
    sink: 'auto',
    mic: 'auto',
    latency_ms: 40,
    duck_media_for_voice: true,
    bunbun_volume: 0.85,
  },
  display: { resolution: 'auto', refresh_hz: 60, hdr: false, scaling: 'auto' },
  ai: {
    enabled: true,
    voice_enabled: true,
    voice: 'bunny-default',
    hint_level: 'gentle',
    commentary: true,
    coop_opt_in: false,
    coop_mode: 'invite-only',
    screen_vision: false,
    memory_enabled: true,
    kid_safe: true,
  },
  updates: { channel: 'stable', auto_check: true },
  privacy: { local_only: true, telemetry: false },
};

/* Mirrors SPEC in system/lib/bunny_sessiond.py. */
const RULES = {
  'session.default_mode': { enum: ['gaming', 'desktop'] },
  'session.autologin': { bool: true },
  'performance.profile': { enum: ['quiet', 'balanced', 'performance', 'custom'] },
  'performance.fps_cap': { int: [30, 240] },
  'performance.tdp_watts': { int: [4, 60] },
  'performance.gpu_driver': { set: ['mesa', 'nvidia', 'amdgpu-pro'] },
  'performance.allow_overclock': { bool: true },
  'performance.mangohud': { bool: true },
  'audio.sink': { set: ['hdmi', 'speakers', 'headphones', 'usb', 'bluetooth'] },
  'audio.mic': { set: ['internal', 'headset', 'usb', 'none'] },
  'audio.latency_ms': { int: [10, 250] },
  'audio.duck_media_for_voice': { bool: true },
  'audio.bunbun_volume': { float: [0, 1] },
  'display.resolution': { set: ['1280x800', '1920x1080', '2560x1600', '3840x2160'] },
  'display.refresh_hz': { int: [30, 165] },
  'display.hdr': { bool: true },
  'display.scaling': { enum: ['auto', '100%', '125%', '150%', '200%'] },
  'ai.enabled': { bool: true },
  'ai.voice_enabled': { bool: true },
  'ai.voice': { set: ['bunny-default', 'bunny-soft', 'bunny-bright'] },
  'ai.hint_level': { enum: ['off', 'gentle', 'helpful', 'spoilery'] },
  'ai.commentary': { bool: true },
  'ai.coop_opt_in': { bool: true },
  'ai.coop_mode': { enum: ['invite-only', 'friends', 'off'] },
  'ai.screen_vision': { bool: true },
  'ai.memory_enabled': { bool: true },
  'ai.kid_safe': { bool: true },
  'updates.channel': { enum: ['stable', 'beta', 'dev'] },
  'updates.auto_check': { bool: true },
  'privacy.local_only': { bool: true },
  'privacy.telemetry': { bool: true },
};

const CONSENT = {
  'ai.coop_opt_in': 'I understand Bun Bun may join multiplayer lobbies',
  'ai.screen_vision': 'Screen vision is a reserved feature and does nothing in v0.1. Continue?',
  'performance.allow_overclock': 'I understand overclocking can damage hardware',
};

const HINTS = [
  'Psst — the lantern in the east wing only lights up if you walk there without sprinting.',
  'Try parrying the second swing instead of the first. The timing is way kinder!',
  'That locked door? There is a vent behind the vending machine. I saw it, promise!',
  'Your health is low, but the checkpoint is two rooms back. I can wait, no rush.',
  'If the puzzle clicks three times, it means the order is moon → leaf → star.',
  'Secret hint: the credits scene changes if you finish with the plushie equipped.',
];

function flatten(tree, prefix = '') {
  const out = {};
  for (const [key, value] of Object.entries(tree)) {
    const dotted = `${prefix}${key}`;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(out, flatten(value, `${dotted}.`));
    } else {
      out[dotted] = value;
    }
  }
  return out;
}

function readPath(tree, dotted) {
  return dotted.split('.').reduce((node, part) => (node == null ? undefined : node[part]), tree);
}

function writePath(tree, dotted, value) {
  const parts = dotted.split('.');
  let node = tree;
  for (const part of parts.slice(0, -1)) node = node[part];
  node[parts.at(-1)] = value;
}

function validate(key, raw) {
  const rule = RULES[key];
  if (!rule) throw new Error(`unknown setting: ${key}`);
  if (rule.bool) {
    if (typeof raw !== 'boolean') throw new Error(`${key}: expected boolean`);
    return raw;
  }
  if (rule.enum) {
    if (!rule.enum.includes(raw)) throw new Error(`${key}: expected one of ${rule.enum.join(', ')}`);
    return raw;
  }
  if (rule.set) {
    if (raw === 'auto') return raw;
    if (!rule.set.includes(raw)) throw new Error(`${key}: unknown value ${raw}`);
    return raw;
  }
  if (rule.int) {
    const value = Number(raw);
    if (!Number.isInteger(value)) throw new Error(`${key}: expected integer`);
    if (value < rule.int[0] || value > rule.int[1]) {
      throw new Error(`${key}: expected ${rule.int[0]}..${rule.int[1]}`);
    }
    return value;
  }
  if (rule.float) {
    const value = Number(raw);
    if (!Number.isFinite(value)) throw new Error(`${key}: expected number`);
    if (value < rule.float[0] || value > rule.float[1]) {
      throw new Error(`${key}: expected ${rule.float[0]}..${rule.float[1]}`);
    }
    return Math.round(value * 1000) / 1000;
  }
  return raw;
}

function demoLibrary() {
  return {
    scanned_at: new Date().toISOString(),
    source: 'mock',
    platforms: DEMO_PLATFORMS.map((p) => ({ ...p })),
    games: DEMO_GAMES.map((game) => ({
      ...game,
      source: 'demo',
      last_played_days: game.last_played,
    })),
    errors: [],
  };
}

export function createMockBackend() {
  const settings = clone(DEFAULT_SETTINGS);
  const state = { mode: 'gaming' };
  let library = demoLibrary();
  let hintIndex = 0;
  let coop = { active: null, minutes: null, allowlist: ['hollow-lantern', 'carrot-kart-8'] };
  let memoryEntries = 14;
  let hintCount = 3;

  const status = () => ({
    version: '0.2.0-mock',
    channel: 'dev',
    target: 'generic',
    target_name: 'PC',
    build_id: 'mock',
    mode: state.mode,
    mode_session: state.mode === 'gaming' ? 'bunny-gaming' : 'bunny-desktop',
    default_mode: settings.session.default_mode,
    live: false,
    display_manager_active: false,
    oobe: { pending: false, preview: false, session: '', user: '' },
    sessions: { gaming: 'bunny-gaming', desktop: 'bunny-desktop', setup: 'bunny-setup' },
    settings: clone(settings),
    agent: { status: 'mock', local_only: true },
  });

  const applyPatch = (patch, confirm) => {
    if (!patch || typeof patch !== 'object' || !Object.keys(patch).length) {
      throw new Error('patch must be a non-empty object');
    }
    const flat = flatten(patch);
    for (const [key, raw] of Object.entries(flat)) {
      const value = validate(key, raw);
      const warning = CONSENT[key];
      if (warning && value === true && !['I AGREE', 'CONFIRM', 'YES'].includes(String(confirm || '').toUpperCase())) {
        throw new Error(`${key} requires confirmation: ${warning}`);
      }
      writePath(settings, key, value);
    }
    const repairs = [];
    if (settings.ai.coop_mode === 'off' && settings.ai.coop_opt_in) {
      settings.ai.coop_opt_in = false;
      repairs.push('coop_opt_in disabled because coop_mode=off');
    }
    if (!settings.ai.enabled && settings.ai.voice_enabled) {
      settings.ai.voice_enabled = false;
      repairs.push('voice_enabled disabled because ai.enabled=false');
    }
    if (settings.privacy.local_only && settings.privacy.telemetry) {
      settings.privacy.telemetry = false;
      repairs.push('telemetry disabled because local_only=true');
    }
    return { settings: clone(settings), repairs };
  };

  const call = async (cmd, args = {}) => {
    await wait(cmd === 'library' ? 420 : 180);
    switch (cmd) {
      case 'ping':
        return { pong: true, version: '0.2.0-mock' };
      case 'status':
        return status();
      case 'get-settings':
        return clone(settings);
      case 'set-settings':
        return applyPatch(args.patch, args.confirm);
      case 'switch-mode': {
        const target = args.mode;
        if (!['gaming', 'desktop'].includes(target)) throw new Error('mode must be gaming or desktop');
        state.mode = target;
        settings.session.default_mode = target;
        return { mode: target, session: status().mode_session, changed: true, restarted_display_manager: true };
      }
      case 'set-mode': {
        const target = args.mode;
        if (!['gaming', 'desktop'].includes(target)) throw new Error('mode must be gaming or desktop');
        settings.session.default_mode = target;
        return { mode: target, session: target === 'gaming' ? 'bunny-gaming' : 'bunny-desktop', applies: 'next login' };
      }
      case 'launch': {
        if (!args.platform) throw new Error('unknown platform');
        return { launched: true, platform: args.platform, pid: 4000 + Math.floor(Math.random() * 900) };
      }
      case 'library': {
        if (args.refresh) library = demoLibrary();
        return clone(library);
      }
      case 'agent':
        return { ok: true, action: args.action || 'status' };
      case 'input-agent':
        return { ok: true, enabled: Boolean(args.enable) };
      case 'update':
        return {
          ok: true,
          action: args.action || 'check',
          output: args.action === 'apply'
            ? 'Demo mode: update staged. Reboot to activate.'
            : 'Demo mode: everything is up to date.',
        };
      case 'power':
        return { ok: true, action: args.action, dry_run: true };
      case 'installer':
        return { launched: false, dry_run: true };
      case 'audit-tail':
        return { lines: ['{"cmd":"switch-mode","args":{"mode":"desktop"}}'] };
      default:
        throw new Error(`unknown command: ${cmd}`);
    }
  };

  const agent = {
    online: true,
    async health() {
      await wait(80);
      return {
        status: 'ok',
        version: '0.2.0-mock',
        voice_backend: 'mock-synth',
        voice_available: true,
        memory: { enabled: true, entries: memoryEntries },
        kill_switch: false,
      };
    },
    async status() {
      await wait(120);
      return {
        agent: {
          version: '0.2.0-mock',
          uptime_seconds: 812,
          voice_backend: 'mock-synth',
          voice_available: true,
          input_enabled: false,
          local_only: true,
        },
        engine: {
          state: { game_id: 'steam:1145360', title: 'Hollow Lantern', platform: 'steam' },
          settings: {
            enabled: settings.ai.enabled,
            voice_enabled: settings.ai.voice_enabled,
            hint_level: settings.ai.hint_level,
            coop_opt_in: settings.ai.coop_opt_in,
          },
          memory: { enabled: settings.ai.memory_enabled, entries: memoryEntries },
          hints: { library: HINTS.length, shown: hintCount },
        },
        coop: { ...coop },
        events: [],
      };
    },
    async hint() {
      await wait(320);
      const text = HINTS[hintIndex % HINTS.length];
      hintIndex += 1;
      hintCount += 1;
      return { hint: { kind: 'hint', text, executed: false, rule: 'gentle', reason: 'demo' } };
    },
    async say(text) {
      await wait(160);
      const clean = String(text || '').slice(0, 240);
      return { spoken: true, text: clean || 'Hi hi!' };
    },
    async join(payload) {
      await wait(420);
      if (!settings.ai.coop_opt_in) {
        return {
          allowed: false,
          reason: 'multiplayer co-op is off; enable it in Bun Bun settings first',
          requires_consent: true,
          status: 'refused',
        };
      }
      const invite = payload.invite || {};
      if (!payload.confirmed) {
        return { allowed: true, status: 'awaiting_player_consent', steps: ['Confirm the invite'] };
      }
      coop = { active: invite.game_id || 'friend-lobby', minutes: 0, allowlist: coop.allowlist };
      return {
        allowed: true,
        status: 'joined',
        steps: [`Launch ${invite.title || invite.game_id || 'the game'}`, 'Accept the invite in-game'],
      };
    },
    async leave() {
      await wait(120);
      coop = { ...coop, active: null, minutes: null };
      return { status: 'left' };
    },
    async purgeMemory() {
      await wait(260);
      const purged = memoryEntries;
      memoryEntries = 0;
      return { purged, remaining: 0 };
    },
  };

  return {
    call,
    agent,
    line: "Hi hi! I'm Bun Bun. Try the lantern room — I left a little secret there.",
  };
}
