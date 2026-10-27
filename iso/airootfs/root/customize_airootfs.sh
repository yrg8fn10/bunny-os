#!/usr/bin/env bash
# =============================================================================
#  archiso airootfs customisation — runs inside the chroot as root.
#  Keep this idempotent: it is re-run on every image build.
# =============================================================================
set -euo pipefail

echo ":: Bunny OS airootfs customisation"

export LANG=en_US.UTF-8
locale-gen 2>/dev/null || true

# --- live user --------------------------------------------------------------
if ! id -u bunny >/dev/null 2>&1; then
  useradd -m -c "Bunny OS" \
    -G wheel,input,video,audio,render,storage,power,lp \
    -s /bin/bash bunny
fi
# Live-only credentials. The installer forces a new password.
echo 'bunny:bunny' | chpasswd
chown -R bunny:bunny /home/bunny

# --- first-boot bootstrap account -------------------------------------------
# The wizard runs as an unprivileged kiosk account. Its password is locked, so
# it can only be entered through SDDM autologin; it is removed (or locked) once
# the user creates their real account. `setup` is reserved by bunny-setupd.
if ! id -u setup >/dev/null 2>&1; then
  useradd -m -c "Bunny OS Setup" \
    -G input,video,audio,render,storage,power,lp \
    -s /bin/bash setup
fi
passwd -l setup >/dev/null 2>&1 || true
chown -R setup:setup /home/setup
printf 'setup\n' > /etc/bunny/oobe-bootstrap
chmod 0644 /etc/bunny/oobe-bootstrap

# --- permissions ------------------------------------------------------------
chmod 0755 /usr/local/bin/* 2>/dev/null || true
chmod 0755 /opt/bunbun/bin/bunbun-cli 2>/dev/null || true
chmod 0700 /root
chmod 0440 /etc/sudoers.d/10-bunny-live
chmod 0644 /etc/bunny/settings.json /etc/bunny/session.conf
chmod 0644 /etc/sddm.conf.d/10-bunny.conf /etc/sddm.conf.d/20-bunny-session.conf 2>/dev/null || true
chmod 0755 /root/customize_airootfs.sh

# --- session units ----------------------------------------------------------
systemctl enable sddm.service
systemctl set-default graphical.target

# bunny-sessiond owns mode switching (root, unix socket, peer-cred checked)
systemctl enable bunny-sessiond.service
# first boot: flatpaks, zram, sysctl tuning, per-user defaults
systemctl enable bunny-firstboot.service
# graphical first-boot wizard (loopback API + kiosk UI). The text account
# prompt is only a recovery/headless fallback now, never an automatic path.
systemctl enable bunny-setupd.service
systemctl disable bunny-setup.service 2>/dev/null || true
# console menu, only reachable from the "Recovery & Maintenance" boot entry
systemctl enable bunny-recovery.service
systemctl enable bunny-update.timer
systemctl enable bunny-health.timer
# hardware / desktop services
systemctl enable NetworkManager.service
systemctl enable bluetooth.service
systemctl enable power-profiles-daemon.service
systemctl enable fstrim.timer
systemctl enable systemd-timesyncd.service
systemctl enable systemd-resolved.service 2>/dev/null || true

# Bun Bun runs as the desktop user, not as root.
systemctl --global enable bunny-bunbun.service 2>/dev/null || true

# Input injection is opt-in and stays masked until the user enables it.
systemctl mask bunny-input-agent.service 2>/dev/null || true

# --- target-specific services -----------------------------------------------
# stage-profile.sh writes /etc/bunny/target (generic|deck|...). Keep these
# conditional so the generic image stays lean.
STAGED_TARGET="$(cat /etc/bunny/target 2>/dev/null || echo generic)"
if [[ "${STAGED_TARGET}" == "deck" ]]; then
  chmod 0644 /etc/bunny/target.conf 2>/dev/null || true
  # Refresh LVFS metadata for devices stock fwupd supports. Deck BIOS/EC
  # updates are delivered through SteamOS, not through this path.
  systemctl enable fwupd-refresh.timer 2>/dev/null || true
fi

# --- live environment niceties ---------------------------------------------
# Autologin straight to the Control Panel, but keep a TTY for recovery.
mkdir -p /etc/systemd/system/getty@tty2.service.d
cat > /etc/systemd/system/getty@tty2.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin bunny --noclear %I $TERM
EOF

# Marker unit for "we are running from the ISO, not an installed system".
mkdir -p /etc/systemd/system
cat > /etc/systemd/system/bunny-live.target <<'EOF'
[Unit]
Description=Bunny OS live session marker

[Install]
WantedBy=multi-user.target
EOF
systemctl enable bunny-live.target

# The live image ships bunny/bunny, so the account provisioner must not run
# here. The installer writes this same marker once it has created the real user;
# without it, a boot with no human account would land on an unanswerable greeter.
install -d -m 0755 /var/lib/bunny
date -u +%FT%TZ > /var/lib/bunny/.account-ready
chmod 0644 /var/lib/bunny/.account-ready

# The live image boots straight to Gaming Mode as the throwaway bunny user.
# The wizard only runs on an installed system, or when the live medium is
# explicitly booted with bunny.oobe=1 to preview it. The installer deletes this
# marker from the target so the first real boot autologins the setup account.
date -u +%FT%TZ > /var/lib/bunny/.oobe-done
chmod 0644 /var/lib/bunny/.oobe-done

# A handheld is offline more often than not. Anything that waits for a default
# route turns a 20 second boot into a two minute one, so the wait-online helpers
# are masked. Services still order after network.target; they simply do not
# block on a link that may never appear.
systemctl mask NetworkManager-wait-online.service systemd-networkd-wait-online.service 2>/dev/null || true

# --- never let a text prompt own first boot ---------------------------------
# If systemd-firstboot runs, it takes tty1 before SDDM, asks for a time zone on
# the console and leaves a prompt with no getty behind it when it exits: the
# screen looks frozen and no key press is delivered. Every value it would ask
# for is pinned in this image (hostname, locale, keymap, machine-id) and the
# time zone is set below, so mask the unit and let the wizard/SDDM own the VT.
systemctl mask systemd-firstboot.service 2>/dev/null || true
ln -sf /usr/share/zoneinfo/UTC /etc/localtime

# A machine-id is generated by archiso; make sure it exists for dbus.
systemd-machine-id-setup 2>/dev/null || true

# Clean pacman caches left by the build.
pacman -cc 2>/dev/null || true
rm -rf /var/cache/pacman/pkg/* 2>/dev/null || true
rm -f /etc/pacman.d/gnupg/*.lock 2>/dev/null || true

echo ":: Bunny OS airootfs ready"
