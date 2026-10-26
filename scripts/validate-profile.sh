#!/usr/bin/env bash
# Static validation of the Bunny OS archiso profile.
# Runs without root; safe on any Linux/macOS host with bash + coreutils.
#
# Usage: validate-profile.sh [--stage DIR] [--strict]
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

STAGE="${ROOT}/build/profile"
STRICT=0
while (( $# > 0 )); do
  case "$1" in
    --stage)
      [[ $# -ge 2 ]] || die "--stage needs a directory"
      STAGE="$2"
      shift 2
      ;;
    --strict) STRICT=1; shift ;;
    --help|-h) echo "usage: validate-profile.sh [--stage DIR] [--strict]"; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

# Relative stage paths are resolved against the current directory.
[[ "${STAGE}" == /* ]] || STAGE="$(pwd -P)/${STAGE}"

banner
log_step "Validating Bunny OS profile"

# ---------------------------------------------------------------------------
log_info "required files"
REQUIRED=(
  "VERSION"
  "build_bunny_os_iso.sh"
  "iso/profiledef.sh"
  "iso/packages.x86_64"
  "iso/pacman.conf"
  "iso/airootfs/root/customize_airootfs.sh"
  "iso/airootfs/etc/os-release"
  "iso/airootfs/etc/bunny/settings.json"
  "iso/airootfs/etc/sddm.conf.d/10-bunny.conf"
  "iso/airootfs/etc/sddm.conf.d/20-bunny-session.conf"
  "system/bin/bunny-session"
  "system/bin/bunny-panel"
  "system/bin/bunny-panel-bridge"
  "system/bin/bunnyctl"
  "system/lib/bunny_sessiond.py"
  "system/lib/bunny_input_agent.py"
  "system/units/bunny-sessiond.service"
  "system/units/bunny-firstboot.service"
  "system/user-units/bunny-bunbun.service"
  "system/wayland-sessions/bunny-gaming.desktop"
  "bunbun/bunbun/service.py"
  "bunbun/bunbun/mam/policy.py"
  "bunbun/bunbun/mam/engine.py"
  "bunbun/bunbun/data/persona.json"
  "bunbun/bunbun/data/hints/generic.json"
  "control-panel/ui/index.html"
  "control-panel/src-tauri/tauri.conf.json"
  "control-panel/src-tauri/Cargo.toml"
  "launchers/bin/bunny-launcher"
  "launchers/bin/bunny-platform-scan"
  "installer/bunny-install"
  "iso/targets/deck/target.conf"
  "iso/targets/deck/packages.x86_64"
  "iso/targets/deck/overlay/efiboot/loader/entries/01-bunny-os.conf"
  "iso/targets/deck/airootfs/etc/systemd/zram-generator.conf"
  "docs/ARCHITECTURE.md"
  "docs/BUILD.md"
  "docs/BUNBUN.md"
  "docs/SAFETY-AND-LEGAL.md"
  "docs/STEAMDECK.md"
)
for rel in "${REQUIRED[@]}"; do
  if [[ -e "${ROOT}/${rel}" ]]; then
    printf '  %s✓%s %s\n' "${C_MINT}" "${C_RESET}" "${rel}"
  else
    check_fail "missing ${rel}"
  fi
done

# ---------------------------------------------------------------------------
log_info "shell syntax"
while IFS= read -r -d '' f; do
  if bash -n "${f}" 2>/dev/null; then
    log_debug "ok ${f#"${ROOT}"/}"
  else
    check_fail "bash -n ${f#"${ROOT}"/}"
  fi
done < <(find "${ROOT}" -path "${ROOT}/build" -prune -o -type f \
  \( -name '*.sh' -o -name 'bunny-session' -o -name 'bunny-panel' -o -name 'bunny-launcher' \
     -o -name 'bunny-platform-scan' -o -name 'bunny-install' \) -print0)
if (( FAILED_CHECKS == 0 )); then
  printf '  %s✓%s all shell scripts parse\n' "${C_MINT}" "${C_RESET}"
fi

# ---------------------------------------------------------------------------
log_info "JSON payloads"
if have python3; then
  while IFS= read -r -d '' f; do
    python3 -m json.tool "${f}" >/dev/null 2>&1 \
      || check_fail "invalid JSON: ${f#"${ROOT}"/}"
  done < <(find "${ROOT}" -path "${ROOT}/build" -prune -o \
    -path '*/node_modules' -prune -o -path '*/target' -prune -o \
    -type f -name '*.json' -print0)
  printf '  %s✓%s JSON validated\n' "${C_MINT}" "${C_RESET}"
else
  log_warn "python3 not found — skipping JSON and Python validation"
fi

# ---------------------------------------------------------------------------
log_info "python sources"
if have python3; then
  if (cd "${ROOT}/bunbun" && python3 -m compileall -q bunbun >/dev/null 2>&1); then
    printf '  %s✓%s bunbun compiles\n' "${C_MINT}" "${C_RESET}"
  else
    check_fail "bunbun failed to compile"
  fi
  for lib in system/lib/*.py; do
    python3 -m py_compile "${lib}" 2>/dev/null \
      || check_fail "py_compile ${lib#"${ROOT}"/}"
  done
  find "${ROOT}/bunbun" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "${ROOT}/system" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
fi

# ---------------------------------------------------------------------------
log_info "systemd units"
while IFS= read -r -d '' unit; do
  name="${unit#"${ROOT}"/}"
  grep -q '^\[Unit\]' "${unit}" || check_fail "${name}: no [Unit] section"
  if [[ "${unit}" == *.service ]]; then
    grep -q '^\[Service\]' "${unit}" || check_fail "${name}: no [Service] section"
    grep -qE '^(ExecStart|Type=oneshot)' "${unit}" || check_fail "${name}: no ExecStart"
    while IFS= read -r exec_line; do
      bin="${exec_line#ExecStart=}"
      bin="${bin#-}"
      bin="${bin%% *}"
      bin="${bin#@}"
      [[ "${bin}" == /* ]] || continue
      if [[ ! -e "${ROOT}/system/bin/$(basename "${bin}")" && ! -e "${bin}" ]]; then
        # Allowed: binaries provided by packages or staged elsewhere.
        case "${bin}" in
          /usr/bin/*|/usr/local/bin/*|/opt/*) log_debug "unit ${name} references packaged ${bin}" ;;
          *) check_fail "${name}: unresolved ExecStart ${bin}" ;;
        esac
      fi
    done < <(grep -E '^ExecStart=' "${unit}" || true)
  fi
done < <(find "${ROOT}/system/units" "${ROOT}/iso/airootfs/etc/systemd/system" -type f -name '*.service' -print0 2>/dev/null)
printf '  %s✓%s unit files inspected\n' "${C_MINT}" "${C_RESET}"

# ---------------------------------------------------------------------------
log_info "desktop entries"
while IFS= read -r -d '' de; do
  name="${de#"${ROOT}"/}"
  grep -q '^\[Desktop Entry\]' "${de}" || check_fail "${name}: missing [Desktop Entry]"
  grep -q '^Name=' "${de}"          || check_fail "${name}: missing Name="
  grep -q '^Type=' "${de}"          || check_fail "${name}: missing Type="
  grep -q '^Exec=' "${de}"          || check_fail "${name}: missing Exec="
done < <(find "${ROOT}/launchers/applications" "${ROOT}/system/wayland-sessions" \
  "${ROOT}/installer/applications" -type f -name '*.desktop' -print0 2>/dev/null)
printf '  %s✓%s desktop entries inspected\n' "${C_MINT}" "${C_RESET}"

# ---------------------------------------------------------------------------
log_info "package lists"
PKG_FILES=("${ROOT}/iso/packages.x86_64")
while IFS= read -r -d '' f; do
  PKG_FILES+=("${f}")
done < <(find "${ROOT}/iso/targets" -mindepth 2 -maxdepth 2 -name packages.x86_64 -print0 2>/dev/null)
for PKG_FILE in "${PKG_FILES[@]}"; do
  [[ -f "${PKG_FILE}" ]] || continue
  rel="${PKG_FILE#"${ROOT}"/}"
  # archiso cannot resolve AUR packages. These must never appear here.
  FORBIDDEN=(google-chrome spotify heroic-games-launcher heroic-games-launcher-bin
             visual-studio-code-bin yay paru debtap steamdeck-dkms)
  for bad in "${FORBIDDEN[@]}"; do
    if grep -qxF "${bad}" "${PKG_FILE}"; then
      check_fail "${rel}: '${bad}' is AUR-only; use Flatpak or an official package"
    fi
  done
  while IFS= read -r pkg; do
    pkg="${pkg%%#*}"
    pkg="${pkg//[[:space:]]/}"
    [[ -z "${pkg}" ]] && continue
    [[ "${pkg}" =~ ^[a-z0-9@._+-]+$ ]] || check_fail "${rel}: suspicious entry '${pkg}'"
  done < "${PKG_FILE}"
  count="$(grep -vcE '^\s*(#|$)' "${PKG_FILE}")"
  printf '  %s✓%s %s: %s explicit packages\n' "${C_MINT}" "${C_RESET}" "${rel}" "${count}"
done

# ---------------------------------------------------------------------------
log_info "build targets"
TARGET_COUNT=0
while IFS= read -r -d '' tc; do
  tdir="$(dirname "${tc}")"
  tname="$(basename "${tdir}")"
  TARGET_COUNT=$(( TARGET_COUNT + 1 ))
  grep -q "^BUNNY_TARGET_ID=\"${tname}\"" "${tc}" \
    || check_fail "target ${tname}: BUNNY_TARGET_ID does not match directory"
  for key in BUNNY_TARGET_NAME BUNNY_ISO_BASENAME BUNNY_GAMESCOPE_ARGS BUNNY_KERNEL_ARGS; do
    grep -q "^${key}=" "${tc}" || check_fail "target ${tname}: missing ${key}"
  done
  [[ -f "${tdir}/packages.x86_64" ]] \
    || check_fail "target ${tname}: missing packages.x86_64"
done < <(find "${ROOT}/iso/targets" -mindepth 2 -maxdepth 2 -name target.conf -print0 2>/dev/null)
if (( TARGET_COUNT > 0 )); then
  printf '  %s✓%s %s target profile(s)\n' "${C_MINT}" "${C_RESET}" "${TARGET_COUNT}"
else
  check_fail "no target profiles in iso/targets"
fi

DECK_CONF="${ROOT}/iso/targets/deck/target.conf"
if [[ -f "${DECK_CONF}" ]]; then
  grep -q 'BUNNY_GAMESCOPE_ARGS=.*1280 -H 800' "${DECK_CONF}" \
    || check_fail "deck target: gamescope is not 1280x800 (LCD native)"
  grep -q 'amd_pstate=active' "${DECK_CONF}" \
    || check_fail "deck target: amd_pstate=active missing"
  grep -qx 'fwupd' "${ROOT}/iso/targets/deck/packages.x86_64" \
    || check_fail "deck target: fwupd missing"
fi

# ---------------------------------------------------------------------------
log_info "line endings & secrets"
while IFS= read -r -d '' f; do
  if grep -qU $'\r' "${f}" 2>/dev/null; then
    check_fail "CRLF line endings: ${f#"${ROOT}"/}"
  fi
done < <(find "${ROOT}" -path "${ROOT}/build" -prune -o -path '*/node_modules' -prune -o \
  -type f \( -name '*.sh' -o -name '*.py' -o -name '*.service' -o -name '*.desktop' \
  -o -name '*.conf' -o -name '*.json' -o -name '*.md' \) -print0)
printf '  %s✓%s no CRLF in scripts\n' "${C_MINT}" "${C_RESET}"

if grep -rInE '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})' \
    "${ROOT}" --exclude-dir=build --exclude-dir=node_modules --exclude-dir=.git >/dev/null 2>&1; then
  check_fail "possible committed API key"
else
  printf '  %s✓%s no obvious secrets\n' "${C_MINT}" "${C_RESET}"
fi

# ---------------------------------------------------------------------------
if [[ -d "${STAGE}" ]]; then
  log_info "staged tree"
  for rel in usr/local/bin/bunny-session \
             usr/local/bin/bunny-panel \
             usr/local/bin/bunny-launcher \
             usr/local/bin/bunny-install \
             usr/local/lib/bunny/bunny_sessiond.py \
             etc/systemd/system/bunny-sessiond.service \
             opt/bunbun/bunbun/service.py \
             opt/bunny/panel/ui/index.html \
             usr/share/wayland-sessions/bunny-gaming.desktop \
             etc/bunny/target \
             etc/bunny/build-info.json; do
    [[ -e "${STAGE}/airootfs/${rel}" ]] \
      && log_debug "staged ${rel}" \
      || check_fail "staged tree missing ${rel}"
  done
  STAGED_TARGET="$(cat "${STAGE}/airootfs/etc/bunny/target" 2>/dev/null || true)"
  if [[ "${STAGED_TARGET}" == "deck" ]]; then
    [[ -f "${STAGE}/airootfs/etc/bunny/target.conf" ]] \
      || check_fail "staged deck tree missing etc/bunny/target.conf"
    grep -q 'BUNNY_GAMESCOPE_ARGS=.*1280 -H 800' \
      "${STAGE}/airootfs/etc/bunny/target.conf" 2>/dev/null \
      || check_fail "staged deck tree: gamescope not 1280x800"
    [[ -f "${STAGE}/airootfs/etc/systemd/zram-generator.conf" ]] \
      || check_fail "staged deck tree missing zram-generator.conf"
  fi
  printf '  %s✓%s staged tree verified\n' "${C_MINT}" "${C_RESET}"
elif (( STRICT )); then
  check_fail "no staged profile at ${STAGE} (run with --stage or build first)"
fi

echo
check_summary
