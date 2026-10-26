"""Bun Bun's voice and personality.

Persona text is deliberately short, warm, and never manipulative.  The
`sanitize` step is what actually reaches the speaker: it strips markup and
emotion, enforces a length budget, and guarantees a sentence ending so the
TTS engine does not run on.
"""
from __future__ import annotations

import json
import random
import re
import unicodedata
from pathlib import Path
from typing import Any

DEFAULT_PERSONA = Path(__file__).parent / "data" / "persona.json"

# Markup / emoji / control characters that should never be spoken.
_MARKUP = re.compile(r"[*_`#>\[\]{}|]")
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF\uFE0F\u200D]"
)
_WHITESPACE = re.compile(r"\s+")

# A tiny, explicit blocklist for text that must never be voiced by a kid-style
# companion.  Extend deliberately; do not make this a general profanity filter.
_FORBIDDEN_PATTERNS = (
    re.compile(r"\b(buy|purchase|upgrade now|limited time offer)\b", re.I),
    re.compile(r"\b(credit card|password|address|phone number)\b", re.I),
    re.compile(r"\b(kill yourself|hate you)\b", re.I),
)


class UnsafeText(ValueError):
    pass


class Persona:
    def __init__(self, data: dict[str, Any], rng: random.Random | None = None,
                 max_chars: int = 180):
        self.data = data
        self.rng = rng or random.Random()
        self.max_chars = max(40, min(max_chars, 400))
        self.name = data.get("name", "Bun Bun")
        self.voice = data.get("voice", {})
        self.lines: dict[str, list[str]] = data.get("lines", {})

    @classmethod
    def load(cls, path: Path | None = None, **kwargs: Any) -> "Persona":
        data = json.loads(Path(path or DEFAULT_PERSONA).read_text("utf-8"))
        return cls(data, **kwargs)

    # -- generation --------------------------------------------------------
    def line(self, kind: str, **fields: Any) -> str:
        pool = self.lines.get(kind) or self.lines.get("idle") or ["..."]
        template = self.rng.choice(pool)
        try:
            text = template.format(**fields)
        except (KeyError, IndexError):
            text = template
        return self.sanitize(text)

    def greet(self) -> str:
        return self.line("greeting")

    def encourage(self) -> str:
        return self.line("encouragement")

    def hint(self, where: str, secret: bool = False) -> str:
        return self.line("secret" if secret else "hint", where=where)

    def stuck(self) -> str:
        return self.line("stuck")

    def celebrate(self) -> str:
        return self.line("victory")

    def break_time(self) -> str:
        return self.line("break_time")

    def coop_invite(self, friend: str) -> str:
        return self.line("coop_invite", friend=friend)

    def coop_joined(self) -> str:
        return self.line("coop_joined")

    def error(self) -> str:
        return self.line("error")

    # -- safety ------------------------------------------------------------
    def check(self, text: str) -> None:
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(text):
                raise UnsafeText(f"persona text rejected by policy: {pattern.pattern}")

    def sanitize(self, text: str) -> str:
        self.check(text)
        text = unicodedata.normalize("NFKC", text)
        text = _EMOJI.sub("", text)
        text = _MARKUP.sub("", text)
        text = _WHITESPACE.sub(" ", text).strip()
        # Collapse the playful "~" more than once; it makes TTS drag.
        text = re.sub(r"~{2,}", "~", text)
        if len(text) > self.max_chars:
            cut = text[: self.max_chars]
            boundary = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"), cut.rfind(" "))
            text = (cut[: boundary + 1] if boundary > 40 else cut).strip()
        if text and text[-1] not in ".!?~":
            text += "."
        return text
