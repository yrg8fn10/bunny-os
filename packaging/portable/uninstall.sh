#!/usr/bin/env bash
# =============================================================================
#  Bunny OS portable uninstall.
#
#  Removes the binaries, the UI, the setup service and the menu entries written
#  by install.sh.  /var/lib/bunny (the "setup finished" marker and the audit
#  log) and /etc/bunny are kept unless --purge is given, so reinstalling keeps
#  the wizard already completed.
#
#    sudo ./uninstall.sh [--prefix /usr/local] [--destdir DIR] [--purge]
# =============================================================================
set -Eeuo pipefail

PREFIX="/usr/local"
DESTDIR=""
PURGE=0

while (( $# > 0 )); do
  case "$1" in
    --prefix) [[ $# -ge 2 ]] || { echo "--prefix needs a path" >&2; exit 2; }
              PREFIX="$2"; shift 2 ;;
    --destdir) [[ $# -ge 2 ]] || { echo "--destdir needs a path" >&2; exit 2; }
               DESTDIR="$2"; shift 2 ;;
    --purge) PURGE=1; shift ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

PREFIX="${PREFIX%/}"
LIB="${PREFIX}/lib/bunny"
BIN="${PREFIX}/bin"
APPS="${PREFIX}/share/applications"
DOCS="${PREFIX}/share/doc/bunny-os"

if [[ -z "${DESTDIR}" && "${EUID}" -ne 0 ]]; then
  echo "run this with sudo" >&2
  exit 1
fi

if [[ -z "${DESTDIR}" ]] && systemctl list-unit-files bunny-setupd.service >/dev/null 2>&1; then
  systemctl disable --now bunny-setupd.service 2>/dev/null || true
fi

for file in "${DESTDIR}${BIN}/bunny-panel" \
            "${DESTDIR}${BIN}/bunny-panel-bridge" \
            "${DESTDIR}${BIN}/bunny-setupd" \
            "${DESTDIR}${BIN}/bunny-os" \
            "${DESTDIR}${BIN}/bunny-os-setup" \
            "${DESTDIR}/etc/systemd/system/bunny-setupd.service" \
            "${DESTDIR}${APPS}/bunny-os.desktop" \
            "${DESTDIR}${APPS}/bunny-os-setup.desktop" \
            "${DESTDIR}/etc/xdg/autostart/bunny-os-setup.desktop" \
            "${DESTDIR}${DOCS}/BAZZITE.md"; do
  [[ -e "${file}" ]] || continue
  rm -f "${file}"
  echo "  removed ${file#${DESTDIR}}"
done

rm -rf "${DESTDIR}${LIB}"
echo "  removed ${LIB}"

if (( PURGE )); then
  rm -rf "${DESTDIR}/var/lib/bunny" "${DESTDIR}/etc/bunny"
  echo "  purged /var/lib/bunny and /etc/bunny"
else
  echo "  kept /var/lib/bunny (setup stays complete); use --purge to remove it"
fi

if [[ -z "${DESTDIR}" ]]; then
  systemctl daemon-reload 2>/dev/null || true
fi

echo "Bunny OS removed from ${DESTDIR}${PREFIX}."
