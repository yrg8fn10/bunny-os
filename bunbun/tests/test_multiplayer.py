"""Tests for the experimental multiplayer join module."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bunbun.multiplayer import (
    JoinConfig,
    MultiplayerConfigError,
    build_launch_command,
    doctor,
    load_config,
    match_game,
)


class FakeGame:
    def __init__(self, name: str, path: str = "/games/x"):
        self.name = name
        self._path = path

    @property
    def path(self) -> str:
        return self._path


class LoadConfigTests(unittest.TestCase):
    def test_defaults_when_missing(self):
        cfg = load_config(tempfile.mktemp(suffix=".json"))
        self.assertEqual(cfg.player_name, "BunBun")
        self.assertEqual(cfg.server_port, 11000)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps({
                "server_host": "192.168.1.50",
                "server_port": 11000,
                "launch_args_template": "-connect {host}:{port} -name {player}",
                "launcher_path": "/opt/nitrox/NitroxLauncher",
            }))
            cfg = load_config(path)
            self.assertEqual(cfg.server_host, "192.168.1.50")
            self.assertEqual(cfg.player_name, "BunBun")

    def test_bad_port_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text(json.dumps({"server_port": 99999}))
            with self.assertRaises(MultiplayerConfigError):
                load_config(path)

    def test_bad_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cfg.json"
            path.write_text("{not json")
            with self.assertRaises(MultiplayerConfigError):
                load_config(path)


class MatchTests(unittest.TestCase):
    def test_matches_subnautica_case_insensitive(self):
        games = [FakeGame("Half-Life 2"), FakeGame("Subnautica")]
        self.assertIs(match_game(games), games[1])

    def test_no_match_returns_none(self):
        self.assertIsNone(match_game([FakeGame("Portal")]))


class LaunchCommandTests(unittest.TestCase):
    def test_none_without_template(self):
        self.assertIsNone(build_launch_command(JoinConfig(server_host="192.168.1.50")))

    def test_placeholders_filled(self):
        cfg = JoinConfig(
            server_host="192.168.1.50",
            server_port=11000,
            player_name="BunBun",
            server_password="hunter2",
            launcher_path="/opt/nitrox/NitroxLauncher",
            launch_args_template="-connect {host}:{port} -name {player} -pass {password}",
        )
        cmd = build_launch_command(cfg)
        self.assertEqual(cmd, [
            "/opt/nitrox/NitroxLauncher",
            "-connect", "192.168.1.50:11000",
            "-name", "BunBun",
            "-pass", "hunter2",
        ])


class DoctorTests(unittest.TestCase):
    def test_report_shape(self):
        cfg = JoinConfig(server_host="192.168.1.50")
        report = doctor(cfg, games=[FakeGame("Subnautica", "/games/subnautica")])
        self.assertTrue(report["game_found"])
        self.assertEqual(report["game_path"], "/games/subnautica")
        self.assertFalse(report["ready_to_join"])
        self.assertEqual(report["server_port"], 11000)


if __name__ == "__main__":
    unittest.main()
