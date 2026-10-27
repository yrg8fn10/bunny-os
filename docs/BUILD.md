# Building Bunny OS

The default build produces:

```
out/BunnyOS-installer.iso
out/BunnyOS-installer.iso.sha256
out/build-manifest.json
```

Target builds keep the same contract with a target-qualified name. The Steam
Deck LCD profile (`--target deck`) produces:

```
out/BunnyOS-deck-installer.iso
out/BunnyOS-deck-installer.iso.sha256
out/build-manifest.json          # "target": "deck"
```

The ISO is a **live installer image**, not an installed system. It boots to the
Control Panel in Gaming Mode and can install itself to a disk with
`bunny-install`.

## 1. What the build needs

`mkarchiso` is not a cross-compiler. It needs a Linux kernel, root, loop
devices and `mount(2)`. That rules out a native build on Windows and macOS.

| Requirement | Why |
|-------------|-----|
| Arch Linux x86_64 | `mkarchiso`, `pacman`, matching package database |
| root | loop-mount the airootfs and create device nodes |
| ~25 GB free | work tree + squashfs + ISO |
| network | download the package set |
| `archiso`, `squashfs-tools`, `libisoburn`, `libarchive`, `openssl` | image creation and checksums |

Install them on Arch:

```bash
sudo pacman -S --needed archiso squashfs-tools libisoburn libarchive openssl
```

Python 3 is optional but enables the JSON/Python stages of validation and the
Bun Bun test suite. `shellcheck`, `zstd` and `gpg` are optional.

## 2. Build on Arch

```bash
git clone <your-fork> bunny-os
cd bunny-os
sudo ./build_bunny_os_iso.sh
```

Useful flags:

| Flag | Effect |
|------|--------|
| `--dry-run` | preflight (non-fatal), stage, validate, write `build/build-plan.txt`; **produces no ISO** |
| `--target NAME` | apply a profile from `iso/targets/NAME/` (currently `deck`); changes packages, boot arguments and the ISO name |
| `--keep-work` | keep `build/archiso-work` for debugging |
| `--no-validate` | skip static validation (not recommended) |
| `--no-clean` | reuse the previous work tree |
| `--jobs N` | override CPU count |
| `--out DIR` | write artefacts elsewhere |
| `--sign KEYID` | detached-sign the SHA-256 file with GPG |
| `--docker` | hand off to `scripts/build-docker.sh` |
| `--verbose` | `set -x` |

Environment variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `BUNNY_CHANNEL` | `stable` | `stable`, `beta`, `dev`; rendered into the image |
| `BUILD_ID` | timestamp | build identifier in the manifest |
| `BUNNY_MIN_FREE_GB` | `25` | preflight free-space floor |
| `BUNNY_OFFLINE` | `0` | set to `1` to skip the mirror reachability check |

## 3. Target profiles

A target is a small overlay on top of the generic image:

```
iso/targets/<name>/
  target.conf        # id, display name, ISO basename, gamescope and kernel args
  packages.x86_64    # extra packages, appended without duplicates
  overlay/           # files copied over the archiso stage (boot entries)
  airootfs/          # files copied into the live/installed root
```

`target.conf` is also installed as `/etc/bunny/target.conf`. `bunny-session`
reads it for gamescope arguments, and `bunny-install` copies its
`BUNNY_KERNEL_ARGS` into the installed systemd-boot entry.

Build the Steam Deck LCD image:

```bash
sudo ./build_bunny_os_iso.sh --target deck
# or: make iso-deck
```

The target is recorded in `/etc/bunny/target`, `build-info.json` and
`build-manifest.json`. There is no implicit hardware detection: a generic ISO
installed on a Deck keeps the generic 1080p gamescope arguments. The profile
and its limitations are documented in [STEAMDECK.md](STEAMDECK.md).

## 4. Verify before and after

```bash
# Static checks only, no root:
python3 tools/verify.py --strict

# Stage + validate without building:
sudo ./build_bunny_os_iso.sh --dry-run
cat build/build-plan.txt

# Bun Bun unit tests (offline, stdlib only):
cd bunbun && python3 -m unittest discover -s tests -t . -v

# The recovery menu's disk picker and the installer's generated post-install
# script (both run without root, disks or Arch):
bash tools/recovery-smoke.sh
bash tools/installer-smoke.sh

# Inspect the result:
ls -lh out/
( cd out && for f in *.iso.sha256; do sha256sum -c "$f"; done )
python3 -m json.tool out/build-manifest.json
```

`tools/verify.ps1` is a Windows mirror for contributors without Python/Git. It
checks structure, JSON, unit sections, desktop entries, CRLF, templates and the
safety invariants. It is not a substitute for `mkarchiso`.

## 5. Build inside Docker

```bash
./build_bunny_os_iso.sh --docker
```

`scripts/build-docker.sh` runs `archlinux:latest` with `--privileged`, mounts
the repository at `/work` and installs the build tools inside the container.

Caveats, stated plainly:

* Docker Desktop on Windows/macOS usually cannot provide working loop devices
  to the container. The script warns and may fail; **CI is the reliable path**.
* The container shares the host kernel. It is not a sandbox for hostile
  package scripts.
* `--privileged` is required because `mkarchiso` mounts filesystems and creates
  device nodes.

## 6. Build in CI

`.github/workflows/build-iso.yml` runs three jobs:

1. **verify** — `tools/verify.py`, shell syntax, Bun Bun tests and the two
   smoke tests (`recovery-smoke.sh`, `installer-smoke.sh`).
2. **build** — privileged Arch container on `ubuntu-latest`, uploads the ISO,
   checksum and manifest as workflow artefacts.
3. **release** — on a `v*` tag, attaches the same files to a GitHub release.

Trigger it manually from the Actions tab (`workflow_dispatch`) or by pushing a
tag. A manual run lets you choose the **target**: `generic` (default) or `deck`.
Pushes and tags always build the generic image.

```bash
git tag v0.1.0
git push origin v0.1.0
```

GitHub-hosted runners allow loop devices inside privileged containers, which
is why this path works where Docker Desktop often does not. Builds take
20–40 minutes and the image is roughly 3–5 GB depending on packages.

## 7. Artefact contract

`out/build-manifest.json` is the machine-readable record of a build:

```json
{
  "product": "Bunny OS",
  "version": "0.1.0",
  "channel": "stable",
  "build_id": "20261026T101500Z",
  "target": "generic",
  "target_name": "generic target",
  "built_at": "2026-10-26T10:15:00Z",
  "git_revision": "abc1234",
  "host": "Linux 6.11.0 x86_64",
  "archiso": "78-1",
  "iso": {
    "filename": "BunnyOS-installer.iso",
    "size_bytes": 3921674240,
    "sha256": "…"
  },
  "contents": {
    "packages": 91,
    "agent": "Bun Bun MAM 0.1",
    "control_panel": "bunny-panel 0.1",
    "session_modes": ["gaming", "desktop"]
  },
  "build_seconds": 1840
}
```

The checksum file is `sha256sum -c` compatible:

```
<sha256>  BunnyOS-installer.iso
```

## 8. Flash and boot

```bash
# Identify the USB stick first. This is destructive.
lsblk
sudo dd if=out/BunnyOS-installer.iso of=/dev/sdX bs=16M status=progress oflag=sync
sync

# or the helper (refuses mounted devices and the running system disk):
sudo ./scripts/flash-usb.sh out/BunnyOS-installer.iso /dev/sdX
```

On Windows, write the ISO with Rufus (**ISO Image mode** on machines that skip
hybrid images, otherwise **DD mode**) or balenaEtcher. Do not use Ventoy: it
copies the ISO as a file and the `archisolabel` lookup fails. For the Steam Deck
LCD, follow [STEAMDECK.md](STEAMDECK.md) instead — it covers the USB-C
requirement, the FAT32/DD difference, boot keys, recovery media and the hardware
checklist.

Boot with UEFI. Secure Boot must be disabled for v0.1 because the image is not
signed with a key enrolled in your firmware. Ventoy and similar multiboot
tools may not pass the `archisolabel` through; write the ISO directly if boot
fails with "cannot find device with label BUNNY_OS".

Live login: user `bunny`, password `bunny`. The installer forces a new password
for the installed system.

## 9. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `preflight: not Arch` | run on Arch, use `--docker`, or CI. `--allow-non-arch` only helps staging/validation. |
| `unknown target 'deck'` | build from the repository root; `iso/targets/deck/` must exist |
| Deck boots at 1920x1080 (letterboxed) | you installed the generic image; rebuild with `--target deck` |
| Deck Wi-Fi/audio/controls missing | check `dmesg` for `rtw88`/`acp5x`/`hid-steam`; see [STEAMDECK.md](STEAMDECK.md) |
| `mkarchiso: command not found` | `sudo pacman -S archiso` |
| `failed to setup loop device` | no loop support (container/WSL). Use privileged Docker on a Linux host or CI. |
| package signature errors | `sudo pacman -Sy archlinux-keyring` then retry; stale container images are a common cause |
| `not enough free space` | 25 GB is the floor; builds with NVIDIA drivers and large desktops need more |
| boot stops at `archisolabel` | wrong ISO write method, or a modified `profiledef.sh` label |
| panel shows "Offline preview" | `bunny-sessiond` not running or user not in `bunny`/`wheel` |
| Bun Bun silent | check `systemctl --user status bunny-bunbun` and `/v1/health`; TTS backend may be unavailable |
| SDDM loops after mode switch | boot TTY2, `bunnyctl set-mode gaming`, reboot; inspect `journalctl -u sddm` |

Build logs are kept at `build/archiso-work/build.log` (unless cleaned) and the
staged profile at `build/profile`.

## 10. Reproducibility

Bunny OS does not yet promise bit-identical images. Package versions move, and
`mkarchiso` embeds timestamps. The manifest records the git revision, archiso
version and host so two builds can be compared. For a reproducible set, pin
packages with a dated mirror and build from a clean container.

## 11. Beta releases

Pushing a `v*` tag builds and publishes automatically:

```
git tag -a v0.1.0-beta.1 -m "beta 1"
git push origin v0.1.0-beta.1
```

A tag has no workflow input, so it builds the `deck` profile (that is what the
tagged channel means). Tags containing a `-` are marked as pre-releases.

GitHub caps a release asset at 2 GiB and the Deck image is about 2.7 GB, so the
release job splits the ISO into 1.9 GB `.part` files, deletes the unsplit copy
and attaches a `READ-ME-FIRST.txt` with the join command. The `.sha256` still
describes the joined ISO:

```
cat BunnyOS-deck-installer.iso.??.part > BunnyOS-deck-installer.iso
sha256sum -c BunnyOS-deck-installer.iso.sha256
```

The same ISO is also a workflow artefact for 14 days, which is the easier route
for testers who have repository access (no joining, no size limit).

### Shipping from a working tree

`scripts/ship-release.sh` is the "patch is merged, publish the new image" path.
It refuses a dirty tree or a branch other than `main`, runs `verify.py --strict`
plus `bash -n` and the Python compile *before* it tags, pushes `main`, creates the
next `vX.Y.Z-beta.N` tag, watches the workflow and prints the release URL:

```
scripts/ship-release.sh              # next beta
scripts/ship-release.sh --dry-run    # check everything, push nothing
scripts/ship-release.sh v0.2.0-beta.1
PYTHON=/path/to/python scripts/ship-release.sh   # if python is not on PATH
```

Verification runs first on purpose: a tag is published to testers, so tagging an
unverified tree is the one mistake the script must not allow.
