"""Voice command intents (pre10 pillar 4: game-library linking).

Bun Bun hears short, plain commands and turns them into actions:

    "link up my steam"           -> link_library
    "what games do we have"      -> list_games
    "let's play subnautica"      -> launch <title>
    "hii buddy"                  -> greet

Parsing is deliberately small and local: regex + fuzzy title matching. No
network, no model, no keys. The MAM policy still gates anything that acts.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

_STRIP = re.compile(r"[^\w\s']", re.I)

_LINK = re.compile(
    r"\b(link|connect|pair|hook up|sync|import)\b.*\b(steam|library|account)\b", re.I)
_LIST = re.compile(
    r"\b(what|which)\b.*\b(games|library)\b|\bwhat can we (play|do)\b|\bshow (my |us |me )?(games|library)\b",
    re.I)
_LAUNCH = re.compile(
    r"\b(let'?s|lets|start|launch|open|play|enter|boot up)\b\s*(.*)", re.I)
_GREET = re.compile(r"\b(hi+|hey+|hello|good morning|good evening|yo)\b[\s,!.]*"
                    r"\b(bun ?bun|buddy|girl|friend|sis|bestie)?\b", re.I)

_LAUNCH_STOPWORDS = {
    "the", "a", "an", "up", "on", "steam", "now", "please", "buddy", "girl",
    "some", "something", "game", "games",
}


@dataclass(frozen=True)
class Command:
    kind: str = "unknown"    # link_library | list_games | launch | greet | unknown
    arg: str = ""

    def to_dict(self) -> dict:
        return {"kind": self.kind, "arg": self.arg}


def _clean_title(raw: str) -> str:
    text = _STRIP.sub(" ", raw or "").strip().lower()
    words = [w for w in text.split() if w not in _LAUNCH_STOPWORDS]
    return " ".join(words)


def parse_command(text: str) -> Command:
    """Turn a transcript into a Command. Unknown text is not a command."""
    text = (text or "").strip()
    if not text:
        return Command()
    if _LINK.search(text):
        return Command(kind="link_library")
    if _LIST.search(text):
        return Command(kind="list_games")
    match = _LAUNCH.search(text)
    if match:
        raw = match.group(2) or ""
        # "let's play X" and "play X" both land here; peel a repeated verb.
        raw = re.sub(r"^(let'?s\s+|lets\s+)?(play\s+|start\s+|launch\s+|open\s+|enter\s+|boot up\s+)?",
                     "", raw, flags=re.I)
        title = _clean_title(raw)
        if len(title.split()) <= 8:
            return Command(kind="launch", arg=title)
    if _GREET.match(text) and len(text) <= 24:
        return Command(kind="greet")
    return Command()


def best_match(title: str, candidates: list, threshold: float = 0.42):
    """Fuzzy-match a spoken title against library entries (Steam-first).

    ``candidates`` are objects with a ``.name``; returns (match, score).
    """
    if not title or not candidates:
        return None, 0.0
    needle = title.lower().strip()
    best, best_score = None, 0.0
    for candidate in candidates:
        name = getattr(candidate, "name", "") or ""
        hay = name.lower()
        score = difflib.SequenceMatcher(None, needle, hay).ratio()
        # A substring hit in a longer title scores well for real games
        # ("subnautica" -> "Subnautica Below Zero").
        if needle and needle in hay:
            score = max(score, 0.9)
        # Word-prefix hits ("black mesa" -> "Black Mesa").
        elif hay.startswith(needle):
            score = max(score, 0.85)
        if score > best_score:
            best, best_score = candidate, score
    if best is not None and best_score >= threshold:
        return best, best_score
    return None, best_score
