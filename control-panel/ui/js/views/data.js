/* Shared read helpers used by multiple views. All of them are defensive: the
   panel must render something useful even when a daemon is half-available. */

import { DEMO_GAMES, DEMO_PLATFORMS } from '../util.js';

export function setting(state, dotted, fallback = false) {
  const node = String(dotted).split('.').reduce(
    (acc, part) => (acc == null ? undefined : acc[part]),
    state.settings,
  );
  return node === undefined ? fallback : node;
}

export function games(state) {
  const list = state.library?.games;
  return Array.isArray(list) && list.length ? list : DEMO_GAMES;
}

export function platforms(state) {
  const list = state.library?.platforms;
  return Array.isArray(list) && list.length ? list : DEMO_PLATFORMS;
}

export function gameId(game) {
  return game.game_id || game.id || game.title;
}

export function lastPlayed(game) {
  const days = Number(game.last_played_days ?? game.last_played ?? 0);
  if (!Number.isFinite(days) || days <= 0) return 'Played today';
  if (days === 1) return 'Played yesterday';
  if (days < 7) return `Played ${days} days ago`;
  if (days < 30) return `Played ${Math.round(days / 7)} weeks ago`;
  return `Played ${Math.round(days / 30)} months ago`;
}

export function modeLabel(mode) {
  return mode === 'desktop' ? 'Desktop Mode' : 'Gaming Mode';
}
