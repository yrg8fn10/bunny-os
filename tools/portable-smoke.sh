#!/usr/bin/env bash
# =============================================================================
#  Portable payload smoke test.
#
#  Builds the tarball that ships Bunny OS to a system that is already running
#  (Bazzite, SteamOS desktop), installs it into a throwaway root and checks the
#  layout, the units, the menu entries and that uninstall really removes it.
#
#  Runs on any host with bash + coreutils: no root, no systemd, no network.
#
#      bash tools/portable-smoke.sh
# =============================================================================
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd -P)"
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

pass=0
fail=0
check() { # expected actual label
  if [[ "$1" == "$2" ]]; then
    pass=$((pass + 1))
    printf '  ok   %s\n' "$3"
  else
    fail=$((fail + 1))
    printf '  FAIL %s (expected %s, got %s)\n' "$3" "$1" "$2"
  fi
}

printf '\n==> building the portable payload\n'
bash "${ROOT}/scripts/build-portable.sh" --out "${TMP}/out" >"${TMP}/build.log" 2>&1 \
  || { cat "${TMP}/build.log"; exit 1; }

archive="$(find "${TMP}/out" -maxdepth 1 -name 'bunny-os-portable-*.tar.gz' -print -quit)"
[[ -n "${archive}" ]] || { echo "no archive built" >&2; exit 1; }
check "yes" "$([[ -s "${archive}.sha256" ]] && echo yes || echo no)" "archive has a checksum"

tar -xzf "${archive}" -C "${TMP}"
payload="$(find "${TMP}" -maxdepth 1 -type d -name 'bunny-os-portable-*' -print -quit)"
[[ -n "${payload}" ]] || { echo "archive did not extract" >&2; exit 1; }

# The tarball must be self-contained: no tokens, no absolute paths from the host.
# The pattern is assembled at run time so this file never holds a literal token.
token_pattern="$(printf '@%s@\\|@%s@\\|@%s@' VERSION CHANNEL BUILD_ID)"
check "0" "$(grep -rIl "${token_pattern}" "${payload}" 2>/dev/null | wc -l | tr -d ' ')" \
  "payload has no unrendered tokens"

printf '\n==> installing into a throwaway root\n'
dest="${TMP}/root"
mkdir -p "${dest}" "${TMP}/stub"
# Record what the installer would ask systemd to do; never touch the host.
cat > "${TMP}/stub/systemctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "${SYSTEMCTL_LOG:?}"
exit 0
EOF
chmod 0755 "${TMP}/stub/systemctl"

log="${TMP}/systemctl.log"
: > "${log}"
PATH="${TMP}/stub:${PATH}" SYSTEMCTL_LOG="${log}" BUNNY_INSTALL_IMAGE=1 \
  "${payload}/install.sh" --destdir "${dest}" >"${TMP}/install.log" 2>&1 \
  || { cat "${TMP}/install.log"; exit 1; }

version="$(tr -d '[:space:]' < "${ROOT}/VERSION")"

for path in \
  "usr/local/bin/bunny-panel" \
  "usr/local/bin/bunny-panel-bridge" \
  "usr/local/bin/bunny-setupd" \
  "usr/local/bin/bunny-os" \
  "usr/local/bin/bunny-os-setup" \
  "usr/local/lib/bunny/ui/index.html" \
  "usr/local/lib/bunny/ui/setup/index.html" \
  "usr/local/lib/systemd/system/bunny-setupd.service" \
  "etc/bunny/build-info.json" \
  "usr/local/share/applications/bunny-os.desktop" \
  "usr/local/share/applications/bunny-os-setup.desktop" \
  "etc/xdg/autostart/bunny-os-setup.desktop" \
  "var/lib/bunny"; do
  check "yes" "$([[ -e "${dest}/${path}" ]] && echo yes || echo no)" "installed ${path}"
done

check "755" "$(stat -c '%a' "${dest}/usr/local/bin/bunny-setupd" 2>/dev/null || stat -f '%Lp' "${dest}/usr/local/bin/bunny-setupd" | sed 's/^0//')" \
  "setup service is executable"

unit="$(cat "${dest}/usr/local/lib/systemd/system/bunny-setupd.service")"
check "yes" "$(grep -q -- '--portable' <<<"${unit}" && echo yes || echo no)" \
  "unit runs the wizard in portable mode"
check "yes" "$(grep -q 'ExecStart=/usr/local/bin/bunny-setupd' <<<"${unit}" && echo yes || echo no)" \
  "unit points at the installed binary"
check "yes" "$(grep -q 'WantedBy=multi-user.target' <<<"${unit}" && echo yes || echo no)" \
  "unit is wanted by multi-user.target"
check "yes" "$(grep -q 'enable bunny-setupd.service' "${log}" && echo yes || echo no)" \
  "image builds enable the unit without starting it"
check "no" "$(grep -q -- '--now' "${log}" && echo yes || echo no)" \
  "image builds never try to start the unit"

check "yes" "$(grep -q '"version": "'"${version}"'"' "${dest}/etc/bunny/build-info.json" && echo yes || echo no)" \
  "build-info carries the release version"
check "yes" "$(grep -q 'Exec=/usr/local/bin/bunny-os$' "${dest}/usr/local/share/applications/bunny-os.desktop" && echo yes || echo no)" \
  "menu entry launches the installed wrapper"
check "yes" "$(grep -q 'Exec=/usr/local/bin/bunny-os-setup' "${dest}/etc/xdg/autostart/bunny-os-setup.desktop" && echo yes || echo no)" \
  "autostart runs the wizard wrapper"

printf '\n==> re-running the installer\n'
before="$(find "${dest}" -type f | wc -l | tr -d ' ')"
PATH="${TMP}/stub:${PATH}" SYSTEMCTL_LOG="${log}" \
  "${payload}/install.sh" --destdir "${dest}" --no-service >"${TMP}/install2.log" 2>&1 \
  || { cat "${TMP}/install2.log"; exit 1; }
after="$(find "${dest}" -type f | wc -l | tr -d ' ')"
check "${before}" "${after}" "installing twice leaves the same number of files"

printf '\n==> uninstalling\n'
"${payload}/uninstall.sh" --destdir "${dest}" >"${TMP}/uninstall.log" 2>&1 \
  || { cat "${TMP}/uninstall.log"; exit 1; }
check "no" "$([[ -e "${dest}/usr/local/bin/bunny-panel" ]] && echo yes || echo no)" \
  "uninstall removes the panel"
check "no" "$([[ -e "${dest}/usr/local/lib/bunny" ]] && echo yes || echo no)" \
  "uninstall removes the UI tree"
check "no" "$([[ -e "${dest}/usr/local/lib/systemd/system/bunny-setupd.service" ]] && echo yes || echo no)" \
  "uninstall removes the unit"
check "yes" "$([[ -e "${dest}/var/lib/bunny" ]] && echo yes || echo no)" \
  "uninstall keeps the setup marker by default"

printf '\n%s/%s portable checks passed\n\n' "${pass}" "$((pass + fail))"
[[ "${fail}" -eq 0 ]]
