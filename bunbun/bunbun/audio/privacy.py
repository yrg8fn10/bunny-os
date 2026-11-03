"""Privacy gate for Bun Bun's ears (Deliverable 3, session-listen mode).

Ava's rule: Bun Bun listens while you play, but the moment she hears something
private she mutes herself, throws the audio away, and only comes back for game
talk. The gate is deliberately conservative: anything that looks like a secret,
a payment detail, a live location or an address ends the listening window and
the clip is deleted without ever being transcribed.

This is a local, keyword-and-pattern classifier, not a model. It is best-effort,
which is exactly why it sits *on top of* the other gates (settings switch,
session scope, hardware kill switch), never instead of them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# Patterns that mean "stop listening now". Order does not matter; any hit wins.
PATTERNS: tuple[tuple[str, str], ...] = (
    ("credentials", r"(?i)\b(my |the )?(password|passcode|pass phrase|pin|api[ -]?key|token|ssh key)\b"),
    ("secrets",     r"(?i)\b(secret answer|recovery code|two[ -]?factor|2fa)\b"),
    ("money",       r"\b(?:\d[ -]*?){13,19}\b"),                          # card-shaped digit runs
    ("money",       r"(?i)\b(bank account|routing number|social security|\bssn\b)\b"),
    ("contact",     r"(?i)\b(my |the )?(home )?(address|phone number|email)\b"),
    ("contact",     r"\b\d{3}[ -.]{0,1}\d{3}[ -.]{0,1}\d{4}\b"),          # phone-shaped
    ("money",       r"(?i)\b(salary|wage|how much i (make|earn|get paid))\b"),
    ("identity",    r"(?i)\b(my )?(birthday|birth date|date of birth)\b"),
)

GREETING_BACK = "Okay, we're talking about games now? Okay! Back to the game~"


@dataclass
class PrivacyGate:
    """Reviews transcribed speech and closes the window on private topics."""

    cooldown_seconds: float = 20.0
    muted_until: float = 0.0
    hits: list[tuple[str, str]] = field(default_factory=list)
    muted_count: int = 0

    def review(self, text: Optional[str], now: float) -> bool:
        """True when the text is game talk; False when it triggered a mute.

        ``None`` (no transcription available) is treated as *not* private but
        also as nothing to keep: callers discard the clip either way.
        """
        if not text:
            return True
        for label, pattern in PATTERNS:
            if re.search(pattern, text):
                self.hits.append((label, text))
                self.muted_until = now + self.cooldown_seconds
                self.muted_count += 1
                return False
        return True

    def muted(self, now: float) -> bool:
        """Inside the cooldown after a hit, capture stays closed."""
        return now < self.muted_until

    def resume(self) -> None:
        self.muted_until = 0.0
