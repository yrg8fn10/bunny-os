"""Game library linking (pre10 pillar 4, Steam first).

Everything is local file parsing: Bun Bun reads Steam's own manifests the way
the game watcher already does, remembers the library in memory, and can launch
a game by voice through ``steam://rungameid/<appid>``. No Web API key, no
login, no network. Epic/GoG arrive in a later build (Ava's call).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .intents import best_match
from .perception.steam import InstalledGame, installed_games

LOG = logging.getLogger("bunbun.library")


class LibraryError(RuntimeError):
    pass


class LibraryManager:
    """The linked game library. Steam-first, fully local."""

    def __init__(self, launcher=None):
        self.games: list[InstalledGame] = []
        self.linked: bool = False
        self.last_linked_at: float = 0.0
        self._launcher = launcher or self._default_launcher

    # -- linking -----------------------------------------------------------
    def link(self, roots: list[Path] | None = None) -> dict:
        """Rescan Steam's manifests and remember the library."""
        games = installed_games(roots)
        self.games = games
        self.linked = True
        import time
        self.last_linked_at = time.time()
        return {"linked": True, "count": len(games),
                "titles": [g.name for g in games]}

    # -- queries -----------------------------------------------------------
    def find(self, title: str):
        game, score = best_match(title, self.games)
        return game, score

    def preview(self, limit: int = 5) -> list[str]:
        return [g.name for g in self.games[:limit]]

    def status(self) -> dict:
        return {"linked": self.linked, "count": len(self.games),
                "platform": "steam", "sample": self.preview(3)}

    # -- launch ------------------------------------------------------------
    @staticmethod
    def _default_launcher(game: InstalledGame) -> bool:
        opener = shutil.which("xdg-open")
        if not opener:
            LOG.info("no xdg-open on PATH; cannot launch %s", game.name)
            return False
        proc = subprocess.run(
            [opener, f"steam://rungameid/{game.app_id}"],
            capture_output=True, timeout=15)
        return proc.returncode == 0

    def launch(self, game: InstalledGame) -> bool:
        ok = bool(self._launcher(game))
        if ok:
            LOG.info("launch requested: %s (app %s)", game.name, game.app_id)
        return ok
