#!/usr/bin/env bash
# =============================================================================
#  recovery-smoke.sh — drive the recovery menu's disk picker without a disk.
#
#  Regression test for the "Replace Bunny OS drops straight back to the menu"
#  loop. The menu used to do
#
#      disk="$(pick_disk)"
#
#  which captured the numbered disk list ("1) /dev/nvme0n1 …") along with the
#  device name. The "type the disk name to confirm" prompt could never match, so
#  every action printed nothing useful and the menu redrew — indistinguishable
#  from a dead button.
#
#  The test loads the real function definitions from bunny-recovery (everything
#  above its entrypoint), stubs the disk list, and answers the prompts with piped
#  input. No root, no disks, no Linux-only tools: it runs in CI and on Windows.
#
#      bash tools/recovery-smoke.sh
# =============================================================================
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
awk '/^need_root "\$@"$/{exit} {print}' system/bin/bunny-recovery > "${tmp}/lib.sh"

if [[ ! -s "${tmp}/lib.sh" ]]; then
  echo "recovery-smoke: could not extract bunny-recovery functions" >&2
  exit 1
fi

fails=0
check() { # check <label> <expected> <actual>
  if [[ "$2" == "$3" ]]; then
    printf '  ok   %s\n' "$1"
  else
    printf '  FAIL %s\n       expected: %q\n       actual:   %q\n' "$1" "$2" "$3"
    fails=$((fails + 1))
  fi
}

# stage <name> <code> — the real functions plus one scenario, as a script
stage() {
  cat "${tmp}/lib.sh" > "${tmp}/$1"
  printf '%s\n' "$2" >> "${tmp}/$1"
}

ONE='/dev/nvme0n1\t476.9G\tBIWIN NA80Y1M10-512G'

# --- 1. a pick stores just the device name ----------------------------------
stage t1.sh "candidate_disks() { printf '${ONE}\\n'; }
PICKED_DISK=\"\"
pick_disk
printf 'RESULT=%s\\n' \"\${PICKED_DISK}\""
out="$(printf '1\n' | bash "${tmp}/t1.sh" 2>/dev/null)"
check "picker stores the device path only" "RESULT=/dev/nvme0n1" "$(grep '^RESULT=' <<<"${out}")"

# --- 2. the confirmation the old code could never satisfy -------------------
stage t2.sh "candidate_disks() { printf '${ONE}\\n'; }
PICKED_DISK=\"\"
pick_disk || exit 1
disk=\"\${PICKED_DISK}\"
confirm=\"\$(ask \"Type the disk name to confirm (\${disk})\")\" || exit 1
if [[ \"\${confirm}\" == \"\${disk}\" ]]; then echo MATCH; else echo \"MISMATCH:\${confirm}\"; fi"
out="$(printf '1\n/dev/nvme0n1\n' | bash "${tmp}/t2.sh" 2>/dev/null)"
check "typed confirmation matches the selected disk" "MATCH" "$(tail -n1 <<<"${out}")"

# --- 3. the second entry is the second disk, not the first ------------------
stage t3.sh "candidate_disks() { printf '/dev/sda\\t1T\\tSamsung\\n/dev/nvme0n1\\t476.9G\\tBIWIN\\n'; }
PICKED_DISK=\"\"
pick_disk
echo \"\${PICKED_DISK}\""
out="$(printf '2\n' | bash "${tmp}/t3.sh" 2>/dev/null)"
check "second entry selects the second disk" "/dev/nvme0n1" "$(tail -n1 <<<"${out}")"

# --- 4. a wrong confirmation is refused by name -----------------------------
stage t4.sh "candidate_disks() { printf '${ONE}\\n'; }
PICKED_DISK=\"\"
pick_disk || exit 1
disk=\"\${PICKED_DISK}\"
confirm=\"\$(ask confirm)\" || exit 1
[[ \"\${confirm}\" == \"\${disk}\" ]] && echo MATCH || { echo \"cancelled - expected '\${disk}'\"; exit 0; }"
out="$(printf '1\nnvme0n1\n' | bash "${tmp}/t4.sh" 2>/dev/null)"
check "wrong confirmation is rejected with the expected name" \
  "cancelled - expected '/dev/nvme0n1'" "$(tail -n1 <<<"${out}")"

# --- 5. closed stdin returns 3 instead of killing the menu ------------------
stage t5.sh "candidate_disks() { printf '${ONE}\\n'; }
if n=\"\$(ask \"Choice\" \"0\" < /dev/null)\"; then
  echo \"read ok:\${n}\"
else
  echo \"rc=\$?\"
fi
echo \"still alive\""
out="$(bash "${tmp}/t5.sh" 2>/dev/null)"
check "closed stdin reports rc=3" "rc=3" "$(sed -n 1p <<<"${out}")"
check "closed stdin does not end the menu" "still alive" "$(tail -n1 <<<"${out}")"

# --- 6. a bare Enter takes the default --------------------------------------
stage t6.sh "candidate_disks() { printf '${ONE}\\n'; }
PICKED_DISK=\"\"
pick_disk
echo \"\${PICKED_DISK}\""
out="$(printf '\n' | bash "${tmp}/t6.sh" 2>/dev/null)"
check "bare Enter takes disk 1" "/dev/nvme0n1" "$(tail -n1 <<<"${out}")"

# --- 7. out-of-range input is refused, not accepted as disk 1 --------------
stage t7.sh "candidate_disks() { printf '${ONE}\\n'; }
PICKED_DISK=\"\"
pick_disk || { echo refused; exit 1; }
echo \"accepted:\${PICKED_DISK}\""
out="$(printf '9\n' | bash "${tmp}/t7.sh" 2>/dev/null)"
check "out-of-range disk number is refused" "refused" "$(tail -n1 <<<"${out}")"

printf '\n%s\n' "$([[ ${fails} -eq 0 ]] && echo 'recovery picker: all checks passed' || echo "recovery picker: ${fails} failure(s)")"
exit "$([[ ${fails} -eq 0 ]] && echo 0 || echo 1)"
