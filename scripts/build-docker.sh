#!/usr/bin/env bash
# Build Bunny OS inside a privileged Arch Linux container.
# Used when the host is not Arch (or is Windows/macOS with Docker Desktop,
# though loop devices are unreliable there — CI is the better path).
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

IMAGE="${BUNNY_DOCKER_IMAGE:-archlinux:latest}"
PASSTHRU=()
for arg in "$@"; do
  case "${arg}" in
    --docker) ;; # we are the docker path
    *) PASSTHRU+=("${arg}") ;;
  esac
done

have docker || die "docker not found. Install Docker, or use GitHub Actions (.github/workflows/build-iso.yml)."
docker info >/dev/null 2>&1 || die "docker daemon not reachable (is it running? are you in the docker group?)"

banner
log_step "Containerised build"
log_info "image: ${IMAGE}"
log_warn "requires --privileged for loop devices + mount"
if [[ "$(uname -s)" != "Linux" ]]; then
  log_warn "non-Linux Docker backends usually cannot create loop devices; CI on ubuntu-latest is recommended"
fi

mkdir -p "${ROOT}/out" "${ROOT}/build"

set -x
TTY_ARGS=()
if [[ -t 0 && -t 1 ]]; then
  TTY_ARGS=(-it)
fi
docker run --rm "${TTY_ARGS[@]}" \
  --privileged \
  --cap-add SYS_ADMIN \
  -v /dev:/dev \
  -v "${ROOT}:/work" \
  -w /work \
  -e "BUNNY_MIN_FREE_GB=${BUNNY_MIN_FREE_GB:-20}" \
  -e "BUNNY_OFFLINE=${BUNNY_OFFLINE:-0}" \
  -e "BUILD_ID=${BUILD_ID:-}" \
  "${IMAGE}" \
  bash -lc '
    set -euo pipefail
    pacman -Sy --noconfirm --needed archiso squashfs-tools libisoburn mtools dosfstools \
      gpg python zstd git >/dev/null
    # mkarchiso requires a non-interactive pacman keyring
    pacman-key --init >/dev/null 2>&1 || true
    ./build_bunny_os_iso.sh '"${PASSTHRU[*]:-}"'
  '
