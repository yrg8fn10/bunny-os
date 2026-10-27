#!/usr/bin/env python3
"""Behavioural checks for system/bin/bunny-setupd.

The privileged first-boot service is the riskiest new component: it is the only
thing that creates an account and it is the only listener the wizard talks to.
This test loads the script as a module, stubs the handful of system tools it
calls, and drives both the service object and its loopback HTTP API. It needs no
root, no NetworkManager, no systemd and no Arch host, so it runs on the build
machine and in CI:

    python3 tools/setupd-smoke.py
"""
from __future__ import annotations

import http.client
import importlib.machinery
import importlib.util
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "system" / "bin" / "bunny-setupd"

passed = 0
failed = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  ok   {label}")
    else:
        failed += 1
        print(f"  FAIL {label}" + (f"\n       {detail}" if detail else ""))


def load_module():
    loader = importlib.machinery.SourceFileLoader("bunny_setupd", str(TARGET))
    spec = importlib.util.spec_from_loader("bunny_setupd", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def main() -> int:
    mod = load_module()
    calls: list[list[str]] = []

    # Nothing in this test may touch the host. System tools are stubbed and
    # accounts are read from a fake /etc/passwd file that does not exist here.
    mod.run = lambda cmd, **kw: (calls.append(list(cmd)), FakeResult())[1]
    real_which = shutil.which
    shutil.which = lambda name: None
    real_human = mod.human_users

    tmp = Path(tempfile.mkdtemp(prefix="bunny-setupd-"))
    try:
        etc = tmp / "etc"
        state = tmp / "state"
        etc.mkdir()
        state.mkdir()
        (etc / "build-info.json").write_text(json.dumps({
            "version": "0.2.0", "channel": "beta", "build_id": "20261027T161341Z",
            "target": "deck", "target_name": "Steam Deck LCD",
        }), "utf-8")
        (etc / "version").write_text("0.2.0\n", "utf-8")
        (etc / "oobe-bootstrap").write_text("setup\n", "utf-8")
        (etc / "session.conf").write_text("BUNNY_USER=bunny\nBUNNY_MODE=gaming\n", "utf-8")

        service = mod.SetupService(state_dir=state, etc_dir=etc, dry_run=True)

        # tzdata lives at /usr/share/zoneinfo on the image; point the service at
        # a miniature copy so the validation path is testable off-target.
        zoneinfo = tmp / "zoneinfo"
        for zone in ("UTC", "Asia/Tokyo", "Europe/London"):
            (zoneinfo / zone).parent.mkdir(parents=True, exist_ok=True)
            (zoneinfo / zone).write_text(zone, "utf-8")
        (zoneinfo / "zone.tab").write_text(
            "UTC\t0\t+0000\tUTC\n"
            "JP\t+353916+1394441\tAsia/Tokyo\n"
            "GB\t+513030-0000731\tEurope/London\n", "utf-8")
        service.zoneinfo = zoneinfo

        print("\nversion and state")
        check(service.version == "0.2.0", "version comes from build-info.json", service.version)
        info = service.state()
        check(info["target_name"] == "Steam Deck LCD" and info["channel"] == "beta",
              "state reports the baked target and channel")
        check(info["mode"] == "oobe", "a missing marker means the wizard is pending", info["mode"])
        check(info["needs_account"] is True, "no human account is reported before setup")
        check(service.pending() is True, "pending() is true before the marker exists")
        (state / ".oobe-done").write_text("done\n", "utf-8")
        check(service.pending() is False, "pending() is false once the marker exists")
        check(service.state()["mode"] == "done", "state reports done after the marker")
        (state / ".oobe-done").unlink()

        print("\ntime zone validation")
        for bad in ("../../etc/passwd", "Not/AZone", "", "Europe/../.."):
            try:
                service.set_timezone(bad)
                check(False, f"rejects time zone {bad!r}")
            except mod.SetupError:
                check(True, f"rejects time zone {bad!r}")
        check(service.set_timezone("Asia/Tokyo") == "Asia/Tokyo", "accepts a real time zone")
        zones = {zone["zone"] for zone in service.timezones()}
        check({"UTC", "Asia/Tokyo", "Europe/London"} <= zones,
              "zone list comes from zone.tab", ",".join(sorted(zones))[:60])

        print("\naccount validation")
        cases = [
            ("Bunny", "pw12345678", "an upper-case username"),
            ("1player", "pw12345678", "a username starting with a digit"),
            ("setup", "pw12345678", "the reserved bootstrap name"),
            ("bunny-setup", "pw12345678", "the reserved bootstrap alias"),
            ("robin", "short", "a short password"),
            ("robin", "x" * 513, "an over-long password"),
            ("robin", "pw12345678", "control characters in the full name"),
        ]
        for name, password, label in cases:
            full = "Bad\nName" if "control" in label else "Robin"
            try:
                service.validate_account(name, full, password)
                check(False, f"rejects {label}")
            except mod.SetupError:
                check(True, f"rejects {label}")
        service.validate_account("robin", "Robin Player", "carrotcake9")
        check(True, "accepts a normal account")
        created = service.create_account("robin", "Robin Player", "carrotcake9")
        check(created.get("username") == "robin", "dry-run account creation reports the name")
        check(any(cmd and cmd[0] == "useradd" for cmd in calls) is False,
              "dry run never calls useradd")

        print("\nfinish")
        mod.human_users = lambda: ["robin"]
        check(service.finish()["session"] == "bunny-gaming", "dry-run finish selects Gaming Mode")
        check(not (state / ".oobe-done").exists(), "dry run does not write the marker")
        mod.human_users = lambda: []
        try:
            service.finish()
            check(False, "finish refuses when no desktop account exists")
        except mod.SetupError:
            check(True, "finish refuses when no desktop account exists")
        mod.human_users = real_human

        print("\nHTTP API")
        handler = mod.SetupHandler
        handler.service = service
        handler.ui_root = ROOT / "control-panel" / "ui"
        handler.token = "test-token-123"
        server = mod.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05},
                                  daemon=True)
        thread.start()

        def request(method: str, path: str, body: dict | None = None,
                    token: str | None = None, host: str = "127.0.0.1") -> tuple[int, dict, str]:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            headers = {"Host": f"{host}:{port}"}
            payload = None
            if body is not None:
                payload = json.dumps(body)
                headers["Content-Type"] = "application/json"
            if token:
                headers["X-Bunny-Setup"] = token
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            raw = response.read()
            conn.close()
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                data = {}
            return response.status, data, raw.decode("utf-8", "replace")

        try:
            status, data, _ = request("GET", "/api/health")
            check(status == 200 and data.get("service") == "bunny-setupd",
                  "health answers without a token", f"{status} {data}")

            status, _, _ = request("GET", "/api/state")
            check(status == 403, "state refuses a request without the token", str(status))

            status, data, _ = request("GET", "/api/state", token="wrong")
            check(status == 403, "state refuses a wrong token", str(status))

            status, data, _ = request("GET", "/api/state", token="test-token-123")
            check(status == 200 and data.get("version") == "0.2.0",
                  "state answers with the token", f"{status} {data.get('version')}")

            status, _, _ = request("POST", "/api/timezone", {"zone": "UTC"})
            check(status == 403, "writes refuse a request without the token", str(status))

            status, data, _ = request("POST", "/api/timezone", {"zone": "../../etc"},
                                      token="test-token-123")
            check(status == 400 and "time zone" in data.get("error", "").lower(),
                  "writes reject an invalid time zone", f"{status} {data}")

            status, data, _ = request("POST", "/api/account",
                                      {"username": "setup", "password": "carrotcake9"},
                                      token="test-token-123")
            check(status == 400 and "reserved" in data.get("error", "").lower(),
                  "account route rejects the reserved name", f"{status} {data}")

            status, _, _ = request("GET", "/api/health", host="evil.example")
            check(status == 403, "a foreign Host header is refused (DNS rebinding)", str(status))

            status, data, html = request("GET", "/setup/")
            check(status == 200 and "test-token-123" in html,
                  "index.html is served with the per-boot token", str(status))
            check("__BUNNY_SETUP_TOKEN__" not in html,
                  "the token placeholder never reaches the browser")

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", "/setup/", headers={"Host": f"127.0.0.1:{port}"})
            response = conn.getresponse()
            csp = response.getheader("Content-Security-Policy") or ""
            response.read()
            conn.close()
            check("frame-ancestors 'none'" in csp and "script-src 'self'" in csp,
                  "index.html is served with a locked-down CSP", csp[:60])

            status, _, _ = request("GET", "/../../etc/passwd")
            check(status in (403, 404), "path traversal is refused", str(status))

            status, _, body = request("GET", "/setup/setup.js")
            check(status == 200 and len(body) > 1000,
                  "the wizard module is served", str(status))
        finally:
            server.shutdown()
            server.server_close()
    finally:
        shutil.which = real_which
        mod.human_users = real_human
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    total = passed + failed
    print(f"{passed}/{total} checks passed" if failed == 0
          else f"{failed} of {total} checks FAILED")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
