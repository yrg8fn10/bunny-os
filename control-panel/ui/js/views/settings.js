/* Settings — session defaults, updates, privacy, power and build info. */

import { esc, icon } from '../util.js';
import { row, segmented, toggle } from '../components.js';
import { setting } from './data.js';

export function render(root, ctx) {
  const { state } = ctx;
  const status = state.status || {};
  const s = (key, fallback) => setting(state, key, fallback);
  const mode = status.mode || 'gaming';
  const connection = state.connection || {};
  const version = status.version || '0.2.0';
  const channel = s('updates.channel', status.channel || 'stable');
  const targetName = status.target_name || status.target || 'PC';
  const buildId = status.build_id || 'local';

  root.innerHTML = `
    <div class="view__head">
      <div>
        <h1 class="view__title">Settings &amp; <em>system.</em></h1>
        <p class="view__sub">Session defaults, update channel and the boring-but-important privacy switches.</p>
      </div>
      <div class="view__aside"><span class="badge badge--live">Bunny OS ${esc(version)}</span></div>
    </div>

    <div class="grid grid--tiles">
      <section class="panel">
        <h2 class="panel__title">Session</h2>
        <div class="card-rows">
          ${row('Default mode',
            'Chosen at boot and after a logout. Gaming Mode launches the Control Panel; Desktop Mode launches Plasma.',
            segmented('session.default_mode', s('session.default_mode'), [
              ['gaming', 'Gaming'], ['desktop', 'Desktop'],
            ]))}
          ${row('Autologin',
            'Signs the console user in automatically. Turn off for a shared or kiosk machine.',
            toggle('session.autologin', s('session.autologin', true), { label: 'Autologin' }))}
          ${row('Switch now',
            `Currently running <strong>${esc(mode === 'gaming' ? 'Gaming Mode' : 'Desktop Mode')}</strong>. Switching restarts the display manager — save your game first.`,
            `<div class="inline">
              <button class="btn btn--sm" data-focusable data-action="switch-mode" data-mode="gaming">Gaming</button>
              <button class="btn btn--sm" data-focusable data-action="switch-mode" data-mode="desktop">Desktop</button>
            </div>`)}
        </div>
        <div class="note" style="margin-top:14px">
          ${icon('mode')}
          <div>The panel asks <code>bunny-sessiond</code> (root, unix socket, peer-credential checked) to rewrite SDDM's autologin. Nothing in the UI runs as root.</div>
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Updates</h2>
        <div class="card-rows">
          ${row('Channel',
            'Stable is the default. Beta and Dev may break saves or drivers; they are opt-in for a reason.',
            segmented('updates.channel', channel, [
              ['stable', 'Stable'], ['beta', 'Beta'], ['dev', 'Dev'],
            ]))}
          ${row('Check automatically',
            'A daily timer runs <code>bunny-update --check</code>. Updates are staged, never forced.',
            toggle('updates.auto_check', s('updates.auto_check', true), { label: 'Auto check' }))}
          ${row('Update now',
            'Reads the channel above. An OSTree deployment keeps the previous image for rollback; a plain Btrfs/pacman install updates in place.',
            `<div class="inline">
              <button class="btn btn--sm" data-focusable data-action="check-update">Check</button>
              <button class="btn btn--sm btn--primary" data-focusable data-action="apply-update">Stage update</button>
            </div>`)}
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Privacy</h2>
        <div class="card-rows">
          ${row('Local-only mode',
            'Keeps every AI feature, hint and memory note on this device. Telemetry is forced off while this is on.',
            toggle('privacy.local_only', s('privacy.local_only', true), { label: 'Local-only mode' }))}
          ${row('Telemetry',
            'Anonymous install health only. Off by default; refused outright in local-only mode.',
            toggle('privacy.telemetry', s('privacy.telemetry', false), { label: 'Telemetry' }))}
          ${row('Bun Bun memory',
            'Remove the local journal of hints and discoveries.',
            `<button class="btn btn--sm btn--danger" data-focusable data-action="purge-memory">Purge memory</button>`)}
          ${row('Privileged actions',
            'Every mode switch, launch and power action is written to an audit log by the daemon.',
            `<button class="btn btn--sm btn--ghost" data-focusable data-action="show-audit">Show recent</button>`)}
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Power</h2>
        <div class="card-rows">
          ${row('Session', 'Log out to the display manager without powering off.', '<button class="btn btn--sm" data-focusable data-action="power" data-op="logout">Log out</button>')}
          ${row('Suspend', 'Suspends to RAM. Handhelds may use more battery than a full shutdown.', '<button class="btn btn--sm" data-focusable data-action="power" data-op="suspend">Suspend</button>')}
          ${row('Restart', 'Reboots into the default session mode.', '<button class="btn btn--sm" data-focusable data-action="power" data-op="reboot">Restart</button>')}
          ${row('Shut down', 'Powers off cleanly. Unsaved progress in games is lost.', '<button class="btn btn--sm btn--danger" data-focusable data-action="power" data-op="poweroff">Shut down</button>')}
        </div>
        ${status.live ? `<button class="btn btn--sm" style="margin-top:14px" data-focusable data-action="installer">${icon('shield')} Open installer</button>` : ''}
      </section>

      <section class="panel">
        <h2 class="panel__title">About</h2>
        <div class="card-rows">
          ${row('Version', 'Compiled into this image at build time.', `<span class="badge">${esc(version)} · ${esc(channel)}</span>`)}
          ${row('Target', 'Hardware profile this image was built for.', `<span class="badge">${esc(targetName)}</span>`)}
          ${row('Build', 'Image build identifier.', `<span class="badge">${esc(buildId)}</span>`)}
          ${row('Session daemon', 'Privileged broker for modes, settings and power.', `<span class="badge ${status.mode ? 'badge--on' : 'badge--off'}">${status.mode ? 'connected' : 'offline'}</span>`)}
          ${row('Panel transport', 'Native shell, loopback bridge, or offline preview.', `<span class="badge">${esc(connection.label || 'unknown')}</span>`)}
          ${row('Bun Bun agent', 'Local HTTP + SSE on 127.0.0.1:8422.', `<span class="badge ${state.bunbun?.online ? 'badge--on' : 'badge--off'}">${state.bunbun?.online ? 'online' : 'offline'}</span>`)}
          ${row('Documentation', 'Architecture, build, sessions, Bun Bun and safety notes ship in <code>/usr/share/doc/bunny-os</code>.', `<span class="badge">docs/</span>`)}
        </div>
        ${connection.mode === 'mock' ? `<div class="note note--warn" style="margin-top:14px">
          ${icon('shield')}
          <div><strong>Offline preview.</strong> Settings here are simulated in memory. Start <code>bunny-sessiond</code> and the bridge to change the real system.</div>
        </div>` : ''}
      </section>
    </div>

    <p class="footer-note">Bunny OS is an independent hobby distribution. Steam, Epic, GOG, Lutris and RetroArch belong to their respective owners.</p>
  `;
}
