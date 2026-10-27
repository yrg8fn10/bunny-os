/* Quick-access menu ("carrot button").
 *
 * One overlay, one owner: it borrows the panel's FocusNav so D-pad and stick
 * work inside it, and it restores whatever scope was active before. Every tile
 * reuses the panel's existing [data-action] delegation, so the menu cannot
 * drift away from the actions the rest of the UI uses.
 */

const CARROT = `<svg viewBox="0 0 24 24" fill="none" stroke="#7a3b2e" stroke-width="1.6"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M14.5 9.5 8 16a3.2 3.2 0 0 0 4.5 4.5L19 14z" fill="#ff9a6b" stroke="#e07a4a"/>
  <path d="M14.5 9.5c1.6-1.6 3.4-2.4 5.2-2.6-.2 1.8-1 3.6-2.6 5.2z" fill="#8bd88f" stroke="#57a95c"/>
  <path d="M9.8 13.2l1.6 1.6M11.6 15.6l1.5 1.4" stroke="#d9683a"/>
</svg>`;

const TILES = [
  { action: 'navigate', view: 'home', label: 'Home', icon: 'i-home' },
  { action: 'navigate', view: 'platforms', label: 'Library', icon: 'i-grid' },
  { action: 'navigate', view: 'tweaks', label: 'Quick settings', icon: 'i-sliders' },
  { action: 'navigate', view: 'bunbun', label: 'Bun Bun', icon: 'i-bunny' },
];

const POWER = [
  { op: 'suspend', label: 'Sleep', icon: 'i-moon' },
  { op: 'logout', label: 'Log out', icon: 'i-exit' },
  { op: 'reboot', label: 'Restart', icon: 'i-refresh' },
  { op: 'poweroff', label: 'Shut down', icon: 'i-power', danger: true },
];

const tile = ({ action, view, op, label, icon, danger }) => {
  // Power tiles carry only an op; the panel's action map names that handler
  // `power`, so default to it rather than emitting data-action="undefined".
  const act = action || (op ? 'power' : 'navigate');
  return `
  <button class="quickmenu__tile${danger ? ' quickmenu__tile--danger' : ''}"
          type="button" data-focusable
          data-action="${act}"${view ? ` data-view="${view}"` : ''}${op ? ` data-op="${op}"` : ''}>
    <svg class="icon" aria-hidden="true"><use href="#${icon}"/></svg>
    <span>${label}</span>
  </button>`;
};

export function createQuickMenu({ nav, host, viewEl }) {
  const root = document.createElement('div');
  root.className = 'quickmenu';
  root.hidden = true;
  root.setAttribute('role', 'dialog');
  root.setAttribute('aria-modal', 'true');
  root.setAttribute('aria-label', 'Quick access');
  root.innerHTML = `
    <div class="quickmenu__panel" tabindex="-1">
      <div class="quickmenu__title">${CARROT}<span>Quick access</span></div>
      <div class="quickmenu__grid">${TILES.map(tile).join('')}</div>
      <div class="quickmenu__section">
        <h3>Power</h3>
        <div class="quickmenu__grid">${POWER.map(tile).join('')}</div>
      </div>
    </div>`;
  (host || document.body).appendChild(root);

  const panel = root.querySelector('.quickmenu__panel');
  let isOpen = false;

  const close = () => {
    if (!isOpen) return;
    isOpen = false;
    root.classList.remove('is-open');
    root.hidden = true;
    document.body.classList.remove('quickmenu-open');
    // Return focus to whatever view is active *now*. A tile may have navigated
    // while the menu was open, so the view captured on open is already stale;
    // restoring it would leave the D-pad pointing at a hidden panel.
    nav.setScope((viewEl && viewEl()) || document.body);
    nav.refresh();
  };

  const open = () => {
    if (isOpen) return;
    isOpen = true;
    root.hidden = false;
    // Force a frame so the opacity transition runs instead of snapping.
    requestAnimationFrame(() => root.classList.add('is-open'));
    document.body.classList.add('quickmenu-open');
    nav.setScope(panel);
  };

  const toggle = () => (isOpen ? close() : open());

  // The panel's own click delegation handles the action; closing happens after
  // it so navigation does not fight the scope restore.
  root.addEventListener('click', (event) => {
    if (event.target.closest('[data-action]')) setTimeout(close, 0);
    else if (event.target === root) close();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'c' || event.key === 'C') {
      const typing = event.target instanceof HTMLElement
        && (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA'
          || event.target.isContentEditable);
      if (typing) return;
      event.preventDefault();
      toggle();
      return;
    }
    if (event.key === 'Escape' && isOpen) {
      event.preventDefault();
      event.stopPropagation();
      close();
    }
  }, { capture: true });

  return { root, open, close, toggle, isOpen: () => isOpen };
}
