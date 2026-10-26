#!/usr/bin/env bash
# Safely flash a Bunny OS image to removable media.
# Usage: sudo flash-usb.sh <image.iso> <block-device>
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

IMG="${1:?usage: flash-usb.sh <image.iso> <block-device>}"
DEV="${2:?usage: flash-usb.sh <image.iso> <block-device>}"

[[ -f "${IMG}" ]] || die "image not found: ${IMG}"
[[ -b "${DEV}" ]] || die "not a block device: ${DEV}"
is_root || die "must run as root"
[[ "${DEV}" != *"nvme0n1"* ]] || die "refusing to write ${DEV} (system disk heuristic)"

# Verify checksum if the sibling file exists.
if [[ -f "${IMG}.sha256" ]]; then
  log_info "verifying checksum"
  (cd "$(dirname "${IMG}")" && sha256sum -c --quiet "$(basename "${IMG}").sha256") \
    || die "checksum mismatch — refusing to flash"
fi

SIZE="$(lsblk -dno SIZE "${DEV}" 2>/dev/null || echo unknown)"
MODEL="$(lsblk -dno MODEL "${DEV}" 2>/dev/null || echo unknown)"
log_warn "about to ERASE ${DEV} (${MODEL}, ${SIZE})"
lsblk "${DEV}" || true
confirm "Type 'yes' to continue" || die "aborted"
[[ "${BUNNY_ASSUME_YES:-0}" == "1" ]] || { read -r -p "confirm again: " a; [[ "${a}" == "yes" ]] || die "aborted"; }

log_info "writing ${IMG} -> ${DEV}"
dd if="${IMG}" of="${DEV}" bs=16M status=progress oflag=sync conv=fsync
sync
log_info "flushing kernel buffers"
blockdev --flushbufs "${DEV}" 2>/dev/null || true
log_info "done. You can unplug ${DEV}."
