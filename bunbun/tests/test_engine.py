"""Scenario tests for the MAM engine: observe -> propose -> gate -> act."""
from __future__ import annotations

import random
import tempfile
import unittest
from pathlib import Path

from bunbun.bus import EventBus
from bunbun.config import PACKAGE_DATA
from bunbun.hints import HintLibrary
from bunbun.mam.engine import MAMEngine
from bunbun.mam.policy import PolicyEngine
from bunbun.memory import Memory
from bunbun.persona import Persona


class FakeClock:
    def __init__(self) -> None:
        self.t = 500.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class EngineHarness:
    def __init__(self, ai: dict | None = None):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = FakeClock()
        self.spoken: list[str] = []
        self.bus = EventBus()
        self.memory = Memory(Path(self.tmp.name) / "mem.sqlite3")
        self.ai = {
            "enabled": True, "voice_enabled": True, "hint_level": "helpful",
            "commentary": True, "coop_opt_in": False, "coop_mode": "invite-only",
            "screen_vision": False, "kid_safe": True, "memory_enabled": True,
        }
        self.ai.update(ai or {})
        self.engine = MAMEngine(
            persona=Persona.load(rng=random.Random(7)),
            hints=HintLibrary.from_directory(PACKAGE_DATA / "hints", rng=random.Random(7)),
            settings_provider=lambda: {"ai": self.ai},
            memory=self.memory,
            bus=self.bus,
            policy=PolicyEngine(clock=self.clock),
            speaker=self._speak,
            clock=self.clock,
            rng=random.Random(7),
        )

    def _speak(self, text: str) -> bool:
        self.spoken.append(text)
        return True

    def close(self) -> None:
        self.engine.close()
        self.tmp.cleanup()


class ObserveTests(unittest.TestCase):
    def test_greeting_on_new_game(self):
        h = EngineHarness()
        try:
            outcomes = h.engine.observe({"game_id": "demo:1", "title": "Demo"})
            self.assertEqual(len(outcomes), 1)
            self.assertTrue(outcomes[0].executed)
            self.assertEqual(outcomes[0].kind, "speak")
            self.assertTrue(h.spoken)
        finally:
            h.close()

    def test_no_greeting_when_voice_off(self):
        h = EngineHarness({"voice_enabled": False})
        try:
            outcomes = h.engine.observe({"game_id": "demo:1", "title": "Demo"})
            self.assertFalse(any(o.executed for o in outcomes))
            self.assertEqual(h.spoken, [])
        finally:
            h.close()

    def test_game_exit_closes_session(self):
        h = EngineHarness()
        try:
            h.engine.observe({"game_id": "demo:1", "title": "Demo"})
            h.engine.observe({})
            self.assertEqual(h.engine.state.game_id, "")
            self.assertEqual(h.memory.stats()["sessions"], 1)
        finally:
            h.close()


class HintTests(unittest.TestCase):
    def test_stuck_player_gets_one_hint(self):
        h = EngineHarness()
        try:
            h.engine.observe({"game_id": "demo", "title": "Demo"})
            outcomes = h.engine.tick({"game_id": "demo", "title": "Demo",
                                      "stuck_seconds": 150})
            hints = [o for o in outcomes if o.kind == "hint" and o.executed]
            self.assertTrue(hints, [o.to_dict() for o in outcomes])
            self.assertIsNotNone(hints[0].hint_id)
            self.assertTrue(h.memory.hint_seen(hints[0].hint_id, "demo"))
        finally:
            h.close()

    def test_hint_is_not_repeated(self):
        h = EngineHarness()
        try:
            h.engine.observe({"game_id": "demo", "title": "Demo"})
            first = h.engine.tick({"game_id": "demo", "stuck_seconds": 150})
            first_ids = [o.hint_id for o in first if o.kind == "hint" and o.executed]
            self.assertTrue(first_ids)
            h.clock.advance(500)
            second = h.engine.tick({"game_id": "demo", "stuck_seconds": 400})
            second_ids = [o.hint_id for o in second if o.kind == "hint" and o.executed]
            # A later stall may offer a *different* unseen hint, but never the
            # same one twice in a session.
            self.assertFalse(set(first_ids) & set(second_ids))
        finally:
            h.close()

    def test_muted_voice_still_shows_hint_on_overlay(self):
        h = EngineHarness({"voice_enabled": False})
        try:
            h.engine.observe({"game_id": "demo", "title": "Demo"})
            outcomes = h.engine.tick({"game_id": "demo", "stuck_seconds": 150})
            hints = [o for o in outcomes if o.kind == "hint" and o.executed]
            self.assertTrue(hints)
            self.assertFalse(hints[0].extra.get("spoken"))
            self.assertEqual(h.spoken, [])
        finally:
            h.close()

    def test_manual_hint_respects_disabled_hints(self):
        h = EngineHarness({"hint_level": "off"})
        try:
            outcome = h.engine.request_hint()
            self.assertIsNotNone(outcome)
            self.assertFalse(outcome.executed)
            self.assertEqual(outcome.rule, "hint-level")
        finally:
            h.close()


class CoopTests(unittest.TestCase):
    def test_invite_requires_consent_and_never_auto_joins(self):
        h = EngineHarness()
        try:
            h.engine.observe({"game_id": "demo", "title": "Demo", "multiplayer": True})
            outcomes = h.engine.tick({"game_id": "demo", "multiplayer": True,
                                      "invite_from": "Mika"})
            joins = [o for o in outcomes if o.kind == "join"]
            self.assertTrue(joins)
            self.assertFalse(joins[0].executed)
            self.assertTrue(joins[0].needs_consent)
            topics = [e["topic"] for e in h.bus.recent(50)]
            self.assertIn("bunbun.consent_request", topics)
        finally:
            h.close()

    def test_frustration_suggests_a_break(self):
        h = EngineHarness()
        try:
            h.engine.observe({"game_id": "demo", "title": "Demo"})
            # The greeting just consumed the SPEAK cooldown.
            h.clock.advance(13)
            outcomes = h.engine.tick({"game_id": "demo", "deaths_recent": 4})
            self.assertTrue(outcomes)
            self.assertEqual(outcomes[0].kind, "speak")
            self.assertTrue(outcomes[0].executed)
        finally:
            h.close()


if __name__ == "__main__":
    unittest.main()
