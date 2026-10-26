#!/usr/bin/env bash
# Sign a release: sha256 + detached GPG signature + release notes stub.
# Usage: sign-release.sh <key-id> [out-dir] [iso-basename]
#
# With one ISO in out/, the basename is detected. When both a generic and a
# target image are present, pass the basename explicitly, for example:
#   sign-release.sh 0xBUNNY out BunnyOS-deck-installer
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
ROOT="$(cd -- "${SCRIPT_DIR}/.." >/dev/null 2>&1 && pwd -P)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

KEY="${1:?usage: sign-release.sh <gpg-key-id> [out-dir] [iso-basename]}"
OUT="${2:-${ROOT}/out}"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"

have gpg || die "gpg not installed"

ISO_BASE="${3:-}"
if [[ -z "${ISO_BASE}" ]]; then
  shopt -s nullglob
  isos=("${OUT}"/*.iso)
  (( ${#isos[@]} == 1 )) \
    || die "expected exactly one ISO in ${OUT}; pass its basename as the third argument"
  ISO_BASE="$(basename "${isos[0]}" .iso)"
fi
ISO="${OUT}/${ISO_BASE}.iso"
SHA="${ISO}.sha256"
[[ -f "${ISO}" ]] || die "no ISO at ${ISO}"
[[ -f "${SHA}" ]] || die "no checksum at ${SHA}"

log_step "Signing Bunny OS ${VERSION} (${ISO_BASE})"
( cd "${OUT}" && sha256sum -c "$(basename "${SHA}")" )

gpg --batch --yes --local-user "${KEY}" \
    --detach-sign --armor \
    -o "${SHA}.asc" \
    "${SHA}"

gpg --verify "${SHA}.asc" "${SHA}"

cat > "${OUT}/RELEASE-${VERSION}.md" <<EOF
# Bunny OS ${VERSION}

Built: $(timestamp)
Commit: $(git -C "${ROOT}" rev-parse --short HEAD 2>/dev/null || echo nogit)

## Artifacts
- \`${ISO_BASE}.iso\`
- \`${ISO_BASE}.iso.sha256\`
- \`${ISO_BASE}.iso.sha256.asc\` (signed with ${KEY})
- \`build-manifest.json\`

## Verify
\`\`\`
sha256sum -c ${ISO_BASE}.iso.sha256
gpg --verify ${ISO_BASE}.iso.sha256.asc ${ISO_BASE}.iso.sha256
\`\`\`
EOF

log_info "release notes: ${OUT}/RELEASE-${VERSION}.md"
