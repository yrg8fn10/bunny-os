"""MAM policy layer — the part that says "no".

Bun Bun's Mine Action Model runs a fixed loop:

    OBSERVE  ->  PROPOSE  ->  GATE  ->  ACT  ->  REMEMBER

`PROPOSE` is creative and cheap.  `GATE` is deliberately boring, explicit, and
fully testable.  Every irreversible or social action (input injection, joining
a lobby, chatting) must pass a named rule here before it can reach an
executor.  If a rule cannot prove consent, the answer is "no".
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Kind(str, Enum):
    SPEAK = "speak"        # voiced line
    HINT = "hint"          # gameplay hint (voiced + overlay)
    OVERLAY = "overlay"    # visual toast only
    INPUT = "input"        # synthesised key/mouse input
    JOIN = "join"          # enter a multiplayer lobby
    CHAT = "chat"          # send a message to another player
    MEMORY = "memory"      # persist a note


@dataclass(frozen=True)
class GameContext:
    game_id: str = ""
    title: str = ""
    platform: str = "steam"
    multiplayer: bool = False
    anticheat: bool = False
    competitive: bool = False
    allowlisted: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GameContext":
        data = data or {}
        return cls(
            game_id=str(data.get("game_id", "")),
            title=str(data.get("title", "")),
            platform=str(data.get("platform", "steam")),
            multiplayer=bool(data.get("multiplayer", False)),
            anticheat=bool(data.get("anticheat", False)),
            competitive=bool(data.get("competitive", False)),
            allowlisted=bool(data.get("allowlisted", False)),
        )


@dataclass(frozen=True)
class SettingsView:
    enabled: bool = True
    voice_enabled: bool = True
    hint_level: str = "gentle"
    commentary: bool = True
    coop_opt_in: bool = False
    coop_mode: str = "invite-only"
    screen_vision: bool = False
    kid_safe: bool = True
    memory_enabled: bool = True
    input_enabled: bool = False

    @classmethod
    def from_settings(cls, settings: dict[str, Any], input_enabled: bool = False) -> "SettingsView":
        ai = settings.get("ai", {}) if isinstance(settings.get("ai"), dict) else {}
        return cls(
            enabled=bool(ai.get("enabled", True)),
            voice_enabled=bool(ai.get("voice_enabled", True)),
            hint_level=str(ai.get("hint_level", "gentle")),
            commentary=bool(ai.get("commentary", True)),
            coop_opt_in=bool(ai.get("coop_opt_in", False)),
            coop_mode=str(ai.get("coop_mode", "invite-only")),
            screen_vision=bool(ai.get("screen_vision", False)),
            kid_safe=bool(ai.get("kid_safe", True)),
            memory_enabled=bool(ai.get("memory_enabled", True)),
            input_enabled=input_enabled,
        )


@dataclass
class Proposal:
    kind: Kind
    text: str = ""
    priority: int = 50
    hint_id: str | None = None
    dedupe_key: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    rule: str
    requires_consent: bool = False


ALLOW = "allow"

# Seconds between two actions of the same kind.  Conservative on purpose: a
# companion that talks every other second is worse than no companion.
DEFAULT_COOLDOWNS: dict[Kind, float] = {
    Kind.SPEAK: 12.0,
    Kind.HINT: 60.0,
    Kind.OVERLAY: 3.0,
    Kind.INPUT: 1.0,
    Kind.JOIN: 30.0,
    Kind.CHAT: 20.0,
    Kind.MEMORY: 0.0,
}

MAX_ACTIONS_PER_MINUTE = 24


class PolicyEngine:
    def __init__(self, cooldowns: dict[Kind, float] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 kill_switch: Callable[[], bool] | None = None):
        self.cooldowns = {**DEFAULT_COOLDOWNS, **(cooldowns or {})}
        self.clock = clock
        self.kill_switch = kill_switch or (lambda: False)
        self._last: dict[Kind, float] = {}
        self._window: deque[float] = deque(maxlen=MAX_ACTIONS_PER_MINUTE * 2)

    # -- introspection -----------------------------------------------------
    @staticmethod
    def rules() -> list[dict[str, str]]:
        return [
            {"rule": "agent-disabled", "effect": "all actions denied while ai.enabled=false"},
            {"rule": "kill-switch", "effect": "denies everything while /run/bunny/agent.lock exists"},
            {"rule": "voice-off", "effect": "speak/hint audio denied when voice_enabled=false"},
            {"rule": "hint-level", "effect": "hints denied at hint_level=off; secrets need spoilery or consent"},
            {"rule": "coop-off", "effect": "input/join/chat denied unless coop_opt_in=true"},
            {"rule": "anticheat", "effect": "never inject input or join anti-cheat protected titles"},
            {"rule": "competitive", "effect": "never inject input into competitive modes"},
            {"rule": "allowlist", "effect": "game must be in the co-op allowlist"},
            {"rule": "input-token", "effect": "input also requires the root-owned input token"},
            {"rule": "invite-only", "effect": "joins require a real lobby invitation"},
            {"rule": "kid-safe-chat", "effect": "kid_safe persona never messages strangers"},
            {"rule": "rate-limit", "effect": f"max {MAX_ACTIONS_PER_MINUTE} actions/minute, per-kind cooldowns"},
        ]

    # -- gate --------------------------------------------------------------
    def evaluate(self, proposal: Proposal, game: GameContext,
                 settings: SettingsView) -> Decision:
        if kind_denied := self._global_denial(settings):
            return kind_denied

        if proposal.kind is Kind.SPEAK:
            if not settings.voice_enabled:
                return Decision(False, "voice is disabled", "voice-off")
        elif proposal.kind is Kind.HINT:
            if settings.hint_level == "off":
                return Decision(False, "hints are disabled", "hint-level")
            if not settings.voice_enabled and not proposal.meta.get("overlay_fallback"):
                return Decision(False, "voice is disabled", "voice-off")
            if game.game_id and game.anticheat:
                # Hints are read-only, but a hint about a protected game can
                # still leak information the player did not ask for.
                if proposal.meta.get("secret"):
                    return Decision(False, "secret hints are disabled for this title",
                                    "anticheat", requires_consent=True)
        elif proposal.kind is Kind.OVERLAY:
            pass
        elif proposal.kind is Kind.MEMORY:
            if not settings.memory_enabled:
                return Decision(False, "memory is disabled", "memory-off")
        elif proposal.kind is Kind.INPUT:
            decision = self._gate_input(game, settings)
            if not decision.allowed:
                return decision
        elif proposal.kind is Kind.JOIN:
            decision = self._gate_join(proposal, game, settings)
            if not decision.allowed:
                return decision
        elif proposal.kind is Kind.CHAT:
            decision = self._gate_chat(proposal, game, settings)
            if not decision.allowed:
                return decision

        return self._gate_rate(proposal)

    # -- individual rules --------------------------------------------------
    def _global_denial(self, settings: SettingsView) -> Decision | None:
        if not settings.enabled:
            return Decision(False, "Bun Bun is disabled in settings", "agent-disabled")
        if self.kill_switch():
            return Decision(False, "kill switch engaged", "kill-switch")
        return None

    def _gate_input(self, game: GameContext, settings: SettingsView) -> Decision:
        if not settings.coop_opt_in:
            return Decision(False, "multiplayer assist is not enabled", "coop-off",
                            requires_consent=True)
        if game.anticheat:
            return Decision(False, "anti-cheat protected title", "anticheat")
        if game.competitive:
            return Decision(False, "competitive mode", "competitive")
        if not game.multiplayer:
            return Decision(False, "single-player titles never receive synthetic input",
                            "singleplayer-only")
        if not game.allowlisted:
            return Decision(False, "game is not in the co-op allowlist", "allowlist")
        if not settings.input_enabled:
            return Decision(False, "input agent is not enabled", "input-token",
                            requires_consent=True)
        return Decision(True, "input permitted", ALLOW)

    def _gate_join(self, proposal: Proposal, game: GameContext,
                   settings: SettingsView) -> Decision:
        if settings.coop_mode == "off":
            return Decision(False, "co-op is turned off", "coop-off")
        if not settings.coop_opt_in:
            return Decision(False, "multiplayer assist is not enabled", "coop-off",
                            requires_consent=True)
        if game.anticheat:
            return Decision(False, "anti-cheat protected title", "anticheat")
        if not game.allowlisted:
            return Decision(False, "game is not in the co-op allowlist", "allowlist")
        if settings.coop_mode == "invite-only" and not proposal.meta.get("invited"):
            return Decision(False, "no pending invitation", "invite-only")
        if not proposal.meta.get("consented"):
            return Decision(False, "player has not confirmed this join", "consent",
                            requires_consent=True)
        return Decision(True, "join permitted", ALLOW)

    def _gate_chat(self, proposal: Proposal, game: GameContext,
                   settings: SettingsView) -> Decision:
        if not settings.coop_opt_in:
            return Decision(False, "multiplayer assist is not enabled", "coop-off",
                            requires_consent=True)
        if settings.kid_safe and not proposal.meta.get("recipient_known"):
            return Decision(False, "kid-safe persona does not message strangers",
                            "kid-safe-chat")
        if not proposal.meta.get("consented"):
            return Decision(False, "message needs player confirmation", "consent",
                            requires_consent=True)
        return Decision(True, "chat permitted", ALLOW)

    def _gate_rate(self, proposal: Proposal) -> Decision:
        now = self.clock()
        while self._window and now - self._window[0] > 60:
            self._window.popleft()
        if len(self._window) >= MAX_ACTIONS_PER_MINUTE:
            return Decision(False, "too many actions this minute", "rate-limit")

        last = self._last.get(proposal.kind)
        cooldown = self.cooldowns.get(proposal.kind, 0.0)
        if last is not None and now - last < cooldown:
            return Decision(False, f"{proposal.kind.value} cooling down for "
                                   f"{cooldown - (now - last):.0f}s", "rate-limit")
        return Decision(True, "ok", ALLOW)

    # -- accounting --------------------------------------------------------
    def commit(self, kind: Kind) -> None:
        now = self.clock()
        self._last[kind] = now
        self._window.append(now)

    def seconds_since(self, kind: Kind) -> float | None:
        last = self._last.get(kind)
        return None if last is None else self.clock() - last

    def reset(self) -> None:
        self._last.clear()
        self._window.clear()
