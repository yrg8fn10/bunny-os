#!/usr/bin/env bash
# fetch-decky.sh — download pinned Decky Loader + CSS Loader releases into
# packaging/bazzite/decky-bake/ so the image build bakes them in. Runs in CI
# (has network) before the payload image is built; the ISO itself installs
# offline. Pinned so upstream releases cannot change an ISO under us.
set -euo pipefail
DECKY_VER="v3.3.1"
CSS_VER="v2.1.2"
OUT="$(dirname "$0")/../packaging/bazzite/decky-bake"

case "$(uname -m)" in
    aarch64|arm64) DECKY_ASSET="PluginLoader-arm64" ;;
    *)             DECKY_ASSET="PluginLoader" ;;
esac

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
test -d "${OUT}/plugins/SDH-CssLoader"
echo "decky-bake ready: $(cat "${OUT}/.loader.version") + CSS Loader ${CSS_VER} ($(du -sh "${OUT}" | cut -f1))"
