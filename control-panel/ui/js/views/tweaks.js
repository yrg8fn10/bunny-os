/* Tweaks — performance, display and audio preferences stored via sessiond.
 *
 * Scope note: v0.1 persists and validates these values. It does not yet
 * reprogram firmware, swap drivers, route PipeWire streams or set per-game
 * frame caps. The UI says so rather than implying the change is live.
 */

import { esc, icon } from '../util.js';
import { range, row, segmented, toggle } from '../components.js';
import { setting } from './data.js';

export function render(root, ctx) {
  const { state } = ctx;
  const s = (key, fallback) => setting(state, key, fallback);

  root.innerHTML = `
    <div class="view__head">
      <div>
        <h1 class="view__title">Tune the <em>machine.</em></h1>
        <p class="view__sub">Saved and validated by the session daemon. These are preferences: v0.1 records them but does not yet reprogram clocks, drivers, PipeWire or per-game caps. Nothing is silently changed.</p>
      </div>
      <div class="view__aside">
        <button class="btn btn--sm btn--ghost" data-focusable data-action="reset-tweaks">Reset to recommended</button>
      </div>
    </div>

    <div class="grid grid--tiles">
      <section class="panel">
        <h2 class="panel__title">Performance</h2>
        <div class="card-rows">
          ${row('Power profile',
            'Your preferred profile. v0.1 does not write firmware clocks or fan curves; the setting is advisory.',
            segmented('performance.profile', s('performance.profile'), [
              ['quiet', 'Quiet'], ['balanced', 'Balanced'],
              ['performance', 'Performance'], ['custom', 'Custom'],
            ]))}
          ${row('Frame cap',
            'Requested cap for gamescope. Stored only: the session script does not apply a per-game cap yet.',
            range('performance.fps_cap', {
              min: 30, max: 240, step: 5, value: s('performance.fps_cap', 60),
              format: (v) => `${v} fps`,
            }))}
          ${row('Power limit',
            'Preferred wattage. No TDP write is performed in v0.1; firmware thermal limits always win.',
            range('performance.tdp_watts', {
              min: 4, max: 60, step: 1, value: s('performance.tdp_watts', 15),
              format: (v) => `${v} W`,
            }))}
          ${row('Graphics driver',
            'Preference only. The driver comes from installed packages; changing this does not swap it.',
            segmented('performance.gpu_driver', s('performance.gpu_driver'), [
              ['auto', 'Auto'], ['mesa', 'Mesa'], ['nvidia', 'NVIDIA'], ['amdgpu-pro', 'AMDGPU-PRO'],
            ]))}
          ${row('MangoHud overlay',
            'MangoHud is installed, but v0.1 does not inject it into launches automatically.',
            toggle('performance.mangohud', s('performance.mangohud'), { label: 'MangoHud overlay' }))}
          ${row('Allow overclocking',
            'Consent flag only. No clock or voltage write is implemented; use vendor tools manually and at your own risk.',
            toggle('performance.allow_overclock', s('performance.allow_overclock'), {
              consent: true, label: 'Allow overclocking',
            }))}
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Display</h2>
        <div class="card-rows">
          ${row('Resolution',
            'Preferred resolution. gamescope still negotiates with the game; this value is not forced in v0.1.',
            segmented('display.resolution', s('display.resolution'), [
              ['auto', 'Auto'], ['1280x800', '1280×800'], ['1920x1080', '1920×1080'],
              ['2560x1600', '2560×1600'], ['3840x2160', '3840×2160'],
            ]))}
          ${row('Refresh rate',
            'Preferred rate. Stored only: the compositor keeps the panel mode it was started with.',
            range('display.refresh_hz', {
              min: 30, max: 165, step: 5, value: s('display.refresh_hz', 60),
              format: (v) => `${v} Hz`,
            }))}
          ${row('HDR',
            'Preference for an HDR-capable panel. No HDR toggle is applied to gamescope in v0.1.',
            toggle('display.hdr', s('display.hdr'), { label: 'HDR' }))}
          ${row('Desktop scaling',
            'Preferred Plasma scaling. Applied by you in System Settings; Bun OS does not rewrite it.',
            segmented('display.scaling', s('display.scaling'), [
              ['auto', 'Auto'], ['100%', '100%'], ['125%', '125%'], ['150%', '150%'], ['200%', '200%'],
            ]))}
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Audio</h2>
        <div class="card-rows">
          ${row('Output',
            'Preferred output device. PipeWire routing is left to the desktop audio settings.',
            segmented('audio.sink', s('audio.sink'), [
              ['auto', 'Auto'], ['hdmi', 'HDMI'], ['speakers', 'Speakers'],
              ['headphones', 'Headphones'], ['usb', 'USB'], ['bluetooth', 'Bluetooth'],
            ]))}
          ${row('Microphone',
            'Preferred input for in-game voice chat. Bun Bun has no microphone listener and never records audio.',
            segmented('audio.mic', s('audio.mic'), [
              ['auto', 'Auto'], ['internal', 'Internal'], ['headset', 'Headset'],
              ['usb', 'USB'], ['none', 'Off'],
            ]))}
          ${row('Voice latency',
            'Preferred buffer hint for future audio work. Not applied to PipeWire in v0.1.',
            range('audio.latency_ms', {
              min: 10, max: 250, step: 5, value: s('audio.latency_ms', 40),
              format: (v) => `${v} ms`,
            }))}
          ${row('Bun Bun volume',
            'Preferred voice gain. Stored as a preference; the agent does not move the system mixer.',
            range('audio.bunbun_volume', {
              min: 0, max: 1, step: 0.05, value: s('audio.bunbun_volume', 0.85),
              format: (v) => `${Math.round(v * 100)}%`,
            }))}
          ${row('Duck media for voice',
            'Preferred behaviour for a future mixer hook. v0.1 does not lower other streams.',
            toggle('audio.duck_media_for_voice', s('audio.duck_media_for_voice'), {
              label: 'Duck media for voice',
            }))}
        </div>
      </section>
    </div>

    <section class="section">
      <div class="note note--warn">
        ${icon('shield')}
        <div><strong>Honest limits.</strong> These controls persist a validated preference set. v0.1 does not write TDP, overclock, force a driver, route PipeWire or inject MangoHud; doing so safely needs per-device backends that are not built yet. Games and the desktop stay in control. See <em>docs/ARCHITECTURE.md</em>.</div>
      </div>
    </section>
  `;
}

export const RECOMMENDED = {
  performance: { profile: 'balanced', fps_cap: 60, tdp_watts: 15, gpu_driver: 'auto', mangohud: false, allow_overclock: false },
  audio: { sink: 'auto', mic: 'auto', latency_ms: 40, duck_media_for_voice: true, bunbun_volume: 0.85 },
  display: { resolution: 'auto', refresh_hz: 60, hdr: false, scaling: 'auto' },
};
