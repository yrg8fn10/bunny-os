"""Session-end farewell ("wag off") lines.

When the player says they are done for today, or closes a game after a
session, Bun Bun gives one short goodbye before anything shuts down.  She
knows the session is over and may nudge a different game for next time.
Local only, no network, kid-friendly, and never pressuring.
"""
from __future__ import annotations

import random
import re
from typing import Iterable

DONE_PHRASES = (
    "done for today",
    "done for tonight",
    "done for now",
    "done playing",
    "i'm done",
    "im done",
    "i am done",
    "calling it",
    "let's call it",
    "lets call it",
    "call it a night",
    "that's all for today",
    "thats all for today",
    "time to quit",
    "let's stop here",
    "lets stop here",
)

FAREWELL_LINES = (
    "Okay, ears down for today! This world is safe from me... for now.",
    "Wag wag. Session over, save file kept warm. Same time tomorrow?",
    "Goodbye for today! I'll guard your save while you're gone.",
    "You're done? Already? Okay... I'm keeping your seat warm. See you next time!",
    "Closing time! You did great today. Want a different game tomorrow? I'll be here.",
    "Ears folded, whiskers relaxed. Done for today. Rest well, boss!",
    "Alright! Powering down my game ears. Go be a human, I'll hold down the base.",
    "See you tomorrow, boss! The bunnies will miss you. Not the fish though.",
)

_PUNCT = re.compile(r"[^\w\s']+")


def said_done(text: str | None) -> bool:
    """True when the player is wrapping up the session."""
    normalized = _PUNCT.sub(" ", (text or "").lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    return any(phrase in normalized for phrase in DONE_PHRASES)


def pick(rng: random.Random | None = None, seen: Iterable[str] | None = None) -> str:
    """Choose a farewell, preferring lines the player has not heard yet."""
    chooser = rng or random.Random()
    seen_set = set(seen or ())
    unseen = [line for line in FAREWELL_LINES if line not in seen_set]
    pool = unseen or list(FAREWELL_LINES)
    return chooser.choice(pool)
