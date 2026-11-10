#!/usr/bin/env bash
# fetch-decky.sh — build the Decky Loader + CSS Loader payload tarball for the
# Bun Bun OS update channel. Since pre9 the ISO does NOT bake the loader in:
# the image carries only the payload digest (packaging/bazzite/decky-payload.sha256)
# and bunny-decky-init downloads the payload from the pinned channel URL once
# first-boot setup is done. This script is the one place that builds that
# payload from the pinned upstream releases; CI never runs it.
set -euo pipefail
DECKY_VER="v3.3.1"
CSS_VER="v2.1.2"
HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="$HERE/../packaging/bazzite"
OUT="${PKG}/decky-payload"

case "$(uname -m)" in
    aarch64|arm64) DECKY_ASSET="PluginLoader-arm64" ;;
    *)             DECKY_ASSET="PluginLoader" ;;
esac

rm -rf "${OUT:?}/"* 2>/dev/null || true
mkdir -p "${OUT}/plugins"
curl -fsSL "https://github.com/SteamDeckHomebrew/decky-loader/releases/download/${DECKY_VER}/${DECKY_ASSET}" \
    -o "${OUT}/PluginLoader"
chmod 0755 "${OUT}/PluginLoader"
printf '%s\n' "${DECKY_VER}" > "${OUT}/.loader.version"
curl -fsSL "https://raw.githubusercontent.com/SteamDeckHomebrew/decky-loader/main/dist/plugin_loader-release.service" \
    -o "${OUT}/plugin_loader-release.service"
test -s "${OUT}/plugin_loader-release.service"

# CSS Loader ships as a Decky plugin zip; unzip so the plugin dir is ready to copy.
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
curl -fsSL "https://github.com/DeckThemes/SDH-CssLoader/releases/download/${CSS_VER}/SDH-CSSLoader-Decky.zip" \
    -o "${TMP}/cssloader.zip"
python3 -m zipfile -e "${TMP}/cssloader.zip" "${TMP}/x"
SRC="$(find "${TMP}/x" -maxdepth 2 -name plugin.json -printf '%h\n' | head -n 1)"
test -n "${SRC}" || { echo "plugin.json not found in CSS Loader zip" >&2; exit 1; }
rm -rf "${OUT}/plugins/SDH-CssLoader"
mv "${SRC}" "${OUT}/plugins/SDH-CssLoader"

test -x "${OUT}/PluginLoader"
test -f "${OUT}/.loader.version"
test -s "${OUT}/plugin_loader-release.service"
test -d "${OUT}/plugins/SDH-CssLoader"

# Deterministic tarball (sorted names, fixed owner/mtime) so the digest in
# decky-payload.sha256 stays meaningful across rebuilds.
PAYLOAD_TARBALL="${PKG}/decky-loader-${DECKY_VER}.tar.gz"
tar --sort=name --owner=0 --group=0 --numeric-owner \
    --mtime='UTC 2026-11-10' -czf "${PAYLOAD_TARBALL}" -C "${OUT}" .
(cd "${PKG}" && sha256sum "$(basename "${PAYLOAD_TARBALL}")" > "$(basename "${PAYLOAD_TARBALL}").sha256")
echo "decky payload ready: ${PAYLOAD_TARBALL} ($(du -sh "${PAYLOAD_TARBALL}" | cut -f1))"
cat "${PAYLOAD_TARBALL}.sha256"
