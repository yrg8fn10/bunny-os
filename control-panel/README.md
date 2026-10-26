# Bunny OS Control Panel

A full-screen, controller-first panel that is also the Gaming Mode session.
The UI is plain HTML/CSS/ES modules — no bundler, no npm install, no runtime
downloads. Three transports, chosen at startup:

| Transport | When | Privileged operations |
|-----------|------|----------------------|
| **Native** (Tauri) | `panel-shell` is installed | `bunny_call` → unix socket |
| **Bridge** (Chromium kiosk) | Tauri shell not built | loopback HTTP → unix socket |
| **Mock** | no daemon, e.g. a browser on a laptop | none; deterministic demo data |

The UI never decides whether an action is allowed. `bunny-sessiond` checks the
peer uid, validates settings against a schema, and audit-logs state changes.

## Layout

```
ui/
  index.html           static shell, SVG sprite, mounts js/app.js
  css/base.css         tokens, resets, ambient background
  css/panel.css        layout, cards, focus ring, modals, toasts
  js/app.js            routing, focus, gamepad, actions, consent modals
  js/api.js            native → bridge → mock failover
  js/mock.js           offline demo backend mirroring the daemon schema
  js/nav.js            geometric D-pad focus navigation
  js/gamepad.js        Gamepad API polling with repeat
  js/components.js     shared settings markup (switch, slider, segmented)
  js/views/*.js        home, platforms, tweaks, bunbun, settings
src-tauri/
  src/main.rs          Tauri builder + single bunny_call command
  src/commands.rs      unix-socket client, command allowlist
  tauri.conf.json      fullscreen window, CSP, frontendDist ../ui
```

## Run the UI without building anything

```bash
python3 -m http.server 8421 --bind 127.0.0.1 --directory control-panel/ui
```

Open `http://127.0.0.1:8421/`. With no daemon the panel selects **Offline
preview** and uses `mock.js`; settings are simulated in memory.

To exercise the real path on a live image:

```bash
sudo systemctl start bunny-sessiond
/usr/local/bin/bunny-panel-bridge --ui /opt/bunny/panel/ui &
xdg-open http://127.0.0.1:8421/
```

## Build the native shell

Requirements: Rust 1.77+, `webkit2gtk-4.1`, `gtk3`, `libsoup3`, `librsvg`
(see the Tauri v2 prerequisites for your distro).

```bash
cd control-panel/src-tauri
cargo build --release          # target/release/bunny-panel
```

The binary expects the UI at `../ui` during development. On an installed system
the image places it at `/usr/lib/bunny/panel-shell` and the UI at
`/opt/bunny/panel/ui`; `bunny-panel` launches it with `--ui`. Tauri's
`frontendDist` is compiled into the binary by `tauri-build`, so the packaged
binary is self-contained if you build with the UI in place.

Bundling (`tauri build`) is disabled in `tauri.conf.json` on purpose: Bunny OS
ships the shell as a plain binary in the image, not as a `.deb`/AppImage.

## Controller map

| Input | Action |
|-------|--------|
| D-pad / left stick | move focus |
| A | activate |
| B | back / close modal |
| LB / RB | previous / next section |
| Start | settings |
| Keyboard arrows / WASD | move |
| Enter / Space | activate |
| Esc / Backspace | back |
| Q / E | sections |
| Y | open Bun Bun settings |

Focus is geometric: views are ordinary grids, no hard-coded neighbour maps.
Modals take over the focus scope until dismissed.

## Design constraints

* **No external assets or fonts.** The panel must render on a machine that has
  never been online.
* **Everything is reachable with a d-pad.** Inputs remain keyboard-friendly.
* **Consent is a modal, not a checkbox buried in a list.** Co-op, screen
  vision and overclocking require an explicit confirmation and are audited.
  Screen vision is a reserved key and does nothing in v0.1; the modal says so.
* **Preferences are labelled as preferences.** Tweaks stores validated values
  but does not yet write TDP, clocks, drivers, PipeWire routing or MangoHud.
* **Offline is a first-class state.** A missing daemon degrades to demo data
  with a visible badge; it never fabricates a successful system change.
