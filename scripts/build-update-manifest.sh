#!/usr/bin/env bash
# =============================================================================
#  build-update-manifest.sh — publish-side manifest for the Bun Bun payload
#  channel.  Run it next to a freshly built payload tarball:
#
#      scripts/build-update-manifest.sh out/portable/bunny-os-portable-*.tar.gz
#
#  It writes MANIFEST.json beside the tarball; both files upload to the
#  channel (archive.org item bun-bun-os-updates).  No API keys on the device:
#  the updater only ever does plain HTTPS downloads of these two files.
# =============================================================================
set -euo pipefail
TARBALL="${1:?usage: build-update-manifest.sh <payload.tar.gz> [out-dir]}"
OUT="${2:-$(dirname -- "${TARBALL}")}"
[[ -f "${TARBALL}" ]] || { echo "no such tarball: ${TARBALL}" >&2; exit 1; }

python3 - "$TARBALL" "$OUT" <<'PY'
import hashlib, json, os, sys, tarfile, time
tarball, out = sys.argv[1], sys.argv[2]
with tarfile.open(tarball, "r:gz") as t:
    top = sorted({m.name.split("/")[0] for m in t.getmembers() if "/" in m.name})[0]
    version = t.extractfile(top + "/VERSION").read().decode().strip()
    try:
        build = json.loads(t.extractfile(top + "/build-manifest.json").read().decode())
    except Exception:
        build = {}
seq = build.get("build_id") or time.strftime("%Y%m%d%H", time.gmtime())
try:
    seq = int(str(seq))
except ValueError:
    seq = int(time.strftime("%Y%m%d%H", time.gmtime()))
h = hashlib.sha256()
size = 0
with open(tarball, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 22), b""):
        h.update(chunk)
        size += len(chunk)
manifest = {
    "manifest_version": 1,
    "version": version,
    "sequence": seq,
    "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "payload": {"name": os.path.basename(tarball), "size": size, "sha256": h.hexdigest()},
    "notes": "Bun Bun payload channel: agent, bunhud, voice",
}
path = os.path.join(out, "MANIFEST.json")
with open(path, "w") as f:
    json.dump(manifest, f, indent=2, sort_keys=True)
    f.write("\n")
print(json.dumps(manifest, indent=2, sort_keys=True))
PY
