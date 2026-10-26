"""MAM engine — observe, propose, gate, act, remember.

The engine is intentionally rule-based: it ships offline, runs in ~30 MB, and
can be audited line by line.  It is not a cloud LLM wrapper; a local model can
be plugged in behind `Proposal` without changing the safety layer.
"""
from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..bus import EventBus
from ..hints import Hint, HintLibrary
from ..memory import Memory
from ..persona import Persona
from .policy import Decision, GameContext, Kind, PolicyEngine, Proposal, SettingsView


@dataclass
class GameState:
    game_id: str = ""
    title: str = ""
    platform: str = "steam"
    multiplayer: bool = False
    anticheat: bool = False
    competitive: bool = False
    allowlisted: bool = False
    stuck_seconds: int = 0
    deaths_recent: int = 0
    elapsed_seconds: int = 0
    paused: bool = False
    invite_from: str | None = None
    secret_nearby: str | None = None
    boss_fight: bool = False
    mood: str = "neutral"       # neutral|excited|tense|frustrated|victory

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GameState":
        data = data or {}
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def context(self) -> GameContext:
        return GameContext(
            game_id=self.game_id,
            title=self.title,
            platform=self.platform,
            multiplayer=self.multiplayer,
            anticheat=self.anticheat,
            competitive=self.competitive,
            allowlisted=self.allowlisted,
        )


@dataclass
class Outcome:
    kind: str
    text: str
    executed: bool
    rule: str
    reason: str
    needs_consent: bool = False
    hint_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MAMEngine:
    def __init__(
        self,
        persona: Persona,
        hints: HintLibrary,
        settings_provider: Callable[[], dict[str, Any]],
        memory: Memory | None = None,
        bus: EventBus | None = None,
        policy: PolicyEngine | None = None,
        speaker: Callable[[str], bool] | None = None,
        input_enabled: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ):
        self.persona = persona
        self.hints = hints
        self.settings_provider = settings_provider
        self.memory = memory
        self.bus = bus or EventBus()
        self.policy = policy or PolicyEngine(clock=clock)
        self.speaker = speaker
        self.input_enabled = input_enabled or (lambda: False)
        self.clock = clock
        self.rng = rng or random.Random()
        self.state = GameState()
        self._session_id: int | None = None
        self._last_tick = 0.0
        self._dedupe: dict[str, float] = {}
        self._started_at = time.time()

    # -- settings ----------------------------------------------------------
    def settings(self) -> SettingsView:
        try:
            raw = self.settings_provider() or {}
        except Exception:  # a broken settings file must not kill the agent
            raw = {}
        return SettingsView.from_settings(raw, input_enabled=bool(self.input_enabled()))

    # -- lifecycle ---------------------------------------------------------
    def observe(self, payload: dict[str, Any]) -> list[Outcome]:
        """Update the world model; emit a greeting when the game changes."""
        new_state = GameState.from_dict(payload)
        previous = self.state
        self.state = new_state
        outcomes: list[Outcome] = []

        if new_state.game_id and new_state.game_id != previous.game_id:
            self._end_session()
            if self.memory and self.memory.enabled:
                self._session_id = self.memory.start_session(new_state.game_id)
            self.bus.publish("game.started", {
                "game_id": new_state.game_id,
                "title": new_state.title,
                "platform": new_state.platform,
                "multiplayer": new_state.multiplayer,
            })
            greeting = self.persona.greet()
            outcomes.append(self._speak(greeting, Kind.SPEAK, dedupe="greeting:" + new_state.game_id))
            self._remember("game.started", new_state.to_dict(), new_state.game_id)

        elif not new_state.game_id and previous.game_id:
            self._end_session()
            self.bus.publish("game.stopped", {"game_id": previous.game_id})

        return [o for o in outcomes if o is not None]

    def _end_session(self) -> None:
        if self.memory and self._session_id is not None:
            self.memory.end_session(self._session_id)
        self._session_id = None

    # -- main loop ---------------------------------------------------------
    def tick(self, payload: dict[str, Any] | None = None) -> list[Outcome]:
        if payload is not None:
            self.state = GameState.from_dict(payload)
        self._last_tick = self.clock()
        settings = self.settings()
        state = self.state
        proposals: list[Proposal] = []

        if not state.game_id:
            return []

        # 1. Co-op invitation needs a human decision, not an automatic join.
        if state.invite_from:
            proposals.append(Proposal(
                kind=Kind.JOIN,
                text=self.persona.coop_invite(state.invite_from),
                priority=90,
                dedupe_key=f"invite:{state.invite_from}",
                meta={"invited": True, "consented": False, "friend": state.invite_from},
            ))

        # 2. A secret is nearby (from a game adapter or local vision).
        if state.secret_nearby:
            level = settings.hint_level
            if level in {"helpful", "spoilery"}:
                proposals.append(Proposal(
                    kind=Kind.HINT,
                    text=self.persona.hint(state.secret_nearby, secret=True),
                    priority=70,
                    dedupe_key=f"secret:{state.game_id}:{state.secret_nearby}",
                    meta={"overlay_fallback": True, "secret": True,
                          "where": state.secret_nearby},
                ))

        # 3. Stuck for a while -> offer one library hint.
        if state.stuck_seconds >= 90 and not state.paused:
            hint = self._pick_hint(settings, allow_secret=settings.hint_level == "spoilery")
            if hint:
                proposals.append(Proposal(
                    kind=Kind.HINT,
                    text=hint.text,
                    priority=60,
                    hint_id=hint.hint_id,
                    dedupe_key=f"hint:{hint.hint_id}",
                    meta={"overlay_fallback": True, "secret": hint.secret,
                          "where": hint.where, "tags": list(hint.tags)},
                ))
            elif settings.commentary:
                proposals.append(Proposal(
                    kind=Kind.SPEAK, text=self.persona.stuck(), priority=40,
                    dedupe_key=f"stuck:{state.game_id}:{state.stuck_seconds // 120}",
                ))

        # 4. Frustration watch: suggest a break before a solution.
        if state.deaths_recent >= 3 or state.mood == "frustrated":
            proposals.append(Proposal(
                kind=Kind.SPEAK, text=self.persona.break_time(), priority=65,
                dedupe_key=f"break:{state.game_id}:{state.deaths_recent}",
            ))

        # 5. Genuine celebration.
        if state.mood == "victory":
            proposals.append(Proposal(
                kind=Kind.SPEAK, text=self.persona.celebrate(), priority=80,
                dedupe_key=f"victory:{state.game_id}:{int(self.clock()) // 10}",
            ))

        # 6. Occasional commentary, never a stream of chatter.
        if settings.commentary and state.mood == "excited" and state.elapsed_seconds > 30:
            proposals.append(Proposal(
                kind=Kind.SPEAK, text=self.persona.encourage(), priority=20,
                dedupe_key=f"cheer:{state.game_id}:{int(self.clock()) // 180}",
            ))

        outcomes: list[Outcome] = []
        for proposal in sorted(proposals, key=lambda p: p.priority, reverse=True):
            if self._deduped(proposal):
                continue
            decision = self.policy.evaluate(proposal, state.context(), settings)
            outcomes.append(self._act(proposal, decision))
        return outcomes

    # -- execution ---------------------------------------------------------
    def _act(self, proposal: Proposal, decision: Decision) -> Outcome:
        voice_on = self.settings().voice_enabled
        if not decision.allowed:
            if decision.requires_consent:
                self.bus.publish("bunbun.consent_request", {
                    "action": proposal.kind.value,
                    "text": proposal.text,
                    "reason": decision.reason,
                    "meta": proposal.meta,
                })
                if proposal.text and voice_on:
                    self._voice(proposal.text)
            self.bus.publish("bunbun.refused", {
                "action": proposal.kind.value, "rule": decision.rule,
                "reason": decision.reason,
            })
            self._remember("proposal.refused", {
                "action": proposal.kind.value, "rule": decision.rule,
            })
            return Outcome(
                kind=proposal.kind.value, text=proposal.text, executed=False,
                rule=decision.rule, reason=decision.reason,
                needs_consent=decision.requires_consent, hint_id=proposal.hint_id,
            )

        self.policy.commit(proposal.kind)
        theme = "bunbun.hint" if proposal.kind is Kind.HINT else "bunbun.say"
        payload = {
            "text": proposal.text,
            "kind": proposal.kind.value,
            "priority": proposal.priority,
            "hint_id": proposal.hint_id,
            **{k: v for k, v in proposal.meta.items() if k != "consented"},
        }
        self.bus.publish(theme, payload)

        spoken = False
        if proposal.kind in {Kind.SPEAK, Kind.HINT} and voice_on:
            spoken = self._voice(proposal.text)

        if proposal.kind is Kind.HINT and proposal.hint_id and self.memory:
            self.memory.mark_hint(proposal.hint_id, self.state.game_id)
            self._remember("hint.shown", {"hint_id": proposal.hint_id},
                           self.state.game_id)

        return Outcome(
            kind=proposal.kind.value, text=proposal.text, executed=True,
            rule=decision.rule, reason=decision.reason, hint_id=proposal.hint_id,
            extra={"spoken": spoken},
        )

    def _speak(self, text: str, kind: Kind, dedupe: str = "") -> Outcome | None:
        if not text or self._deduped(Proposal(kind=kind, text=text, dedupe_key=dedupe)):
            return None
        proposal = Proposal(kind=kind, text=text, dedupe_key=dedupe)
        decision = self.policy.evaluate(proposal, self.state.context(), self.settings())
        return self._act(proposal, decision)

    def _voice(self, text: str) -> bool:
        if not text or not self.speaker:
            return False
        try:
            return bool(self.speaker(text))
        except Exception:
            self.bus.publish("bunbun.error", {"stage": "tts"})
            return False

    # -- helpers -----------------------------------------------------------
    def _pick_hint(self, settings: SettingsView, allow_secret: bool) -> Hint | None:
        seen = self.memory.hint_seen if self.memory and self.memory.enabled else None
        return self.hints.pick(
            self.state.game_id,
            level=settings.hint_level,
            seen=(lambda hid: bool(seen(hid, self.state.game_id))) if seen else None,
            allow_secret=allow_secret,
        )

    def _deduped(self, proposal: Proposal) -> bool:
        key = proposal.dedupe_key
        if not key:
            return False
        now = self.clock()
        last = self._dedupe.get(key)
        if last is not None and now - last < 120:
            return True
        self._dedupe[key] = now
        if len(self._dedupe) > 512:
            cutoff = now - 600
            self._dedupe = {k: v for k, v in self._dedupe.items() if v >= cutoff}
        return False

    def _remember(self, kind: str, payload: dict[str, Any], game_id: str | None = None) -> None:
        if self.memory and self.memory.enabled:
            self.memory.record(kind, payload, game_id or self.state.game_id or None)

    # -- on-demand actions -------------------------------------------------
    def request_hint(self, allow_secret: bool = False) -> Outcome | None:
        settings = self.settings()
        if settings.hint_level == "off":
            return Outcome(kind=Kind.HINT.value, text="", executed=False,
                           rule="hint-level", reason="hints are disabled")

        hint = self._pick_hint(settings, allow_secret=allow_secret
                               or settings.hint_level == "spoilery")
        if not hint:
            return self._speak(
                "I'm all out of hints for this one! You're doing great anyway~",
                Kind.SPEAK, dedupe=f"no-hints:{self.state.game_id}")
        proposal = Proposal(
            kind=Kind.HINT, text=hint.text, priority=95, hint_id=hint.hint_id,
            dedupe_key=f"manual:{hint.hint_id}",
            meta={"overlay_fallback": True, "secret": hint.secret, "where": hint.where},
        )
        decision = self.policy.evaluate(proposal, self.state.context(), settings)
        if decision.rule == "rate-limit":
            # A human asked; bypass the per-kind cooldown but keep rate limits.
            decision = Decision(True, "player requested", "manual")
        return self._act(proposal, decision)

    def say(self, text: str) -> bool:
        """Speak a caller-supplied line (already sanitised by the persona)."""
        clean = self.persona.sanitize(text)
        outcome = self._speak(clean, Kind.SPEAK)
        return bool(outcome and outcome.executed)

    def consent(self, action: Kind, granted: bool, note: str = "") -> dict[str, Any]:
        if self.memory and self.memory.enabled:
            self.memory.record_consent(action.value, granted, note)
        self.bus.publish("bunbun.consent", {
            "action": action.value, "granted": granted, "note": note,
        })
        return {"action": action.value, "granted": granted}

    def status(self) -> dict[str, Any]:
        settings = self.settings()
        return {
            "state": self.state.to_dict(),
            "settings": {
                "enabled": settings.enabled,
                "voice_enabled": settings.voice_enabled,
                "hint_level": settings.hint_level,
                "coop_opt_in": settings.coop_opt_in,
                "coop_mode": settings.coop_mode,
                "input_enabled": settings.input_enabled,
            },
            "memory": self.memory.stats() if self.memory else {"enabled": False},
            "hints": {"library": len(self.hints), "shown": self.memory.hint_count()
                      if self.memory else 0},
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "policy": {"cooldowns": {k.value: v for k, v in self.policy.cooldowns.items()}},
        }

    def close(self) -> None:
        self._end_session()
        if self.memory:
            self.memory.close()
