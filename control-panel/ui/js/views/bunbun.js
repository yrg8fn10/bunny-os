/* Bun Bun — persona, hint controls, co-op consent and memory. */

import { esc, icon } from '../util.js';
import { row, segmented, toggle } from '../components.js';
import { setting } from './data.js';

function stat(value, label) {
  return `<div class="stat"><div class="stat__value">${esc(value)}</div><div class="stat__label">${esc(label)}</div></div>`;
}

export function render(root, ctx) {
  const { state } = ctx;
  const bunbun = state.bunbun || {};
  const status = bunbun.status || {};
  const engine = status.engine || {};
  const agent = status.agent || {};
  const memory = engine.memory || {};
  const hints = engine.hints || {};
  const coop = status.coop || {};
  const online = Boolean(bunbun.online);
  const line = bunbun.line || 'Hi hi! I am Bun Bun. I watch the game, keep notes, and try very hard not to spoil the good bits.';
  const s = (key, fallback) => setting(state, key, fallback);

  const active = coop.active;
  const allowlist = Array.isArray(coop.allowlist) ? coop.allowlist : [];

  root.innerHTML = `
    <div class="view__head">
      <div>
        <h1 class="view__title">Bun Bun, <em>your co-op buddy.</em></h1>
        <p class="view__sub">A kid-voice bunny who comments, hints and joins friends — only when you say yes. Everything runs locally; nothing is uploaded.</p>
      </div>
      <div class="view__aside">
        <span class="chip chip--ghost" data-state="${online ? 'online' : 'offline'}">
          <span class="dot"></span>${online ? 'Agent online' : 'Agent offline'}
        </span>
      </div>
    </div>

    <section class="bunbun-hero">
      <div class="bunbun-hero__avatar"><img src="assets/bunny.svg" alt="" width="88" height="88"></div>
      <div>
        <div class="bubble">
          <div class="bubble__name">Bun Bun · MAM engine</div>
          <p>${esc(line)}</p>
        </div>
        <div class="hero__actions">
          <button class="btn btn--primary" data-focusable data-action="ask-hint">${icon('hint')} Hint, please</button>
          <button class="btn" data-focusable data-action="ask-hint" data-secret="1">${icon('shield')} Secret hint</button>
          <button class="btn" data-focusable data-action="say-hi">${icon('bunny')} Say hi</button>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="stat-grid">
        ${stat(hints.shown ?? 0, 'Hints shown')}
        ${stat(memory.entries ?? 0, 'Memory notes')}
        ${stat(agent.voice_backend || 'offline', 'Voice backend')}
        ${stat(agent.input_enabled ? 'on' : 'off', 'Input assist')}
        ${stat(active ? 'joined' : 'idle', 'Co-op lobby')}
      </div>
    </section>

    <div class="grid grid--tiles" style="margin-top:26px">
      <section class="panel">
        <h2 class="panel__title">Voice &amp; commentary</h2>
        <div class="card-rows">
          ${row('Bun Bun enabled',
            'The master switch. Turning this off stops commentary, hints and co-op.',
            toggle('ai.enabled', s('ai.enabled', true), { label: 'Bun Bun enabled' }))}
          ${row('Voice',
            'Synthesised locally with an original character voice — never a clone of a real person.',
            toggle('ai.voice_enabled', s('ai.voice_enabled', true), { label: 'Voice' }))}
          ${row('Voice style',
            'Bright is a little faster and higher; soft is quieter for late sessions.',
            segmented('ai.voice', s('ai.voice'), [
              ['bunny-default', 'Default'], ['bunny-soft', 'Soft'], ['bunny-bright', 'Bright'],
            ]))}
          ${row('Commentary',
            'Short reactions to events the watcher reports — game start, deaths, long stalls. It does not analyse the screen.',
            toggle('ai.commentary', s('ai.commentary', true), { label: 'Commentary' }))}
          ${row('Hint level',
            'Gentle nudges, direct help, or full spoilers. Secret hints always ask first.',
            segmented('ai.hint_level', s('ai.hint_level'), [
              ['off', 'Off'], ['gentle', 'Gentle'], ['helpful', 'Helpful'], ['spoilery', 'Spoilery'],
            ]))}
          ${row('Remember this session',
            'Keeps a short local journal of hints and discoveries. Purge it any time.',
            toggle('ai.memory_enabled', s('ai.memory_enabled', true), { label: 'Memory' }))}
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Multiplayer co-op</h2>
        <div class="card-rows">
          ${row('Allow lobby invites',
            'Bun Bun may analyse an invite and suggest a join. You still confirm every lobby.',
            toggle('ai.coop_opt_in', s('ai.coop_opt_in'), { consent: true, label: 'Allow lobby invites' }))}
          ${row('Who can invite',
            'Invite-only ignores strangers entirely. Friends uses your platform friend list.',
            segmented('ai.coop_mode', s('ai.coop_mode'), [
              ['invite-only', 'Invite only'], ['friends', 'Friends'], ['off', 'Off'],
            ]))}
        </div>

        <div class="lobby">
          <div class="lobby__head">
            <strong>Join a lobby</strong>
            <span class="badge ${active ? 'badge--on' : 'badge--off'}">${active ? `In ${esc(active)}` : 'Not joined'}</span>
          </div>
          <p class="row__desc">Paste a Steam lobby link or a lobby code. Bun Bun checks the allowlist and anti-cheat policy before anything launches.</p>
          <div class="inline">
            <input class="text-input" data-focusable data-invite-input
                   placeholder="steam://joinlobby/… or lobby code" aria-label="Lobby invite">
            <button class="btn btn--primary" data-focusable data-action="join-lobby">Ask to join</button>
          </div>
          ${active ? `<button class="btn btn--sm btn--ghost" data-focusable data-action="leave-lobby">Leave lobby</button>` : ''}
          <div class="kbd-list" style="margin-top:12px">
            ${allowlist.length
              ? allowlist.map((game) => `<span class="badge">${esc(game)}</span>`).join('')
              : '<span class="badge">allowlist empty</span>'}
          </div>
        </div>

        <div class="note note--warn" style="margin-top:16px">
          ${icon('shield')}
          <div><strong>Hard no:</strong> competitive modes, anti-cheat protected titles, purchases, and anything that needs a stranger's chat. Bun Bun joins as a labelled AI buddy, never as a human player.</div>
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Privacy</h2>
        <div class="card-rows">
          ${row('Screen vision',
            'Reserved for a future adapter. Nothing captures or reads frames in v0.1, so this toggle changes no behaviour.',
            toggle('ai.screen_vision', s('ai.screen_vision'), { consent: true, label: 'Screen vision (reserved)' }))}
          ${row('Kid-safe chat',
            'Filters stranger chat and blocks requests for personal information. Recommended for shared consoles.',
            toggle('ai.kid_safe', s('ai.kid_safe', true), { label: 'Kid-safe chat' }))}
          ${row('Memory journal',
            'Delete every hint, discovery and preference Bun Bun has stored for you.',
            `<button class="btn btn--sm btn--danger" data-focusable data-action="purge-memory">Purge memory</button>`)}
        </div>
        <div class="note" style="margin-top:14px">
          ${icon('shield')}
          <div>Local-only by design. The agent binds <code>127.0.0.1:8422</code>, keeps no telemetry, and drops any request whose Host header is not loopback.</div>
        </div>
      </section>
    </div>
  `;
}
