#!/usr/bin/env bash
# =============================================================================
#  native-updater-test.sh — offline test harness for bunny-update-native.
#  Runs the full state machine against a local fake channel (manifest + image
#  server) with the stub deploy backend. No root, no real filesystem.
# =============================================================================
set -Eeuo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
updater="${here}/../system/bin/bunny-update-native"
work="$(mktemp -d)"
content="${work}/content"
state="${work}/state"
cache="${work}/cache"
mkdir -p "${content}" "${state}" "${cache}"

PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ok: $1"; }
fail() { FAIL=$((FAIL+1)); echo "  FAIL: $1"; }
assert_eq() { # $1=what $2=expected $3=actual
  if [[ "$2" == "$3" ]]; then ok "$1"; else fail "$1 (expected '$2', got '$3')"; fi
}

# --- fake channel (binds an OS-assigned port and publishes it) -------------------
cat > "${work}/server.py" <<'PY'
import http.server, os, sys
content = sys.argv[1]
class H(http.server.BaseHTTPRequestHandler):
    def _serve(self):
        path = os.path.join(content, "NATIVE-MANIFEST.json") \
            if self.path.startswith("/NATIVE-MANIFEST") \
            else os.path.join(content, os.path.basename(self.path))
        if not os.path.exists(path):
            self.send_error(404); return
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        with open(os.path.join(content, "requests.log"), "a") as f:
            f.write("GET %s Range=%s\n" % (self.path, rng or "-"))
        start = 0
        code = 200
        headers = {"Content-Length": str(size)}
        if rng and rng.startswith("bytes="):
            start = int(rng.split("-")[0][6:])
            code = 206
            headers = {"Content-Range": "bytes %d-%d/%d" % (start, size - 1, size),
                       "Content-Length": str(size - start)}
        self.send_response(code)
        for k, v in headers.items(): self.send_header(k, v)
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            self.wfile.write(f.read())
    do_GET = _serve
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
open(os.path.join(content, "port"), "w").write(str(srv.server_address[1]))
srv.serve_forever()
PY

image="${content}/update.img"
head -c 1048576 /dev/urandom > "${image}"
real_sha="$(sha256sum "${image}" | cut -d' ' -f1)"
write_manifest() { # $1=version $2=sha256 $3=size
  python3 - "$1" "$2" "$3" "${port}" "${content}" <<'PY'
import json, sys
version, sha, size, port, content = sys.argv[1:6]
m = {"native": {"version": version,
     "image_url": "http://127.0.0.1:%s/update.img" % port,
     "sha256": sha, "size": int(size) if size else 0,
     "changelog": "test channel"}}
json.dump(m, open(content + "/NATIVE-MANIFEST.json", "w"))
PY
}

run() { env "${UPD_ENV[@]}" "${updater}" "$@" >/dev/null 2>&1; }
get_state() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))' "${state}/state.json" "$1"; }

python3 "${work}/server.py" "${content}" >/dev/null 2>&1 &
srvpid=$!
trap 'kill ${srvpid} 2>/dev/null; rm -rf "${work}"' EXIT

# wait for the server to publish its port and accept connections (startup race)
port=""
for _ in $(seq 1 50); do
  [[ -f "${content}/port" ]] && port="$(cat "${content}/port")" && break
  sleep 0.2
done
[[ -n "${port}" ]] || { echo "FAIL: fake channel never started"; exit 1; }
for _ in $(seq 1 25); do
  python3 -c "import socket; s=socket.socket(); s.connect(('127.0.0.1', ${port})); s.close()" 2>/dev/null && break
  sleep 0.2
done

UPD_ENV=(BUNNY_ALLOW_NONROOT=1 BUNNY_STAGE_BACKEND=stub
         BUNNY_UPDATE_STATE_DIR="${state}" BUNNY_UPDATE_CACHE_DIR="${cache}"
         BUNNY_RUNNING_VERSION="0.2.0-beta9"
         BUNNY_NATIVE_MANIFEST_URL="http://127.0.0.1:${port}/NATIVE-MANIFEST.json")

echo "== CHECK =="
# 1. channel offline -> stays IDLE, exits clean
run --check --manifest-url "http://127.0.0.1:1/nope"
assert_eq "offline check stays IDLE" "IDLE" "$(get_state phase)"
# 2. up-to-date -> nothing to do
write_manifest "0.2.0-beta9" "${real_sha}" 1048576
run --check
assert_eq "same version -> IDLE" "IDLE" "$(get_state phase)"
# 3. newer version -> CHECK carries the candidate
write_manifest "0.2.0-beta10" "${real_sha}" 1048576
run --check
assert_eq "newer version -> CHECK" "CHECK" "$(get_state phase)"
assert_eq "candidate version recorded" "0.2.0-beta10" "$(get_state version)"

echo "== PULL + WATCHDOG RESUME =="
# 4. full pull
run --pull
assert_eq "pulled file exists" "0" "$([[ -f "${cache}/0.2.0-beta10.img" ]]; echo $?)"
assert_eq "pulled size matches" "1048576" "$(stat -c%s "${cache}/0.2.0-beta10.img")"
# 5. simulate a dead download at byte 524288; resume must continue, not restart
head -c 524288 /dev/urandom > "${cache}/0.2.0-beta10.img"
run --pull
assert_eq "resumed pull completes" "1048576" "$(stat -c%s "${cache}/0.2.0-beta10.img")"
grep -q "Range=bytes=524288-" "${content}/requests.log" \
  && ok "resume sent Range from the exact byte offset" \
  || fail "no Range header in the server log"

echo "== VERIFY =="
# 6. corrupted expectation -> three attempts, then surface, never stage
#    (the digest the state carries at CHECK time is the one VERIFY enforces)
cp "${image}" "${cache}/0.2.0-beta10.img"
python3 -c '
import json, sys
p = sys.argv[1]
s = json.load(open(p)); s["sha256"] = "0" * 64
json.dump(s, open(p, "w"))' "${state}/state.json"
rc=0; run --verify || rc=$?
assert_eq "digest mismatch exits nonzero" "1" "${rc}"
assert_eq "mismatch -> ERROR surfaced" "ERROR" "$(get_state phase)"
# 7. correct digest -> verified
cp "${image}" "${cache}/0.2.0-beta10.img"
write_manifest "0.2.0-beta10" "${real_sha}" 1048576
python3 -c '
import json, sys
p = sys.argv[1]
s = json.load(open(p))
s["pull_attempts"] = 0; s["image"] = None; s["sha256"] = sys.argv[2]
json.dump(s, open(p, "w"))' "${state}/state.json" "${real_sha}"
run --pull; run --verify
assert_eq "digest ok -> verified" "True" "$(get_state verified)"

echo "== STAGE + APPLY =="
run --stage
assert_eq "stage -> READY" "READY" "$(get_state phase)"
assert_eq "staged version marker" "0.2.0-beta10" "$(cat "${state}/staged/version")"
run --apply
assert_eq "no consent -> still READY" "READY" "$(get_state phase)"
run --apply --yes
assert_eq "consent -> APPLY" "APPLY" "$(get_state phase)"
assert_eq "applied marker" "0" "$([[ -f "${state}/applied" ]]; echo $?)"

echo "== HEALTH =="
# 8. healthy probe -> IDLE, counters cleared
LIVE_ENV=("${UPD_ENV[@]}" BUNNY_HEALTH_URL="http://127.0.0.1:${port}/NATIVE-MANIFEST.json")
env "${LIVE_ENV[@]}" "${updater}" --health >/dev/null 2>&1
assert_eq "healthy boot -> IDLE" "IDLE" "$(get_state phase)"
# 9. back to APPLY, then three unhealthy probes auto-rollback
run --stage; run --apply --yes
DEAD_ENV=("${UPD_ENV[@]}" BUNNY_HEALTH_URL="http://127.0.0.1:1/v1/health")
env "${DEAD_ENV[@]}" "${updater}" --health >/dev/null 2>&1 || true
env "${DEAD_ENV[@]}" "${updater}" --health >/dev/null 2>&1 || true
assert_eq "two failures -> UNHEALTHY" "UNHEALTHY" "$(get_state phase)"
env "${DEAD_ENV[@]}" "${updater}" --health >/dev/null 2>&1 || true
assert_eq "third failure -> auto rollback" "IDLE" "$(get_state phase)"
assert_eq "rollback marker" "0" "$([[ -f "${state}/rolled-back" ]]; echo $?)"
assert_eq "bad version recorded" "0.2.0-beta10" "$(cat "${state}/bad-versions.txt")"

echo "== BAD-VERSION SKIP + RECOVERY =="
run --check
assert_eq "bad version skipped on next check" "bad-version-skipped" "$(get_state check_result)"
write_manifest "0.2.0-beta11" "${real_sha}" 1048576
run --check
assert_eq "newer version after rollback -> CHECK" "CHECK" "$(get_state phase)"

echo
echo "${PASS} passed, ${FAIL} failed"
[[ "${FAIL}" -eq 0 ]]
