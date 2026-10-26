"""Hint library.

Hints are plain JSON so players and modders can add their own without touching
code.  Each hint declares a level, tags, an optional game id (``*`` is generic)
and a short spoken phrase.  Nothing is fetched from the network.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

LEVEL_ORDER = {"off": 0, "gentle": 1, "helpful": 2, "spoilery": 3}


@dataclass(frozen=True)
class Hint:
    hint_id: str
    game: str
    level: str
    text: str
    where: str = ""
    tags: tuple[str, ...] = ()
    secret: bool = False

    @property
    def level_value(self) -> int:
        return LEVEL_ORDER.get(self.level, 1)

    def as_dict(self) -> dict:
        return {
            "id": self.hint_id,
            "game": self.game,
            "level": self.level,
            "text": self.text,
            "where": self.where,
            "tags": list(self.tags),
            "secret": self.secret,
        }


class HintLibrary:
    def __init__(self, hints: Iterable[Hint] | None = None, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self._hints: list[Hint] = list(hints or [])

    @classmethod
    def from_directory(cls, path: Path, rng: random.Random | None = None) -> "HintLibrary":
        hints: list[Hint] = []
        path = Path(path)
        if not path.is_dir():
            return cls([], rng=rng)
        for file in sorted(path.glob("*.json")):
            try:
                data = json.loads(file.read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for raw in data.get("hints", []):
                try:
                    hints.append(Hint(
                        hint_id=str(raw["id"]),
                        game=str(raw.get("game", "*")),
                        level=str(raw.get("level", "gentle")),
                        text=str(raw["text"]),
                        where=str(raw.get("where", "")),
                        tags=tuple(raw.get("tags", [])),
                        secret=bool(raw.get("secret", False)),
                    ))
                except (KeyError, TypeError):
                    continue
        return cls(hints, rng=rng)

    def __len__(self) -> int:
        return len(self._hints)

    def add(self, hint: Hint) -> None:
        self._hints.append(hint)

    def for_game(self, game_id: str) -> list[Hint]:
        return [h for h in self._hints if h.game in {game_id, "*"}]

    def pick(self, game_id: str, level: str = "gentle", seen: Callable[[str], bool] | None = None,
             tags: set[str] | None = None, allow_secret: bool = False) -> Hint | None:
        """Choose an unseen hint at or below `level`.

        Unseen hints win; if everything is seen we return None rather than
        repeating ourselves.  Secrets are opt-in even at high hint levels.
        """
        ceiling = LEVEL_ORDER.get(level, 1)
        if ceiling == 0:
            return None
        seen = seen or (lambda _hint_id: False)
        candidates = [
            h for h in self.for_game(game_id)
            if h.level_value <= ceiling
            and not (h.secret and not allow_secret)
            and not seen(h.hint_id)
            and (not tags or set(h.tags) & tags)
        ]
        if not candidates:
            return None
        # Prefer the most specific (game-specific) and most relevant hints.
        candidates.sort(key=lambda h: (h.game == game_id, h.level_value), reverse=True)
        top = candidates[0]
        same_tier = [h for h in candidates if h.game == top.game and h.level_value == top.level_value]
        return self.rng.choice(same_tier)
