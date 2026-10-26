#!/usr/bin/env bash
# Preflight: verify this host can actually produce a bootable Bunny OS image.
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

ALLOW_NON_ARCH=0
DRY_RUN=0

for arg in "$@"; do
  case "${arg}" in
    --allow-non-arch) ALLOW_NON_ARCH=1 ;;
    --dry-run)        DRY_RUN=1; ALLOW_NON_ARCH=1 ;;
    --help|-h)        echo "usage: preflight.sh [--dry-run] [--allow-non-arch]"; exit 0 ;;
    *) die "unknown argument: ${arg}" ;;
  esac
done

banner
log_step "Host preflight"

OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
ARCH="$(uname -m 2>/dev/null || echo unknown)"
MIN_FREE_GB=${BUNNY_MIN_FREE_GB:-25}

log_info "host      : ${OS_NAME} ${ARCH}"
log_info "archiso   : $(archiso_version)"
log_info "cpus      : $(cpus)"
log_info "free space: $(free_gb /) GB on /"

fatal=0
soft=0

# --- hard requirements ------------------------------------------------------
if is_linux; then
  printf '  %s✓%s Linux host\n' "${C_MINT}" "${C_RESET}"
else
  printf '  %s✗%s Linux host (found %s)\n' "${C_RED}" "${C_RESET}" "${OS_NAME}"
  log_error "mkarchiso needs a Linux kernel: loop devices, mount, mknod and root are required."
  fatal=1
fi

if is_arch; then
  printf '  %s✓%s Arch Linux (pacman + archiso repos)\n' "${C_MINT}" "${C_RESET}"
else
  if (( ALLOW_NON_ARCH )); then
    printf '  %s!%s Arch Linux (ignored: --allow-non-arch)\n' "${C_YELLOW}" "${C_RESET}"
  else
    printf '  %s✗%s Arch Linux (found a non-Arch distro)\n' "${C_RED}" "${C_RESET}"
    fatal=1
  fi
fi

if have mkarchiso; then
  printf '  %s✓%s mkarchiso present\n' "${C_MINT}" "${C_RESET}"
else
  printf '  %s✗%s mkarchiso missing\n' "${C_RED}" "${C_RESET}"
  fatal=1
fi

# Check binaries, not package names: squashfs-tools installs mksquashfs/unsquashfs
# and there is no `squashfs-tools` executable to find on PATH.
for cmd in pacman bsdtar mksquashfs unsquashfs xorriso openssl lsinitcpio awk sed find; do
  if have "${cmd}"; then
    printf '  %s✓%s %s\n' "${C_MINT}" "${C_RESET}" "${cmd}"
  else
    printf '  %s✗%s %s missing\n' "${C_RED}" "${C_RESET}" "${cmd}"
    fatal=1
  fi
done

if is_root; then
  printf '  %s✓%s running as root\n' "${C_MINT}" "${C_RESET}"
else
  printf '  %s✗%s root privileges (mkarchiso loop-mounts the airootfs)\n' "${C_RED}" "${C_RESET}"
  fatal=1
fi

AVAIL_GB="$(free_gb / || echo 0)"
if (( AVAIL_GB >= MIN_FREE_GB )); then
  printf '  %s✓%s %s GB free (>= %s GB)\n' "${C_MINT}" "${C_RESET}" "${AVAIL_GB}" "${MIN_FREE_GB}"
else
  printf '  %s✗%s only %s GB free (need %s GB)\n' "${C_RED}" "${C_RESET}" "${AVAIL_GB}" "${MIN_FREE_GB}"
  fatal=1
fi

# --- soft requirements ------------------------------------------------------
for cmd in shellcheck python3 zstd gpg; do
  if have "${cmd}"; then
    printf '  %s✓%s %s (optional)\n' "${C_DIM}" "${C_RESET}" "${cmd}"
  else
    printf '  %s!%s %s missing (optional)\n' "${C_YELLOW}" "${C_RESET}" "${cmd}"
    soft=$((soft + 1))
  fi
done

if [[ "${BUNNY_OFFLINE:-0}" != "1" ]] && ! curl -fsSL --max-time 5 https://geo.mirror.pkgbuild.com >/dev/null 2>&1; then
  printf '  %s!%s package mirrors unreachable (mkarchiso needs network)\n' "${C_YELLOW}" "${C_RESET}"
  soft=$((soft + 1))
fi

echo
if (( fatal > 0 )); then
  if (( DRY_RUN )); then
    log_warn "preflight failed, continuing because --dry-run was requested"
  else
    log_error "preflight failed — refusing to build a broken image."
    cat <<'EOF'

  Fix it with one of these:

    Arch host      sudo pacman -S --needed archiso squashfs-tools libisoburn
                   sudo ./build_bunny_os_iso.sh

    Any Linux host ./build_bunny_os_iso.sh --docker      (needs Docker + loop devices)
    No Linux host  push to GitHub; .github/workflows/build-iso.yml builds it in CI

  Windows/macOS cannot build this image directly: mkarchiso requires loop
  devices and mount(2). Use the Docker or CI path instead.
EOF
    exit 1
  fi
fi

if (( soft > 0 )); then
  log_warn "${soft} optional item(s) missing"
fi
log_info "preflight complete"
