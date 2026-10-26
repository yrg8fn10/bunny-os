"""Integration test: the local HTTP API actually serves.

Runs entirely on loopback with an ephemeral port and no audio device.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.request
from dataclasses import replace
from pathlib import Path

from bunbun.config import load_config
from bunbun.service import AgentService, ApiServer


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["XDG_RUNTIME_DIR"] = self.tmp.name
        # The service reads ai.* from a settings file, not from AgentConfig.
        # Point it at a throwaway file so the test never touches /etc.
        settings_path = Path(self.tmp.name) / "settings.json"
        settings_path.write_text(
            json.dumps({"ai": {"enabled": True, "hint_level": "off",
                               "voice_enabled": False}}),
            encoding="utf-8",
        )
        self._old_settings_env = os.environ.get("BUNBUN_SETTINGS")
        os.environ["BUNBUN_SETTINGS"] = str(settings_path)
        config = replace(
            load_config(),
            data_dir=Path(self.tmp.name),
            voice_enabled=False,
            tts_backend="none",
            memory_enabled=True,
        )
        self.service = AgentService(config)
        self.service.start()
        self.server = ApiServer(("127.0.0.1", 0), self.service)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.service.stop()
        if self._old_settings_env is None:
            os.environ.pop("BUNBUN_SETTINGS", None)
        else:
            os.environ["BUNBUN_SETTINGS"] = self._old_settings_env
        self.tmp.cleanup()

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(self.url(path), timeout=5) as resp:
            return json.loads(resp.read().decode())

    def post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            self.url(path), data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def test_health(self):
        data = self.get("/health")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["voice_backend"], "null")
        self.assertFalse(data["kill_switch"])

    def test_status_shape(self):
        data = self.get("/v1/status")
        for key in ("agent", "engine", "watcher", "coop", "events"):
            self.assertIn(key, data)
        self.assertTrue(data["agent"]["local_only"])

    def test_policy_is_exposed(self):
        rules = {r["rule"] for r in self.get("/v1/policy")["rules"]}
        self.assertIn("anticheat", rules)
        self.assertIn("input-token", rules)

    def test_state_observation_is_accepted(self):
        data = self.post("/v1/state", {"game_id": "demo:1", "title": "Demo",
                                       "stuck_seconds": 10})
        self.assertIn("outcomes", data)
        self.assertEqual(self.get("/v1/state")["game_id"], "demo:1")

    def test_say_requires_text(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post("/v1/say", {})
        self.assertEqual(ctx.exception.code, 400)

    def test_hint_when_hints_disabled_reports_rule(self):
        data = self.post("/v1/hint", {})
        hint = data["hint"]
        self.assertFalse(hint["executed"])

    def test_memory_purge(self):
        self.post("/v1/state", {"game_id": "demo:2"})
        data = self.post("/v1/memory/purge", {})
        self.assertTrue(data["purged"])


if __name__ == "__main__":
    unittest.main()
