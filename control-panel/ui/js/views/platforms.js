/* Platforms — library browser plus the game services Bunny OS knows about. */

import { bytes, esc, gradientFor, icon, initials, platformLabel } from '../util.js';
import { empty } from '../components.js';
import { games, gameId, lastPlayed, platforms } from './data.js';

const FILTERS = ['all', 'steam', 'epic', 'gog', 'lutris', 'retroarch'];

function platformCard(platform) {
  const label = platform.name || platformLabel(platform.id);
  const ready = platform.installed !== false;
  return `<button class="platform" data-focusable data-action="launch-platform"
      data-platform="${esc(platform.id)}" style="--tint:${platform.id === 'steam' ? 'rgba(142,205,247,.18)' : 'rgba(255,138,199,.14)'}">
    <span class="platform__top">
      <span class="platform__logo">${esc(initials(label))}</span>
      <span class="badge ${ready ? 'badge--on' : 'badge--off'}">${ready ? 'Installed' : 'Not installed'}</span>
    </span>
    <span class="platform__name">${esc(label)}</span>
    <span class="platform__desc">${esc(platform.note || '')}</span>
    <span class="platform__foot">
      <span class="badge">${esc(platform.kind || 'native')}</span>
      <span class="section__link">${ready ? 'Launch' : 'Set up'} ${icon('arrow')}</span>
    </span>
  </button>`;
}

function gameCard(game) {
  const title = game.title || 'Untitled';
  return `<button class="game-card" data-focusable data-action="launch-game"
      data-platform="${esc(game.platform || 'steam')}"
      data-game="${esc(gameId(game))}"
      data-title="${esc(title)}">
    <span class="game-card__art" style="--art:${gradientFor(title)}">
      <span class="game-card__mono">${esc(initials(title))}</span>
      <span class="game-card__badge">${esc(platformLabel(game.platform))}</span>
    </span>
    <span class="game-card__body">
      <span class="game-card__name">${esc(title)}</span>
      <span class="game-card__meta">${esc(lastPlayed(game))}${game.size_bytes ? ` · ${bytes(game.size_bytes)}` : ''}</span>
    </span>
  </button>`;
}

export function render(root, ctx) {
  const { state } = ctx;
  const library = state.library || {};
  const allGames = games(state);
  const allPlatforms = platforms(state);
  const active = state.libraryFilter || 'all';
  const visible = active === 'all' ? allGames : allGames.filter((game) => game.platform === active);
  const filters = FILTERS.filter((id) => id === 'all' || allGames.some((game) => game.platform === id));

  const scanned = library.scanned_at
    ? new Date(library.scanned_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : 'demo data';

  root.innerHTML = `
    <div class="view__head">
      <div>
        <h1 class="view__title">Your <em>library.</em></h1>
        <p class="view__sub">Steam, Epic, GOG, Lutris and RetroArch in one controller-friendly list. Scans stay on this device — last scan ${esc(scanned)}.</p>
      </div>
      <div class="view__aside">
        <button class="btn btn--sm" data-focusable data-action="refresh-library">Rescan</button>
        <span class="badge">${allGames.length} games</span>
      </div>
    </div>

    <section class="section">
      <div class="section__head"><h2 class="section__title">Services</h2></div>
      <div class="grid grid--platforms">${allPlatforms.map(platformCard).join('')}</div>
    </section>

    <section class="section">
      <div class="section__head">
        <h2 class="section__title">Installed games</h2>
        <div class="seg" role="group" aria-label="Filter library">
          ${filters.map((id) => `<button class="seg__opt${id === active ? ' is-on' : ''}" data-focusable
              data-action="filter-library" data-platform="${esc(id)}"
              aria-pressed="${id === active}">${esc(id === 'all' ? 'All' : platformLabel(id))}</button>`).join('')}
        </div>
      </div>
      ${visible.length
        ? `<div class="grid grid--games">${visible.map(gameCard).join('')}</div>`
        : empty('No games found for this service yet. Install one, then press <strong>Rescan</strong>.')}
      <div class="note" style="margin-top:18px">
        ${icon('shield')}
        <div><strong>Epic and GOG run through Heroic.</strong> Bunny OS never asks for store passwords; Heroic keeps its own session tokens, and the library scan only reads local manifests.</div>
      </div>
      ${library.error ? `<div class="note note--warn" style="margin-top:12px">${icon('shield')}<div>${esc(library.error)}</div></div>` : ''}
    </section>
  `;
}
