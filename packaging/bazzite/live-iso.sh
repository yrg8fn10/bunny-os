#!/usr/bin/env bash
# =============================================================================
#  Turn the Bunny OS Deck image into a live installer image.
#
#  Titanoboa wraps a bootc image into a bootable ISO.  For that the image needs
#  three things it does not ship as a normal desktop image:
#
#    1. a live root (dracut-live + the livesys scripts), because the ISO boots
#       the image itself, not a separate rescue environment;
#    2. Anaconda with a default kickstart that installs *this* image from the
#       container storage titanoboa embeds in the ISO, so the install works
#       with no network;
#    3. /usr/lib/bootc-image-builder/iso.yaml, which tells image-builder how to
#       label the ISO and what the GRUB entries look like.
#
#  The recipe mirrors ublue's own installer payload (ublue-os/bazzite
#  installer/build.sh and titanoboa_hook_postrootfs.sh) without vendoring their
#  whole tree: everything here is package installs plus systemd enable calls.
# =============================================================================
set -euxo pipefail

VARIANT_ID="${VARIANT_ID:-bunny-deck}"
IMAGE_REF="${IMAGE_REF:-localhost/bunny-deck:latest}"
ISO_LABEL="${ISO_LABEL:-BunnyOS-Live}"

# Bazzite pins versions for its desktop; Anaconda drags in new ones and the
# versionlocks make dnf fail with an unreadable dependency error.
dnf -qy versionlock clear || true

# --- 1. live root ------------------------------------------------------------
dnf install -y --setopt=install_weak_deps=False \
    dracut-live livesys-scripts grub2-efi-x64-cdboot

kernel="$(kernel-install list --json pretty | jq -r '.[] | select(.has_kernel == true) | .version' | head -1)"
test -n "${kernel}"

# shellcheck disable=SC2086
DRACUT_NO_XATTR=1 dracut -v --force --zstd --reproducible --no-hostonly \
    --add "dmsquash-live dmsquash-live-autooverlay" \
    "/usr/lib/modules/${kernel}/initramfs.img" "${kernel}"

# The Deck has no keyboard at the greeter: livesys starts the live session.
sed -i "s/^livesys_session=.*/livesys_session=kde/" /etc/sysconfig/livesys
systemctl enable livesys.service livesys-late.service

# image-builder looks for the EFI tree under /boot/efi.
mkdir -p /boot/efi
cp -av /usr/lib/efi/*/*/EFI /boot/efi/

# ostree wants room for temporary files; /run is a small tmpfs on a live boot.
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

# --- 2. Anaconda -------------------------------------------------------------
dnf install -y --setopt=install_weak_deps=False --allowerasing \
    anaconda-live libblockdev-btrfs libblockdev-lvm libblockdev-dm

mkdir -p /var/lib/rpm-state

# The default kickstart installs the very image the ISO was built from.  The
# transport is containers-storage because titanoboa embeds the payload there,
# which is what makes the install work without a network connection.
cat >> /usr/share/anaconda/interactive-defaults.ks <<EOF

# --- Bunny OS ---------------------------------------------------------------
%pre-install --erroronfail
rm -rf /mnt/sysroot/boot/efi/EFI/fedora
%end

ostreecontainer --url=${IMAGE_REF} --transport=containers-storage --no-signature-verification

%include /usr/share/anaconda/post-scripts/restore-selinux-labels.ks
%include /usr/share/anaconda/post-scripts/disable-fedora-flatpak.ks
EOF

printf 'Bunny OS live image (${VARIANT_ID})\n' > /etc/system-release

# Services that make no sense in a live session (they would fight the installer
# or try to reach the network).
for unit in rpm-ostreed-automatic.timer uupd.timer bazzite-flatpak-manager.service \
            ublue-flatpak-manager.service flatpak-add-fedora-repos.service \
            bootloader-update.service bazzite-hardware-setup.service \
            ublue-hardware-setup.service greenboot-healthcheck.service \
            greenboot-set-rollback-trigger.service check-sb-key.service; do
  systemctl disable "${unit}" 2>/dev/null || true
done

# A live session must not start Steam over the installer.
rm -f /etc/skel/.config/autostart/steam*.desktop || true
rm -f /usr/share/applications/bazzite-steam*.desktop || true

# --- 3. ISO contract ---------------------------------------------------------
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

dnf clean all
rm -rf /var/cache/dnf /var/cache/libdnf5
