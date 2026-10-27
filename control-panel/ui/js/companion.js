/* Bun Bun companion overlay (Gaming Mode, bottom-right).
 *
 * She is screen-aware, not camera-aware. Three inputs drive her:
 *
 *   1. session mode   — gaming vs desktop (she only appears in gaming);
 *   2. panel state    — the active view (home / library / settings ...);
 *   3. screen content — the title the perception watcher reports, plus the
 *                       panel's event stream (hints, co-op invites, launches).
 *
 * No webcam, no face tracking, no microphone: every reaction comes from state
 * the panel already has. That also means she can never react to something the
 * user did not already share with the local UI.
 *
 * Cost: one small DOM subtree and one timer. Emotes are CSS transforms, so the
 * overlay stays out of the GPU's way while a game is running.
 */

const IDLE_MS = 4 * 60 * 1000;      // silence before an idle line
const MIN_GAP_MS = 9000;            // never machine-gun the bubble
const BUBBLE_MS = 6500;

const IDLE_LINES = [
  'Tiny hop! Still here if you need a hint.',
  'I like this part. Take your time~',
  'Want me to peek at the map? Just ask.',
  'Hydration check! Water is a power-up.',
];

const EVENT_REACTIONS = {
  'game.launch': { emote: 'hop', line: 'Ooh, starting {title}! I will watch quietly.' },
  'game.started': { emote: 'hop', line: 'Here we go! Have fun~' },
  'hint.ready': { emote: 'think', line: 'I found something. Open Bun Bun when you want it.' },
  'coop.consent_request': { emote: 'wave', line: 'A friend invited us! Check Bun Bun before I join.' },
  'coop.joined': { emote: 'cheer', line: 'I am in! Playing as your AI buddy, as promised.' },
  'coop.refused': { emote: 'think', line: 'I sat that lobby out. Ask me why in Bun Bun.' },
  'performance.throttle': { emote: 'think', line: 'Temps are creeping up. Want a quieter profile?' },
  'update.available': { emote: 'wave', line: 'An update is ready. Install it from Settings when you like.' },
};

const VIEW_LINES = {
  platforms: 'Pick anything! I will keep the hints ready.',
  tweaks: 'Careful in Tweaks - small changes, big battery.',
  settings: 'Settings time. Nothing here bites.',
  bunbun: 'You came to see me? Hi hi!',
};

const VIEW_EMOTE = {
  platforms: 'hop',
  tweaks: 'think',
  settings: 'think',
  bunbun: 'cheer',
};

const avatar = `assets/bunny.svg`;
export function createCompanion({ onOpen, host } = {}) {
  const root = document.createElement('div');
  root.className = 'companion';
  root.hidden = true;
  root.setAttribute('aria-label', 'Bun Bun companion');
  root.innerHTML = `
    <div class="companion__bubble" role="status" aria-live="polite"></div>
    <div class="companion__avatar" data-emote="idle">
      <img src="${avatar}" alt="Bun Bun">
      <button class="companion__open" type="button" aria-label="Open Bun Bun" title="Open Bun Bun"></button>
    </div>`;
  (host || document.body).appendChild(root);

  const bubble = root.querySelector('.companion__bubble');
  const face = root.querySelector('.companion__avatar');
  root.querySelector('.companion__open')?.addEventListener('click', () => onOpen?.());

  let lastSpoke = 0;
  let lastIdle = 0;
  let bubbleTimer = 0;
  let emoteTimer = 0;
  const screen = { mode: 'gaming', view: 'home', title: '', platform: '', online: false };

  const setEmote = (emote) => {
    face.dataset.emote = emote || 'idle';
    window.clearTimeout(emoteTimer);
    if (emote && emote !== 'idle') {
      emoteTimer = window.setTimeout(() => { face.dataset.emote = 'idle'; }, 2400);
    }
  };

  const say = (line, { emote = 'wave', force = false } = {}) => {
    if (!line) return;
    const now = Date.now();
    if (!force && now - lastSpoke < MIN_GAP_MS) return;
    lastSpoke = now;
    bubble.textContent = line;
    bubble.classList.add('is-visible');
    setEmote(emote);
    window.clearTimeout(bubbleTimer);
    bubbleTimer = window.setTimeout(() => bubble.classList.remove('is-visible'), BUBBLE_MS);
  };

  const show = (visible) => {
    root.hidden = !visible;
    root.classList.toggle('is-away', !visible);
  };

  const setScreen = (patch = {}) => {
    const previous = { ...screen };
    Object.assign(screen, patch);

    // The companion belongs to Gaming Mode only; Desktop Mode is Plasma's.
    show(screen.mode !== 'desktop');

    if (screen.mode === 'desktop') return undefined;

    // Active app changed: the strongest signal we have about "what is on screen".
    if (screen.title && screen.title !== previous.title) {
      say(`Ooh, ${screen.title}! I will keep quiet and watch.`, { emote: 'hop' });
      return;
    }

    // Panel view changed: UI-state reaction, only for the views that have one.
    if (screen.view !== previous.view && VIEW_LINES[screen.view]) {
      say(VIEW_LINES[screen.view], { emote: VIEW_EMOTE[screen.view] || 'wave' });
    }
    return undefined;
  };

  const react = (topic, payload = {}) => {
    const rule = EVENT_REACTIONS[topic];
    if (!rule) return;
    const line = rule.line.replace('{title}',
      payload.title || payload.game || screen.title || 'that one');
    say(line, { emote: rule.emote });
  };

  window.setInterval(() => {
    if (root.hidden) return;
    const now = Date.now();
    if (now - lastSpoke < IDLE_MS || now - lastIdle < IDLE_MS) return;
    lastIdle = now;
    say(IDLE_LINES[Math.floor(Math.random() * IDLE_LINES.length)], { emote: 'hop', force: true });
  }, 30000);

  return { root, setScreen, react, say, show };
}
