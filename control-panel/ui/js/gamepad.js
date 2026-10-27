/* Gamepad discovery and repeat handling for the Control Panel.
   Standard mapping: A=0 B=1 X=2 Y=3 LB=4 RB=5 Start=9 D-pad 12-15.
   Steam Input users get the same events because Steam exposes a virtual pad. */

const REPEAT_MS = 190;
const DEADZONE = 0.5;

export function startGamepad({ onAction, onGamepad } = {}) {
  let raf = 0;
  let last = 0;
  let held = null;
  let heldSince = 0;
  let previous = new Map();
  let connected = false;
  let chordArmed = true;

  const buttonToAction = (index) => {
    switch (index) {
      case 0: return 'accept';
      case 1: return 'back';
      case 4: return 'tab-left';
      case 5: return 'tab-right';
      case 9: return 'menu';
      case 12: return 'up';
      case 13: return 'down';
      case 14: return 'left';
      case 15: return 'right';
      default: return null;
    }
  };

  const loop = (time) => {
    raf = window.requestAnimationFrame(loop);
    const pads = navigator.getGamepads?.() || [];
    const pad = Array.from(pads).find((p) => p && p.connected);

    if (!pad) {
      if (connected) {
        connected = false;
        onGamepad?.(null);
      }
      return;
    }
    if (!connected) {
      connected = true;
      onGamepad?.(pad);
    }

    // --- buttons ---------------------------------------------------------
    // LB+RB is the quick-access chord. While both are held, the individual
    // shoulder buttons must not also page through sections.
    const lbDown = Boolean(pad.buttons[4]?.pressed);
    const rbDown = Boolean(pad.buttons[5]?.pressed);
    if (lbDown && rbDown && chordArmed) {
      chordArmed = false;
      onAction?.('quick-menu');
    } else if (!lbDown && !rbDown) {
      chordArmed = true;
    }

    pad.buttons.forEach((button, index) => {
      const action = buttonToAction(index);
      if (!action) return;
      if ((index === 4 && rbDown) || (index === 5 && lbDown)) return;
      const pressed = button.pressed || button.value > 0.6;
      const was = previous.get(index) || false;
      previous.set(index, pressed);
      if (!pressed || was) return;
      if (action === 'left' || action === 'right' || action === 'up' || action === 'down') {
        held = action;
        heldSince = time;
      }
      if (time - last > 40) {
        last = time;
        onAction?.(action);
      }
    });

    // --- held d-pad / stick repeat ---------------------------------------
    if (held && time - heldSince > REPEAT_MS && time - last > REPEAT_MS) {
      const stillDown = pad.buttons[12]?.pressed || pad.buttons[13]?.pressed
        || pad.buttons[14]?.pressed || pad.buttons[15]?.pressed;
      if (stillDown) {
        last = time;
        onAction?.(held);
      } else {
        held = null;
      }
    }

    // --- left stick ------------------------------------------------------
    const x = pad.axes[0] ?? 0;
    const y = pad.axes[1] ?? 0;
    if (Math.abs(x) > DEADZONE || Math.abs(y) > DEADZONE) {
      if (time - last > 210) {
        last = time;
        if (Math.abs(x) > Math.abs(y)) onAction?.(x < 0 ? 'left' : 'right');
        else onAction?.(y < 0 ? 'up' : 'down');
      }
    }
  };

  raf = window.requestAnimationFrame(loop);

  const onConnected = (event) => {
    onGamepad?.(event.gamepad || null);
    document.body.classList.add('has-gamepad');
  };
  const onDisconnected = () => {
    const any = Array.from(navigator.getGamepads?.() || []).some((p) => p?.connected);
    if (!any) {
      onGamepad?.(null);
      document.body.classList.remove('has-gamepad');
    }
  };

  window.addEventListener('gamepadconnected', onConnected);
  window.addEventListener('gamepaddisconnected', onDisconnected);

  return () => {
    window.cancelAnimationFrame(raf);
    window.removeEventListener('gamepadconnected', onConnected);
    window.removeEventListener('gamepaddisconnected', onDisconnected);
  };
}
