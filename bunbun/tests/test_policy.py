"""The policy gate is the most important code in the agent: test it hard."""
from __future__ import annotations

import unittest

from bunbun.mam.policy import (
    GameContext,
    Kind,
    PolicyEngine,
    Proposal,
    SettingsView,
)


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def settings(**overrides) -> SettingsView:
    base = dict(enabled=True, voice_enabled=True, hint_level="gentle", commentary=True,
                coop_opt_in=False, coop_mode="invite-only", screen_vision=False,
                kid_safe=True, memory_enabled=True, input_enabled=False)
    base.update(overrides)
    return SettingsView(**base)


def co_op_game(**overrides) -> GameContext:
    base = dict(game_id="steam:480", title="Bunny Test", platform="steam",
                multiplayer=True, anticheat=False, competitive=False, allowlisted=True)
    base.update(overrides)
    return GameContext(**base)


class GlobalTests(unittest.TestCase):
    def test_disabled_agent_denies_everything(self):
        engine = PolicyEngine()
        decision = engine.evaluate(Proposal(kind=Kind.SPEAK, text="hi"),
                                   GameContext(), settings(enabled=False))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "agent-disabled")

    def test_kill_switch(self):
        engine = PolicyEngine(kill_switch=lambda: True)
        decision = engine.evaluate(Proposal(kind=Kind.OVERLAY), GameContext(), settings())
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "kill-switch")

    def test_disabled_voice_blocks_speech(self):
        engine = PolicyEngine()
        decision = engine.evaluate(Proposal(kind=Kind.SPEAK, text="hi"),
                                   GameContext(), settings(voice_enabled=False))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "voice-off")

    def test_overlay_still_allowed_without_voice(self):
        engine = PolicyEngine()
        decision = engine.evaluate(Proposal(kind=Kind.OVERLAY, text="hi"),
                                   GameContext(), settings(voice_enabled=False))
        self.assertTrue(decision.allowed)

    def test_hints_off(self):
        engine = PolicyEngine()
        decision = engine.evaluate(Proposal(kind=Kind.HINT, text="look left",
                                            meta={"overlay_fallback": True}),
                                   GameContext(), settings(hint_level="off"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "hint-level")

    def test_hint_with_overlay_fallback_when_muted(self):
        engine = PolicyEngine()
        decision = engine.evaluate(Proposal(kind=Kind.HINT, text="look left",
                                            meta={"overlay_fallback": True}),
                                   GameContext(), settings(voice_enabled=False))
        self.assertTrue(decision.allowed)


class InputTests(unittest.TestCase):
    def test_input_denied_without_opt_in(self):
        engine = PolicyEngine()
        decision = engine.evaluate(Proposal(kind=Kind.INPUT), co_op_game(), settings())
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "coop-off")
        self.assertTrue(decision.requires_consent)

    def test_input_allowed_when_every_gate_is_green(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.INPUT), co_op_game(),
            settings(coop_opt_in=True, input_enabled=True),
        )
        self.assertTrue(decision.allowed, decision.reason)

    def test_anticheat_never(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.INPUT), co_op_game(anticheat=True),
            settings(coop_opt_in=True, input_enabled=True),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "anticheat")

    def test_competitive_never(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.INPUT), co_op_game(competitive=True),
            settings(coop_opt_in=True, input_enabled=True),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "competitive")

    def test_singleplayer_never_gets_input(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.INPUT), co_op_game(multiplayer=False),
            settings(coop_opt_in=True, input_enabled=True),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "singleplayer-only")

    def test_allowlist_required(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.INPUT), co_op_game(allowlisted=False),
            settings(coop_opt_in=True, input_enabled=True),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "allowlist")

    def test_root_token_required(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.INPUT), co_op_game(),
            settings(coop_opt_in=True, input_enabled=False),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "input-token")
        self.assertTrue(decision.requires_consent)


class JoinAndChatTests(unittest.TestCase):
    def test_join_requires_invite_in_invite_only_mode(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.JOIN, meta={"consented": True}),
            co_op_game(), settings(coop_opt_in=True),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "invite-only")

    def test_join_requires_player_consent(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.JOIN, meta={"invited": True}),
            co_op_game(), settings(coop_opt_in=True),
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_consent)

    def test_join_allowed_with_invite_and_consent(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.JOIN, meta={"invited": True, "consented": True}),
            co_op_game(), settings(coop_opt_in=True),
        )
        self.assertTrue(decision.allowed, decision.reason)

    def test_join_refused_for_anticheat(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.JOIN, meta={"invited": True, "consented": True}),
            co_op_game(anticheat=True), settings(coop_opt_in=True),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "anticheat")

    def test_kid_safe_persona_never_messages_strangers(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.CHAT, meta={"consented": True}),
            co_op_game(), settings(coop_opt_in=True, kid_safe=True),
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.rule, "kid-safe-chat")

    def test_chat_allowed_with_known_recipient(self):
        engine = PolicyEngine()
        decision = engine.evaluate(
            Proposal(kind=Kind.CHAT, meta={"consented": True, "recipient_known": True}),
            co_op_game(), settings(coop_opt_in=True, kid_safe=True),
        )
        self.assertTrue(decision.allowed, decision.reason)


class RateLimitTests(unittest.TestCase):
    def test_cooldown_between_speeches(self):
        clock = FakeClock()
        engine = PolicyEngine(clock=clock)
        first = engine.evaluate(Proposal(kind=Kind.SPEAK, text="one"), GameContext(), settings())
        self.assertTrue(first.allowed)
        engine.commit(Kind.SPEAK)
        second = engine.evaluate(Proposal(kind=Kind.SPEAK, text="two"), GameContext(), settings())
        self.assertFalse(second.allowed)
        self.assertEqual(second.rule, "rate-limit")
        clock.advance(13)
        third = engine.evaluate(Proposal(kind=Kind.SPEAK, text="three"), GameContext(), settings())
        self.assertTrue(third.allowed)

    def test_per_minute_budget(self):
        clock = FakeClock()
        engine = PolicyEngine(cooldowns={Kind.OVERLAY: 0.0}, clock=clock)
        for i in range(24):
            decision = engine.evaluate(Proposal(kind=Kind.OVERLAY), GameContext(), settings())
            self.assertTrue(decision.allowed, f"action {i} should fit the budget")
            engine.commit(Kind.OVERLAY)
        blocked = engine.evaluate(Proposal(kind=Kind.OVERLAY), GameContext(), settings())
        self.assertFalse(blocked.allowed)
        self.assertEqual(blocked.rule, "rate-limit")


if __name__ == "__main__":
    unittest.main()
