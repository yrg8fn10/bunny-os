#!/usr/bin/env bash
# Stage the archiso profile: copy iso/, overlay system payloads, render tokens.
# Usage: stage-profile.sh <repo-root> <stage-dir> [--target NAME] [--allow-non-arch]
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

ROOT=""
STAGE=""
TARGET=""
while (( $# > 0 )); do
  case "$1" in
    --target)
      [[ $# -ge 2 ]] || die "--target needs a profile name"
      TARGET="$2"
      shift 2
      ;;
    --allow-non-arch) shift ;;   # accepted for compatibility; staging is host-neutral
    -*) die "unknown argument: $1" ;;
    *)
      if [[ -z "${ROOT}" ]]; then
        ROOT="$1"
      elif [[ -z "${STAGE}" ]]; then
        STAGE="$1"
      else
        die "unexpected argument: $1"
      fi
      shift
      ;;
  esac
done

[[ -n "${ROOT}" && -n "${STAGE}" ]] \
  || die "usage: stage-profile.sh <repo-root> <stage-dir> [--target NAME]"

[[ -d "${ROOT}/iso" ]] || die "no iso/ directory under ${ROOT}"
[[ -n "${STAGE}" ]] || die "empty stage dir"

VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
BUILD_ID="${BUILD_ID:-$(stamp_short)}"
BUILD_DATE="$(timestamp)"
CHANNEL="${BUNNY_CHANNEL:-dev}"

TARGET_DIR=""
if [[ -n "${TARGET}" ]]; then
  [[ "${TARGET}" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid target name '${TARGET}'"
  TARGET_DIR="${ROOT}/iso/targets/${TARGET}"
  [[ -d "${TARGET_DIR}" ]] || die "unknown target '${TARGET}' (no iso/targets/${TARGET})"
  [[ -f "${TARGET_DIR}/target.conf" ]] || die "target '${TARGET}' has no target.conf"
  # shellcheck disable=SC1090,SC1091
  source "${TARGET_DIR}/target.conf"
  [[ "${BUNNY_TARGET_ID:-}" == "${TARGET}" ]] \
    || die "iso/targets/${TARGET}/target.conf: BUNNY_TARGET_ID='${BUNNY_TARGET_ID:-}' does not match directory"
fi

log_step "Staging archiso profile"
log_info "version ${VERSION} · build ${BUILD_ID} · channel ${CHANNEL}"
if [[ -n "${TARGET}" ]]; then
  log_info "target ${TARGET} · ${BUNNY_TARGET_NAME:-unnamed}"
fi

safe_rmrf "${STAGE}"
mkdir -p "${STAGE}"

# 1. Profile skeleton --------------------------------------------------------
cp -a "${ROOT}/iso/." "${STAGE}/"
rm -rf "${STAGE}/overrides"   # build-time only, never shipped in the image

AIR="${STAGE}/airootfs"
mkdir -p "${AIR}/usr/local/bin" \
         "${AIR}/usr/local/lib/bunny" \
         "${AIR}/etc/systemd/system" \
         "${AIR}/etc/systemd/user" \
         "${AIR}/usr/share/wayland-sessions" \
         "${AIR}/usr/share/applications" \
         "${AIR}/opt/bunny/panel" \
         "${AIR}/opt/bunbun" \
         "${AIR}/etc/bunny"

# 2. Boot loader seed --------------------------------------------------------
# archiso needs efiboot/ and syslinux/ trees. Seed them from the packaged
# releng profile, then apply Bunny OS branding on top.
SEED="$(releng_profile || true)"
for dir in efiboot syslinux grub; do
  if [[ ! -d "${STAGE}/${dir}" && -d "${ROOT}/iso/overrides/${dir}" ]]; then
    mkdir -p "${STAGE}/${dir}"
  fi
done

if [[ -n "${SEED}" ]]; then
  for dir in efiboot syslinux; do
    if [[ ! -d "${STAGE}/${dir}" ]]; then
      log_debug "seeding ${dir}/ from ${SEED}"
      cp -a "${SEED}/${dir}" "${STAGE}/${dir}"
    fi
  done
else
  log_warn "archiso releng profile not found; boot trees must exist in iso/"
fi

if [[ -d "${ROOT}/iso/overrides" ]]; then
  log_debug "applying boot branding overrides"
  cp -a "${ROOT}/iso/overrides/." "${STAGE}/"
fi

# 2b. Target stage overlay ---------------------------------------------------
# A target may replace boot entries (kernel args, menu titles) and add packages.
# The overlay is applied after the base overrides so the more specific target
# wins. Packages are appended; duplicates are dropped so base/target can both
# list e.g. zram-generator without breaking the build.
if [[ -n "${TARGET_DIR}" ]]; then
  if [[ -d "${TARGET_DIR}/overlay" ]]; then
    log_debug "applying ${TARGET} stage overlay"
    cp -a "${TARGET_DIR}/overlay/." "${STAGE}/"
  fi
  if [[ -f "${TARGET_DIR}/packages.x86_64" ]]; then
    log_debug "merging ${TARGET} packages"
    {
      printf '\n# --- target: %s (%s) ------------------------------------------\n' \
        "${TARGET}" "${BUNNY_TARGET_NAME:-unnamed}"
      while IFS= read -r pkg || [[ -n "${pkg}" ]]; do
        pkg="$(printf '%s' "${pkg}" | tr -d '[:space:]')"
        [[ -z "${pkg}" || "${pkg}" == \#* ]] && continue
        grep -qxF "${pkg}" "${STAGE}/packages.x86_64" && continue
        printf '%s\n' "${pkg}"
      done < "${TARGET_DIR}/packages.x86_64"
    } >> "${STAGE}/packages.x86_64"
  fi
fi

# 3. System payload ----------------------------------------------------------
copy_tree() { # src dst mode
  local src="$1" dst="$2" mode="${3:-0644}"
  [[ -d "${src}" ]] || { log_debug "skip missing ${src}"; return 0; }
  mkdir -p "${dst}"
  cp -a "${src}/." "${dst}/"
  find "${dst}" -type f -exec chmod "${mode}" {} +
}

copy_tree "${ROOT}/system/lib"              "${AIR}/usr/local/lib/bunny"       0644
copy_tree "${ROOT}/system/units"            "${AIR}/etc/systemd/system"        0644
copy_tree "${ROOT}/system/wayland-sessions" "${AIR}/usr/share/wayland-sessions" 0644
copy_tree "${ROOT}/system/user-units"        "${AIR}/etc/systemd/user"          0644
copy_tree "${ROOT}/launchers/applications"  "${AIR}/usr/share/applications"    0644

# Executables
if [[ -d "${ROOT}/system/bin" ]]; then
  cp -a "${ROOT}/system/bin/." "${AIR}/usr/local/bin/"
fi
if [[ -d "${ROOT}/launchers/bin" ]]; then
  cp -a "${ROOT}/launchers/bin/." "${AIR}/usr/local/bin/"
fi
find "${AIR}/usr/local/bin" -type f -exec chmod 0755 {} +

# Bun Bun agent (source only — no caches, no tests)
log_debug "vendoring bunbun"
mkdir -p "${AIR}/opt/bunbun"
cp -a "${ROOT}/bunbun/." "${AIR}/opt/bunbun/"
rm -rf "${AIR}/opt/bunbun/tests" \
       "${AIR}/opt/bunbun/__pycache__" \
       "${AIR}/opt/bunbun/.venv"
find "${AIR}/opt/bunbun" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${AIR}/opt/bunbun" -name '*.pyc' -delete
if [[ -f "${AIR}/opt/bunbun/bin/bunbun-cli" ]]; then
  chmod 0755 "${AIR}/opt/bunbun/bin/bunbun-cli"
  ln -sf /opt/bunbun/bin/bunbun-cli "${AIR}/usr/local/bin/bunbun"
fi

# Control Panel UI (dependency-free web UI, rendered by the Tauri shell or kiosk)
log_debug "vendoring control panel"
mkdir -p "${AIR}/opt/bunny/panel/ui"
cp -a "${ROOT}/control-panel/ui/." "${AIR}/opt/bunny/panel/ui/"

# Installer
if [[ -f "${ROOT}/installer/bunny-install" ]]; then
  install -Dm0755 "${ROOT}/installer/bunny-install" "${AIR}/usr/local/bin/bunny-install"
fi
for entry in "${ROOT}"/installer/applications/*.desktop; do
  [[ -e "${entry}" ]] || continue
  install -Dm0644 "${entry}" "${AIR}/usr/share/applications/$(basename "${entry}")"
done

# Documentation shipped with the image. Units and recovery instructions point
# at /usr/share/doc/bunny-os, so the directory must exist on a live system.
install -d -m0755 "${AIR}/usr/share/doc/bunny-os"
for doc in "${ROOT}"/docs/*.md; do
  [[ -e "${doc}" ]] || continue
  install -Dm0644 "${doc}" "${AIR}/usr/share/doc/bunny-os/$(basename "${doc}")"
done
for doc in "${ROOT}/README.md" "${ROOT}/LICENSE"; do
  [[ -e "${doc}" ]] || continue
  install -Dm0644 "${doc}" "${AIR}/usr/share/doc/bunny-os/$(basename "${doc}")"
done

# 3b. Target airootfs overlay -----------------------------------------------
# Hardware-specific configuration (zram sizing, udev rules, drop-ins). Always
# write the target marker so validate-profile.sh and the installer can tell a
# generic image from a Deck-tuned one without guessing.
if [[ -n "${TARGET_DIR}" && -d "${TARGET_DIR}/airootfs" ]]; then
  log_debug "applying ${TARGET} airootfs overlay"
  cp -a "${TARGET_DIR}/airootfs/." "${AIR}/"
fi
printf '%s\n' "${TARGET:-generic}" > "${AIR}/etc/bunny/target"
chmod 0644 "${AIR}/etc/bunny/target"
if [[ -n "${TARGET_DIR}" ]]; then
  install -Dm0644 "${TARGET_DIR}/target.conf" "${AIR}/etc/bunny/target.conf"
fi

# 4. Live-session tweaks -----------------------------------------------------
install -Dm0644 "${ROOT}/iso/airootfs/etc/os-release" "${AIR}/etc/os-release"
chmod 0755 "${AIR}/root/customize_airootfs.sh" 2>/dev/null || true

# 5. Render tokens ----------------------------------------------------------
log_step "Rendering build tokens"
render_tokens "${AIR}" \
  "VERSION=${VERSION}" \
  "BUILD_ID=${BUILD_ID}" \
  "BUILD_DATE=${BUILD_DATE}" \
  "CHANNEL=${CHANNEL}"
# Boot menus live outside airootfs. Without this the menu title would keep the
# literal version token, and target boot entries could not be versioned.
for bootdir in "${STAGE}/efiboot" "${STAGE}/syslinux" "${STAGE}/grub"; do
  [[ -d "${bootdir}" ]] || continue
  render_tokens "${bootdir}" \
    "VERSION=${VERSION}" \
    "BUILD_ID=${BUILD_ID}" \
    "BUILD_DATE=${BUILD_DATE}" \
    "CHANNEL=${CHANNEL}"
done
# profiledef.sh drives the ISO filename via iso_version, and it sits at the stage
# root — outside both airootfs and the boot trees rendered above. render_tokens
# accepts a single file path, so this renders exactly that one file.
render_tokens "${STAGE}/profiledef.sh" \
  "VERSION=${VERSION}" \
  "BUILD_ID=${BUILD_ID}" \
  "BUILD_DATE=${BUILD_DATE}" \
  "CHANNEL=${CHANNEL}"

# A token that survives staging means a file type render_tokens does not know
# about (syslinux.cfg was one) would ship a literal version token in the image.
# Only the trees archiso actually copies are scanned: the staged profile also
# carries the target overlay sources under targets/, which keep their tokens.
scan_trees=("${AIR}")
for bootdir in efiboot syslinux grub; do
  if [[ -d "${STAGE}/${bootdir}" ]]; then
    scan_trees+=("${STAGE}/${bootdir}")
  fi
done
left="$(grep -rIl -E '@(VERSION|BUILD_ID|BUILD_DATE|CHANNEL)@' "${scan_trees[@]}" \
  --include='*.conf' --include='*.cfg' --include='*.sh' --include='*.py' \
  --include='*.desktop' --include='*.service' --include='*.json' \
  --include='*.html' --include='*.js' --include='*.css' --include='*.md' \
  --include='os-release' --include='motd' \
  2>/dev/null || true)"
if [[ -n "${left}" ]]; then
  die "unrendered build tokens in: ${left//$'\n'/, }"
fi

# 6. Build provenance ------------------------------------------------------
PROVENANCE_ARGS=(
  version "${VERSION}"
  build_id "${BUILD_ID}"
  build_date "${BUILD_DATE}"
  channel "${CHANNEL}"
  target "${TARGET:-generic}"
  target_name "${BUNNY_TARGET_NAME:-generic}"
  host "$(uname -srm 2>/dev/null || echo unknown)"
  archiso "$(archiso_version)"
)
PROVENANCE="$(json_kv "${PROVENANCE_ARGS[@]}")"
printf '%s\n' "${PROVENANCE}" > "${AIR}/etc/bunny/build-info.json"
# Minimal version file for helpers that need one line and no JSON parser
# (recovery, account setup, shell prompts). The JSON above stays authoritative.
printf '%s\n' "${VERSION}" > "${AIR}/etc/bunny/version"
chmod 0644 "${AIR}/etc/bunny/version"

# 7. Sanity ---------------------------------------------------------------
[[ -f "${AIR}/etc/systemd/system/bunny-sessiond.service" ]] \
  || die "staging incomplete: bunny-sessiond.service missing"
[[ -f "${AIR}/opt/bunny/panel/ui/index.html" ]] \
  || die "staging incomplete: panel UI missing"
[[ -f "${AIR}/opt/bunbun/bunbun/service.py" ]] \
  || die "staging incomplete: bunbun service missing"
[[ -f "${AIR}/etc/bunny/target" ]] \
  || die "staging incomplete: target marker missing"

log_info "stage ready: ${STAGE} ($(human_size "${STAGE}"))"
