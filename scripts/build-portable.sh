#!/usr/bin/env bash
# =============================================================================
#  Bunny OS portable payload
# -----------------------------------------------------------------------------
#  Packages the parts of Bunny OS that do not need the ISO: the Control Panel,
#  its bridge and the first-boot wizard, plus an installer that drops them on
#  a system that is already running (Bazzite, SteamOS Desktop Mode, any other
#  systemd distro).
#
#  Produces:
#      out/bunny-os-portable-<version>.tar.gz
#      out/bunny-os-portable-<version>.tar.gz.sha256
#      out/portable/bunny-os-portable-<version>/     (staging tree)
#
#  This same tarball is what the Bazzite image build layers on top of
#  ghcr.io/ublue-os/bazzite-deck (see packaging/bazzite/Containerfile).
#
#  Usage: scripts/build-portable.sh [--out DIR] [--no-archive]
# =============================================================================
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
OUT_DIR="${ROOT}/out"
ARCHIVE=1

while (( $# > 0 )); do
  case "$1" in
    --out) [[ $# -ge 2 ]] || die "--out needs a directory"; OUT_DIR="$2"; shift 2 ;;
    --no-archive) ARCHIVE=0; shift ;;
    -*) die "unknown argument: $1" ;;
    *) die "unexpected argument: $1" ;;
  esac
done

VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
BUILD_ID="${BUILD_ID:-$(stamp_short)}"
# safe_rmrf only accepts paths that look like build directories, and a
# relative --out would never match that pattern.
mkdir -p "${OUT_DIR}"
OUT_DIR="$(cd -- "${OUT_DIR}" >/dev/null 2>&1 && pwd -P)"
NAME="bunny-os-portable-${VERSION}"
STAGE_ROOT="${OUT_DIR}/portable"
STAGE="${STAGE_ROOT}/${NAME}"

log_step "Staging the portable payload"
log_info "version ${VERSION} - build ${BUILD_ID}"

safe_rmrf "${STAGE}"
mkdir -p "${STAGE}/bin" "${STAGE}/ui" "${STAGE}/docs"

# --- binaries ----------------------------------------------------------------
for tool in bunny-panel bunny-panel-bridge bunny-setupd; do
  src="${ROOT}/system/bin/${tool}"
  [[ -f "${src}" ]] || die "missing ${src}"
  install -m 0755 "${src}" "${STAGE}/bin/${tool}"
done
for tool in bunny-os bunny-os-setup; do
  src="${ROOT}/packaging/portable/bin/${tool}"
  [[ -f "${src}" ]] || die "missing ${src}"
  install -m 0755 "${src}" "${STAGE}/bin/${tool}"
done

# --- web UI ------------------------------------------------------------------
cp -a "${ROOT}/control-panel/ui/." "${STAGE}/ui/"
find "${STAGE}/ui" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "${STAGE}/ui" -type f -name '*.pyc' -delete 2>/dev/null || true

# --- the Bun Bun agent (the MAM engine, stdlib-only) ---------------------------
mkdir -p "${STAGE}/agent"
cp -a "${ROOT}/bunbun/." "${STAGE}/agent/"
rm -rf "${STAGE}/agent/tests" "${STAGE}/agent/.venv" "${STAGE}/agent/pyproject.toml" "${STAGE}/agent/__pycache__" 2>/dev/null || true
find "${STAGE}/agent" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "${STAGE}/agent" -type f -name '*.pyc' -delete 2>/dev/null || true
[[ -f "${STAGE}/agent/bunbun/service.py" ]] || die "agent engine missing bunbun/service.py"

# --- the desktop wallpaper ------------------------------------------------------
mkdir -p "${STAGE}/wallpaper"
[[ -f "${ROOT}/assets/wallpaper/bunny-glow.png" ]] || die "missing ${ROOT}/assets/wallpaper/bunny-glow.png"
cp -a "${ROOT}/assets/wallpaper/bunny-glow.png" "${STAGE}/wallpaper/bunny-glow.png"

# --- the neural voice (Piper, bundled so Bun Bun sounds human out of the box) ---
#  Pinned upstream URLs + sha256: the model ships as bunny-default.onnx, the key
#  the engine's find_voice() looks for in /usr/share/bunbun/voices.
VOICE_CACHE="${OUT_DIR}/voice-cache"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
PIPER_SHA256="a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992"
VOICE_DIR_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"
VOICE_MODEL_SHA256="b3a6e47b57b8c7fbe6a0ce2518161a50f59a9cdd8a50835c02cb02bdd6206c18"
VOICE_JSON_SHA256="95a23eb4d42909d38df73bb9ac7f45f597dbfcde2d1bf9526fdeaf5466977d77"
command -v curl >/dev/null || die "curl is needed to fetch the voice"
mkdir -p "${VOICE_CACHE}"
sha_ok() { echo "$2  $1" | (cd "$(dirname "$1")" && sha256sum -c - >/dev/null 2>&1); }
if [[ ! -f "${VOICE_CACHE}/piper" ]]; then
  log_info "voice    fetching the Piper engine (pinned)"
  [[ -f "${VOICE_CACHE}/piper.tar.gz" ]] || curl -fL --retry 3 -o "${VOICE_CACHE}/piper.tar.gz" "${PIPER_URL}"
  sha_ok "${VOICE_CACHE}/piper.tar.gz" "${PIPER_SHA256}" || die "piper release checksum mismatch"
  rm -rf "${VOICE_CACHE}/piper-extract"; mkdir -p "${VOICE_CACHE}/piper-extract"
  tar -xzf "${VOICE_CACHE}/piper.tar.gz" -C "${VOICE_CACHE}/piper-extract"
  mv "${VOICE_CACHE}/piper-extract/piper" "${VOICE_CACHE}/piper"
fi
if [[ ! -f "${VOICE_CACHE}/bunny-default.onnx" ]]; then
  log_info "voice    fetching the Bun Bun voice model (pinned)"
  curl -fL --retry 3 -o "${VOICE_CACHE}/bunny-default.onnx" "${VOICE_DIR_URL}/en_US-amy-medium.onnx?download=true"
  curl -fL --retry 3 -o "${VOICE_CACHE}/bunny-default.onnx.json" "${VOICE_DIR_URL}/en_US-amy-medium.onnx.json"
fi
sha_ok "${VOICE_CACHE}/bunny-default.onnx" "${VOICE_MODEL_SHA256}" || die "voice model checksum mismatch"
sha_ok "${VOICE_CACHE}/bunny-default.onnx.json" "${VOICE_JSON_SHA256}" || die "voice config checksum mismatch"
mkdir -p "${STAGE}/voice"
cp -a "${VOICE_CACHE}/piper" "${STAGE}/voice/piper"
cp -a "${VOICE_CACHE}/bunny-default.onnx" "${VOICE_CACHE}/bunny-default.onnx.json" "${STAGE}/voice/"

# --- documentation and installer --------------------------------------------
cp -a "${ROOT}/packaging/portable/install.sh"   "${STAGE}/install.sh"
cp -a "${ROOT}/packaging/portable/uninstall.sh" "${STAGE}/uninstall.sh"
chmod 0755 "${STAGE}/install.sh" "${STAGE}/uninstall.sh"
for doc in "${ROOT}"/docs/*.md; do
  [[ -e "${doc}" ]] || continue
  install -m 0644 "${doc}" "${STAGE}/docs/$(basename "${doc}")"
done
printf '%s\n' "${VERSION}" > "${STAGE}/VERSION"

# The docs describe the release; render the same tokens the ISO build renders
# so nothing ships with a placeholder in it.
render_tokens "${STAGE}" \
  "VERSION=${VERSION}" \
  "CHANNEL=portable" \
  "BUILD_ID=${BUILD_ID}" \
  "TARGET=portable" \
  "TARGET_NAME=Existing Linux system"

# --- manifest ----------------------------------------------------------------
cat > "${STAGE}/build-manifest.json" <<EOF
{
  "product": "Bunny OS",
  "variant": "portable",
  "version": "${VERSION}",
  "channel": "portable",
  "build_id": "${BUILD_ID}",
  "built_at": "$(timestamp)",
  "target": "portable",
  "target_name": "Existing Linux system",
  "contents": {
    "panel": "bunny-panel",
    "bridge": "bunny-panel-bridge",
    "setup": "bunny-setupd --portable",
    "ui": "control-panel/ui"
  }
}
EOF

# Nothing may ship with a template token left in it.
if grep -rIl '@VERSION@\|@CHANNEL@\|@BUILD_ID@' "${STAGE}" 2>/dev/null | grep -q .; then
  grep -rIl '@VERSION@\|@CHANNEL@\|@BUILD_ID@' "${STAGE}" >&2 || true
  die "unrendered token in the portable payload"
fi

log_info "payload  ${STAGE}"

if (( ARCHIVE )); then
  mkdir -p "${OUT_DIR}"
  archive="${OUT_DIR}/${NAME}.tar.gz"
  rm -f "${archive}" "${archive}.sha256"
  tar -czf "${archive}" -C "${STAGE_ROOT}" "${NAME}"
  ( cd "${OUT_DIR}" && sha256sum "$(basename "${archive}")" > "$(basename "${archive}").sha256" )
  log_step "Portable payload ready"
  log_info "archive  ${archive}"
  log_info "size     $(du -h "${archive}" | cut -f1)"
  log_info "sha256   $(cut -d' ' -f1 "${archive}.sha256")"
fi
