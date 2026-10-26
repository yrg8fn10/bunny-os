/* Small, dependency-free helpers shared by the panel views. */

export const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (ch) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]
  ));

export const icon = (name, cls = 'icon') =>
  `<svg class="${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

export function bytes(n) {
  const value = Number(n) || 0;
  if (value <= 0) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** i).toFixed(i > 1 ? 1 : 0)} ${units[i]}`;
}

const PALETTE = [
  ['#5b2a4e', '#1d1226'],
  ['#1f3b4d', '#0f1720'],
  ['#4a2a1f', '#1c1109'],
  ['#2c3b2a', '#101a12'],
  ['#3b2a5b', '#150f22'],
  ['#5b3a2a', '#1a1109'],
  ['#254a4a', '#0d1a1a'],
];

export function gradientFor(seed) {
  let hash = 0;
  const text = String(seed ?? 'bunny');
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) % 9973;
  const [a, b] = PALETTE[hash % PALETTE.length];
  return `linear-gradient(140deg, ${a}, ${b})`;
}

export function initials(name) {
  const words = String(name ?? '').replace(/[^\p{L}\p{N} ]/gu, '').split(/\s+/).filter(Boolean);
  return (words.slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?').slice(0, 2);
}

export const PLATFORM_LABELS = {
  steam: 'Steam',
  epic: 'Epic Games',
  heroic: 'Heroic',
  gog: 'GOG',
  lutris: 'Lutris',
  retroarch: 'RetroArch',
  desktop: 'Desktop',
};

export const platformLabel = (id) => PLATFORM_LABELS[id] || String(id || '').replace(/^\w/, (c) => c.toUpperCase());

export function greeting(date = new Date()) {
  const hour = date.getHours();
  if (hour < 5) return 'Still up?';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function debounce(fn, ms = 260) {
  let handle = null;
  return (...args) => {
    window.clearTimeout(handle);
    handle = window.setTimeout(() => fn(...args), ms);
  };
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, Number(value) || min));
}

/** Deterministic "installed" demo data so the UI is never empty in preview. */
export const DEMO_GAMES = [
  { game_id: 'steam:1145360', title: 'Hollow Lantern', platform: 'steam', size_bytes: 14_400_000_000, last_played: 2 },
  { game_id: 'steam:620', title: 'Portal Pals', platform: 'steam', size_bytes: 9_100_000_000, last_played: 9 },
  { game_id: 'epic:carrot', title: 'Carrot Kart 8', platform: 'epic', size_bytes: 22_000_000_000, last_played: 22 },
  { game_id: 'gog:void', title: 'Void Garden', platform: 'gog', size_bytes: 6_400_000_000, last_played: 40 },
  { game_id: 'steam:413150', title: 'Stardrop Valley', platform: 'steam', size_bytes: 1_200_000_000, last_played: 51 },
  { game_id: 'retroarch:nes', title: 'Retro Collection', platform: 'retroarch', size_bytes: 320_000_000, last_played: 88 },
];

export const DEMO_PLATFORMS = [
  { id: 'steam', name: 'Steam', installed: true, kind: 'native', note: 'Proton, Big Picture and controller profiles are ready.' },
  { id: 'epic', name: 'Epic Games', installed: true, kind: 'flatpak', note: 'Provided by Heroic. Legendary handles installs.' },
  { id: 'gog', name: 'GOG', installed: true, kind: 'flatpak', note: 'GOG library appears inside Heroic.' },
  { id: 'lutris', name: 'Lutris', installed: false, kind: 'flatpak', note: 'Optional: emulators, non-Steam shortcuts and Wine titles.' },
  { id: 'retroarch', name: 'RetroArch', installed: true, kind: 'flatpak', note: 'Controller-first emulation frontend.' },
  { id: 'desktop', name: 'Desktop Mode', installed: true, kind: 'native', note: 'KDE Plasma with the full studio toolchain.' },
];
