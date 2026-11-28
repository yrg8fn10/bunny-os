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
for tool in bunny-panel bunny-panel-bridge bunny-setupd bunbun-join bunny-desktop-theme bunny-taskbar bunny-boot-jingle bunny-upgrade; do
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

# --- the Game Mode presence layer (bunhud) -------------------------------------
mkdir -p "${STAGE}/bunhud"
cp -a "${ROOT}/tools/bunhud/." "${STAGE}/bunhud/"
find "${STAGE}/bunhud" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "${STAGE}/bunhud" -type f -name '*.pyc' -delete 2>/dev/null || true
[[ -f "${STAGE}/bunhud/bunhud.py" ]] || die "bunhud missing bunhud.py"
[[ -f "${STAGE}/bunhud/assets/bunhud-placeholder.png" ]] || die "bunhud missing placeholder sprite"

# The payload carries pywayland wheels for the python builds a Deck might run,
# so a payload update can rebuild bunhud's pylibs without reaching PyPI.  Best
# effort per tag: the updater falls back to PyPI for whatever is missing.
mkdir -p "${STAGE}/bunhud/wheels"
if command -v pip3 >/dev/null 2>&1; then
  for v in 310 311 312 313 314; do
    pip3 download --only-binary=:all: --no-deps --no-cache-dir -q \
      --python-version "${v}" --implementation cp --abi "cp${v}" \
      --platform manylinux_2_34_x86_64 \
      -d "${STAGE}/bunhud/wheels" pywayland==0.4.19 >/dev/null 2>&1 \
      || true
  done
  pip3 download --only-binary=:all: --no-deps --no-cache-dir -q \
    --python-version 3 --platform any \
    -d "${STAGE}/bunhud/wheels" pycparser >/dev/null 2>&1 || true
  pip3 download --only-binary=:all: --no-deps --no-cache-dir -q \
    --python-version 3 --platform manylinux_2_34_x86_64 --abi abi3 \
    -d "${STAGE}/bunhud/wheels" cffi >/dev/null 2>&1 || true
  ls "${STAGE}/bunhud/wheels" | head -1 >/dev/null 2>&1 \
    || echo "  ! no wheels bundled; the updater will use PyPI" >&2
fi

# --- the desktop wallpaper ------------------------------------------------------
mkdir -p "${STAGE}/wallpaper"
[[ -f "${ROOT}/assets/wallpaper/bunny-glow.png" ]] || die "missing ${ROOT}/assets/wallpaper/bunny-glow.png"
cp -a "${ROOT}/assets/wallpaper/bunny-glow.png" "${STAGE}/wallpaper/bunny-glow.png"
[[ -f "${ROOT}/assets/wallpaper/bunny-desktop.png" ]] && cp -a "${ROOT}/assets/wallpaper/bunny-desktop.png" "${STAGE}/wallpaper/bunny-desktop.png"
[[ -f "${ROOT}/assets/wallpaper/bunny-game-mode.png" ]] && cp -a "${ROOT}/assets/wallpaper/bunny-game-mode.png" "${STAGE}/wallpaper/bunny-game-mode.png"

# --- the startup jingle ----------------------------------------------------------
mkdir -p "${STAGE}/sounds"
[[ -f "${ROOT}/assets/sounds/boot-jingle.wav" ]] || die "missing ${ROOT}/assets/sounds/boot-jingle.wav"
cp -a "${ROOT}/assets/sounds/boot-jingle.wav" "${STAGE}/sounds/boot-jingle.wav"

# --- the Bunny cursor set (pink-glow Xcursor theme) -----------------------------
#  Generated by tools/make-bunny-cursors.py and committed under assets/cursors,
#  so the image build never needs Pillow.
mkdir -p "${STAGE}/cursors"
[[ -f "${ROOT}/assets/cursors/BunnyCursor/index.theme" ]] || die "missing ${ROOT}/assets/cursors/BunnyCursor/index.theme"
cp -a "${ROOT}/assets/cursors/BunnyCursor/." "${STAGE}/cursors/"

# --- the Game Mode theme (CSS Loader, bunny-cute) --------------------------------
#  The ISO bakes this at /usr/share/bunny-os/decky-theme. The payload carries it
#  too, so an upgrade refreshes the theme on an already-running Deck without a
#  reflash: new CSS, ears, and paw spinner land with the same bunny-upgrade.
mkdir -p "${STAGE}/decky-theme"
[[ -d "${ROOT}/packaging/bazzite/decky-theme/bunny-cute" ]] || die "missing ${ROOT}/packaging/bazzite/decky-theme/bunny-cute"
cp -a "${ROOT}/packaging/bazzite/decky-theme/bunny-cute" "${STAGE}/decky-theme/bunny-cute"

# --- the neural voice (Piper, bundled so Bun Bun sounds human out of the box) ---
#  Pinned upstream URLs + sha256: the model ships as bunny-default.onnx, the key
#  the engine's find_voice() looks for in /usr/share/bunbun/voices.
VOICE_CACHE="${OUT_DIR}/voice-cache"
PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
PIPER_SHA256="a50cb45f355b7af1f6d758c1b360717877ba0a398cc8cbe6d2a7a3a26e225992"
# Bun Bun's voice: the "THV" speaker (speaker id 1) of Piper's L2-Arctic voice,
# a real person reading English with a gentle Vietnamese accent. The model ships
# as bunny-default.onnx, the key the engine's find_voice() looks for. Dataset:
# L2-Arctic (Zhao et al., Interspeech 2018), license CC BY-NC 4.0 - fine for
# personal use; re-check before any commercial redistribution.
VOICE_DIR_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/l2arctic/medium"
VOICE_MODEL_SHA256="d89f6f124bf1e7735b2179d2141b8001c3e19169d5e743ed6e35624f4c76f044"
VOICE_JSON_SHA256="a97e2ba653e9efcdc1bdcec64a398c8beb19ae5e8dfdbfe4ad6841983e56c07c"
command -v curl >/dev/null || die "curl is needed to fetch the voice"
mkdir -p "${VOICE_CACHE}"
sha_ok() { echo "$2  $1" | (cd "$(dirname "$1")" && sha256sum -c - >/dev/null 2>&1); }
if [[ ! -d "${VOICE_CACHE}/piper" ]]; then
  log_info "voice    fetching the Piper engine (pinned)"
  [[ -f "${VOICE_CACHE}/piper.tar.gz" ]] || curl -fL --retry 3 -o "${VOICE_CACHE}/piper.tar.gz" "${PIPER_URL}"
  sha_ok "${VOICE_CACHE}/piper.tar.gz" "${PIPER_SHA256}" || die "piper release checksum mismatch"
  rm -rf "${VOICE_CACHE}/piper-extract"; mkdir -p "${VOICE_CACHE}/piper-extract"
  tar -xzf "${VOICE_CACHE}/piper.tar.gz" -C "${VOICE_CACHE}/piper-extract"
  mv "${VOICE_CACHE}/piper-extract/piper" "${VOICE_CACHE}/piper"
fi
if [[ ! -f "${VOICE_CACHE}/bunny-default.onnx" ]]; then
  log_info "voice    fetching the Bun Bun voice model (pinned)"
  curl -fL --retry 3 -o "${VOICE_CACHE}/bunny-default.onnx" "${VOICE_DIR_URL}/en_US-l2arctic-medium.onnx?download=true"
  curl -fL --retry 3 -o "${VOICE_CACHE}/bunny-default.onnx.json" "${VOICE_DIR_URL}/en_US-l2arctic-medium.onnx.json"
fi
sha_ok "${VOICE_CACHE}/bunny-default.onnx" "${VOICE_MODEL_SHA256}" || die "voice model checksum mismatch"
sha_ok "${VOICE_CACHE}/bunny-default.onnx.json" "${VOICE_JSON_SHA256}" || die "voice config checksum mismatch"
mkdir -p "${STAGE}/voice"
cp -a "${VOICE_CACHE}/piper" "${STAGE}/voice/piper"
cp -a "${VOICE_CACHE}/bunny-default.onnx" "${VOICE_CACHE}/bunny-default.onnx.json" "${STAGE}/voice/"
# Bun Bun's real voice: the pre-rendered v2 voice bank (103 clips, Kokoro af_sky
# wearing Ava's own voice color). The engine's find_bank() looks for it at
# /usr/share/bunbun/voices/bank; the installer places it there.
[[ -d "${ROOT}/bunbun/assets/voice-bank" && -f "${ROOT}/bunbun/assets/voice-bank/manifest.json" ]] \
  || die "voice bank missing: bunbun/assets/voice-bank"
mkdir -p "${STAGE}/voice/bank"
cp -a "${ROOT}/bunbun/assets/voice-bank/." "${STAGE}/voice/bank/"
cat > "${STAGE}/voice/VOICE-NOTE.txt" <<'EOF'
Bun Bun's official voice is the SERENA preset of Qwen3-TTS 0.6B
CustomVoice (the qwentts.cpp engine, Apache-2.0), fully local. Serena is a
synthetic preset voice, not a cloned real child. The Piper
en_US-l2arctic engine (dataset: L2-Arctic, Zhao et al., Interspeech 2018,
license CC BY-NC 4.0) and the pre-rendered v2 voice bank (Kokoro af_sky)
remain as fallbacks if the Qwen engine is unavailable.
EOF

# --- Bun Bun's ears: whisper.cpp local speech-to-text ----------------------------
#  She understands speech fully on-device; nothing leaves the machine. The
#  whisper-cli binary is built once per build host (whisper.cpp; zig cc works
#  on hosts without a gcc), and the model is the pinned public tiny.en build.
STT_BIN="${WHISPER_CLI:-/tmp/whisper.cpp/build/bin/whisper-cli}"
STT_CACHE="${STT_CACHE:-${HOME}/.cache/bunbun-build}"
STT_MODEL_SHA256="c77c5766f1cef09b6b7d47f21b546cbddd4157886b3b5d6d4f709e91e66c7c2b"
log_info "stt      staging Bun Bun's local ears (whisper.cpp, tiny.en)"
if [[ -x "${STT_BIN}" ]]; then
  mkdir -p "${STAGE}/stt"
  cp -a "${STT_BIN}" "${STAGE}/stt/whisper-cli"
  if [[ ! -f "${STT_CACHE}/ggml-tiny.en-q5_1.bin" ]]; then
    mkdir -p "${STT_CACHE}"
    log_info "stt      fetching the tiny.en model (pinned)"
    curl -fL --retry 3 -o "${STT_CACHE}/ggml-tiny.en-q5_1.bin" \
      "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en-q5_1.bin"
  fi
  sha_ok "${STT_CACHE}/ggml-tiny.en-q5_1.bin" "${STT_MODEL_SHA256}" || die "speech model checksum mismatch"
  cp -a "${STT_CACHE}/ggml-tiny.en-q5_1.bin" "${STAGE}/stt/"
else
  log_warn "no whisper-cli found at ${STT_BIN}; this payload ships without Bun Bun's ears"
fi

# --- Bun Bun's brain: the local MAM model (llama.cpp + tiny instruct GGUF) ----
#  She chats conversationally, fully on-device. The CLI is the pinned public
#  llama.cpp b12803 ubuntu-x64 build (libs shipped beside it; the wrapper sets
#  LD_LIBRARY_PATH), the model is Qwen2.5-0.5B-Instruct Q4_K_M GGUF
#  (Apache-2.0; bartowski quantization). Sources are env-overridable per
#  build host, like STT_BIN above.
MAM_CLI_DIR="${MAM_CLI_DIR:-/tmp/llama-b12803}"
MAM_MODEL_SRC="${MAM_MODEL_SRC:-/tmp/bunbun-model.gguf}"
log_info "mam      staging Bun Bun's local brain (llama.cpp + Qwen2.5-0.5B Q4_K_M)"
if [[ -x "${MAM_CLI_DIR}/llama-cli" && -f "${MAM_MODEL_SRC}" ]]; then
  mkdir -p "${STAGE}/mam" "${STAGE}/share/bunbun/models" "${STAGE}/bin"
  cp -a "${MAM_CLI_DIR}/llama-cli" "${STAGE}/mam/llama-cli"
  cp -a "${MAM_CLI_DIR}"/*.so* "${STAGE}/mam/" 2>/dev/null || true
  cp -a "${MAM_MODEL_SRC}" "${STAGE}/share/bunbun/models/qwen2.5-0.5b-instruct-q4_k_m.gguf"
  cat > "${STAGE}/bin/bunbun-llama-cli" <<'WRAP'
#!/bin/sh
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LIBS="${DIR}/../lib/bunny/mam"
LD_LIBRARY_PATH="${LIBS}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" exec "${LIBS}/llama-cli" "$@"
WRAP
  chmod 0755 "${STAGE}/bin/bunbun-llama-cli"
else
  log_warn "no llama.cpp CLI / model found (${MAM_CLI_DIR}, ${MAM_MODEL_SRC}); this payload ships without Bun Bun's local brain"
fi

# --- Bun Bun's official voice: the Qwen3-TTS engine (the SERENA preset) ------
#  Ava picked this voice by ear on Nov 27 2026 (it supersedes the Kokoro
#  af_sky color, which now lives behind the pre-rendered voice bank as a
#  fallback).  The engine is qwentts.cpp (Apache-2.0, built once per build
#  host with zig cc; Serena is a synthetic CustomVoice preset, so no real
#  child's voice is involved), the models are the pinned Qwen3-TTS 0.6B
#  CustomVoice talker + codec GGUFs.  Sources are env-overridable per build
#  host, like STT_BIN above.
QWEN_BIN_SRC="${QWEN_BIN_SRC:-/workspace/vh_keep/qwentts/build}"
QWEN_MODELS_SRC="${QWEN_MODELS_SRC:-/workspace/vh_keep/models}"
log_info "voice    staging Bun Bun's official voice (Qwen3-TTS, Serena preset)"
if [[ -x "${QWEN_BIN_SRC}/qwen-tts" && -f "${QWEN_MODELS_SRC}/talker.gguf" && -f "${QWEN_MODELS_SRC}/tokenizer.gguf" ]]; then
  mkdir -p "${STAGE}/qwentts" "${STAGE}/share/bunbun/models" "${STAGE}/bin"
  cp -a "${QWEN_BIN_SRC}/qwen-tts" "${STAGE}/qwentts/qwen-tts"
  cp -a "${QWEN_BIN_SRC}"/*.so* "${STAGE}/qwentts/" 2>/dev/null || true
  cp -a "${QWEN_MODELS_SRC}/talker.gguf" "${STAGE}/share/bunbun/models/qwen-talker-0.6b-customvoice-Q4_K_M.gguf"
  cp -a "${QWEN_MODELS_SRC}/tokenizer.gguf" "${STAGE}/share/bunbun/models/qwen-tokenizer-12hz-Q4_K_M.gguf"
  cat > "${STAGE}/bin/bunbun-qwen-tts" <<'WRAP'
#!/bin/sh
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LIBS="${DIR}/../lib/bunny/qwentts"
MODELS="${BUNBUN_MODELS_DIR:-/usr/local/share/bunbun/models}"
LD_LIBRARY_PATH="${LIBS}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" exec "${LIBS}/qwen-tts" \
  --model "${MODELS}/qwen-talker-0.6b-customvoice-Q4_K_M.gguf" \
  --codec "${MODELS}/qwen-tokenizer-12hz-Q4_K_M.gguf" "$@"
WRAP
  chmod 0755 "${STAGE}/bin/bunbun-qwen-tts"
else
  log_warn "no qwentts engine / models found (${QWEN_BIN_SRC}, ${QWEN_MODELS_SRC}); this payload ships without Bun Bun's official voice"
fi

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
