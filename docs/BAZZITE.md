# Bunny OS on Bazzite (Steam Deck LCD)

This is the second way to run Bunny OS on a Steam Deck: instead of building the
whole system from Arch packages (`docs/STEAMDECK.md`), the official
**Bazzite Deck** image is used as the base and the Bunny OS layer is baked on
top of it.

The point of doing it this way is the hardware. Bazzite already ships the boot
chain, kernel, firmware, controller handling and Gaming Mode that work on a
Deck, so the only untested part is Bunny OS itself.

```
ghcr.io/ublue-os/bazzite-deck:stable
        + Bunny OS payload (Control Panel, bridge, first-boot wizard)
        = localhost/bunny-deck:live   ->   titanoboa   ->   BunnyOS-deck-bazzite.iso
```

> **Status: beta.** The image builds in CI and passes the same static
> verification as the Arch ISO, but it has not been installed on physical
> hardware by this project. Treat the checklist at the end of this page as
> something you verify.

## Which image should I use?

| | `BunnyOS-deck-installer.iso` | `BunnyOS-deck-bazzite.iso` |
|---|---|---|
| Base | Arch Linux, built here | Bazzite Deck, built by ublue |
| ISO size | ~2.7 GB | ~6-8 GB |
| Installer | Bunny's own `bunny-install` | Anaconda (Bazzite's installer) |
| Kernel | Arch `linux` | Bazzite's Deck kernel |
| Steam / Gaming Mode | Steam from Arch | Bazzite's tuned Gaming Mode |
| Updates | none | `rpm-ostree` / `ujust update` |
| Best for | a clean, minimal Deck | a Deck that should behave like Bazzite |

Both boot into the same Bunny OS first-boot wizard and land in the same
Control Panel.

## Installing the Bazzite image

1. Download the ISO from the release page. If it ships as `.01.part`,
   `.02.part`, join the parts first:

   ```
   Right-click Start > Terminal, then in the folder with the parts:
   copy /b BunnyOS-deck-bazzite.iso.01.part+BunnyOS-deck-bazzite.iso.02.part BunnyOS-deck-bazzite.iso
   ```

   Check the result against the `.sha256` file before flashing:

   ```
   certutil -hashfile BunnyOS-deck-bazzite.iso SHA256
   ```

2. Flash it with Rufus in **ISO Image mode**, not DD mode.

3. On the Deck, power off, hold **Volume Down**, press **Power**, and pick the
   USB device from the boot menu.

4. The ISO boots the Bunny OS Deck image itself and starts Anaconda. Choose the
   internal drive and let it install. The image is local to the medium, so the
   installer works without a network connection.

5. Reboot without the stick. The Deck boots straight into the Bunny OS wizard.

Anaconda also gives you a **root password** and a **user account** step. The
account you create there is the one you log in with afterwards; the wizard still
asks for the network and the time zone, and can create the desktop account if
you skip it in the installer.

### First boot

The first boot runs `bunny-setupd` and `bunny-panel --setup` as a Wayland kiosk.
The wizard walks through welcome, network, time zone and account and then writes
`/var/lib/bunny/.oobe-done`. From the next boot the panel opens directly.

The wizard is designed for the Deck's controls alone:

| Deck control | Wizard action |
|---|---|
| D-pad | move focus |
| A (Enter in lizard mode) | select, or open the on-screen keyboard in a text field |
| B (Escape) | back |
| Touch | tap directly, including the keyboard |

The Deck's controller starts in "lizard mode", where it presents itself as a
keyboard, which is why A arrives as `Enter`. The wizard handles both that and
real gamepad events, so a paired controller works too.

## Portable install (no new image)

If the Deck already runs Bazzite or SteamOS and you do not want to reinstall,
the same payload is available as a tarball:

```
tar -xzf bunny-os-portable-<version>.tar.gz
cd bunny-os-portable-<version>
sudo ./install.sh
```

It installs the Control Panel and the setup service under `/usr/local`, adds a
**Bunny OS** entry to the application menu, and opens the wizard on the next
login until it is finished. The boot loader, kernel, greeter and account are
not touched.

Uninstalling keeps `/var/lib/bunny`, so a reinstall does not replay the wizard:

```
sudo ./uninstall.sh            # keep the "setup finished" marker
sudo ./uninstall.sh --purge    # forget it too
```

The service runs `bunny-setupd --portable`: network and time zone only. It never
creates an account, never rewrites SDDM and never restarts the session.

## Building it yourself

The CI workflow `.github/workflows/build-bazzite-iso.yml` does the whole job:

1. verifies the repository (`tools/verify.py --strict`, shell syntax);
2. frees the runner and puts podman storage on a btrfs loopback;
3. builds the portable tarball with `scripts/build-portable.sh`;
4. `podman build packaging/bazzite/` on top of `bazzite-deck:stable`;
5. runs `packaging/bazzite/live-iso.sh` inside the image to add the live root,
   Anaconda and the `iso.yaml` contract, and commits the result;
6. hands the committed image to `ublue-os/titanoboa`, which writes the ISO;
7. publishes it as a release asset for `v*-bazzite` tags.

Locally, with podman and about 60 GB free:

```
bash scripts/build-portable.sh
cp out/bunny-os-portable-*.tar.gz packaging/bazzite/bunny-os-portable.tar.gz
sudo podman build --cap-add sys_admin --security-opt label=disable \
  --build-arg BASE_IMAGE=ghcr.io/ublue-os/bazzite-deck:stable \
  --build-arg BUNNY_VERSION="$(cat VERSION)" \
  -t localhost/bunny-deck:live packaging/bazzite/
```

Everything the image installs lives in `/usr` (ostree makes `/usr/local` a
symlink into `/var`, which an update can prune). The only runtime state is
`/var/lib/bunny`: the setup marker and the audit log.

The two upstream inputs are pinned in the workflow so an upstream change cannot
silently alter the image:

| Input | Pin |
|---|---|
| `ublue-os/bazzite` | `b00fd741f950dbaf3fe4694454f942d268fd9e18` |
| `ublue-os/titanoboa` | `5c457c3d0518bd17e754be0fd98a60d29d26abb4` |

## What this does not do

- **No OLED support.** The `galileo` model is not validated; the same warning
  as in `docs/STEAMDECK.md` applies.
- **No custom kernel.** Bazzite's kernel is used as shipped.
- **No separate update channel for Bunny OS.** Bunny OS is part of the image, so
  it moves when the image does.
- **No dual boot.** Installing replaces what is on the internal drive. Use a
  spare SSD or back up first.

## Checklist for a real Deck

- [ ] ISO boots from the USB device (Volume Down + Power).
- [ ] Anaconda installs to the internal drive and the Deck reboots into Bunny OS.
- [ ] Wi-Fi `10ec:c822` associates from the wizard, without a keyboard.
- [ ] Time zone can be picked with the D-pad, and the on-screen keyboard opens
      on the password field.
- [ ] The wizard finishes and does not reappear after a reboot.
- [ ] Audio works (`1022:15e2`); the panel and Gaming Mode both have sound.
- [ ] Touchscreen `2808:1015` drives the wizard and the panel.
- [ ] Suspend and resume from Gaming Mode.
- [ ] `rpm-ostree status` shows one deployment, and `bunny-os` still starts
      after an update.
