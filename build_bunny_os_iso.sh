#!/usr/bin/env bash
# =============================================================================
#  Bunny OS — ISO build pipeline
# -----------------------------------------------------------------------------
#  Compiles the archiso profile in iso/, overlays the Bunny OS system payloads
#  (session daemon, Control Panel, Bun Bun agent, store launchers, installer),
#  validates everything, and produces:
#
#      out/BunnyOS-installer.iso   (BunnyOS-<target>-installer.iso with --target)
#      out/BunnyOS-installer.iso.sha256
#      out/build-manifest.json
#
#  Requirements: Arch Linux (or --docker), root, ~25 GB free, network.
#
#  Usage:
#      sudo ./build_bunny_os_iso.sh
#      sudo ./build_bunny_os_iso.sh --target deck  # Steam Deck LCD profile
#      sudo ./build_bunny_os_iso.sh --dry-run        # stage + validate only
#      ./build_bunny_os_iso.sh --docker              # build inside Arch container
#      sudo ./build_bunny_os_iso.sh --sign 0xBUNNY  # gpg-sign the checksum
# =============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
# shellcheck source=scripts/lib/common.sh
source "${SCRIPT_DIR}/scripts/lib/common.sh"

# --- Defaults ---------------------------------------------------------------
ROOT="${SCRIPT_DIR}"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
CHANNEL="${BUNNY_CHANNEL:-stable}"
ISO_BASENAME="BunnyOS-installer"
TARGET=""
OUT_DIR="${ROOT}/out"
BUILD_ROOT="${ROOT}/build"
STAGE="${BUILD_ROOT}/profile"
ARCHISO_WORK="${BUILD_ROOT}/archiso-work"
BUILD_ID="${BUILD_ID:-$(stamp_short)}"
JOBS="$(cpus)"

DOCKER=0
DRY_RUN=0
KEEP_WORK=0
VALIDATE=1
SIGN_KEY=""
CLEAN_FIRST=1
FORWARD_ARGS=()

# --- Args -------------------------------------------------------------------
while (( $# > 0 )); do
  case "$1" in
    --docker)       DOCKER=1; FORWARD_ARGS+=("$1"); shift ;;
    --target)       TARGET="${2:?--target needs a profile name}"; FORWARD_ARGS+=("$1" "$2"); shift 2 ;;
    --dry-run)      DRY_RUN=1; shift ;;
    --keep-work)    KEEP_WORK=1; shift ;;
    --no-validate)  VALIDATE=0; shift ;;
    --no-clean)     CLEAN_FIRST=0; shift ;;
    --sign)         SIGN_KEY="${2:?--sign needs a key id}"; shift 2 ;;
    --out)          OUT_DIR="${2:?--out needs a directory}"; shift 2 ;;
    --jobs|-j)      JOBS="${2:?--jobs needs a number}"; shift 2 ;;
    --verbose|-v)   BUNNY_VERBOSE=1; set -x; shift ;;
    --help|-h)      sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

export BUNNY_VERBOSE BUILD_ID CHANNEL

# --- Docker hand-off --------------------------------------------------------
if (( DOCKER == 1 )); then
  exec "${ROOT}/scripts/build-docker.sh" "${FORWARD_ARGS[@]}"
fi

# --- Target profile ---------------------------------------------------------
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
  ISO_BASENAME="${BUNNY_ISO_BASENAME:-BunnyOS-${TARGET}-installer}"
fi
TARGET_NAME="${BUNNY_TARGET_NAME:-generic}"
TARGET_LABEL="${TARGET:-generic}"
[[ -n "${TARGET}" ]] && TARGET_LABEL+=" (${TARGET_NAME})"

# --- Trap -------------------------------------------------------------------
on_error() {
  local code=$?
  log_error "build failed at ${BASH_SOURCE[0]}:${LINENO} (exit ${code})"
  log_info  "logs: ${ARCHISO_WORK}/build.log (if mkarchiso started)"
  log_info  "staged profile kept at ${STAGE} for inspection"
  exit "${code}"
}
trap on_error ERR

# --- 0. Banner --------------------------------------------------------------
banner
log_info "Bunny OS ${VERSION} · channel ${CHANNEL} · build ${BUILD_ID}"
log_info "target: ${TARGET_LABEL}"
log_info "root: ${ROOT}"
log_info "jobs: ${JOBS}"

# --- 1. Preflight ----------------------------------------------------------
log_step "1/6 Preflight"
if (( DRY_RUN )); then
  bash "${ROOT}/scripts/preflight.sh" --dry-run || log_warn "preflight reported issues (dry-run continues)"
else
  bash "${ROOT}/scripts/preflight.sh"
fi

# --- 2. Stage --------------------------------------------------------------
log_step "2/6 Stage profile"
mkdir -p "${BUILD_ROOT}" "${OUT_DIR}"
if (( CLEAN_FIRST )); then
  [[ -d "${ARCHISO_WORK}" ]] && safe_rmrf "${ARCHISO_WORK}"
fi
STAGE_ARGS=("${ROOT}" "${STAGE}" --allow-non-arch)
[[ -n "${TARGET}" ]] && STAGE_ARGS+=(--target "${TARGET}")
bash "${ROOT}/scripts/stage-profile.sh" "${STAGE_ARGS[@]}"

# --- 3. Validate ----------------------------------------------------------
log_step "3/6 Validate"
if (( VALIDATE )); then
  bash "${ROOT}/scripts/validate-profile.sh" --stage "${STAGE}"
else
  log_warn "validation skipped by --no-validate"
fi

# --- 4. Build --------------------------------------------------------------
log_step "4/6 mkarchiso"
if (( DRY_RUN )); then
  log_warn "dry-run: skipping mkarchiso"
  mkdir -p "${OUT_DIR}"
  {
    echo "Bunny OS dry-run build plan"
    echo "  version   : ${VERSION}"
    echo "  build id  : ${BUILD_ID}"
    echo "  target    : ${TARGET_LABEL}"
    echo "  profile   : ${STAGE}"
    echo "  output    : ${OUT_DIR}/${ISO_BASENAME}.iso"
    echo "  packages  : $(grep -vcE '^\s*(#|$)' "${STAGE}/packages.x86_64")"
    echo "  payload   : $(human_size "${STAGE}/airootfs")"
    echo "  bootmodes : $(grep -E '^bootmodes' "${STAGE}/profiledef.sh" || echo unknown)"
    echo "  next      : sudo ./build_bunny_os_iso.sh${TARGET:+ --target ${TARGET}}"
  } | tee "${BUILD_ROOT}/build-plan.txt"
  log_info "stage and validation complete; nothing bootable was produced"
  exit 0
fi

START_TS="$(date +%s)"
# Never let a stale image from a previous run be mistaken for this build.
rm -f "${OUT_DIR}"/*.iso "${OUT_DIR}"/*.iso.sha256 2>/dev/null || true
log_info "mkarchiso -v -w ${ARCHISO_WORK} -o ${OUT_DIR} ${STAGE}"
# Both directories must exist before the pipeline starts: the tee writes
# build.log into the work dir, and under pipefail a failing tee would mark the
# whole build failed even when mkarchiso produced a good ISO.
mkdir -p "${OUT_DIR}" "${ARCHISO_WORK}"
if ! mkarchiso -v -w "${ARCHISO_WORK}" -o "${OUT_DIR}" "${STAGE}" 2>&1 | tee "${ARCHISO_WORK}/build.log"; then
  die "mkarchiso failed — see ${ARCHISO_WORK}/build.log"
fi
BUILD_SECS=$(( $(date +%s) - START_TS ))
log_info "mkarchiso finished in $((BUILD_SECS / 60))m $((BUILD_SECS % 60))s"

# --- 5. Collect ------------------------------------------------------------
log_step "5/6 Collect image"
BUILT_ISO="$(find "${OUT_DIR}" -maxdepth 1 -type f -name '*.iso' -printf '%T@ %p\n' \
  | sort -nr | awk 'NR==1 {sub(/^[^ ]+ /, ""); print}')"
[[ -n "${BUILT_ISO}" && -f "${BUILT_ISO}" ]] || die "mkarchiso produced no ISO in ${OUT_DIR}"

FINAL_ISO="${OUT_DIR}/${ISO_BASENAME}.iso"
if [[ "${BUILT_ISO}" != "${FINAL_ISO}" ]]; then
  mv -f -- "${BUILT_ISO}" "${FINAL_ISO}"
fi

# --- 5a. Verify every path the boot entries ask for exists in the image -----
# archiso only copies files the profile actually references, and it skips
# /arch/boot/*-ucode.img whenever the initramfs already embeds microcode. An
# entry pointing at a file that was never copied boots as far as the loader and
# then dies with "Error preparing initrd: Not found", which is invisible to any
# check that runs before mkarchiso. List the finished image and cross-check.
log_step "5/6 Verifying boot entry paths"
ISO_TREE="$(bsdtar -tf "${FINAL_ISO}")" || die "cannot list ${FINAL_ISO}"
BOOT_REFS_MISSING=0
while IFS= read -r conf; do
  while IFS= read -r ref; do
    [[ -n "${ref}" ]] || continue
    ref="${ref#/}"
    if ! grep -qxF -- "${ref}" <<<"${ISO_TREE}"; then
      log_error "${conf#"${STAGE}/"}: references '${ref}', which is not in the image"
      BOOT_REFS_MISSING=$(( BOOT_REFS_MISSING + 1 ))
    fi
  done < <(sed -nE 's#^[[:space:]]*(linux|initrd|LINUX|INITRD)[[:space:]]+(/[^[:space:]]+).*#\2#p' "${conf}")
done < <(find "${STAGE}" -type f \( -path '*/loader/entries/*.conf' -o -name 'syslinux.cfg' \) -print)
if (( BOOT_REFS_MISSING > 0 )); then
  die "${BOOT_REFS_MISSING} boot entry path(s) missing from the image - it would fail to boot"
fi
log_info "all boot entry paths present in the image"

# --- 5b. Verify the image survives being copied onto FAT32 ------------------
# The Steam Deck firmware only enumerates USB media it can read as FAT32, so the
# supported flashing path is Rufus "ISO Image mode", which copies the ISO 9660
# tree verbatim onto a FAT32 partition. Two properties have to hold for that to
# reach a running system, and neither is visible until the Deck is booting.
log_step "5/6 Verifying FAT32 flashing compatibility"

# The initramfs finds airootfs.sfs by volume label, and the loader entries carry
# archisolabel= rendered from profiledef.sh. If the label on the image and the
# label the entries ask for ever drift, the live system panics looking for root.
ISO_LABEL_EXPECTED="$(sed -nE 's#^iso_label="([^"]*)".*#\1#p' "${STAGE}/profiledef.sh")"
if have blkid; then
  ISO_LABEL_ACTUAL="$(blkid -p -o value -s LABEL "${FINAL_ISO}" 2>/dev/null || true)"
  if [[ "${ISO_LABEL_ACTUAL}" != "${ISO_LABEL_EXPECTED}" ]]; then
    die "volume label is '${ISO_LABEL_ACTUAL}', boot entries look for '${ISO_LABEL_EXPECTED}'"
  fi
  log_info "volume label matches boot entries: ${ISO_LABEL_ACTUAL}"
else
  log_warn "blkid not available - skipping volume label check"
fi

# FAT32 cannot store a file of 4 GiB or more, and Rufus refuses to extract one.
TOO_BIG="$(bsdtar -tvf "${FINAL_ISO}" 2>/dev/null \
  | awk '$5 ~ /^[0-9]+$/ && $5 >= 4294967296 { print $5 " " $NF }')"
if [[ -n "${TOO_BIG}" ]]; then
  die "these files exceed the FAT32 4 GiB limit: ${TOO_BIG}"
fi
log_info "no file exceeds the FAT32 4 GiB limit"

# Sanity: the squashfs the entries will boot into must be where archisobasedir
# says it is.
INSTALL_DIR_STAGED="$(sed -nE 's#^install_dir="([^"]*)".*#\1#p' "${STAGE}/profiledef.sh")"
grep -qxF "${INSTALL_DIR_STAGED}/x86_64/airootfs.sfs" <<<"${ISO_TREE}" \
  || die "${INSTALL_DIR_STAGED}/x86_64/airootfs.sfs missing from the image"
log_info "airootfs.sfs present under ${INSTALL_DIR_STAGED}/x86_64/"

ISO_SHA="$(sha256_of "${FINAL_ISO}")"
ISO_SIZE="$(stat -c '%s' "${FINAL_ISO}" 2>/dev/null || stat -f '%z' "${FINAL_ISO}")"
printf '%s  %s\n' "${ISO_SHA}" "$(basename "${FINAL_ISO}")" \
  | tee "${FINAL_ISO}.sha256" >/dev/null

# Optional detached signature over the checksum file.
if [[ -n "${SIGN_KEY}" ]]; then
  if have gpg; then
    gpg --batch --yes --local-user "${SIGN_KEY}" --detach-sign --armor "${FINAL_ISO}.sha256"
    log_info "signed: ${FINAL_ISO}.sha256.asc"
  else
    log_warn "gpg unavailable; skipped signing"
  fi
fi

# --- 6. Manifest -----------------------------------------------------------
log_step "6/6 Manifest"
PKG_COUNT="$(grep -vcE '^\s*(#|$)' "${STAGE}/packages.x86_64" || echo 0)"
GIT_REV="$(git -C "${ROOT}" rev-parse --short HEAD 2>/dev/null || echo "nogit")"
cat > "${OUT_DIR}/build-manifest.json" <<JSON
{
  "product": "Bunny OS",
  "version": "${VERSION}",
  "channel": "${CHANNEL}",
  "build_id": "${BUILD_ID}",
  "target": "${TARGET:-generic}",
  "target_name": "${TARGET_NAME}",
  "built_at": "$(timestamp)",
  "git_revision": "${GIT_REV}",
  "host": "$(json_escape "$(uname -srm)")",
  "archiso": "$(archiso_version)",
  "iso": {
    "filename": "$(basename "${FINAL_ISO}")",
    "size_bytes": ${ISO_SIZE},
    "sha256": "${ISO_SHA}"
  },
  "contents": {
    "packages": ${PKG_COUNT},
    "agent": "Bun Bun MAM 0.1",
    "control_panel": "bunny-panel 0.1",
    "session_modes": ["gaming", "desktop"]
  },
  "build_seconds": ${BUILD_SECS}
}
JSON

if (( KEEP_WORK == 0 )); then
  log_debug "cleaning archiso work tree"
  safe_rmrf "${ARCHISO_WORK}" || log_warn "could not clean ${ARCHISO_WORK}"
fi

log_step "Done"
log_info "image    : ${FINAL_ISO}"
log_info "$(printf '%-10s' "size") : $(( ISO_SIZE / 1024 / 1024 )) MiB"
log_info "sha256   : ${ISO_SHA}"
log_info "manifest : ${OUT_DIR}/build-manifest.json"
if [[ "${TARGET}" == "deck" ]]; then
  log_info "target   : Steam Deck LCD (read docs/STEAMDECK.md before flashing)"
fi
cat <<EOF

  Flash it with:
      sudo dd if=${FINAL_ISO} of=/dev/sdX bs=16M status=progress oflag=sync
      # or
      sudo bunny-install --flash ${FINAL_ISO} /dev/sdX

  On Windows use Rufus (DD mode) or balenaEtcher. Do not use Ventoy.

EOF
