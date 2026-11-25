# The Bunny taskbar

The Bun Bun desktop dock for Desktop Mode: a Mac-like cute taskbar,
bunny-pink, frosted glass, magnification on hover, a running dot under each
open app, and Bun Bun's ears at one end and a soft clock at the other.

It is a normal compositor client, NOT a Steam replacement: a small frameless
Chromium window pinned to the bottom edge by KWin window rules, serving the
dock UI from `control-panel/ui/taskbar` over a loopback-only server.
Game Mode is untouched.

## Layout

- `system/bin/bunny-taskbar` - the launcher: serves the UI on
  `127.0.0.1:8433`, writes its KWin rule (bottom-centre, borderless, skip
  taskbar and pager, keep above), then opens the app window.
- `control-panel/ui/taskbar/` - the dock UI (rides the panel UI copy in the
  payload, so no extra staging is needed).
- `launchers/autostart/bunny-taskbar.desktop` - the autostart entry, copied
  to `/etc/xdg/autostart` by the portable install.

## Security posture (same rules as bunny-panel-bridge)

Binds 127.0.0.1 only, runs as the desktop user, re-checks the Host header,
serves a fixed whitelist of taskbar paths, and launches a fixed whitelist of
apps. The web page cannot name a command.

## Usage

    bunny-taskbar            # start the dock (autostart does this in Desktop Mode)
    bunny-taskbar --quit     # stop it
    bunny-taskbar --serve-only --ui control-panel/ui/taskbar   # dev
    bunny-taskbar --no-pin   # open unpinned (when the KWin rule misbehaves)

## Notes

- If `kwriteconfig6/5` is missing the dock still opens, just unpinned; if
  Chromium's Wayland app id does not match the rule's `bunny-taskbar` class,
  the same fallback applies. `--no-pin` is the escape hatch.
- All-ages, local-only, no telemetry.
