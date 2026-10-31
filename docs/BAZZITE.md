# Bunny OS on Bazzite (Steam Deck LCD)

This is the second way to run Bunny OS on a Steam Deck: instead of building the
whole system from Arch packages (`docs/STEAMDECK.md`), the official
**Bazzite Deck** image is used as the base and the Bunny OS layer is baked on
top of it.

The point of doing it this way is the hardware. Bazzite already ships the boot
chain, kernel, firmware, controller handling and Gaming Mode that work on a
Deck, so the only untested part is Bunny OS itself.

```
ghcr.io/ublue-os/bazzite:stable            live medium
   + anaconda-live, dracut-live, livesys
   + localhost/bunny-deck:latest in storage
        |
        v
   titanoboa -> BunnyOS-deck-bazzite.iso

ghcr.io/ublue-os/bazzite-deck:stable       installed system
   + Bunny OS payload (panel, bridge, wizard)
        = localhost/bunny-deck:latest
```

The live medium is the *desktop* image, not the Deck image: on the Deck image
the machine boots into Gaming Mode, which is no place to run an installer. That
is exactly how Bazzite builds its own ISO, and it means everything the installer
needs (Anaconda, its profile, the live user, the desktop session) is stock
upstream behaviour.

> **Status: beta.** The image builds in CI and passes the same static
> verification as the Arch ISO, but it has not been installed on physical
> hardware by this project. Treat the checklist at the end of this page as
> something you verify.
>
> **Latest build:** [`v0.2.0-beta.5-bazzite`](https://github.com/yrg8fn10/bunny-os/releases/tag/v0.2.0-beta.5-bazzite)
> - 7.3 GB, shipped as four `.part` files plus `READ-ME-FIRST.txt`.

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

1. Download the release assets. `READ-ME-FIRST.txt` in the release has the exact
   file names. The image is about 7.3 GB, so GitHub's 2 GiB asset limit means it
   ships as numbered parts - join all of them, in order, into one ISO:

   ```
   Right-click Start > Terminal, then in the folder with the parts:
   copy /b BunnyOS-deck-bazzite.iso.01.part+BunnyOS-deck-bazzite.iso.02.part+BunnyOS-deck-bazzite.iso.03.part+BunnyOS-deck-bazzite.iso.04.part BunnyOS-deck-bazzite.iso
   ```

   `READ-ME-FIRST.txt` prints the same command with the parts this build
   actually produced. Check the result against the `.sha256` file before
   flashing:

   ```
   certutil -hashfile BunnyOS-deck-bazzite.iso SHA256
   ```

2. Flash it with Rufus in **ISO Image mode**, not DD mode.

3. On the Deck, power off, hold **Volume Down**, press **Power**, and pick the
   USB device from the boot menu.

4. The medium boots a Bazzite desktop and opens the installer automatically.
   Anaconda's UI is a browser window: use the touchscreen (or a USB mouse).

5. Choose the internal drive and let it install. The image is local to the
   medium, so the installer works without a network connection.

6. Reboot without the stick. The Deck boots into Gaming Mode for the first
   time, installs its flatpak applications (Steam and friends) from Flathub,
   and the Bunny OS wizard opens the first time you switch to Desktop Mode.

Anaconda also gives you a **root password** and a **user account** step. The
account you create there is the one you log in with afterwards; the wizard still
asks for the network and the time zone, and can create the desktop account if
you skip it in the installer.

### First boot

`bunny-setupd` is enabled at build time, so it is already running when the
Desktop Mode session starts. `bunny-os-setup` opens the wizard on the first
login after install and exits immediately on later logins; the wizard writes
`/var/lib/bunny/.oobe-done` when it finishes.

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
the same payload is available as a tarball, and every Bazzite release page
attaches it:

```
tar -xzf bunny-os-portable-0.2.0.tar.gz
cd bunny-os-portable-0.2.0
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
4. builds `bunny-deck` from `packaging/bazzite/Containerfile` on top of
   `bazzite-deck:stable` - the image that ends up on the Deck;
5. saves that image to `packaging/bazzite/bunny-deck.oci`;
6. builds `bunny-live` from `packaging/bazzite/Containerfile.live` on top of
   `bazzite:stable`, runs `live-iso.sh` to add the live root, Anaconda, the
   kickstart and the payload image in container storage;
7. hands `bunny-live` to `ublue-os/titanoboa`, which writes the ISO;
8. for a `v*-bazzite` tag, splits the ISO into 1.9 GB parts, writes
   `READ-ME-FIRST.txt` and publishes everything as a prerelease.

A manual run (`workflow_dispatch`) does steps 1-7 and keeps the ISO as a
workflow artefact, which is convenient for testing but not for downloading -
the release is the delivery path.

Locally, with podman and about 60 GB free:

```
bash scripts/build-portable.sh
cp out/bunny-os-portable-*.tar.gz packaging/bazzite/bunny-os-portable.tar.gz

sudo podman build --cap-add sys_admin --security-opt label=disable \
  --build-arg BUNNY_VERSION="$(cat VERSION)" \
  -t localhost/bunny-deck:latest packaging/bazzite/

sudo podman save --format oci-archive \
  -o packaging/bazzite/bunny-deck.oci localhost/bunny-deck:latest

sudo podman build --cap-add sys_admin --security-opt label=disable \
  -f packaging/bazzite/Containerfile.live \
  -t localhost/bunny-live:latest packaging/bazzite/
```

Then, with titanoboa checked out, `image-ref: localhost/bunny-live:latest`.

Everything the payload installs lives in `/usr` (ostree makes `/usr/local` a
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
- **No custom kernel.** Bazzite's kernel is used as shipped, which means the
  medium needs **Secure Boot disabled** (the Deck ships that way). Bazzite's own
  ISO swaps in a Fedora-signed kernel for Secure Boot machines; this one does
  not.
- **No update channel yet.** The installed system's container reference points
  at the local image, so `rpm-ostree upgrade` has nowhere to pull from. A new
  Bunny OS release means a new ISO.
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
