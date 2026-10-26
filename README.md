# Bunny OS

A controller-first, Arch-based gaming distribution with a SteamOS-shaped couch
experience, a KDE Plasma desktop mode, and **Bun Bun** — a local AI co-op buddy
who gives hints, cheers you on, and can join allowlisted lobbies with your
explicit consent.

Bunny OS boots straight into a full-screen Control Panel. No keyboard required;
a d-pad is enough. Switch to Desktop Mode from the panel and you get a normal
Plasma session with the same games and files.

```
UEFI → systemd-boot → SDDM → Gaming Mode (gamescope) → Control Panel
                          └→ Desktop Mode (KDE Plasma Wayland)
```

## Status

This repository is the **source** of Bunny OS. The build pipeline produces a
bootable live installer image:

```
out/BunnyOS-installer.iso
out/BunnyOS-installer.iso.sha256
out/build-manifest.json
```

**No ISO is checked in.** Building one requires Arch Linux, root, loop devices
and `mkarchiso`; a native build on Windows or macOS is not possible. Use an Arch
host, the privileged Docker path on a Linux host, or the GitHub Actions workflow
(see [BUILD.md](docs/BUILD.md)).

Known gaps, stated plainly:

* The **immutable/OSTree core is only partially realised**. Installs use Btrfs
  subvolumes today; `bunny-update` has an OSTree path for future deployments.
* The installer is **UEFI-only, whole-disk, and unencrypted** in v0.1.
* Bun Bun is **rule-based**, not a neural model. No hot mic, no screen capture.
* Input injection is keyboard/mouse only, masked by default, and hard-denied in
  anti-cheat and competitive titles.
* The native Tauri shell is optional; the image falls back to Chromium kiosk.
* The **Steam Deck LCD target is beta**. It uses plain Arch packages and has not
  been certified on physical Deck hardware; the OLED model is out of scope for
  now. See [STEAMDECK.md](docs/STEAMDECK.md).

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture and roadmap.

## What is in the box

| Area | What you get |
|------|--------------|
| **Gaming Mode** | gamescope → full-screen Control Panel, gamepad + keyboard navigation |
| **Desktop Mode** | KDE Plasma Wayland, same user and game libraries |
| **Panel** | Home, Platforms, Tweaks, Bun Bun, Settings; every action reachable by d-pad |
| **Platforms** | Steam (native), Epic and GOG via Heroic, Lutris, RetroArch |
| **Tweaks** | Saved performance, display and audio preferences with validation; hardware writes are not wired yet |
| **Bun Bun** | Persona, hints, commentary, co-op planner, memory purge, kill switch |
| **Sessions** | `bunny-session`, SDDM autologin, one-command mode switch, recovery docs |
| **Installer** | Guided whole-disk UEFI install with Btrfs subvolumes and systemd-boot |
| **Build** | One pipeline, `--dry-run`, Docker path, CI artefact + release workflow |

## Repository map

```
build_bunny_os_iso.sh   pipeline: preflight → stage → validate → mkarchiso → out/
iso/                    archiso profile, package list, pacman.conf, airootfs seed
iso/targets/            per-device profiles (deck = Steam Deck LCD)
system/                 session daemon, session scripts, systemd units, SDDM entries
bunbun/                 Bun Bun agent (Python stdlib only) + offline test suite
control-panel/          dependency-free web UI + optional Tauri v2 shell
launchers/              allowlisted game launchers and library scanner
installer/              destructive whole-disk installer
scripts/                preflight, stage, validate, docker, flash, sign
tools/                  verify.py (canonical), verify.ps1 (Windows mirror)
docs/                   architecture, build, sessions, Bun Bun, safety/legal
```

## Try the panel without installing anything

The UI is plain HTML/CSS/ES modules. No npm, no bundler, no network:

```bash
python3 -m http.server 8420 --bind 127.0.0.1 --directory control-panel/ui
# open http://127.0.0.1:8420/
```

With no daemon running, the panel detects that and switches to **Offline
preview** (`js/mock.js`). Actions are simulated in memory and clearly labelled;
nothing claims to have changed the system.

To exercise the real backend on a live image:

```bash
sudo systemctl start bunny-sessiond
/usr/local/bin/bunny-panel-bridge --ui /opt/bunny/panel/ui &
xdg-open http://127.0.0.1:8421/
```

## Verify the repository

```bash
# Canonical, works on any Linux/macOS with Python 3.10+:
python3 tools/verify.py --strict

# Bun Bun unit tests, offline:
cd bunbun && python3 -m unittest discover -s tests -t . -v

# Windows contributor mirror (no Python/Git needed):
powershell -ExecutionPolicy Bypass -File tools\verify.ps1
```

`verify` checks structure, JSON, systemd unit sections, desktop entries, line
endings, template tokens, package hygiene, and the safety invariants. It does
not build an image and cannot prove the ISO boots.

## Build the ISO

On Arch Linux:

```bash
sudo pacman -S --needed archiso squashfs-tools libisoburn libarchive openssl
sudo ./build_bunny_os_iso.sh
```

Stage and validate only, without claiming to produce an image:

```bash
sudo ./build_bunny_os_iso.sh --dry-run
cat build/build-plan.txt
```

Docker (Linux host recommended) and CI:

```bash
./build_bunny_os_iso.sh --docker
# or run the "build-iso" workflow from the Actions tab
```

Steam Deck LCD image (1280x800 gamescope, zram, fwupd, Deck kernel arguments):

```bash
sudo ./build_bunny_os_iso.sh --target deck   # out/BunnyOS-deck-installer.iso
```

Read [STEAMDECK.md](docs/STEAMDECK.md) before flashing or installing: it covers
the LCD support matrix, the live-USB-first recommendation, SteamOS recovery and
the hardware test checklist.

Full requirements, flags, artefact contract, flashing and troubleshooting:
[BUILD.md](docs/BUILD.md).

## Safety model in one paragraph

The Control Panel is an unprivileged client. `bunny-sessiond` is the only root
broker; it checks peer uid, validates settings against a schema, and audit-logs
state changes. Bun Bun runs as your user on loopback with no cloud calls. It can
speak and show hints freely, but input injection and lobby joins need explicit
opt-in, an allowlist entry, and (for input) a root-owned token. Anti-cheat and
competitive titles are hard-denied. The input agent is masked at build time and
has a panic switch. Full details, residual risks and legal notes:
[BUNBUN.md](docs/BUNBUN.md) and
[SAFETY-AND-LEGAL.md](docs/SAFETY-AND-LEGAL.md).

## Documentation

| Document | Contents |
|----------|----------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Layers, privilege boundary, boot flow, filesystem, roadmap |
| [BUILD.md](docs/BUILD.md) | Host requirements, flags, Docker, CI, artefacts, flashing |
| [SESSIONS.md](docs/SESSIONS.md) | Gaming/Desktop modes, autologin, switching, recovery |
| [BUNBUN.md](docs/BUNBUN.md) | Persona, MAM loop, hints, TTS, API/SSE, co-op, input agent |
| [SAFETY-AND-LEGAL.md](docs/SAFETY-AND-LEGAL.md) | Hard denials, consent, anti-cheat, privacy, licensing |
| [control-panel/README.md](control-panel/README.md) | UI transports, controller map, native shell build |

## Contributing

Small, reviewable changes are welcome. Before opening a pull request:

1. Run `python3 tools/verify.py --strict` and the Bun Bun tests.
2. Keep the safety invariants intact. Do not remove the anti-cheat,
   competitive, allowlist or input-token checks.
3. State which parts are stubs. Do not fabricate a successful build in docs or
   UI.
4. Keep line endings LF and avoid binary blobs in the tree.

## Licence

MIT. See [LICENSE](LICENSE). Bunny OS is not affiliated with Valve, Epic Games,
GOG, KDE, Arch Linux, or any anti-cheat vendor. Emulator ROMs and BIOS files are
not included.
