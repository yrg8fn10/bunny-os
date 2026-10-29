/* =============================================================================
   Bunny OS first-boot wizard.

   One screen per decision, driven entirely by the controller or a finger.  The
   privileged work happens in bunny-setupd; this module only renders, validates
   locally and calls the loopback API with the per-boot token.

   ?mock=1   deterministic backend for headless tests and screenshots
   ?step=ID  jump straight to a step (welcome|network|timezone|account|done)
   ========================================================================== */

import { FocusNav } from '../js/nav.js';
import { startGamepad } from '../js/gamepad.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(window.location.search);
const MOCK = params.get('mock') === '1';
const TOKEN = document.querySelector('meta[name="bunny-setup-token"]')?.content || '';
const API_BASE = (params.get('api') || '').replace(/\/+$/, '');
const START_STEP = params.get('step') || '';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));

const COMMON_ZONES = [
  'UTC', 'Europe/London', 'Europe/Berlin', 'Europe/Paris', 'Europe/Madrid',
  'Europe/Rome', 'Europe/Amsterdam', 'Europe/Stockholm', 'Europe/Warsaw',
  'Europe/Kyiv', 'America/New_York', 'America/Chicago', 'America/Denver',
  'America/Los_Angeles', 'America/Sao_Paulo', 'America/Mexico_City',
  'Asia/Tokyo', 'Asia/Seoul', 'Asia/Shanghai', 'Asia/Singapore',
  'Asia/Kolkata', 'Asia/Dubai', 'Australia/Sydney', 'Pacific/Auckland',
];

const ICONS = {
  wifi: '<path d="M3.5 9.2a13 13 0 0 1 17 0"/><path d="M6.6 12.6a8.6 8.6 0 0 1 10.8 0"/><path d="M9.6 16a4.3 4.3 0 0 1 4.8 0"/><circle cx="12" cy="19.2" r="1.1" fill="currentColor" stroke="none"/>',
  ethernet: '<rect x="3" y="5" width="18" height="12" rx="2.5"/><path d="M8 21h8M12 17v4"/><path d="M7 9h2M11 9h2M15 9h2M7 13h2M11 13h2M15 13h2"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  user: '<circle cx="12" cy="8.5" r="3.6"/><path d="M4.8 20c.7-3.6 3.6-5.6 7.2-5.6s6.5 2 7.2 5.6"/>',
  check: '<path d="M5 12.5l4.2 4.2L19 7"/>',
  sparkle: '<path d="M12 3.5l1.7 5.1 5.1 1.7-5.1 1.7L12 17.1l-1.7-5.1L5.2 10.3l5.1-1.7z"/><path d="M19 16.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 4.5V10h-5.5"/>',
  lock: '<rect x="5" y="10" width="14" height="10" rx="2.4"/><path d="M8.5 10V7.8a3.5 3.5 0 0 1 7 0V10"/>',
  arrow: '<path d="M9 5l7 7-7 7"/>',
  keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2.4"/><path d="M6 10h.01M9.5 10h.01M13 10h.01M16.5 10h.01M7 14h10"/>',
  shield: '<path d="M12 3l7 3v6c0 4.2-2.9 7.7-7 9-4.1-1.3-7-4.8-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.2 5.2l1.4 1.4M17.4 17.4l1.4 1.4M5.2 18.8l1.4-1.4M17.4 6.6l1.4-1.4"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  party: '<path d="M4 20l4.2-10.5L18.5 19z"/><path d="M13.5 3.5l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9z"/><path d="M19 11l.6 1.6 1.6.6-1.6.6-.6 1.6-.6-1.6-1.6-.6 1.6-.6z"/>',
};

const icon = (name, size = 24) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24"
  fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"
  stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.check}</svg>`;

// ---------------------------------------------------------------------------
// mock backend — the same shapes bunny-setupd returns
// ---------------------------------------------------------------------------
const MOCK_NETWORKS = [
  { ssid: 'Bunny Hutch', signal: 92, security: 'WPA2', secured: true, open: false },
  { ssid: 'Meadow 5G', signal: 78, security: 'WPA2 WPA3', secured: true, open: false },
  { ssid: 'Carrot Patch', signal: 61, security: 'WPA2', secured: true, open: false },
  { ssid: 'Guest Warren', signal: 44, security: '', secured: false, open: true },
  { ssid: 'Thumper-Fi', signal: 29, security: 'WPA2', secured: true, open: false },
];

const mock = {
  connected: false,
  ssid: '',
  ip: '',
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  zones: null,
  account: null,
  finished: false,
  // Every path the UI asked for, so tools/setup-smoke.html can prove the
  // wizard talks to the same endpoints bunny-setupd serves.
  requests: [],
};

const mockState = () => ({
  ok: true,
  product: 'Bunny OS',
  version: '0.2.0',
  channel: 'stable',
  build_id: '20261027T161341Z',
  target: 'deck',
  target_name: 'Steam Deck LCD',
  mode: 'oobe',
  live: false,
  preview: false,
  done: false,
  needs_account: true,
  existing_user: null,
  bootstrap_user: 'setup',
  network: {
    connected: mock.connected,
    kind: mock.connected ? 'wifi' : null,
    ssid: mock.ssid,
    ip: mock.ip,
    signal: mock.connected ? 92 : 0,
    device: mock.connected ? 'wlan0' : '',
    connection: mock.ssid,
  },
  timezone: mock.timezone,
  uptime: 4,
});

const mockZones = () => {
  if (mock.zones) return mock.zones;
  const extra = ['Africa/Cairo', 'Africa/Johannesburg', 'America/Argentina/Buenos_Aires',
    'America/Vancouver', 'Asia/Bangkok', 'Asia/Jakarta', 'Asia/Jerusalem',
    'Asia/Karachi', 'Asia/Manila', 'Asia/Taipei', 'Atlantic/Reykjavik',
    'Australia/Melbourne', 'Australia/Perth', 'Europe/Dublin', 'Europe/Helsinki',
    'Europe/Istanbul', 'Europe/Lisbon', 'Europe/Prague', 'Europe/Vienna',
    'Pacific/Honolulu'];
  const zones = [...new Set([...COMMON_ZONES, ...extra])].map((zone) => ({
    zone,
    region: zone.includes('/') ? zone.split('/')[0] : 'Other',
    city: zone.split('/').pop().replace(/_/g, ' '),
  }));
  zones.sort((a, b) => a.zone.localeCompare(b.zone));
  mock.zones = zones;
  return zones;
};

async function mockApi(path, { method = 'GET', body = null } = {}) {
  mock.requests.push(path);
  await sleep(method === 'GET' ? 40 : 420);
  if (path === '/api/state') return mockState();
  if (path === '/api/networks') {
    return {
      ok: true,
      networks: MOCK_NETWORKS,
      status: mockState().network,
    };
  }
  if (path === '/api/timezones') return { ok: true, timezones: mockZones() };
  if (path === '/api/connect') {
    const ssid = String(body?.ssid || '');
    if (!ssid) throw new Error('Pick a network first.');
    if (ssid === 'Thumper-Fi' && !body?.password) {
      throw new Error('That network needs a password.');
    }
    mock.connected = true;
    mock.ssid = ssid;
    mock.ip = '192.168.1.42';
    return { ok: true, network: mockState().network };
  }
  if (path === '/api/timezone') {
    mock.timezone = String(body?.zone || 'UTC');
    return { ok: true, timezone: mock.timezone };
  }
  if (path === '/api/account') {
    const username = String(body?.username || '');
    if (!/^[a-z_][a-z0-9_-]{0,31}$/.test(username)) {
      throw new Error('Use lower-case letters, digits, _ or -, starting with a letter.');
    }
    if (String(body?.password || '').length < 8) {
      throw new Error('Use at least 8 characters for the password.');
    }
    mock.account = username;
    return { ok: true, username, created: true };
  }
  if (path === '/api/finish') {
    mock.finished = true;
    return { ok: true, user: mock.account || 'bunny', session: 'bunny-gaming' };
  }
  throw new Error(`mock: no route ${path}`);
}

async function api(path, options = {}) {
  if (MOCK) return mockApi(path, options);
  const { method = 'GET', body = null, timeout = 60000 } = options;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      cache: 'no-store',
      headers: {
        'X-Bunny-Setup': TOKEN,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = null; }
    if (!response.ok || (data && data.ok === false)) {
      throw new Error(data?.error || `${response.status} ${response.statusText}`);
    }
    return data;
  } finally {
    window.clearTimeout(timer);
  }
}

// ---------------------------------------------------------------------------
// state
// ---------------------------------------------------------------------------
const state = {
  info: null,
  steps: [],
  index: 0,
  busy: false,
  network: { status: null, networks: [], loaded: false, scanning: false },
  timezone: { zones: null, selected: '', applied: '' },
  account: { created: false, username: '' },
  keyboard: { open: false, target: null, layout: 'lower' },
  dialog: { open: false, ssid: '', hidden: false, secured: true },
  clockTimer: 0,
};

let nav = null;
let stepEl = null;

// The D-pad scope is the whole setup frame, not just the step body: the primary
// "Get started"/"Continue" button lives in the footer, and a controller user
// must be able to reach it. The geometric nav walks down from the step to it.
const frame = () => $('setup');

// ---------------------------------------------------------------------------
// boot
// ---------------------------------------------------------------------------
function showBoot() {
  $('setup').hidden = true;
  $('boot').hidden = false;
  nav?.setScope($('boot'));
  nav?.refresh();
}

function showSetup() {
  $('boot').hidden = true;
  $('setup').hidden = false;
  $('version-label').textContent = state.info.preview
    ? 'First-boot setup · preview'
    : 'First-boot setup';
  $('target-label').textContent = state.info.target_name || 'This device';
  $('build-label').textContent = `v${state.info.version}`;
  state.steps = defs();
  const start = START_STEP ? Math.max(0, state.steps.findIndex((s) => s.id === START_STEP)) : 0;
  go(start, { initial: true });
}

async function boot() {
  if (MOCK) {
    state.info = mockState();
    showSetup();
    if (START_STEP === 'account' && !state.info.needs_account) {
      // Tests may jump to the account step even when the mock has no user.
      state.info.needs_account = true;
    }
    return;
  }
  // The kiosk can start a moment before the service binds its socket.
  for (let attempt = 0; attempt < 90; attempt += 1) {
    try {
      const health = await api('/api/health', { timeout: 2000 });
      if (health?.ok) {
        state.info = await api('/api/state', { timeout: 8000 });
        showSetup();
        return;
      }
    } catch { /* service is still starting */ }
    await sleep(500);
  }
  showBoot();
}

// ---------------------------------------------------------------------------
// steps
// ---------------------------------------------------------------------------
function defs() {
  const steps = [
    { id: 'welcome', label: 'Welcome', icon: 'sparkle' },
    { id: 'network', label: 'Network', icon: 'wifi' },
    { id: 'timezone', label: 'Time', icon: 'clock' },
  ];
  if (state.info.needs_account) steps.push({ id: 'account', label: 'Account', icon: 'user' });
  steps.push({ id: 'done', label: 'Ready', icon: 'party' });
  return steps;
}

function renderProgress() {
  const host = $('progress');
  host.innerHTML = state.steps.map((step, index) => {
    const done = index < state.index;
    const active = index === state.index;
    return `${index ? '<span class="progress__line"><i style="width:'
      + (done || active ? '100%' : '0') + '"></i></span>' : ''}
      <div class="progress__item${done ? ' is-done' : ''}${active ? ' is-active' : ''}">
        <span class="progress__dot">${done ? icon('check', 14) : index + 1}</span>
        <span>${esc(step.label)}</span>
      </div>`;
  }).join('');
}

function go(index, { initial = false } = {}) {
  if (!state.steps.length) return;
  state.index = Math.max(0, Math.min(state.steps.length - 1, index));
  const step = state.steps[state.index];
  window.clearInterval(state.clockTimer);
  closeKeyboard({ silent: true });
  closeDialog({ silent: true });
  renderProgress();
  renderStep(step.id);
  updateActions();
  if (!initial) {
    stepEl = $('step');
    stepEl.scrollTop = 0;
  }
}

function advance() {
  if (state.busy) return;
  const step = state.steps[state.index];
  if (!step) return;
  switch (step.id) {
    case 'welcome':
      go(state.index + 1);
      break;
    case 'network':
      if (!state.network.status?.connected) {
        toast('No network yet', 'You can join Wi-Fi later from Settings. Continuing offline is fine.');
      }
      go(state.index + 1);
      break;
    case 'timezone':
      applyTimezone(state.timezone.selected || state.info.timezone || 'UTC', { quiet: true })
        .finally(() => go(state.index + 1));
      break;
    case 'account':
      // Once the account exists the fields are gone; "Continue" must move on
      // instead of re-validating an empty form.
      if (state.account.created) go(state.index + 1);
      else submitAccount();
      break;
    case 'done':
      finish();
      break;
    default:
      go(state.index + 1);
  }
}

function back() {
  if (state.keyboard.open) { closeKeyboard(); return; }
  if (state.dialog.open) { closeDialog(); return; }
  if (state.index > 0) go(state.index - 1);
}

function updateActions() {
  const step = state.steps[state.index];
  if (!step) return;
  const next = $('next');
  const backBtn = $('back');
  backBtn.hidden = state.index === 0;
  next.disabled = state.busy;
  const labels = {
    welcome: 'Get started',
    network: state.network.status?.connected ? 'Continue' : 'Continue offline',
    timezone: 'Continue',
    account: state.account.created ? 'Continue' : 'Create account',
    done: 'Start Gaming Mode',
  };
  next.innerHTML = state.busy
    ? '<span class="spinner"></span> Working…'
    : esc(labels[step.id] || 'Continue');
}

// ---------------------------------------------------------------------------
// step renderers
// ---------------------------------------------------------------------------
function renderStep(id) {
  stepEl = $('step');
  stepEl.dataset.step = id;
  stepEl.className = 'step' + (['welcome', 'done'].includes(id) ? ' step--center' : '');
  if (id === 'welcome') stepEl.innerHTML = welcomeStep();
  else if (id === 'network') stepEl.innerHTML = networkStep();
  else if (id === 'timezone') stepEl.innerHTML = timezoneStep();
  else if (id === 'account') stepEl.innerHTML = accountStep();
  else if (id === 'done') stepEl.innerHTML = doneStep();
  nav.setScope(frame());
  nav.refresh();
  if (id === 'network' && !state.network.loaded) loadNetworks();
  if (id === 'timezone') setupTimezoneStep();
  if (id === 'account') setupAccountStep();
  if (id === 'done') updateFinishSummary();
}

function welcomeStep() {
  const info = state.info;
  return `
    <div class="step__hero">
      <div class="step__art"><img src="../assets/bunny.svg" alt=""></div>
      <div>
        <span class="eyebrow">${icon('sparkle', 15)} Welcome</span>
        <h1 class="step__title">Let's get your <em>Deck</em> ready.</h1>
        <p class="step__lead">A few quick choices and Bunny OS will be yours:
          a network, the right clock, and an account for your games.</p>
      </div>
    </div>
    <div class="step__body">
      <div class="card">
        <div class="status">
          <div class="status__icon">${icon('shield', 24)}</div>
          <div class="status__text">
            <div class="status__title">Bunny OS ${esc(info.version)}</div>
            <div class="status__sub">${esc(info.target_name)} · build ${esc(info.build_id || 'local')}</div>
          </div>
        </div>
      </div>
      <ul class="feature-list">
        <li><span class="feature-dot">${icon('grid', 15)}</span><span><b>One panel</b> for Steam, Heroic, Lutris and RetroArch.</span></li>
        <li><span class="feature-dot">${icon('wifi', 15)}</span><span><b>Works offline.</b> Nothing here needs an account in the cloud.</span></li>
        <li><span class="feature-dot">${icon('keyboard', 15)}</span><span><b>Controller and touch</b> are both first-class.</span></li>
      </ul>
      ${info.preview ? `<div class="card card--tight"><div class="status">
        <div class="status__icon">${icon('sparkle', 22)}</div>
        <div class="status__text"><div class="status__title">Preview mode</div>
        <div class="status__sub">You booted the live image with the setup preview. Nothing is installed or changed permanently.</div></div>
      </div></div>` : ''}
    </div>`;
}

function signalBars(signal) {
  const level = Math.max(1, Math.min(4, Math.round((signal || 0) / 25)));
  return `<span class="bars" aria-label="Signal ${signal || 0}%">
    ${[1, 2, 3, 4].map((n) => `<i class="${n <= level ? 'on' : ''}"></i>`).join('')}
  </span>`;
}

function networkStep() {
  const status = state.network.status || {};
  const connected = Boolean(status.connected);
  const title = connected
    ? (status.kind === 'wifi' ? (status.ssid || 'Wi-Fi connected') : 'Wired connection')
    : 'Not connected';
  const sub = connected
    ? [status.ip, status.connection].filter(Boolean).join(' · ') || 'You are online.'
    : 'Join a Wi-Fi network, or continue and set it up later.';
  return `
    <div class="step__hero">
      <div class="step__art">${icon('wifi', 72)}</div>
      <div>
        <span class="eyebrow">${icon('wifi', 15)} Step 2 · Network</span>
        <h1 class="step__title">Get <em>online.</em></h1>
        <p class="step__lead">Bunny OS can install launchers and updates once it has a
          connection. You can skip this and join a network later.</p>
      </div>
    </div>
    <div class="step__body">
      <div class="card">
        <div class="status">
          <div class="status__icon" data-state="${connected ? 'on' : 'off'}">
            ${icon(connected ? (status.kind === 'ethernet' ? 'ethernet' : 'wifi') : 'wifi', 24)}
          </div>
          <div class="status__text">
            <div class="status__title">${esc(title)}</div>
            <div class="status__sub">${esc(sub)}</div>
          </div>
          <button class="btn btn--sm btn--ghost" type="button" data-action="scan"
                  data-focusable ${state.network.scanning ? 'disabled' : ''}>
            ${state.network.scanning ? '<span class="spinner"></span>' : icon('refresh', 15)} Scan
          </button>
        </div>
      </div>
      <div class="card card--tight">
        <div class="card__head">
          <div>
            <div class="card__title">Wi-Fi networks</div>
            <div class="card__sub">${state.network.scanning ? 'Scanning…' : 'Tap a network to join it.'}</div>
          </div>
          <button class="btn btn--sm btn--ghost" type="button" data-action="hidden" data-focusable>
            Hidden network
          </button>
        </div>
        <div class="net-list" id="net-list">${networkList()}</div>
      </div>
    </div>`;
}

function networkList() {
  if (state.network.scanning && !state.network.networks.length) {
    return `<div class="empty"><span class="spinner"></span><div style="margin-top:10px">Looking for networks…</div></div>`;
  }
  if (!state.network.networks.length) {
    return `<div class="empty">No networks found. Move closer to the router, or use a wired connection.</div>`;
  }
  const connectedSsid = state.network.status?.connected ? state.network.status.ssid : '';
  return state.network.networks.map((network) => `
    <button class="net${network.ssid === connectedSsid ? ' is-connected' : ''}" type="button"
            data-action="join" data-ssid="${esc(network.ssid)}"
            data-secured="${network.secured ? '1' : '0'}" data-focusable>
      <span class="status__icon" style="width:38px;height:38px;border-radius:13px">
        ${icon(network.secured ? 'lock' : 'wifi', 18)}
      </span>
      <span style="min-width:0">
        <span class="net__name">${esc(network.ssid)}</span>
        <span class="net__meta">${network.open ? 'Open network' : esc(network.security || 'Secured')}</span>
      </span>
      <span class="net__right">${signalBars(network.signal)}
        <span class="net__meta">${network.signal}%</span></span>
    </button>`).join('');
}

async function loadNetworks() {
  state.network.scanning = true;
  state.network.loaded = true;
  if (state.steps[state.index]?.id === 'network') {
    renderStep('network');
    updateActions();
  }
  try {
    const data = await api('/api/networks', { timeout: 70000 });
    state.network.networks = data?.networks || [];
    state.network.status = data?.status || (await api('/api/state')).network;
    state.info.network = state.network.status;
  } catch (err) {
    state.network.networks = [];
    toast('Could not scan for Wi-Fi', err.message || String(err), { kind: 'warn' });
  } finally {
    state.network.scanning = false;
    if (state.steps[state.index]?.id === 'network') {
      renderStep('network');
      updateActions();
    }
  }
}

function timezoneStep() {
  return `
    <div class="step__hero">
      <div class="step__art">${icon('clock', 72)}</div>
      <div>
        <span class="eyebrow">${icon('sun', 15)} Step 3 · Time</span>
        <h1 class="step__title">Set the <em>clock.</em></h1>
        <p class="step__lead">Pick where you are. The clock, calendar and scheduled
          downloads follow this time zone.</p>
      </div>
    </div>
    <div class="step__body">
      <div class="card">
        <div class="clock-preview">
          <span class="clock-preview__time" id="clock-time">--:--</span>
          <span class="clock-preview__date" id="clock-date">—</span>
        </div>
        <div class="search" id="zone-search-wrap">
          ${icon('clock', 16)}
          <input id="zone-search" type="text" placeholder="Search a city or region…"
                 autocomplete="off" spellcheck="false" data-keyboard="zone-search">
        </div>
      </div>
      <div class="card card--tight">
        <div class="card__head">
          <div class="card__title">Common time zones</div>
          <span class="card__sub" id="zone-current"></span>
        </div>
        <div class="zone-grid" id="zone-common">${zoneGrid(commonZones())}</div>
      </div>
      <div class="card card--tight" id="zone-all-card" hidden>
        <div class="card__head"><div class="card__title" id="zone-all-title">All time zones</div></div>
        <div class="zone-list" id="zone-all">${zoneGrid(state.timezone.zones || [])}</div>
      </div>
    </div>`;
}

function commonZones() {
  const all = state.timezone.zones || [];
  const byZone = new Map(all.map((zone) => [zone.zone, zone]));
  return COMMON_ZONES.map((zone) => byZone.get(zone) || {
    zone,
    city: zone.split('/').pop().replace(/_/g, ' '),
    region: zone.includes('/') ? zone.split('/')[0] : 'Other',
  });
}

function zoneGrid(zones, compact = false) {
  if (!zones.length) return '<div class="empty">Type to search every time zone.</div>';
  return zones.map((zone) => `
    <button class="zone${state.timezone.selected === zone.zone ? ' is-selected' : ''}"
            type="button" data-action="zone" data-zone="${esc(zone.zone)}" data-focusable>
      <div class="zone__city">${esc(zone.city)}</div>
      ${compact ? '' : `<div class="zone__id">${esc(zone.zone)}</div>`}
    </button>`).join('');
}

function filterZones(value) {
  const query = String(value || '').trim().toLowerCase();
  const all = state.timezone.zones || [];
  const filtered = query
    ? all.filter((zone) => zone.zone.toLowerCase().includes(query)
      || zone.city.toLowerCase().includes(query))
    : [];
  if (!$('zone-all')) return;
  $('zone-all-card').hidden = !query;
  $('zone-all').innerHTML = query
    ? zoneGrid(filtered.slice(0, 120))
    : '<div class="empty">Type to search every time zone.</div>';
  if ($('zone-all-title')) {
    $('zone-all-title').textContent = query
      ? `${filtered.length} match${filtered.length === 1 ? '' : 'es'}`
      : 'All time zones';
  }
  nav.refresh();
}

async function setupTimezoneStep() {
  if (!state.timezone.zones) {
    try {
      const data = await api('/api/timezones', { timeout: 15000 });
      state.timezone.zones = data?.timezones || [];
    } catch {
      state.timezone.zones = [];
    }
  }
  const current = state.info.timezone || 'UTC';
  state.timezone.selected = state.timezone.selected || current;
  state.timezone.applied = state.timezone.applied || current;
  // Mark the current zone before the user touches anything; the grid was
  // rendered before this async load finished.
  document.querySelectorAll('.zone').forEach((node) => {
    node.classList.toggle('is-selected', node.dataset.zone === state.timezone.selected);
  });
  $('zone-current').textContent = current;
  paintClock();
  window.clearInterval(state.clockTimer);
  state.clockTimer = window.setInterval(paintClock, 1000);
}

function paintClock() {
  const zone = state.timezone.selected || state.info.timezone || 'UTC';
  try {
    const now = new Date();
    const time = new Intl.DateTimeFormat('en-GB', {
      timeZone: zone, hour: '2-digit', minute: '2-digit', hour12: false,
    }).format(now);
    const date = new Intl.DateTimeFormat('en-GB', {
      timeZone: zone, weekday: 'short', day: 'numeric', month: 'short',
    }).format(now);
    if ($('clock-time')) $('clock-time').textContent = time;
    if ($('clock-date')) $('clock-date').textContent = date;
  } catch {
    if ($('clock-time')) $('clock-time').textContent = '--:--';
    if ($('clock-date')) $('clock-date').textContent = zone;
  }
}

async function applyTimezone(zone, { quiet = false } = {}) {
  if (!zone || zone === state.timezone.applied) return;
  state.timezone.selected = zone;
  try {
    await api('/api/timezone', { method: 'POST', body: { zone }, timeout: 20000 });
    state.timezone.applied = zone;
    state.info.timezone = zone;
    paintClock();
    if (!quiet) toast('Time zone changed', zone.replace(/_/g, ' '));
  } catch (err) {
    toast('Could not change the time zone', err.message || String(err), { kind: 'warn' });
  }
}

function accountStep() {
  if (state.account.created) {
    return `
      <div class="step__hero">
        <div class="step__art">${icon('check', 72)}</div>
        <div>
          <span class="eyebrow">${icon('user', 15)} Step 4 · Account</span>
          <h1 class="step__title">Welcome, <em>${esc(state.account.username)}</em>.</h1>
          <p class="step__lead">Your account is ready. It owns this device and can install
            applications and apply updates.</p>
        </div>
      </div>
      <div class="step__body">
        <div class="card">
          <div class="status">
            <div class="avatar">${esc((state.account.username || 'B')[0].toUpperCase())}</div>
            <div class="status__text">
              <div class="status__title">${esc(state.account.username)}</div>
              <div class="status__sub">Device owner · wheel, audio, video, input</div>
            </div>
          </div>
        </div>
      </div>`;
  }
  return `
    <div class="step__hero">
      <div class="step__art">${icon('user', 72)}</div>
      <div>
        <span class="eyebrow">${icon('user', 15)} Step 4 · Account</span>
        <h1 class="step__title">Make it <em>yours.</em></h1>
        <p class="step__lead">This is the account you will use on the Deck. It is stored
          only on this device.</p>
      </div>
    </div>
    <div class="step__body">
      <div class="card">
        <div class="account-grid">
          <label class="field">
            <span class="field__label">Full name <span class="field__hint">(optional)</span></span>
            <input class="field__input" id="acct-name" type="text" maxlength="64"
                   autocomplete="off" spellcheck="false" placeholder="Alex Bunny"
                   data-keyboard="acct-name">
          </label>
          <label class="field">
            <span class="field__label">Username</span>
            <input class="field__input" id="acct-user" type="text" maxlength="32"
                   autocomplete="off" spellcheck="false" placeholder="player"
                   data-keyboard="acct-user">
            <span class="field__hint">Lower-case letters, digits, _ or -. This is the name you log in with.</span>
          </label>
          <label class="field">
            <span class="field__label">Password</span>
            <input class="field__input" id="acct-pass" type="password" maxlength="128"
                   autocomplete="new-password" placeholder="At least 8 characters"
                   data-keyboard="acct-pass">
          </label>
          <label class="field">
            <span class="field__label">Confirm password</span>
            <input class="field__input" id="acct-confirm" type="password" maxlength="128"
                   autocomplete="new-password" placeholder="Repeat it"
                   data-keyboard="acct-confirm">
          </label>
          <div class="field__error" id="acct-error" role="alert" hidden></div>
        </div>
        <div class="note" style="margin-top:14px;color:var(--muted-2);font-size:12.5px;line-height:1.5">
          ${icon('shield', 15)} The account is created locally by a root helper. Your password
          is never written to a log and never leaves this device.
        </div>
      </div>
    </div>`;
}

function setupAccountStep() {
  const user = $('acct-user');
  if (user && !user.value) user.value = suggestUsername($('acct-name')?.value || '');
  if ($('acct-name')) {
    $('acct-name').addEventListener('input', () => {
      const field = $('acct-user');
      if (field && !field.dataset.touched) field.value = suggestUsername($('acct-name').value);
    });
  }
  if (user) {
    user.addEventListener('input', () => { user.dataset.touched = '1'; });
  }
}

function suggestUsername(fullName) {
  const base = String(fullName || '')
    .normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 24);
  if (!base) return 'player';
  return /^[a-z_]/.test(base) ? base : `b${base}`;
}

async function submitAccount() {
  const username = ($('acct-user')?.value || '').trim();
  const fullName = ($('acct-name')?.value || '').trim();
  const password = $('acct-pass')?.value || '';
  const confirm = $('acct-confirm')?.value || '';
  const error = $('acct-error');
  const fail = (message) => {
    if (error) { error.textContent = message; error.hidden = false; }
    return false;
  };
  if (!/^[a-z_][a-z0-9_-]{0,31}$/.test(username)) {
    fail('Use lower-case letters, digits, _ or -, starting with a letter.');
    return;
  }
  if (password.length < 8) { fail('Use at least 8 characters for the password.'); return; }
  if (password !== confirm) { fail('The passwords do not match.'); return; }
  if (error) error.hidden = true;

  setBusy(true);
  try {
    const result = await api('/api/account', {
      method: 'POST',
      body: { username, full_name: fullName, password },
      timeout: 45000,
    });
    state.account.created = true;
    state.account.username = result?.username || username;
    state.info.needs_account = false;
    toast('Account created', `${state.account.username} is ready.`);
    renderStep('account');
    updateActions();
  } catch (err) {
    fail(err.message || String(err));
  } finally {
    setBusy(false);
  }
}

function doneStep() {
  return `
    <div class="step__hero">
      <div class="step__art">${icon('party', 72)}</div>
      <div>
        <span class="eyebrow">${icon('check', 15)} All set</span>
        <h1 class="step__title">Ready to <em>play.</em></h1>
        <p class="step__lead">Bunny OS will restart the display and open Gaming Mode.
          You can change any of this later in the Control Panel.</p>
      </div>
    </div>
    <div class="step__body">
      <div class="done-list" id="done-list"></div>
    </div>`;
}

function updateFinishSummary() {
  const host = $('done-list');
  if (!host) return;
  const status = state.network.status || state.info.network || {};
  const account = state.account.username || state.info.existing_user || '';
  const rows = [
    ['Network', status.connected
      ? (status.kind === 'wifi' ? (status.ssid || 'Wi-Fi') : 'Wired')
      : 'Skipped — set up later'],
    ['Time zone', (state.timezone.selected || state.info.timezone || 'UTC').replace(/_/g, ' ')],
    ...(account ? [['Account', account]] : []),
    ['Version', `${state.info.version} · ${state.info.target_name}`],
  ];
  host.innerHTML = rows.map(([label, value]) => `
    <div class="done-row">
      <span class="done-row__check">${icon('check', 15)}</span>
      <span class="done-row__label">${esc(label)}</span>
      <span class="done-row__value">${esc(value)}</span>
    </div>`).join('');
}

async function finish() {
  setBusy(true);
  try {
    const result = await api('/api/finish', { method: 'POST', body: {}, timeout: 30000 });
    if (MOCK) {
      toast('Setup complete', 'In a real session Gaming Mode would start now.');
      setBusy(false);
      return;
    }
    if (result?.portable) {
      // Portable install (Bazzite, SteamOS desktop, any distro): the desktop
      // belongs to the host, so there is no session to restart. Say so and
      // leave the page usable instead of showing a spinner that never ends.
      toast('Setup complete', 'Open Bunny OS from your applications menu.');
      stepEl.innerHTML = `
        <div class="step__hero" style="grid-column:1/-1;align-items:center;text-align:center">
          <div class="step__art">${icon('party', 72)}</div>
          <div>
            <h1 class="step__title">All <em>set</em></h1>
            <p class="step__lead">Close this window and start Bunny OS from your applications menu.</p>
          </div>
        </div>`;
      $('progress').hidden = true;
      $('next').hidden = true;
      $('back').hidden = true;
      setBusy(false);
      return;
    }
    // SDDM is about to restart; stay on the spinner until it does.
    stepEl.innerHTML = `
      <div class="step__hero" style="grid-column:1/-1;align-items:center;text-align:center">
        <div class="step__art">${icon('party', 72)}</div>
        <div>
          <h1 class="step__title">Starting <em>Gaming Mode…</em></h1>
          <p class="step__lead">The screen will blink once while the session restarts.</p>
        </div>
      </div>`;
    $('progress').hidden = true;
    $('next').hidden = true;
    $('back').hidden = true;
  } catch (err) {
    setBusy(false);
    toast('Could not finish setup', err.message || String(err), { kind: 'warn' });
  }
}

// ---------------------------------------------------------------------------
// account / network dialogs
// ---------------------------------------------------------------------------
function openWifiDialog({ ssid = '', secured = true, hidden = false } = {}) {
  state.dialog = { open: true, ssid, secured, hidden };
  $('wifi-dialog').hidden = false;
  $('wifi-title').textContent = hidden ? 'Join a hidden network' : `Join ${ssid || 'network'}`;
  $('wifi-sub').textContent = secured || hidden
    ? 'Enter the Wi-Fi password. It is sent only to NetworkManager.'
    : 'This network is open. You can connect without a password.';
  const ssidField = $('wifi-ssid');
  ssidField.value = ssid;
  ssidField.readOnly = !hidden;
  $('wifi-password').value = '';
  $('wifi-error').hidden = true;
  $('wifi-skip').hidden = !hidden;
  nav.setScope($('wifi-dialog').querySelector('.dialog__panel'));
  nav.refresh();
  if (secured || hidden) {
    openKeyboard($('wifi-password'));
  } else {
    nav.focus($('wifi-join'));
  }
}

function closeDialog({ silent = false } = {}) {
  state.dialog.open = false;
  $('wifi-dialog').hidden = true;
  if (!silent) {
    nav.setScope(frame());
    nav.refresh();
  }
}

async function joinNetwork(ssid, password = '') {
  const error = $('wifi-error');
  if (error) error.hidden = true;
  setBusy(true);
  $('wifi-join').disabled = true;
  $('wifi-join').innerHTML = '<span class="spinner"></span> Connecting…';
  try {
    const result = await api('/api/connect', {
      method: 'POST',
      body: { ssid, password, hidden: state.dialog.hidden },
      timeout: 70000,
    });
    state.network.status = result?.network || (await api('/api/state')).network;
    state.info.network = state.network.status;
    const data = await api('/api/networks', { timeout: 70000 }).catch(() => null);
    if (data?.networks) state.network.networks = data.networks;
    closeKeyboard({ silent: true });
    closeDialog({ silent: true });
    renderStep('network');
    updateActions();
    toast('Connected', `${ssid} is online.`);
  } catch (err) {
    if (error) {
      error.textContent = err.message || String(err);
      error.hidden = false;
    }
  } finally {
    setBusy(false);
    if ($('wifi-join')) {
      $('wifi-join').disabled = false;
      $('wifi-join').textContent = 'Connect';
    }
  }
}

// ---------------------------------------------------------------------------
// on-screen keyboard
// ---------------------------------------------------------------------------
const KEY_ROWS = {
  lower: [
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
    ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p'],
    ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l', '-'],
    [{ label: '⇧', action: 'shift', cls: 'key--wide' }, 'z', 'x', 'c', 'v', 'b', 'n', 'm', '_',
      { label: '⌫', action: 'back', cls: 'key--wide' }],
    [{ label: '123', action: 'symbols', cls: 'key--wide' },
      { label: 'space', action: 'space', cls: 'key--space' },
      { label: 'Done', action: 'done', cls: 'key--action' }],
  ],
  upper: [
    ['!', '@', '#', '$', '%', '^', '&', '*', '(', ')'],
    ['Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P'],
    ['A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', '_'],
    [{ label: '⇧', action: 'lower', cls: 'key--wide' }, 'Z', 'X', 'C', 'V', 'B', 'N', 'M', '+',
      { label: '⌫', action: 'back', cls: 'key--wide' }],
    [{ label: '123', action: 'symbols', cls: 'key--wide' },
      { label: 'space', action: 'space', cls: 'key--space' },
      { label: 'Done', action: 'done', cls: 'key--action' }],
  ],
  symbols: [
    ['!', '@', '#', '$', '%', '&', '*', '(', ')', '0'],
    ['-', '_', '=', '+', '[', ']', '{', '}', '\\', '/'],
    [':', ';', '"', "'", ',', '.', '?', '<', '>', '|'],
    [{ label: 'abc', action: 'lower', cls: 'key--wide' }, '~', '`', '^', '€', '£', '·', '°',
      { label: '⌫', action: 'back', cls: 'key--wide' }],
    [{ label: 'space', action: 'space', cls: 'key--space' },
      { label: 'Done', action: 'done', cls: 'key--action' }],
  ],
};

function openKeyboard(input) {
  if (!input) return;
  state.keyboard.open = true;
  state.keyboard.target = input;
  state.keyboard.layout = input.type === 'password' ? 'lower' : 'lower';
  const label = input.closest('.field')?.querySelector('.field__label')?.textContent?.trim()
    || input.getAttribute('aria-label') || 'Type';
  $('keyboard-title').textContent = label.replace(/\s*\(optional\)\s*/i, '');
  $('keyboard').hidden = false;
  paintKeyboard();
  nav.setScope($('keyboard'));
  nav.refresh();
  nav.focus($('keyboard-rows').querySelector('[data-key]'));
}

function closeKeyboard({ silent = false } = {}) {
  if (!state.keyboard.open) return;
  const target = state.keyboard.target;
  state.keyboard.open = false;
  state.keyboard.target = null;
  $('keyboard').hidden = true;
  if (!silent) {
    if (state.dialog.open) {
      nav.setScope($('wifi-dialog').querySelector('.dialog__panel'));
    } else {
      nav.setScope(frame());
    }
    nav.refresh();
    if (target && target.isConnected) nav.focus(target);
  }
}

function keyboardValue() {
  const input = state.keyboard.target;
  if (!input) return '';
  if (input.type === 'password') return '•'.repeat(Math.min(input.value.length, 40));
  return input.value;
}

function paintKeyboard() {
  $('keyboard-value').textContent = keyboardValue();
  const rows = KEY_ROWS[state.keyboard.layout] || KEY_ROWS.lower;
  $('keyboard-rows').innerHTML = rows.map((row) => `
    <div class="keyboard__row">${row.map((key) => {
      if (typeof key === 'string') {
        return `<button class="key" type="button" data-key="${esc(key)}" data-focusable>${esc(key)}</button>`;
      }
      return `<button class="key ${key.cls || ''}" type="button" data-key-action="${esc(key.action)}"
        data-focusable>${esc(key.label)}</button>`;
    }).join('')}</div>`).join('');
}

function keyboardPress(key) {
  const input = state.keyboard.target;
  if (!input) return;
  if (key && key.dataset.key !== undefined) {
    input.value += key.dataset.key;
  } else if (key) {
    const action = key.dataset.keyAction;
    if (action === 'shift') state.keyboard.layout = 'upper';
    else if (action === 'lower') state.keyboard.layout = 'lower';
    else if (action === 'symbols') state.keyboard.layout = 'symbols';
    else if (action === 'back') input.value = input.value.slice(0, -1);
    else if (action === 'space') input.value += ' ';
    else if (action === 'done') { closeKeyboard(); return; }
  }
  input.dispatchEvent(new Event('input', { bubbles: true }));
  paintKeyboard();
}

function keyboardHardware(event) {
  if (!state.keyboard.open) return false;
  const input = state.keyboard.target;
  if (!input) return false;
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  if (event.key === 'Escape') { closeKeyboard(); return true; }
  if (event.key === 'Enter') { closeKeyboard(); return true; }
  if (event.key === 'Backspace') {
    input.value = input.value.slice(0, -1);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    paintKeyboard();
    return true;
  }
  if (event.key.length === 1) {
    input.value += event.key;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    paintKeyboard();
    return true;
  }
  return false;
}

// ---------------------------------------------------------------------------
// busy / toasts
// ---------------------------------------------------------------------------
function setBusy(flag) {
  state.busy = flag;
  updateActions();
  const backBtn = $('back');
  if (backBtn) backBtn.disabled = flag;
}

function toast(title, message, { kind = 'info' } = {}) {
  const host = $('toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast${kind === 'warn' ? ' toast--warn' : ''}`;
  el.innerHTML = `<strong>${esc(title)}</strong>${esc(message || '')}`;
  host.appendChild(el);
  while (host.children.length > 3) host.firstElementChild?.remove();
  window.setTimeout(() => el.remove(), 5200);
}

// ---------------------------------------------------------------------------
// wiring
// ---------------------------------------------------------------------------
function wire() {
  nav = new FocusNav({
    onActivate: () => nav.activate(),
    onBack: () => back(),
    onMenu: () => {},
    onTab: (dir) => (dir < 0 ? back() : advance()),
  });

  $('next').addEventListener('click', () => advance());
  $('back').addEventListener('click', () => back());
  $('boot-retry').addEventListener('click', () => { $('boot').hidden = true; boot(); });

  startGamepad({
    onAction(action) {
      if (action === 'accept') nav.activate();
      else if (action === 'back') back();
      else if (['up', 'down', 'left', 'right'].includes(action)) nav.move(action);
      else if (action === 'tab-left') back();
      else if (action === 'tab-right') advance();
    },
  });

  // Capture phase: while the on-screen keyboard is open, a hardware keyboard
  // should type into the target instead of moving the focus ring.
  document.addEventListener('keydown', (event) => {
    if (keyboardHardware(event)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  $('step').addEventListener('click', (event) => {
    const input = event.target.closest('input[data-keyboard]');
    if (input) {
      openKeyboard(input);
      return;
    }
    const el = event.target.closest('[data-action]');
    if (!el) return;
    const action = el.dataset.action;
    if (action === 'scan') loadNetworks();
    else if (action === 'hidden') openWifiDialog({ hidden: true, secured: true });
    else if (action === 'join') {
      const ssid = el.dataset.ssid;
      const secured = el.dataset.secured === '1';
      if (secured) openWifiDialog({ ssid, secured: true });
      else joinNetwork(ssid, '');
    } else if (action === 'zone') {
      const zone = el.dataset.zone;
      state.timezone.selected = zone;
      document.querySelectorAll('.zone').forEach((node) => {
        node.classList.toggle('is-selected', node.dataset.zone === zone);
      });
      applyTimezone(zone);
    }
  });

  // The Deck's controller in lizard mode reports A as Enter, and FocusNav
  // deliberately leaves Enter to a focused text field. Without this, A on the
  // account or search field does nothing and the on-screen keyboard can only
  // be raised with a finger, so the account step would be touch-only.
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' || state.keyboard.open) return;
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    if (!input.hasAttribute('data-keyboard') && !input.closest('#wifi-dialog')) return;
    event.preventDefault();
    openKeyboard(input);
  });

  // Delegated: renderStep() replaces #step's innerHTML, so listeners bound to
  // the search field itself would be dropped on every re-render and typing
  // would silently stop filtering.
  $('step').addEventListener('input', (event) => {
    if (event.target.closest('#zone-search')) filterZones(event.target.value);
  });

  $('keyboard-rows').addEventListener('click', (event) => {
    const key = event.target.closest('[data-key], [data-key-action]');
    if (key) keyboardPress(key);
  });
  $('keyboard-close').addEventListener('click', () => closeKeyboard());

  $('wifi-join').addEventListener('click', () => {
    const ssid = $('wifi-ssid').value.trim();
    const password = $('wifi-password').value;
    if (!ssid) {
      const error = $('wifi-error');
      error.textContent = 'Enter the network name.';
      error.hidden = false;
      return;
    }
    joinNetwork(ssid, password);
  });
  $('wifi-cancel').addEventListener('click', () => closeDialog());
  $('wifi-skip').addEventListener('click', () => {
    state.dialog.hidden = true;
    $('wifi-ssid').readOnly = false;
    $('wifi-password').focus();
    openKeyboard($('wifi-password'));
  });
  $('wifi-password').addEventListener('click', () => openKeyboard($('wifi-password')));

  window.addEventListener('online', () => {
    if (state.steps[state.index]?.id === 'network') {
      api('/api/state').then((info) => {
        state.info = info;
        state.network.status = info.network;
        renderStep('network');
      }).catch(() => {});
    }
  });
}

// Exposed for tools/setup-smoke.html and for debugging on a Deck.
window.__BUNNY_SETUP__ = {
  get state() { return state; },
  get mock() { return MOCK; },
  get requests() { return mock.requests.slice(); },
  go, advance, back,
  openKeyboard, closeKeyboard,
  selectZone: (zone) => applyTimezone(zone),
  selectNetwork: (ssid, password = '') => joinNetwork(ssid, password),
};

wire();
boot();
