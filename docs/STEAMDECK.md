# Bunny OS on the Steam Deck (LCD)

This page covers the **Steam Deck LCD** (Valve "Jupiter", the 2022 1280x800
model) only. The OLED model ("Galileo") has different display, Wi-Fi and
firmware behaviour and is **not validated** by this profile yet.

> **Status: beta, not hardware-certified.** The profile is built from the
> upstream Arch Linux support described on the ArchWiki Steam Deck page. The
> project has no physical Deck in its test rack, so treat every item in the
> checklist below as something *you* verify before trusting an install.

## What the profile changes

| Setting | Generic image | `--target deck` |
|---------|---------------|-----------------|
| gamescope | 1920x1080 internal | **1280x800 @ 60 Hz**, native panel |
| Kernel arguments | distro defaults | adds `amd_pstate=active` |
| zram | package only | `/etc/systemd/zram-generator.conf` (RAM/2, capped 8 GiB, zstd) |
| Firmware tooling | not installed | `fwupd` + `fwupd-refresh.timer` (peripherals; not Deck BIOS) |
| Diagnostics | basic | `alsa-utils`, `evtest`, `lm_sensors`, `vulkan-tools`, `mesa-utils` |
| Wi-Fi regulatory DB | distro default | `wireless-regdb` |
| ISO name | `BunnyOS-installer.iso` | `BunnyOS-deck-installer.iso` |

The common package set already contains `linux-firmware` (which pulls
`linux-firmware-amdgpu`), `sof-firmware`, `alsa-ucm-conf`, `pipewire`,
`wireplumber`, `bluez`, `NetworkManager`, `vulkan-radeon`, `mesa`, `steam`,
`gamescope` and `zram-generator`.

## What works with plain Arch packages

These are the LCD components and their upstream drivers. None of them require
Valve's kernel tree:

| Component | ID | Driver / firmware |
|-----------|----|-------------------|
| Wi-Fi | `10ec:c822` (RTL8822CE) | `rtw88` + `rtw88` firmware |
| GPU | `1002:163f` (Van Gogh) | `amdgpu` + `linux-firmware-amdgpu` |
| Audio | `1022:15e2` (ACP) | `snd_pci_acp5x` + `alsa-ucm-conf` |
| Bluetooth | `13d3:3555` (RTL8822CE) | `btusb` + `rtw88` firmware |
| Touchscreen | `2808:1015` (FTS3528) | `hid-multitouch` |
| Controls | `28de:1205` (Valve Deck) | `hid-steam` |
| Fan | ACPI | `acpi` thermal + `lm_sensors` |

Known upstream behaviour on the LCD model:

* Audio works out of the box on kernels 6.1 and newer.
* The panel only advertises **60 Hz**. There is no VRR on the LCD model.
* The built-in controller starts in **lizard mode** (keyboard/mouse emulation).
  Hold the `≡` (Menu) button for about a second to switch it to gamepad mode.
* Fan control is functional, but the SteamOS fan curve is Valve software, not a
  kernel feature.

## What is missing compared with SteamOS

* **Valve kernel patches.** `steamdeck-dkms` (AUR) packages them. archiso cannot
  use the AUR, and Bunny OS does not ship an out-of-tree kernel.
* **TDP and power tuning.** `ryzenadj` is AUR-only. The Control Panel's Tweaks
  page stores preferences but does not write TDP limits.
* **SteamOS fan curve and firmware tooling.** `fwupd` is included for devices
  stock Arch can update (docks, SSDs, some peripherals). Valve's Deck BIOS/EC
  update path is not published on LVFS for stock fwupd; use SteamOS or Valve's
  recovery/update flow for those.
* **SteamOS Game Mode.** Bunny OS boots its own Control Panel through gamescope;
  it does not use Valve's Game Mode UI.
* **Dual boot, disk encryption and BIOS installs.** All out of scope for v0.1.

## Build the Deck image

On Arch Linux with root:

```bash
sudo pacman -S --needed archiso squashfs-tools libisoburn libarchive openssl
sudo ./build_bunny_os_iso.sh --target deck
```

Outputs:

```
out/BunnyOS-deck-installer.iso
out/BunnyOS-deck-installer.iso.sha256
out/build-manifest.json          # "target": "deck"
```

Or from the Makefile:

```bash
make iso-deck          # native Arch host, sudo
make iso-deck-docker   # privileged Arch container on a Linux host
```

In GitHub Actions, run the **build-iso** workflow manually and choose
`deck` as the target. Selecting the target on a normal push is not possible;
pushes build the generic image.

Stage and inspect without producing an image:

```bash
sudo ./build_bunny_os_iso.sh --target deck --dry-run
cat build/build-plan.txt
```

## Flash from Windows 11

The build needs Linux, but flashing does not.

1. Download `BunnyOS-deck-installer.iso` and its `.sha256` from the CI artefact
   or release.
2. Verify it (PowerShell):
   ```powershell
   Get-FileHash .\BunnyOS-deck-installer.iso -Algorithm SHA256
   Get-Content .\BunnyOS-deck-installer.iso.sha256
   ```
3. Write it to a USB stick with **Rufus** or **balenaEtcher**. At least 8 GB;
   16 GB is comfortable.
4. **Preferred for the Steam Deck: Rufus "ISO Image mode" (FAT32).** The Deck's
   firmware only enumerates USB media it can read as FAT32, so a DD-written
   image can be invisible in the boot manager even though it is a valid hybrid
   ISO. ISO mode copies the same files onto a FAT32 partition, which the Deck
   does see — the live system only needs the files and the `BUNNY_OS` label.
   Select **GPT** + **UEFI (non CSM)**, then answer **ISO Image mode** when
   Rufus asks.
5. DD mode also boots once the media is enumerated, but if the Deck shows no
   USB entry, ISO mode is the supported workaround. Both must keep the
   `BUNNY_OS` volume label: the initramfs finds `airootfs.sfs` by label.
6. **Do not use Ventoy** or any tool that keeps the ISO as a file on a shared
   partition. The live system needs the `BUNNY_OS` label on the filesystem that
   holds `arch/`.
7. The Deck has a single USB-C port. Use a USB-C flash drive, or a USB-C hub
   with a USB-A stick. A hub is also the easiest way to attach a keyboard for
   recovery.

Writing the ISO **erases the USB stick**, not the Deck.

## Boot the Deck

1. Power the Deck off.
2. Hold **Volume Down + Power** until the boot menu appears.
3. Select the USB device. If it is not listed, reflash in Rufus **ISO Image
   mode** (FAT32) — the Deck skips USB media it cannot read as FAT32, and DD
   mode leaves the ISO's ISO9660 layout in place.
4. **Volume Up + Power** opens the UEFI settings, including boot order.

The Deck's firmware does not enforce Secure Boot for removable media, but the
image is unsigned. On other machines, disable Secure Boot before booting it.

## Choose an install mode

### A. Live USB only (recommended first)

Boot the stick and do **not** run `bunny-install`. This is the lowest-risk way
to test the panel, Bun Bun, Wi-Fi, audio and controls. SteamOS and every game on
the internal drive stay untouched. The live session is RAM-backed
(`cow_spacesize=4G`), so expect changes to disappear on reboot.

### B. Replace SteamOS (destructive)

`bunny-install` is **whole-disk**. It erases the eMMC/NVMe, creates a 512 MiB
ESP plus Btrfs (`@`, `@home`, `@var`, `@snapshots`) and installs systemd-boot.
There is no dual-boot support in v0.1 and no "install alongside" option.

Before doing this:

1. Create a **SteamOS recovery USB** from Valve's recovery image on another
   computer. This is the only supported way back to SteamOS.
2. Back up saves and anything in `/home`.
3. Keep the Bunny OS USB stick: it is also your rescue environment.

Then boot the Bunny OS stick and run:

```bash
sudo bunny-install
```

The installer lists disks, requires you to type `ERASE`, and refuses to install
onto the running USB. On a Deck the internal drive is usually
`/dev/mmcblk0` (64 GB eMMC) or `/dev/nvme0n1` (256/512 GB NVMe). Confirm with
`lsblk` before typing `ERASE`.

After installation, remove the USB stick and boot the internal drive. The first
boot runs `bunny-firstboot` (Flatpak remotes and apps, sysctl, snapshots), which
needs network for the Flatpak downloads.

### C. Dual boot with SteamOS

Not supported. The installer does not shrink partitions or add a second boot
entry, and SteamOS updates can rewrite the ESP. Do not attempt a manual
partitioning workaround on a Deck you care about.

## LCD test checklist

Run these on the live USB before installing. `sudo` is passwordless for the live
`bunny` user.

| # | Check | Command / action | Pass criteria |
|---|-------|------------------|---------------|
| 1 | Panel mode | `cat /sys/class/drm/card*-eDP-1/modes` | `1280x800` listed first |
| 2 | Gaming Mode | boot to the panel | Control Panel fills the screen, no letterboxing |
| 3 | Controller | hold `≡`, then `evtest` | a gamepad device appears; d-pad navigates the panel |
| 4 | Touch | tap Home / Settings | panel responds to touch |
| 5 | Wi-Fi | `nmcli device wifi list` | RTL8822CE scans and connects |
| 6 | Bluetooth | `bluetoothctl scan on` | controller/headset discovered |
| 7 | Speakers | `speaker-test -c 2 -t wav -l 1` | sound from both speakers |
| 8 | Headphones | plug into the 3.5 mm jack | output switches, no hiss |
| 9 | GPU | `vulkaninfo --summary` | `VANGOGH` / RADV device, no errors |
| 10 | Sensors | `sensors` | CPU/GPU temperatures and fan RPM plausible |
| 11 | IMU | `monitor-sensor` | accelerometer/orientation events |
| 12 | Suspend | `systemctl suspend`, press power | resumes to the panel, Wi-Fi reconnects |
| 13 | Steam | launch Steam from Platforms | login screen renders, a game starts |
| 14 | Desktop | Settings → Desktop Mode | Plasma starts; return to Gaming Mode |
| 15 | Firmware | `fwupdmgr get-devices` | devices enumerate; Deck BIOS may not be listed as updatable |
| 16 | Installer | `sudo bunny-install --dry-run` | sees the internal disk, changes nothing |

If a check fails, note the command output and the kernel log
(`journalctl -b -k`) before opening an issue.

## Recovery

| Situation | Recovery |
|-----------|----------|
| Live USB will not boot | reflash in Rufus **ISO Image mode** (FAT32); try a USB-A stick through a hub |
| Boot menu shows no USB entry | DD mode is invisible to some Deck firmware; reflash in ISO mode |
| `Error preparing initrd: Not found` | the entry referenced a file archiso did not ship; rebuild with current `iso/overrides` |
| Bunny install failed halfway | boot the live USB again and reinstall, or restore SteamOS from the recovery USB |
| Want SteamOS back | boot the SteamOS recovery USB and reimage the internal drive |
| Panel stuck / no session | `Ctrl+Alt+F2`, log in as `bunny`, `journalctl -b -u sddm`, then `sudo bunnyctl set-mode gaming` |
| Wi-Fi missing after an update | `pacman -Q linux-firmware`; `dmesg | grep -i rtw88` |

SteamOS recovery erases the internal drive. There is no supported path from
Bunny OS back to SteamOS that preserves Bunny OS data, so keep backups.

## Reporting Deck results

Include the model (LCD/OLED), the build id from `out/build-manifest.json`, the
checks that failed, and the relevant `journalctl` lines. Results from the OLED
model are useful but are not treated as LCD validation.
