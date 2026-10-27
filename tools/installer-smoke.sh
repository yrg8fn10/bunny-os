#!/usr/bin/env bash
# =============================================================================
#  installer-smoke.sh — check the script the installer writes for the target.
#
#  bunny-install builds /root/bunny-postinstall.sh inside a heredoc and runs it
#  with arch-chroot. `bash -n installer/bunny-install` never parses that body, so
#  a broken line there is only discovered after a user's disk has been wiped and
#  the machine will not boot. This test renders the heredoc exactly the way the
#  installer does (dummy values, unquoted heredoc expansions) and checks the
#  result.
#
#      bash tools/installer-smoke.sh
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT

fails=0
check() { # check <label> <expected> <actual>
  if [[ "$2" == "$3" ]]; then
    printf '  ok   %s\n' "$1"
  else
    printf '  FAIL %s\n       expected: %q\n       actual:   %q\n' "$1" "$2" "$3"
    fails=$((fails + 1))
  fi
}

start="$(grep -n 'cat > "${TARGET}/root/bunny-postinstall.sh"' installer/bunny-install | cut -d: -f1)"
end="$(awk -v s="${start}" 'NR>s && $0=="POSTINSTALL" {print NR; exit}' installer/bunny-install)"
if [[ -z "${start}" || -z "${end}" ]]; then
  echo "installer-smoke: could not locate the post-install heredoc" >&2
  exit 1
fi

TARGET="${tmp}/target"
mkdir -p "${TARGET}/root"
TIMEZONE="UTC"; LOCALE="en_US.UTF-8"; HOSTNAME="bunnyos"; USERNAME="bunny"
ROOT_UUID="11111111-2222-3333-4444-555555555555"; EXTRA_KERNEL_ARGS=""
export TARGET TIMEZONE LOCALE HOSTNAME USERNAME ROOT_UUID EXTRA_KERNEL_ARGS

sed -n "${start},${end}p" installer/bunny-install > "${tmp}/frag.sh"

# Render both account modes exactly the way bunny-install does. OOBE=1 is the
# default (the wizard creates the account); OOBE=0 is the --user/BUNNY_PASSWORD
# path. Both bodies end up in the file because the condition is resolved at
# runtime, so this proves neither branch has a syntax error.
render() { # render <oobe> <username>
  local oobe="$1" user="$2" target="${tmp}/target-${1}"
  mkdir -p "${target}/root"
  TARGET="${target}" USERNAME="${user}" OOBE="${oobe}" \
    bash "${tmp}/frag.sh" || return 1
  printf '%s' "${target}/root/bunny-postinstall.sh"
}

script="$(render 1 "")" || { echo "installer-smoke: rendering the OOBE heredoc failed" >&2; exit 1; }
legacy="$(render 0 "bunny")" || { echo "installer-smoke: rendering the account heredoc failed" >&2; exit 1; }
[[ -s "${script}" && -s "${legacy}" ]] \
  || { echo "installer-smoke: heredoc produced no file" >&2; exit 1; }

# 1. the generated script must be valid bash
if bash -n "${script}" 2>"${tmp}/err" && bash -n "${legacy}" 2>>"${tmp}/err"; then
  check "generated post-install scripts parse" ok ok
else
  check "generated post-install scripts parse" ok "syntax error: $(head -n2 "${tmp}/err" | tr '\n' ' ')"
fi

# 2. the OOBE path must hand first boot to the wizard and delete the live login
check "OOBE install drops the live bunny user" "yes" \
  "$(grep -q 'userdel bunny' "${script}" && echo yes || echo no)"
check "OOBE install clears the wizard marker" "yes" \
  "$(grep -q 'rm -f /var/lib/bunny/.oobe-done' "${script}" && echo yes || echo no)"
check "OOBE install seeds the setup session" "yes" \
  "$(grep -q 'SDDM_SESSION=bunny-setup' "${script}" && echo yes || echo no)"
check "OOBE install enables bunny-setupd" "yes" \
  "$(grep -q 'systemctl enable bunny-setupd.service' "${script}" && echo yes || echo no)"
check "OOBE install disables the text prompt" "yes" \
  "$(grep -q 'systemctl disable bunny-setup.service' "${script}" && echo yes || echo no)"

# 2. the archiso initramfs drop-in has to go before mkinitcpio runs, otherwise
#    the installed system builds an initramfs that looks for the USB stick.
rm_line="$(grep -n '^rm -f /etc/mkinitcpio.conf.d/archiso.conf' "${script}" | cut -d: -f1)"
mk_line="$(grep -n '^mkinitcpio -P' "${script}" | cut -d: -f1)"
check "post-install removes archiso.conf" "yes" "$([[ -n "${rm_line}" ]] && echo yes || echo no)"
check "archiso.conf is removed before mkinitcpio -P" "yes" \
  "$([[ -n "${rm_line}" && -n "${mk_line}" && "${rm_line}" -lt "${mk_line}" ]] && echo yes || echo no)"

# 3. /etc/hosts must carry the expanded hostname, not the literal ${HOSTNAME}
check "/etc/hosts has the hostname expanded" "yes" \
  "$(grep -q '127.0.1.1 *bunnyos' "${script}" && echo yes || echo no)"
check "/etc/hosts is not left unexpanded" "yes" \
  "$(grep -q '\${HOSTNAME}' "${script}" && echo no || echo yes)"

# 4. one -G with a comma list; repeated -G flags would keep only the last group
check "useradd gets a single -G" "1" "$(grep -c 'UG_ARGS=(-G' "${script}")"
check "useradd does not hardcode a group list" "yes" \
  "$(grep -q 'wheel,input,video,audio' "${script}" && echo no || echo yes)"

# 5. an install must never leave root with a password or a live sudoers rule
check "post-install locks root" "yes" \
  "$(grep -q 'passwd -l root' "${script}" && echo yes || echo no)"
check "post-install drops the live sudoers rule" "yes" \
  "$(grep -q 'rm -f /etc/sudoers.d/10-bunny-live' "${script}" && echo yes || echo no)"

printf '\n%s\n' "$([[ ${fails} -eq 0 ]] && echo 'installer post-install: all checks passed' || echo "installer post-install: ${fails} failure(s)")"
exit "$([[ ${fails} -eq 0 ]] && echo 0 || echo 1)"
