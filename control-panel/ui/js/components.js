/* Reusable markup fragments for settings rows. Keeping them here means every
   view renders toggles, segmented controls and sliders exactly the same way. */

import { esc } from './util.js';

export function row(name, desc, control, { stack = false } = {}) {
  return `<div class="row${stack ? ' row--stack' : ''}">
    <div class="row__label">
      <span class="row__name">${name}</span>
      ${desc ? `<span class="row__desc">${desc}</span>` : ''}
    </div>
    <div class="row__control">${control}</div>
  </div>`;
}

export function segmented(key, current, options, { consent = false } = {}) {
  const buttons = options.map(([value, label]) => `
    <button class="seg__opt${value === current ? ' is-on' : ''}" data-focusable
            data-action="set-setting" data-key="${esc(key)}" data-value="${esc(value)}"
            ${consent ? 'data-consent="1"' : ''}
            ${value === current ? 'aria-pressed="true"' : 'aria-pressed="false"'}>${esc(label)}</button>`);
  return `<div class="seg" role="group" aria-label="${esc(key)}">${buttons.join('')}</div>`;
}

export function toggle(key, value, { consent = false, label = '' } = {}) {
  return `<button class="switch" role="switch" aria-checked="${value ? 'true' : 'false'}"
           data-focusable data-action="toggle-setting" data-key="${esc(key)}"
           ${consent ? 'data-consent="1"' : ''}
           aria-label="${esc(label || key)}"></button>`;
}

export function range(key, { min, max, step = 1, value, format = String }) {
  const numeric = Number(value);
  const pct = Math.max(0, Math.min(100, ((numeric - min) / (max - min)) * 100));
  return `<div class="range">
    <input type="range" min="${min}" max="${max}" step="${step}" value="${esc(numeric)}"
           data-focusable data-setting-range="${esc(key)}"
           aria-label="${esc(key)}" style="--fill:${pct}%">
    <output>${esc(format(numeric))}</output>
  </div>`;
}

export function chip(label, { tone = '' } = {}) {
  return `<span class="badge${tone ? ` badge--${tone}` : ''}">${esc(label)}</span>`;
}

export function empty(text, { art = 'assets/bunny.svg' } = {}) {
  return `<div class="empty">
    <img src="${esc(art)}" alt="" width="72" height="72">
    <p>${text}</p>
  </div>`;
}
