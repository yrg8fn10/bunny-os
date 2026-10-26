"""Memory and co-op tests: local data, explicit consent."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bunbun.action.coop import CoopAgent, JoinInvite
from bunbun.bus import EventBus
from bunbun.memory import Memory


class MemoryTests(unittest.TestCase):
    def test_events_and_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Memory(Path(tmp) / "m.sqlite3") as mem:
                mem.record("test", {"a": 1}, "demo")
                self.assertEqual(mem.recent(5)[0]["payload"], {"a": 1})
                self.assertFalse(mem.hint_seen("h1", "demo"))
                mem.mark_hint("h1", "demo")
                self.assertTrue(mem.hint_seen("h1", "demo"))
                self.assertEqual(mem.hint_count("demo"), 1)

    def test_sessions_are_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Memory(Path(tmp) / "m.sqlite3") as mem:
                sid = mem.start_session("demo")
                mem.end_session(sid)
                self.assertEqual(mem.stats()["sessions"], 1)

    def test_purge_removes_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            with Memory(Path(tmp) / "m.sqlite3") as mem:
                mem.record("test", {})
                mem.mark_hint("h", "demo")
                mem.record_consent("coop", True)
                mem.purge()
                stats = mem.stats()
                self.assertEqual(stats["events"], 0)
                self.assertEqual(stats["sessions"], 0)
                self.assertEqual(mem.hint_count(), 0)

    def test_disabled_memory_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "m.sqlite3"
            with Memory(path, enabled=False) as mem:
                mem.record("test", {})
                self.assertEqual(mem.recent(), [])
                self.assertFalse(path.exists())


class CoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.allow = Path(self.tmp.name) / "allow.txt"
        self.allow.write_text("# allowlisted titles\ndemo:1\n", "utf-8")
        self.bus = EventBus()
        self.agent = CoopAgent(self.bus, allowlist_path=self.allow,
                               launcher="/bin/true", opener="/bin/true")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @staticmethod
    def settings(opt_in: bool = True, mode: str = "invite-only") -> dict:
        return {"ai": {"coop_opt_in": opt_in, "coop_mode": mode}}

    def invite(self, **kwargs) -> JoinInvite:
        base = dict(friend="Mika", game_id="demo:1", title="Demo",
                    platform="steam", app_id="1", lobby_id="12345")
        base.update(kwargs)
        return JoinInvite.from_dict(base)

    def test_allowlist_parsing(self):
        self.assertTrue(self.agent.allowlisted(self.invite()))
        self.assertFalse(self.agent.allowlisted(self.invite(game_id="other:2", app_id="2")))

    def test_opt_in_required(self):
        decision = self.agent.evaluate(self.invite(), self.settings(opt_in=False))
        self.assertFalse(decision.allowed)
        self.assertIn("off", decision.reason)

    def test_anticheat_refused(self):
        decision = self.agent.evaluate(self.invite(anticheat=True), self.settings())
        self.assertFalse(decision.allowed)
        self.assertIn("anti-cheat", decision.reason)

    def test_competitive_refused(self):
        decision = self.agent.evaluate(self.invite(competitive=True), self.settings())
        self.assertFalse(decision.allowed)

    def test_unknown_title_refused(self):
        decision = self.agent.evaluate(
            self.invite(game_id="nope:9", app_id="9", title="Nope"), self.settings())
        self.assertFalse(decision.allowed)
        self.assertIn("allowlist", decision.reason)

    def test_join_without_confirmation_only_asks(self):
        result = self.agent.join(self.invite(), self.settings(), player_confirmed=False)
        self.assertEqual(result["status"], "awaiting_player_consent")
        self.assertIsNone(self.agent.active_invite)

    def test_dry_run_never_launches(self):
        result = self.agent.join(self.invite(), self.settings(),
                                 player_confirmed=True, dry_run=True)
        self.assertEqual(result["status"], "dry-run")
        self.assertIsNone(self.agent.active_invite)

    def test_console_join_deep_links_only_for_steam_lobbies(self):
        plan = self.agent.build_plan(self.invite(platform="epic", lobby_id=""))
        self.assertTrue(any("in-game" in step for step in plan))

    def test_status_is_auditable(self):
        self.agent.join(self.invite(), self.settings(), player_confirmed=False)
        status = self.agent.status()
        self.assertEqual(status["audit"][0]["action"], "consent-requested")


if __name__ == "__main__":
    unittest.main()
