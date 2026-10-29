#!/usr/bin/env bash
# =============================================================================
#  Bunny OS portable install - the Control Panel and the first-boot wizard on
#  a system that is already running (Bazzite, SteamOS in Desktop Mode, or any
#  other Linux with systemd, NetworkManager, python3 and a Chromium browser).
#
#  Nothing here touches the boot loader, the kernel, the desktop session or
#  the greeter.  Every file lands under the install prefix plus /etc and
#  /var, so removing the package returns the machine to exactly what it was.
#
#  Usage:
#    sudo ./install.sh                 # install for every user on this system
#    sudo ./install.sh --no-autostart  # do not open the wizard at login
#    sudo ./install.sh --destdir DIR   # packaging test: no systemctl, no /var
#    ./install.sh --dry-run            # print what would happen
# =============================================================================
set -Eeuo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
PREFIX="/usr/local"
DESTDIR=""
AUTOSTART=1
SERVICE=1
DRY_RUN=0

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while (( $# > 0 )); do
  case "$1" in
    --prefix) [[ $# -ge 2 ]] || { echo "--prefix needs a path" >&2; exit 2; }
              PREFIX="$2"; shift 2 ;;
    --destdir) [[ $# -ge 2 ]] || { echo "--destdir needs a path" >&2; exit 2; }
               DESTDIR="$2"; shift 2 ;;
    --no-autostart) AUTOSTART=0; shift ;;
    --no-service) SERVICE=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

PREFIX="${PREFIX%/}"
LIB="${PREFIX}/lib/bunny"
BIN="${PREFIX}/bin"
APPS="${PREFIX}/share/applications"
UNIT_DIR="/etc/systemd/system"
STATE_DIR="/var/lib/bunny"
ETC_DIR="/etc/bunny"
AUTOSTART_DIR="/etc/xdg/autostart"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '  ! %s\n' "$*" >&2; }
die()  { printf '  x %s\n' "$*" >&2; exit 1; }

run() {
  if (( DRY_RUN )); then
    printf '    [dry-run] %s\n' "$*"
    return 0
  fi
  "$@"
}

# Write a file from stdin, swallowing it during a dry run.
put() { # path
  if (( DRY_RUN )); then
    cat >/dev/null
    return 0
  fi
  cat > "$1"
}

[[ -f "${HERE}/VERSION" ]] || die "this script must run from the unpacked tarball"
VERSION="$(tr -d '[:space:]' < "${HERE}/VERSION")"
BUILD_ID="$(sed -n 's/.*"build_id": *"\([^"]*\)".*/\1/p' "${HERE}/build-manifest.json" 2>/dev/null | head -1)"
[[ -n "${BUILD_ID}" ]] || BUILD_ID="local"

step "Bunny OS ${VERSION} portable install"
info "payload  : ${HERE}"
info "prefix   : ${DESTDIR}${PREFIX}"
info "state    : ${DESTDIR}${STATE_DIR}"

if [[ -z "${DESTDIR}" && "${EUID}" -ne 0 ]]; then
  die "run this with sudo (it writes to ${PREFIX}, /etc and /var)"
fi

# --- 1. what are we installing onto? -----------------------------------------
OS_ID="unknown"
OS_NAME="this system"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_NAME="${PRETTY_NAME:-${NAME:-this system}}"
fi
info "host     : ${OS_NAME}"

if [[ -d /ostree/repo ]] || [[ -e /run/ostree-booted ]]; then
  info "layout   : immutable (rpm-ostree); ${PREFIX} is persistent here"
elif [[ -f /etc/steamos-release ]]; then
  info "layout   : SteamOS; Desktop Mode only, and ${PREFIX} needs the rootfs unlocked"
else
  info "layout   : writable root"
fi

command -v python3 >/dev/null 2>&1 \
  || die "python3 is required (Bazzite: rpm-ostree install python3; SteamOS: pacman -S python)"

BROWSER=""
for candidate in chromium chromium-browser google-chrome-stable google-chrome \
                 brave-browser microsoft-edge-stable; do
  if command -v "${candidate}" >/dev/null 2>&1; then BROWSER="${candidate}"; break; fi
done
if [[ -z "${BROWSER}" ]] && command -v flatpak >/dev/null 2>&1; then
  for app in org.chromium.Chromium com.google.Chrome com.brave.Browser; do
    if flatpak info "${app}" >/dev/null 2>&1; then BROWSER="flatpak ${app}"; break; fi
  done
fi
if [[ -z "${BROWSER}" ]]; then
  warn "no Chromium browser found. Install one of:"
  warn "  Bazzite : rpm-ostree install chromium   (or: flatpak install flathub org.chromium.Chromium)"
  warn "  SteamOS : sudo steamos-readonly disable && sudo pacman -S chromium"
else
  info "browser  : ${BROWSER}"
fi

# --- 2. files ----------------------------------------------------------------
step "Installing files"

run install -d -m 0755 "${DESTDIR}${BIN}" \
                          "${DESTDIR}${LIB}" \
                          "${DESTDIR}${PREFIX}/share/applications" \
                          "${DESTDIR}${ETC_DIR}" \
                          "${DESTDIR}${STATE_DIR}"

if (( DRY_RUN )); then
  info "[dry-run] copy bin/* -> ${BIN}"
  info "[dry-run] copy ui/   -> ${LIB}/ui"
else
  for file in "${HERE}"/bin/*; do
    install -Dm0755 "${file}" "${DESTDIR}${BIN}/$(basename "${file}")"
  done
  rm -rf "${DESTDIR}${LIB:?}/ui"
  mkdir -p "${DESTDIR}${LIB}/ui"
  cp -a "${HERE}/ui/." "${DESTDIR}${LIB}/ui/"
  find "${DESTDIR}${LIB}/ui" -type d -exec chmod 0755 {} +
  find "${DESTDIR}${LIB}/ui" -type f -exec chmod 0644 {} +
  if [[ -d "${HERE}/docs" ]]; then
    install -d -m 0755 "${DESTDIR}${PREFIX}/share/doc/bunny-os"
    for doc in "${HERE}"/docs/*.md; do
      [[ -e "${doc}" ]] || continue
      install -Dm0644 "${doc}" "${DESTDIR}${PREFIX}/share/doc/bunny-os/$(basename "${doc}")"
    done
  fi
fi
info "binaries : $(cd "${HERE}/bin" && ls | tr '\n' ' ')"

# Version metadata lives in /etc so the panel and the wizard report the build
# they were installed from, not the host's os-release.
put "${DESTDIR}${ETC_DIR}/build-info.json" <<EOF
{
  "product": "Bunny OS",
  "version": "${VERSION}",
  "channel": "portable",
  "build_id": "${BUILD_ID}",
  "target": "portable",
  "target_name": "Existing Linux system",
  "layout": "portable"
}
EOF
chmod 0644 "${DESTDIR}${ETC_DIR}/build-info.json" 2>/dev/null || true
info "metadata : ${ETC_DIR}/build-info.json"

# --- 3. the setup service ----------------------------------------------------
if (( SERVICE )); then
  step "Installing bunny-setupd.service"
  run install -d -m 0755 "${DESTDIR}${UNIT_DIR}"
  put "${DESTDIR}${UNIT_DIR}/bunny-setupd.service" <<EOF
[Unit]
Description=Bunny OS Setup Service (portable)
Documentation=file://${PREFIX}/share/doc/bunny-os/BAZZITE.md
After=NetworkManager.service local-fs.target
Wants=NetworkManager.service

[Service]
Type=simple
Environment=BUNNY_PANEL_UI=${LIB}/ui
# --portable: the host already owns the account, the greeter and the session,
# so this only configures the network and the time zone. It never restarts a
# display manager and never creates a user.
ExecStart=${BIN}/bunny-setupd --portable --port ${BUNNY_SETUP_PORT:-8430} --ui ${LIB}/ui
Restart=on-failure
RestartSec=2s
StateDirectory=bunny
StateDirectoryMode=0755
RuntimeDirectory=bunny
RuntimeDirectoryMode=0750

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=no
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
LockPersonality=yes
ReadWritePaths=/etc ${STATE_DIR} /var/log/bunny /run/bunny

[Install]
WantedBy=multi-user.target
EOF
  chmod 0644 "${DESTDIR}${UNIT_DIR}/bunny-setupd.service" 2>/dev/null || true
  if [[ -n "${BUNNY_INSTALL_IMAGE:-}" ]]; then
    # Image build (Bazzite/bootc): enable the unit, but there is no PID 1 to
    # start it and no reason to reload a daemon that is not running.
    run systemctl enable bunny-setupd.service
  elif [[ -z "${DESTDIR}" ]]; then
    run systemctl daemon-reload
    run systemctl enable --now bunny-setupd.service
  else
    info "[destdir] unit installed, systemctl not run"
  fi
else
  warn "skipping the setup service; run bunny-os-setup by hand for the wizard"
fi

# --- 4. menu entries ---------------------------------------------------------
step "Installing menu entries"
put "${DESTDIR}${APPS}/bunny-os.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bunny OS
GenericName=Control Panel
Comment=Controller-first panel for Bunny OS
Exec=${BIN}/bunny-os
Icon=${LIB}/ui/assets/bunny.svg
Terminal=false
Categories=Game;Settings;
Keywords=bunny;panel;controller;
EOF
put "${DESTDIR}${APPS}/bunny-os-setup.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bunny OS Setup
GenericName=First-boot wizard
Comment=Network, time zone and account setup for Bunny OS
Exec=${BIN}/bunny-os-setup
Icon=${LIB}/ui/assets/bunny.svg
Terminal=false
Categories=System;Settings;
NoDisplay=false
EOF
chmod 0644 "${DESTDIR}${APPS}/bunny-os.desktop" "${DESTDIR}${APPS}/bunny-os-setup.desktop" 2>/dev/null || true
info "apps     : bunny-os.desktop, bunny-os-setup.desktop"

if (( AUTOSTART )); then
  run install -d -m 0755 "${DESTDIR}${AUTOSTART_DIR}"
  put "${DESTDIR}${AUTOSTART_DIR}/bunny-os-setup.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Bunny OS Setup
Comment=Opens once, on the first login after install
Exec=${BIN}/bunny-os-setup
Icon=${LIB}/ui/assets/bunny.svg
Terminal=false
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
EOF
  chmod 0644 "${DESTDIR}${AUTOSTART_DIR}/bunny-os-setup.desktop" 2>/dev/null || true
  info "autostart: the wizard opens on the next login until it is finished"
fi

# --- 5. shims ----------------------------------------------------------------
# Bazzite's /usr/local is the one writable, update-proof place on the machine,
# but SteamOS only mounts it read-only until the rootfs is unlocked, so keep
# the hint visible instead of failing silently at launch time.
step "Checking reachability"
for tool in "${BIN}/bunny-panel" "${BIN}/bunny-os" "${LIB}/ui/index.html" "${LIB}/ui/setup/index.html"; do
  if [[ -e "${DESTDIR}${tool}" ]]; then info "ok       : ${tool}"; else warn "missing  : ${tool}"; fi
done

step "Done"
cat <<EOF
    Bunny OS ${VERSION} is installed.

    Start it        : bunny-os
    Run the wizard  : bunny-os-setup
    Setup service   : systemctl status bunny-setupd
    Remove it       : sudo ${HERE}/uninstall.sh

    The panel runs the host's browser in app mode. The wizard configures the
    network and the time zone, writes /var/lib/bunny/.oobe-done and leaves the
    host's account, greeter and session untouched.
EOF
