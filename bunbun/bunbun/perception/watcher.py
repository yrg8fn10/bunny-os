"""Background game watcher.

Polls local launchers, detects start/stop transitions, and publishes them on the
event bus.  Deliberately cheap: file mtimes are cached, /proc is scanned at a
low frequency, and nothing is written outside memory.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from ..bus import EventBus
from . import heroic, steam

LOG = logging.getLogger("bunbun.watcher")


@dataclass
class Snapshot:
    game_id: str = ""
    title: str = ""
    platform: str = ""
    install_dir: str = ""
    anticheat: bool = False
    multiplayer: bool = False
    detected_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "title": self.title,
            "platform": self.platform,
            "install_dir": self.install_dir,
            "anticheat": self.anticheat,
            "multiplayer": self.multiplayer,
            "detected_at": self.detected_at,
        }


class GameWatcher(threading.Thread):
    def __init__(self, bus: EventBus, interval: float = 3.0,
                 library_interval: float = 60.0,
                 multiplayer_hints: set[str] | None = None):
        super().__init__(name="bunbun-watcher", daemon=True)
        self.bus = bus
        self.interval = max(1.0, interval)
        self.library_interval = max(10.0, library_interval)
        self.multiplayer_hints = {h.lower() for h in (multiplayer_hints or set())}
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._snapshot = Snapshot()
        self._games: list[steam.InstalledGame] = []
        self._last_library_scan = 0.0
        self._last_anticheat = False

    # -- public ------------------------------------------------------------
    @property
    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._snapshot

    def stop(self) -> None:
        self._stop.set()

    # -- thread ------------------------------------------------------------
    def run(self) -> None:
        LOG.info("watcher started (interval=%.1fs)", self.interval)
        while not self._stop.is_set():
            try:
                self.poll()
            except Exception:
                LOG.exception("watcher poll failed")
            self._stop.wait(self.interval)

    def poll(self) -> Snapshot | None:
        now = time.monotonic()
        if now - self._last_library_scan > self.library_interval or not self._games:
            self._games = steam.installed_games() + heroic.all_installed()
            self._last_library_scan = now
            LOG.debug("library scan: %d titles", len(self._games))

        running = steam.running_game(self._games)
        anticheat = steam.anticheat_running() if running else False

        if running is None:
            if self.snapshot.game_id:
                with self._lock:
                    previous = self._snapshot
                    self._snapshot = Snapshot()
                self.bus.publish("game.exited", {"game_id": previous.game_id,
                                                 "title": previous.title})
                LOG.info("game exited: %s", previous.title)
            return None

        game_id = (f"{running.platform}:{running.app_id}"
                   if running.platform != "steam" else f"steam:{running.app_id}")
        with self._lock:
            previous = self._snapshot
            self._snapshot = Snapshot(
                game_id=game_id,
                title=running.name,
                platform=running.platform,
                install_dir=str(running.path),
                anticheat=anticheat,
                multiplayer=self._guess_multiplayer(running.name),
                detected_at=previous.detected_at if previous.game_id == game_id else time.time(),
            )
            snapshot = self._snapshot

        if previous.game_id != game_id:
            self.bus.publish("game.detected", snapshot.as_dict())
            LOG.info("game detected: %s (%s)", snapshot.title, snapshot.platform)
        if anticheat != self._last_anticheat:
            self.bus.publish("game.anticheat", {"active": anticheat, "game_id": game_id})
            self._last_anticheat = anticheat
        return snapshot

    def _guess_multiplayer(self, title: str) -> bool:
        return any(hint in title.lower() for hint in self.multiplayer_hints)
