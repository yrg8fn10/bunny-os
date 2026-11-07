#!/usr/bin/env bash
# Installs the Fedora live-install launcher files. The "Install Bunny OS"
# button runs /usr/bin/liveinst, which the live session needs along with its
# polkit rule and setup helper.
# - ISO build: the files sit beside this script, installed from the repo.
# - Booted live session: run with sudo; missing files are fetched from the repo.
set -euo pipefail
RAW="https://raw.githubusercontent.com/yrg8fn10/bunny-os/main/packaging/bazzite/liveinstaller"
files=(liveinst liveinst-setup.sh locale1-x11-sync locale1-x11-sync.service \
       org.fedoraproject.pkexec.liveinst.policy liveinst-setup.desktop liveinst.desktop)
here="$(dirname "$(readlink -f "${BASH_SOURCE[0]:-/dev/stdin}")" 2>/dev/null || echo /nonexistent)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
for f in "${files[@]}"; do
  if [ -f "$here/$f" ]; then cp "$here/$f" "$tmp/$f"
  else curl -fsSL "$RAW/$f" -o "$tmp/$f"; fi
done
install -m 0755 "$tmp/liveinst" /usr/bin/liveinst
install -m 0755 "$tmp/liveinst-setup.sh" /usr/libexec/liveinst-setup.sh
install -m 0755 "$tmp/locale1-x11-sync" /usr/libexec/locale1-x11-sync
install -m 0644 "$tmp/locale1-x11-sync.service" /usr/lib/systemd/user/locale1-x11-sync.service
install -m 0644 "$tmp/org.fedoraproject.pkexec.liveinst.policy" /usr/share/polkit-1/actions/org.fedoraproject.pkexec.liveinst.policy
install -m 0644 "$tmp/liveinst-setup.desktop" /etc/xdg/autostart/liveinst-setup.desktop
install -m 0644 "$tmp/liveinst.desktop" /usr/share/applications/liveinst.desktop
test -x /usr/bin/liveinst
echo "installer launcher ready: /usr/bin/liveinst"
