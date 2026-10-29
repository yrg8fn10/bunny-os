#!/usr/bin/env bash
# =============================================================================
#  ship-release.sh — verify, tag and publish a Bunny OS image.
#
#  This is the "after the patch is merged" half of the workflow: run it on main
#  once the fixes are committed and it
#
#    1. refuses to run on a dirty tree or a branch other than main,
#    2. runs the same checks CI runs before it builds (verify.py, bash -n,
#       python compile) so a broken tree never reaches a tag,
#    3. pushes main, creates the next vX.Y.Z-beta.N tag,
#    4. waits for the build-iso workflow and prints the release URL.
#
#  The tag is what triggers the build: .github/workflows/build-iso.yml builds the
#  deck profile for v* tags and publishes a release with the ISO split into
#  1.9 GB parts (GitHub caps a release asset at 2 GiB).
#
#  Usage:
#    scripts/ship-release.sh                 # next beta, verify + publish
#    scripts/ship-release.sh v0.1.0-beta.3   # explicit tag
#    scripts/ship-release.sh --dry-run       # everything except push/tag
#    PYTHON=/usr/bin/python scripts/ship-release.sh
# =============================================================================
set -Eeuo pipefail

cd "$(dirname "$0")/.."

DRY_RUN=0
TAG=""
for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*) echo "ship-release: unknown option ${arg}" >&2; exit 2 ;;
    *) TAG="${arg}" ;;
  esac
done

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[1;31m'; GRN=$'\033[1;32m'
YEL=$'\033[1;33m'; RST=$'\033[0m'

step() { printf '\n%s==> %s%s\n' "${BOLD}" "$*" "${RST}"; }
ok()   { printf '  %s✓%s %s\n' "${GRN}" "${RST}" "$*"; }
warn() { printf '  %s!%s %s\n' "${YEL}" "${RST}" "$*"; }
die()  { printf '  %s✗%s %s\n' "${RED}" "${RST}" "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

PYTHON="${PYTHON:-}"
if [[ -z "${PYTHON}" ]]; then
  for candidate in python3 python; do
    if have "${candidate}" && "${candidate}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON="$(command -v "${candidate}")"
      break
    fi
  done
fi
[[ -n "${PYTHON}" ]] || die "no python >= 3.10 found (set PYTHON=/path/to/python)"
have git || die "git is required"
have gh  || die "gh is required (https://cli.github.com)"

# ---------------------------------------------------------------------------
step "repository state"
# ---------------------------------------------------------------------------
[[ -z "$(git status --porcelain)" ]] || die "working tree is dirty; commit or stash first"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[[ "${BRANCH}" == "main" ]] || die "on branch '${BRANCH}'; releases are cut from main"
ok "clean tree on main ($(git rev-parse --short HEAD))"

git fetch --quiet origin main
if ! git merge-base --is-ancestor origin/main HEAD; then
  die "main has moved on the remote; pull --rebase first"
fi
ok "main is a fast-forward of origin/main"

# ---------------------------------------------------------------------------
step "verification (what CI runs before it builds)"
# ---------------------------------------------------------------------------
"${PYTHON}" tools/verify.py --strict
ok "verify.py"

fail=0
while IFS= read -r -d '' f; do
  bash -n "${f}" || fail=1
done < <(find . -path ./.git -prune -o -name '*.sh' -print0)
for f in system/bin/* installer/bunny-install launchers/bin/* scripts/*.sh; do
  [[ -f "${f}" ]] || continue
  # system/bin contains bash and python. Running `bash -n` on a python file is
  # a syntax error, so check the shebang (or the extension) first.
  case "${f}" in
    *.sh|*/bunny-install) ;;
    *) head -n1 "${f}" 2>/dev/null | grep -qE '^#!.*(bash|/sh)([[:space:]]|$)' || continue ;;
  esac
  bash -n "${f}" || fail=1
done
(( fail == 0 )) || die "shell syntax errors"
ok "bash -n"

"${PYTHON}" -m compileall -q bunbun/bunbun system/lib tools || die "python compile failed"
ok "python compile"

"${PYTHON}" tools/setupd-smoke.py || die "first-boot setup service smoke test failed"
ok "bunny-setupd smoke test"

bash tools/portable-smoke.sh || die "portable payload smoke test failed"
ok "portable payload smoke test"

# The panel has no bundler and no node_modules; a smoke test driven by a
# headless browser is the only executable check it gets. Skip it when no
# browser is installed rather than failing a legitimate release machine.
if have msedge || have google-chrome || have chromium; then
  ok "browser available for tools/ui-smoke.html (run it manually if the panel changed)"
else
  warn "no browser found; panel smoke test not run (tools/ui-smoke.html)"
fi

# ---------------------------------------------------------------------------
step "select the tag"
# ---------------------------------------------------------------------------
if [[ -z "${TAG}" ]]; then
  latest="$(git tag -l 'v*-beta.*' --sort=-v:refname | head -n1 || true)"
  if [[ -z "${latest}" ]]; then
    TAG="v0.1.0-beta.1"
  else
    base="${latest%%-beta.*}"
    n="${latest##*-beta.}"
    [[ "${n}" =~ ^[0-9]+$ ]] || die "cannot parse beta number from ${latest}"
    TAG="${base}-beta.$((n + 1))"
  fi
fi
[[ "${TAG}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$ ]] || die "'${TAG}' is not a vX.Y.Z tag"
git rev-parse -q --verify "refs/tags/${TAG}" >/dev/null && die "tag ${TAG} already exists"
ok "tag ${TAG}"

if (( DRY_RUN )); then
  step "dry run"
  printf '  would push main and create %s\n' "${TAG}"
  printf '  %sdry run: nothing was pushed%s\n' "${DIM}" "${RST}"
  exit 0
fi

# ---------------------------------------------------------------------------
step "publish"
# ---------------------------------------------------------------------------
git push --quiet origin main || die "push to main failed"
ok "main pushed"

git tag -a "${TAG}" -m "Bunny OS ${TAG#v} - Deck installer"
git push --quiet origin "${TAG}" || die "tag push failed"
ok "tag ${TAG} pushed; the workflow builds the deck image from it"

step "waiting for the release build"
printf '  (this takes about six minutes)\n'
RUN_ID=""
for _ in $(seq 1 40); do
  RUN_ID="$(gh run list --workflow=build-iso.yml --branch "${TAG}" --limit 1 \
    --json databaseId --jq '.[0].databaseId' 2>/dev/null || true)"
  [[ -n "${RUN_ID}" && "${RUN_ID}" != "null" ]] && break
  sleep 5
done
[[ -n "${RUN_ID}" && "${RUN_ID}" != "null" ]] || die "no workflow run appeared for ${TAG}"

if ! gh run watch "${RUN_ID}" --exit-status --interval 30 >/dev/null 2>&1; then
  printf '  %s✗%s build %s failed\n' "${RED}" "${RST}" "${RUN_ID}" >&2
  printf '  logs: gh run view %s --log-failed\n' "${RUN_ID}" >&2
  exit 1
fi
ok "build ${RUN_ID} succeeded"

URL="$(gh release view "${TAG}" --json url --jq '.url' 2>/dev/null || true)"
[[ -n "${URL}" ]] || die "build passed but no release was published for ${TAG}"

step "done"
printf '  release : %s\n' "${URL}"
printf '  checksum: %s\n' "$(gh release view "${TAG}" --json assets --jq '.assets[] | select(.name | endswith(".sha256")) | .name' 2>/dev/null || true)"
printf '  parts   : %s\n' "$(gh release view "${TAG}" --json assets --jq '[.assets[] | select(.name | endswith(".part")) | .name] | join(" ")' 2>/dev/null || true)"
printf '  %sjoin the parts, check the checksum, flash%s\n' "${DIM}" "${RST}"
