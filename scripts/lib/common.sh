#!/usr/bin/env bash
# Shared helpers for the Bunny OS build pipeline.
# Sourced, never executed directly.

# shellcheck shell=bash

if [[ -n "${BUNNY_COMMON_SH:-}" ]]; then
  return 0
fi
BUNNY_COMMON_SH=1

# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
if [[ -t 1 && "${NO_COLOR:-}" == "" ]]; then
  C_RESET=$'\033[0m'
  C_BOLD=$'\033[1m'
  C_DIM=$'\033[2m'
  C_PINK=$'\033[38;5;213m'
  C_MINT=$'\033[38;5;121m'
  C_YELLOW=$'\033[33m'
  C_RED=$'\033[31m'
  C_BLUE=$'\033[38;5;111m'
else
  C_RESET="" C_BOLD="" C_DIM="" C_PINK="" C_MINT="" C_YELLOW="" C_RED="" C_BLUE=""
fi

banner() {
  printf '%s\n' "${C_PINK}${C_BOLD}"
  cat <<'EOF'
   /)   /)
  ( (  ( (
   \ )  \ )     B U N N Y   O S
    \(    \)    -----------------
     \_)  \_)   steam-first. bunny-approved.
EOF
  printf '%s\n' "${C_RESET}"
}

log_info()  { printf '%s[bunny]%s %s\n' "${C_MINT}" "${C_RESET}" "$*"; }
log_step()  { printf '\n%s==> %s%s\n' "${C_PINK}${C_BOLD}" "$*" "${C_RESET}"; }
log_warn()  { printf '%s[warn]%s %s\n' "${C_YELLOW}" "${C_RESET}" "$*" >&2; }
log_error() { printf '%s[fail]%s %s\n' "${C_RED}" "${C_RESET}" "$*" >&2; }
log_debug() { [[ "${BUNNY_VERBOSE:-0}" == "1" ]] && printf '%s[debug]%s %s\n' "${C_DIM}" "${C_RESET}" "$*" || true; }

die() {
  log_error "$*"
  exit 1
}

have() { command -v "$1" >/dev/null 2>&1; }

require_cmd() {
  local missing=()
  local cmd
  for cmd in "$@"; do
    have "${cmd}" || missing+=("${cmd}")
  done
  if (( ${#missing[@]} > 0 )); then
    die "missing required command(s): ${missing[*]}"
  fi
}

confirm() {
  local prompt="${1:-Continue?}" reply
  if [[ "${BUNNY_ASSUME_YES:-0}" == "1" ]]; then
    return 0
  fi
  read -r -p "${prompt} [y/N] " reply || return 1
  [[ "${reply}" =~ ^[Yy]$ ]]
}

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
is_linux()   { [[ "$(uname -s 2>/dev/null)" == "Linux" ]]; }
is_arch()    { [[ -f /etc/arch-release ]]; }
is_root()    { [[ "${EUID:-$(id -u)}" -eq 0 ]]; }
is_ci()      { [[ "${CI:-}" == "true" || "${GITHUB_ACTIONS:-}" == "true" ]]; }

cpus() {
  if have nproc; then nproc; else echo 4; fi
}

free_gb() {
  local path="${1:-/}"
  df -Pk "${path}" 2>/dev/null | awk 'NR==2 {printf "%d", $4/1048576}'
}

human_size() {
  local path="$1"
  if have du; then du -sh "${path}" 2>/dev/null | cut -f1; else echo "?"; fi
}

archiso_version() {
  if [[ -f /usr/lib/archiso/VERSION ]]; then
    tr -d '[:space:]' < /usr/lib/archiso/VERSION
  elif have pacman; then
    pacman -Q archiso 2>/dev/null | awk '{print $2}' | sed 's/-[0-9.]*$//'
  else
    echo "unknown"
  fi
}

# Resolve the archiso releng profile shipped with the installed package.
releng_profile() {
  local p
  for p in /usr/share/archiso/configs/releng /usr/share/archiso/configs/baseline; do
    [[ -d "${p}" ]] && { printf '%s' "${p}"; return 0; }
  done
  return 1
}

# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------
safe_rmrf() {
  local target="$1"
  [[ -n "${target}" ]] || die "safe_rmrf: empty path"
  [[ "${target}" != "/" && "${target}" != "${HOME}" ]] || die "safe_rmrf: refusing ${target}"
  case "${target}" in
    */build/*|*/build|*/out/*|*/out|*/stage|*/archiso-work) rm -rf -- "${target}" ;;
    *) die "safe_rmrf: refusing to delete ${target}" ;;
  esac
}

write_file() {
  local path="$1"
  mkdir -p -- "$(dirname -- "${path}")"
  cat > "${path}"
}

sha256_of() {
  local file="$1"
  if have sha256sum; then sha256sum "${file}" | awk '{print $1}';
  elif have shasum; then shasum -a 256 "${file}" | awk '{print $1}';
  else die "no sha256sum/shasum available"; fi
}

timestamp() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
stamp_short() { date -u +"%Y%m%dT%H%M%SZ"; }

# ---------------------------------------------------------------------------
# Templating — replaces @TOKEN@ placeholders from KEY=VALUE pairs
# ---------------------------------------------------------------------------
render_tokens() {
  local root="$1"; shift
  local pair key value f
  # syslinux.cfg ends in .cfg, not .conf: leaving it out shipped the unrendered
  # version token in the BIOS menu tree of every image.
  local -a find_args=(-type f \( -name '*.conf' -o -name '*.cfg' -o -name '*.json' -o -name '*.desktop' \
    -o -name '*.service' -o -name '*.timer' -o -name '*.sh' -o -name '*.py' \
    -o -name '*.js' -o -name '*.css' -o -name '*.html' -o -name '*.md' \
    -o -name 'os-release' -o -name 'motd' \))

  for pair in "$@"; do
    key="${pair%%=*}"
    value="${pair#*=}"
    value="${value//&/\\&}"
    value="${value//\//\\/}"
    while IFS= read -r -d '' f; do
      grep -Iq . "${f}" 2>/dev/null || continue
      if grep -qF "@${key}@" "${f}" 2>/dev/null; then
        sed -i "s|@${key}@|${value}|g" "${f}"
        log_debug "rendered @${key}@ in ${f#"${root}"/}"
      fi
    done < <(find "${root}" "${find_args[@]}" -print0 2>/dev/null)
  done
}

# ---------------------------------------------------------------------------
# JSON helpers (no external deps)
# ---------------------------------------------------------------------------
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\t'/\\t}"
  printf '%s' "${s}"
}

json_kv() {
  # json_kv key value [key value ...] -> one-line JSON object
  local out="{" sep="" k v
  while (( $# >= 2 )); do
    k="$1"; v="$2"; shift 2
    out+="${sep}\"$(json_escape "${k}")\":\"$(json_escape "${v}")\""
    sep=","
  done
  printf '%s}' "${out}"
}

# ---------------------------------------------------------------------------
# Assertions used by validators
# ---------------------------------------------------------------------------
FAILED_CHECKS=0
check() {
  local label="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  %s✓%s %s\n' "${C_MINT}" "${C_RESET}" "${label}"
  else
    printf '  %s✗%s %s\n' "${C_RED}" "${C_RESET}" "${label}"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
  fi
}

check_fail() {
  printf '  %s✗%s %s (%s)\n' "${C_RED}" "${C_RESET}" "$1" "${2:-}"
  FAILED_CHECKS=$((FAILED_CHECKS + 1))
}

check_summary() {
  if (( FAILED_CHECKS > 0 )); then
    log_error "${FAILED_CHECKS} check(s) failed"
    return 1
  fi
  log_info "all checks passed"
}
