/* Home — the "what do I play next?" screen. */

import { DEMO_GAMES, bytes, esc, gradientFor, greeting, icon, initials, platformLabel } from '../util.js';
import { games, lastPlayed, modeLabel, platforms } from './data.js';

function gameCard(game, index) {
  const title = game.title || 'Untitled';
  return `<button class="game-card" data-focusable data-action="launch-game"
      data-platform="${esc(game.platform || 'steam')}"
      data-game="${esc(game.game_id || game.id || '')}"
      data-title="${esc(title)}" style="animation-delay:${index * 30}ms">
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

function quickTile(platform) {
  const label = platformLabel(platform.id);
  const ready = platform.installed !== false;
  return `<button class="tile" data-focusable data-action="launch-platform"
      data-platform="${esc(platform.id)}">
    <span class="tile__icon">${icon(platform.id === 'desktop' ? 'mode' : 'play')}</span>
    <span class="tile__body">
      <span class="tile__name">${esc(label)}</span>
      <span class="tile__desc">${esc(platform.note || '')}</span>
    </span>
    <span class="badge ${ready ? 'badge--on' : 'badge--off'}">${ready ? 'Ready' : 'Install'}</span>
  </button>`;
}

export function render(root, ctx) {
  const { state } = ctx;
  const mode = state.status?.mode || 'gaming';
  const catalogue = games(state);
  const recent = catalogue.slice(0, 4);
  const resume = recent[0] || DEMO_GAMES[0];
  const bunbun = state.bunbun || {};
  const online = Boolean(bunbun.online);
  const line = bunbun.line || 'Hi hi! Pick something to play and I will keep you company.';
  const platformList = platforms(state).slice(0, 6);
  const live = Boolean(state.status?.live);
  const catalogCount = catalogue.length;

  root.innerHTML = `
    <div class="view__head">
      <div>
        <h1 class="view__title">${esc(greeting())}, <em>player.</em></h1>
        <p class="view__sub">${mode === 'gaming'
          ? 'Your games are ready. Bun Bun is standing by with hints, commentary and the occasional terrible pun.'
          : 'You are in Desktop Mode. The Control Panel is still available as an app — press Start to come back.'}</p>
      </div>
      <div class="view__aside">
        <span class="chip chip--ghost" data-state="${online ? 'online' : 'offline'}">
          <span class="dot"></span>${online ? 'Bun Bun online' : 'Bun Bun offline'}
        </span>
        <span class="badge badge--live">${esc(modeLabel(mode))}</span>
      </div>
    </div>

    <section class="hero">
      <div class="hero__body">
        <span class="hero__eyebrow">${icon('play')} Resume where you left off</span>
        <h2 class="hero__title">${esc(resume.title)}<span>${esc(platformLabel(resume.platform))}</span></h2>
        <p class="hero__text">${esc(lastPlayed(resume))}. With memory on, Bun Bun keeps a local note of hints you have already seen and asks before spoiling a secret.</p>
        <div class="hero__actions">
          <button class="btn btn--primary" data-focusable data-action="launch-game"
                  data-platform="${esc(resume.platform || 'steam')}"
                  data-game="${esc(resume.game_id || resume.id || '')}"
                  data-title="${esc(resume.title || '')}">${icon('play')} Play now</button>
          <button class="btn" data-focusable data-action="navigate" data-view="platforms">Browse library</button>
          <button class="btn btn--ghost" data-focusable data-action="toggle-mode">${icon('mode')} ${mode === 'gaming' ? 'Desktop Mode' : 'Gaming Mode'}</button>
        </div>
      </div>
      <div class="hero__art">
        <img src="assets/bunny.svg" alt="" width="260" height="260">
      </div>
    </section>

    <section class="section">
      <div class="stat-grid">
        <div class="stat"><div class="stat__value">${catalogCount}</div><div class="stat__label">Games found</div></div>
        <div class="stat"><div class="stat__value">${esc(mode === 'gaming' ? 'Gaming' : 'Desktop')}</div><div class="stat__label">Session mode</div></div>
        <div class="stat"><div class="stat__value">${online ? 'Online' : 'Offline'}</div><div class="stat__label">Bun Bun</div></div>
        <div class="stat"><div class="stat__value">${esc(state.connection?.mode === 'mock' ? 'Demo' : 'Local')}</div><div class="stat__label">Data source</div></div>
      </div>
    </section>

    <section class="section">
      <div class="section__head">
        <h2 class="section__title">Continue playing</h2>
        <button class="section__link" data-focusable data-action="navigate" data-view="platforms">
          All platforms ${icon('arrow')}
        </button>
      </div>
      <div class="grid grid--games">${recent.map(gameCard).join('')}</div>
    </section>

    <section class="section">
      <div class="section__head"><h2 class="section__title">Jump in</h2></div>
      <div class="stack">
        ${platformList.map(quickTile).join('')}
        ${live ? `<button class="tile tile--accent" data-focusable data-action="installer">
          <span class="tile__icon">${icon('shield')}</span>
          <span class="tile__body">
            <span class="tile__name">Install Bunny OS</span>
            <span class="tile__desc">Guided installer for this machine. Live session only.</span>
          </span>
          <span class="badge badge--live">Live</span>
        </button>` : ''}
      </div>
    </section>

    <section class="section">
      <div class="bunbun-hero">
        <div class="bunbun-hero__avatar"><img src="assets/bunny.svg" alt="" width="88" height="88"></div>
        <div>
          <div class="bubble">
            <div class="bubble__name">Bun Bun · ${online ? 'awake' : 'napping'}</div>
            <p>${esc(line)}</p>
          </div>
          <div class="hero__actions">
            <button class="btn btn--primary" data-focusable data-action="ask-hint">${icon('hint')} Ask for a hint</button>
            <button class="btn" data-focusable data-action="navigate" data-view="bunbun">Tune Bun Bun</button>
          </div>
        </div>
      </div>
    </section>

    ${state.library?.error ? `<section class="section"><div class="note note--warn">
      ${icon('shield')}<div><strong>Library scan failed.</strong> ${esc(state.library.error)}</div>
    </div></section>` : ''}
  `;
}
