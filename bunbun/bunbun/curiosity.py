"""curiosity: Bun Bun's get-to-know-you layer.

The persona Ava described (Nov 17, 2026): she gets curious about you first,
because you can't help someone you haven't met yet.  She asks a few small,
wholesome questions over time, remembers the answers locally, and lets them
color how she helps later (reminders, flavor, presence).

Guardrails (deliberate, not optional; Ava asked for this build to be careful):

- ASKS ARE RARE.  At most one question per game session, never in the first
  minutes (a warm-up delay), and a hard cap per rolling week.
- SHE NEVER NAGS.  A question is asked exactly once.  Silence, a shrug, or
  an answer all close it the same way; she never re-asks, never follows up,
  and never presses.
- WHOLESALE TOPICS ONLY.  Questions come from the local bank and nowhere
  else: small-talk and taste-level only.  No health, money, family,
  location, or feelings-diary probes.  The bank is plain JSON so players
  and modders can read every line before she ever speaks one.
- ANSWERS STAY LOCAL.  They live in the same SQLite store as everything
  else Bun Bun keeps, they never sync or upload, and purge() erases them
  with the rest.
- OFF SWITCH.  ``curiosity_enabled`` in settings, and the master
  ``memory_enabled`` switch disables her too.

v0 is deliberately simple: ask, absorb, recall.  Using the answers to
personalize help is the next layer and reads these events, so nothing here
needs to change when it lands.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_BANK = Path(__file__).parent / "data" / "curiosity.json"

# The answer is held only long enough for one reply; anything after that is
# the player's business, not a pending question.
_ASKED_EVENT = "curiosity.asked"
_ANSWER_EVENT = "curiosity.answer"
_WEEK_SECONDS = 7 * 24 * 3600
_MIN_ANSWER_CHARS = 2
_MAX_STORED_CHARS = 200

# Short, warm acknowledgments.  She files the answer away and moves on; no
# follow-up question, ever.
_ACKS = (
    "oh! noted, filed away in my little brain.",
    "eehee, i'll remember that!",
    "got it, tucked away safe and sound.",
    "ooh, good one. remembered!",
    "nice, that's going in my notes.",
)


@dataclass(frozen=True)
class Question:
    qid: str
    text: str
    tags: tuple[str, ...] = ()


class Curiosity:
    """The curious-but-careful get-to-know-you layer."""

    def __init__(
        self,
        store: Any,
        config: Any,
        rng: random.Random | None = None,
        bank_path: Path | None = None,
    ):
        self.store = store
        self.config = config
        self.rng = rng or random.Random()
        self._bank: list[Question] = []
        self._load_bank(bank_path or DEFAULT_BANK)
        self._session_game: str | None = None
        self._warm_until = 0.0
        self._asked_this_session = False
        self._pending: str | None = None

    # -- bank ---------------------------------------------------------------
    def _load_bank(self, path: Path) -> None:
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            self._bank = [
                Question(q["id"], q["text"], tuple(q.get("tags", ())))
                for q in raw.get("questions", [])
                if q.get("id") and q.get("text")
            ]
        except (OSError, ValueError, KeyError):
            self._bank = []  # a broken bank means silence, never a crash

    # -- session lifecycle ---------------------------------------------------
    def session_start(self, game_id: str, now: float | None = None) -> None:
        self._session_game = game_id or "unknown"
        warm = float(getattr(self.config, "curiosity_minutes_into_session", 12.0))
        self._warm_until = (now if now is not None else time.time()) + warm * 60.0
        self._asked_this_session = False
        self._pending = None

    def session_end(self) -> None:
        self._session_game = None
        self._warm_until = 0.0
        self._asked_this_session = False
        self._pending = None

    @property
    def pending(self) -> str | None:
        return self._pending

    # -- asking --------------------------------------------------------------
    def maybe_ask(self, now: float | None = None) -> str | None:
        """Return one question to speak, or None.  Gates, in order."""
        if not getattr(self.config, "curiosity_enabled", True):
            return None
        if self.store is None or not getattr(self.store, "enabled", True):
            return None
        if not self._session_game or self._asked_this_session or self._pending:
            return None
        now = time.time() if now is None else now
        if now < self._warm_until:
            return None
        cap = int(getattr(self.config, "curiosity_max_per_week", 5))
        if self._asked_in_week(now) >= cap:
            return None
        asked = self._asked_ids()
        fresh = [q for q in self._bank if q.qid not in asked]
        if not fresh:
            return None  # she never recycles; silence until the bank grows
        q = self.rng.choice(fresh)
        self._pending = q.qid
        self._asked_this_session = True
        self.store.record(_ASKED_EVENT, {"qid": q.qid, "text": q.text},
                          game_id=self._session_game)
        return q.text

    # -- absorbing -----------------------------------------------------------
    def absorb(self, text: str, now: float | None = None) -> str | None:
        """Take the player's next utterance as the answer, if one is pending.

        Returns a short acknowledgment line for the caller to speak, or None.
        A question is closed no matter what the player said; she never
        re-asks and never presses.
        """
        if not self._pending:
            return None
        qid, self._pending = self._pending, None
        clean = (text or "").strip()
        if len(clean) < _MIN_ANSWER_CHARS:
            return None  # not an answer; she just lets it go
        self.store.record(_ANSWER_EVENT,
                          {"qid": qid, "answer": clean[:_MAX_STORED_CHARS]},
                          game_id=self._session_game)
        return self.rng.choice(_ACKS)

    # -- recall --------------------------------------------------------------
    def recall(self, qid: str) -> str | None:
        """The most recent answer the player gave to a question, if any."""
        try:
            for event in self.store.recent(limit=500):
                if event.get("kind") != _ANSWER_EVENT:
                    continue
                payload = event.get("payload") or {}
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except ValueError:
                        continue
                if payload.get("qid") == qid:
                    return str(payload.get("answer") or "") or None
        except Exception:
            return None
        return None

    def known_facts(self, limit: int = 20) -> dict[str, str]:
        """Everything she knows so far; the newest answer wins per question."""
        facts: dict[str, str] = {}
        try:
            for event in self.store.recent(limit=500):
                if event.get("kind") != _ANSWER_EVENT:
                    continue
                payload = event.get("payload") or {}
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except ValueError:
                        continue
                qid = payload.get("qid")
                answer = payload.get("answer")
                if qid and answer and qid not in facts:
                    facts[str(qid)] = str(answer)[:_MAX_STORED_CHARS]
        except Exception:
            return {}
        return dict(list(facts.items())[:limit])

    # -- internals -----------------------------------------------------------
    def _asked_ids(self) -> set[str]:
        out: set[str] = set()
        try:
            for event in self.store.recent(limit=500):
                if event.get("kind") != _ASKED_EVENT:
                    continue
                payload = event.get("payload") or {}
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except ValueError:
                        continue
                if payload.get("qid"):
                    out.add(str(payload["qid"]))
        except Exception:
            pass
        return out

    def _asked_in_week(self, now: float) -> int:
        count = 0
        try:
            for event in self.store.recent(limit=500):
                if event.get("kind") != _ASKED_EVENT:
                    continue
                if float(event.get("ts", 0)) >= now - _WEEK_SECONDS:
                    count += 1
        except Exception:
            pass
        return count
