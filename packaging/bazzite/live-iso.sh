#!/usr/bin/env bash
# =============================================================================
#  Turn the Bazzite desktop image into the Bunny OS live installer.
#
#  Runs inside the live image build (see Containerfile.live).  By the time this
#  script runs:
#
#    /src/anaconda/     the Anaconda profile for the live medium
#    /ctx/bunny-deck.oci  the payload image, saved by the workflow
#
#  The result boots to a KDE desktop, opens Anaconda on login, and installs
#  localhost/bunny-deck:latest from local container storage - no network.
# =============================================================================
set -euxo pipefail

ISO_LABEL="${ISO_LABEL:-BunnyOS-Live}"
PAYLOAD_TAG="${PAYLOAD_TAG:-localhost/bunny-deck:latest}"
VARIANT_ID="${VARIANT_ID:-bunny-deck}"

# Bazzite pins versions for its desktop.  Anaconda drags in newer ones and the
# versionlocks turn that into an unreadable dependency error.
dnf -qy versionlock clear || true

# --- 1. live root and installer ---------------------------------------------
dnf install -y --setopt=install_weak_deps=False --allowerasing \
    dracut-live \
    livesys-scripts \
    grub2-efi-x64-cdboot \
    anaconda-live \
    firefox \
    libblockdev-btrfs libblockdev-lvm libblockdev-dm

# Anaconda Web UI keeps state here.
mkdir -p /var/lib/rpm-state

kernel="$(find /usr/lib/modules -maxdepth 1 -mindepth 1 -type d -printf '%f\n' | head -1)"
test -n "${kernel}"
test -f "/usr/lib/modules/${kernel}/vmlinuz"

# The ISO boots the image itself, so the initramfs has to be able to find a
# live root on the medium.
DRACUT_NO_XATTR=1 dracut -v --force --zstd --reproducible --no-hostonly \
    --add "dmsquash-live dmsquash-live-autooverlay" \
    "/usr/lib/modules/${kernel}/initramfs.img" "${kernel}"

# livesys starts the desktop session for the live user on the Deck's panel.
sed -i "s/^livesys_session=.*/livesys_session=kde/" /etc/sysconfig/livesys
systemctl enable livesys.service livesys-late.service

# --- 2. what image-builder expects ------------------------------------------
# EFI tree: shim, grub and the fallback binary.
mkdir -p /boot/efi
cp -av /usr/lib/efi/*/*/EFI /boot/efi/
cp -v /boot/efi/EFI/fedora/grubx64.efi /boot/efi/EFI/BOOT/fbx64.efi || true

# ostree wants a lot of temporary space; /run is a small tmpfs on a live boot.
rm -rf /var/tmp
mkdir -p /var/tmp
cat > /etc/systemd/system/var-tmp.mount <<'EOF'
[Unit]
Description=Larger tmpfs for /var/tmp on the live system

[Mount]
What=tmpfs
Where=/var/tmp
Type=tmpfs
Options=size=50%,nr_inodes=1m

[Install]
WantedBy=local-fs.target
EOF
systemctl enable var-tmp.mount

# --- 3. Anaconda -------------------------------------------------------------
mkdir -p /etc/anaconda/profile.d /etc/anaconda/conf.d
install -m 0644 /src/anaconda/bunny.conf /etc/anaconda/profile.d/bunny.conf
install -m 0644 /src/anaconda/anaconda.conf /etc/anaconda/conf.d/anaconda.conf

printf 'Bunny OS live image (%s)\n' "${VARIANT_ID}" > /etc/system-release

# This is a live medium, not a desktop: Anaconda installs the *payload* image,
# which keeps every one of these services enabled.  They are disabled here
# only, and only so they do not fight the installer or reach for the network
# while it runs.
for unit in rpm-ostreed-automatic.timer uupd.timer \
            bazzite-flatpak-manager.service ublue-flatpak-manager.service \
            flatpak-add-fedora-repos.service bootloader-update.service \
            bazzite-hardware-setup.service ublue-hardware-setup.service \
            ublue-system-setup.service ublue-guest-user.service \
            ublue-os-media-automount.service brew-upgrade.timer \
            brew-update.timer brew-setup.service \
            greenboot-healthcheck.service greenboot-set-rollback-trigger.service \
            rpm-ostree-countme.service tailscaled.service \
            input-remapper.service switcheroo-control.service \
            check-sb-key.service; do
  systemctl disable "${unit}" 2>/dev/null || true
done
for unit in podman-auto-update.timer bazzite-user-setup.service \
            ublue-user-setup.service; do
  systemctl --global disable "${unit}" 2>/dev/null || true
done

# The installer is the only thing to do on this medium.
install -d /etc/skel/.config/autostart
cat > /etc/skel/.config/autostart/bunny-installer.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Install Bunny OS
Comment=Install Bunny OS on this Steam Deck
Exec=/usr/bin/liveinst
Icon=org.fedoraproject.AnacondaInstaller
Terminal=false
X-GNOME-Autostart-enabled=true
EOF

# --- 4. the payload image ----------------------------------------------------
# Anaconda installs this image out of local container storage, which is what
# makes the install work with no network connection.  The workflow saves it as
# an OCI archive so nothing has to be pulled here.
if [[ -f /ctx/bunny-deck.oci ]]; then
  podman load -i /ctx/bunny-deck.oci
fi

if ! podman image exists "${PAYLOAD_TAG}"; then
  # podman save/load keeps tags in newer versions only; retag by ID as a
  # fallback so the kickstart does not depend on the archive's metadata.
  image_id="$(podman images --format '{{.Id}}' | head -1)"
  test -n "${image_id}"
  podman tag "${image_id}" "${PAYLOAD_TAG}"
fi
podman image exists "${PAYLOAD_TAG}"
podman images

# --- 5. the kickstart --------------------------------------------------------
# No %post: the payload is a complete image, so Anaconda only has to deploy it.
cat >> /usr/share/anaconda/interactive-defaults.ks <<EOF

# --- Bunny OS ---------------------------------------------------------------
ostreecontainer --url=${PAYLOAD_TAG} --transport=containers-storage --no-signature-verification
EOF

# --- 6. the ISO contract -----------------------------------------------------
mkdir -p /usr/lib/bootc-image-builder
cat > /usr/lib/bootc-image-builder/iso.yaml <<EOF
label: "${ISO_LABEL}"
grub2:
  timeout: 5
  entries:
    - name: "Install Bunny OS on this Steam Deck"
      linux: "/images/pxeboot/vmlinuz quiet rhgb root=live:CDLABEL=${ISO_LABEL} enforcing=0 rd.live.image"
      initrd: "/images/pxeboot/initrd.img"
    - name: "Install Bunny OS (Basic Graphics Mode)"
      linux: "/images/pxeboot/vmlinuz quiet rhgb root=live:CDLABEL=${ISO_LABEL} enforcing=0 rd.live.image nomodeset"
      initrd: "/images/pxeboot/initrd.img"
EOF

# --- 7. sanity ---------------------------------------------------------------
test -f /usr/lib/bootc-image-builder/iso.yaml
test -f "/usr/lib/modules/${kernel}/initramfs.img"
test -d /boot/efi/EFI
test -f /etc/anaconda/profile.d/bunny.conf
test -f /etc/skel/.config/autostart/bunny-installer.desktop
grep -q 'root=live:CDLABEL' /usr/lib/bootc-image-builder/iso.yaml

dnf clean all
rm -rf /var/cache/dnf /var/cache/libdnf5
