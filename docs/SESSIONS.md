# Sessions and mode switching

Bunny OS has exactly two graphical sessions. Both are normal Wayland session
entries that SDDM can start; there is no custom display manager.

| Mode | SDDM session name | Entry point | What you see |
|------|-------------------|-------------|--------------|
| Gaming Mode | `bunny-gaming` | `/usr/local/bin/bunny-session gaming` | gamescope → Control Panel |
| Desktop Mode | `bunny-desktop` | `/usr/local/bin/bunny-session desktop` | KDE Plasma Wayland |

Gaming Mode is the default on the live image and after installation.

## 1. Gaming Mode

`bunny-session gaming` sets a predictable environment and then replaces itself
with the compositor:

```bash
XDG_SESSION_TYPE=wayland
QT_QPA_PLATFORM=wayland
PROTON_ENABLE_NVAPI=1
DXVK_ASYNC=1
MANGOHUD=0                    # the panel controls the overlay
```

Resolution and refresh come from `/etc/bunny/session.conf`
(`BUNNY_GAMESCOPE_ARGS`). The default is `-W 1920 -H 1080 -r 60 --adaptive-sync
--force-grab-cursor`; change it there if your display differs. A target build
can override it in `/etc/bunny/target.conf`, which is sourced after
`session.conf`. The Steam Deck LCD target uses `-W 1280 -H 800 -r 60`.

The chain is:

```
gamescope  →  bunny-panel --kiosk  →  native shell or Chromium  →  UI
```

If gamescope is unavailable, `bunny-session` falls back to `cage`, then to a
bare panel. The fallback is intentional: a broken compositor should still show
a usable recovery UI, not a black screen.

Steam is launched from the panel, but it runs as a normal child process. Closing
the panel does not necessarily stop a game; gamescope keeps the session alive.

## 2. Desktop Mode

`bunny-session desktop` execs `startplasma-wayland` (or `startplasma-x11` if
Plasma's Wayland session is missing). The Control Panel is available as a
normal application (`bunny-control-panel.desktop`) and can be pinned to the
taskbar.

The panel is not a window manager. In Desktop Mode it is just another app, and
games launched from it behave like games launched from the Plasma menu.

## 3. Switching modes

Three equivalent entry points:

```bash
bunnyctl switch-mode desktop      # switch now
bunnyctl set-mode gaming          # default for the next login
bunnyctl status
```

The panel's mode chip and Settings → Session call the same daemon commands.

`bunny-sessiond` performs the switch as root:

1. Validate the requested mode (`gaming` or `desktop`).
2. Persist `session.default_mode` in `/etc/bunny/settings.json`.
3. Write `/var/lib/bunny/state.json` (mode, session name, boot id).
4. Rewrite `/etc/sddm.conf.d/20-bunny-session.conf` with the autologin session.
5. If SDDM is active, `systemctl restart sddm.service`.

Step 4 happens before step 5 on purpose: if the restart is interrupted, the
next boot still lands in a complete, consistent session.

### What is preserved

* Home directories, game libraries and `/var` are untouched.
* The Bun Bun agent is a user service; it stops with the session and restarts
  on the next login.
* Running games are terminated when the display manager restarts. The panel
  warns before switching and the daemon does not try to save state for you.

## 4. Autologin

Two drop-ins matter:

| File | Written by | Purpose |
|------|------------|---------|
| `/etc/sddm.conf.d/10-bunny.conf` | image / installer | Wayland, theme, power commands (no autologin) |
| `/etc/sddm.conf.d/20-bunny-session.conf` | seeded at build, then `bunny-sessiond` | autologin user and session (`bunny-gaming`/`bunny-desktop`) |

The seed sets `User=bunny` and `Session=bunny-gaming`. `bunny-sessiond` rewrites
the file whenever `session.default_mode` or `session.autologin` changes, so the
setting and the drop-in can never disagree. An empty `User=` disables autologin.

Autologin is on by default because a console should boot into a gamepad UI.
Turn it off for shared machines:

```bash
bunnyctl set session.autologin=false
```

That removes the automatic login but leaves the session entries intact, so the
SDDM greeter appears normally. The change takes effect at the next login; the
daemon does not restart SDDM for an autologin-only edit.

## 5. Live image vs installed system

The live image and an installed system share the same units, but not the same
state:

* **Live:** user `bunny` / password `bunny`, TTY2 autologin for recovery,
  `/run/archiso` marks the environment, the installer is available in the
  panel, and firstboot avoids writing to the USB stick where possible.
* **Installed:** the installer removes the live sudoers rule and TTY2
  autologin, creates a new machine-id, locks the root password, and enables
  firstboot for Flatpak provisioning.

`/run/archiso` is the authoritative "am I live?" marker. Both the daemon
(`status.live`) and the installer check it.

## 6. Recovery

If a mode switch leaves you at a black screen or a login loop:

1. Switch to a TTY: `Ctrl+Alt+F2` (live) or `Ctrl+Alt+F3` (installed).
2. Log in as your user.
3. Inspect the session:

   ```bash
   bunnyctl status
   journalctl -b -u sddm --no-pager | tail -80
   journalctl -b -u bunny-sessiond --no-pager | tail -40
   ```

4. Force a known-good default and reboot:

   ```bash
   sudo bunnyctl set-mode gaming
   sudo systemctl restart sddm
   ```

If SDDM itself is broken, start a session manually:

```bash
startplasma-wayland          # desktop recovery
bunny-session gaming         # panel recovery, needs a TTY with DRM access
```

If the panel cannot start, `bunny-panel --dev` serves the UI on
`127.0.0.1:8421` for a browser on another machine. This is a development path,
not a supported recovery console.

## 7. Configuration files

| File | Owner | Notes |
|------|-------|-------|
| `/etc/bunny/session.conf` | image | session names, gamescope args, agent toggle |
| `/etc/bunny/target.conf` | image (target builds) | per-device gamescope and kernel args |
| `/etc/bunny/settings.json` | `bunny-sessiond` | validated settings tree |
| `/etc/sddm.conf.d/*.conf` | image / daemon | autologin and theme |
| `/var/lib/bunny/state.json` | daemon | current mode, last switch, boot id |
| `/var/log/bunny/sessiond-audit.log` | daemon | one JSON object per privileged command |

`session.conf` is read by `bunny-session` and by the daemon's fallback logic.
It is intentionally simple `KEY=value` so it can be edited from a TTY with
`nano`.

## 8. Security notes

* Autologin means physical access is game over. That is true of every console;
  use full-disk encryption and a firmware password if the device leaves home.
* The panel cannot escalate privileges. It can only ask the daemon, which
  checks the caller's uid and group membership.
* The input agent is **masked** at build time. Enabling it writes
  `/etc/bunny/allow-input-agent` and requires an explicit consent token; see
  [BUNBUN.md](BUNBUN.md).
* Mode switches and power actions are audit-logged with the caller uid and
  arguments. The log is root-owned.
