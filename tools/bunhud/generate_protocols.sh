#!/bin/sh
# Regenerates wlr_layer_shell_unstable_v1.py from the protocol XML.
# Requires: pip install pywayland
# The v0 daemon does not use layer-shell popups, so the get_popup request
# (which would need xdg-shell) is stripped from a local copy of the XML.
# wayland.xml comes from the wayland project; layer-shell from wlr-protocols.
set -e
cd "$(dirname "$0")"
[ -f protocols/wlr-layer-shell-v0.xml ] || python3 - <<'PY'
import re
src = open('protocols/wlr-layer-shell-unstable-v1.xml').read()
out = re.sub(r'\s*<request name="get_popup">.*?</request>', '', src, flags=re.S)
open('protocols/wlr-layer-shell-v0.xml', 'w').write(out)
PY
PKG_CONFIG="${PKG_CONFIG:-pkg-config}" python3 -m pywayland.scanner \
    -i protocols/wayland.xml protocols/wlr-layer-shell-v0.xml -o .
echo "regenerated wlr_layer_shell_unstable_v1.py"
