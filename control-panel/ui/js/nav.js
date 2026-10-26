/* Spatial focus navigation for D-pad, left stick and keyboard.
   Everything focusable carries [data-focusable]; navigation is geometric so
   views can be laid out freely without hard-coded neighbour maps. */

const DIRS = ['up', 'down', 'left', 'right'];

export class FocusNav {
  constructor({ onActivate, onBack, onMenu, onTab } = {}) {
    this.scope = document.body;
    this.current = null;
    this.onActivate = onActivate || (() => {});
    this.onBack = onBack || (() => {});
    this.onMenu = onMenu || (() => {});
    this.onTab = onTab || (() => {});

    document.addEventListener('keydown', (event) => this._onKey(event), { passive: false });
    document.addEventListener('focusin', (event) => {
      const el = event.target.closest?.('[data-focusable]');
      if (el) this._paint(el);
    });
  }

  setScope(element) {
    this.scope = element || document.body;
    this.refresh();
  }

  refresh() {
    const items = this.items();
    if (!items.length) return;
    if (!this.current || !items.includes(this.current)) this.focus(items[0]);
  }

  items() {
    const root = this.scope;
    if (!root) return [];
    return Array.from(root.querySelectorAll('[data-focusable]')).filter((el) => {
      if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
      if (el.closest('[hidden]')) return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 1 && rect.height > 1;
    });
  }

  focus(element, { scroll = true } = {}) {
    if (!element) return;
    this._paint(element);
    if (scroll) {
      const rect = element.getBoundingClientRect();
      const margin = 120;
      if (rect.top < margin || rect.bottom > window.innerHeight - 60) {
        element.scrollIntoView({ block: 'center', behavior: 'smooth' });
      }
    }
  }

  _paint(element) {
    if (this.current === element) return;
    if (this.current) {
      this.current.classList.remove('is-focused');
      this.current.removeAttribute('data-focused');
    }
    this.current = element;
    element.classList.add('is-focused');
    element.setAttribute('data-focused', 'true');
    if (typeof element.focus === 'function') {
      try { element.focus({ preventScroll: true }); } catch { /* older webviews */ }
    }
  }

  activate() {
    const el = this.current;
    if (!el) return;
    el.click();
  }

  move(direction) {
    const items = this.items();
    if (!items.length) return;
    if (!this.current || !items.includes(this.current)) {
      this.focus(items[0]);
      return;
    }
    const from = this.current.getBoundingClientRect();
    const fx = from.left + from.width / 2;
    const fy = from.top + from.height / 2;

    let best = null;
    let bestScore = Infinity;

    for (const candidate of items) {
      if (candidate === this.current) continue;
      const rect = candidate.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = cx - fx;
      const dy = cy - fy;
      const TOL = 24;

      let primary;
      let secondary;
      if (direction === 'left') {
        if (dx > -TOL) continue;
        primary = -dx;
        secondary = Math.abs(dy);
      } else if (direction === 'right') {
        if (dx < TOL) continue;
        primary = dx;
        secondary = Math.abs(dy);
      } else if (direction === 'up') {
        if (dy > -TOL) continue;
        primary = -dy;
        secondary = Math.abs(dx);
      } else {
        if (dy < TOL) continue;
        primary = dy;
        secondary = Math.abs(dx);
      }

      // Weighted distance: strongly prefer same-row/column targets, then the
      // closest one. This behaves well for mixed card grids and rails.
      const score = primary + secondary * 2.6 + Math.hypot(dx, dy) * 0.08;
      if (score < bestScore) {
        bestScore = score;
        best = candidate;
      }
    }

    if (best) this.focus(best);
  }

  _onKey(event) {
    const target = event.target;
    const isRange = target instanceof HTMLInputElement && target.type === 'range';
    if (isRange) {
      // Sliders own their arrow keys; Escape still backs out of the view.
      if (event.key === 'Escape') {
        event.preventDefault();
        this.onBack();
      }
      return;
    }

    const typing = target instanceof HTMLElement
      && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
    if (typing && !['Escape', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;

    const map = {
      ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right',
      w: 'up', s: 'down', a: 'left', d: 'right',
      W: 'up', S: 'down', A: 'left', D: 'right',
    };

    if (map[event.key]) {
      event.preventDefault();
      this.move(map[event.key]);
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      this.activate();
      return;
    }
    if (event.key === 'Escape' || event.key === 'Backspace') {
      event.preventDefault();
      this.onBack();
      return;
    }
    if (event.key === 'q' || event.key === 'Q' || event.key === 'PageUp') {
      this.onTab(-1);
      return;
    }
    if (event.key === 'e' || event.key === 'E' || event.key === 'PageDown') {
      this.onTab(1);
      return;
    }
    if (event.key === 'y' || event.key === 'Y') {
      this.onMenu();
    }
  }
}

export const directionFromAxis = (x, y) => {
  const ax = Math.abs(x);
  const ay = Math.abs(y);
  if (ax < 0.55 && ay < 0.55) return null;
  if (ax > ay) return x < 0 ? 'left' : 'right';
  return y < 0 ? 'up' : 'down';
};

export { DIRS };
