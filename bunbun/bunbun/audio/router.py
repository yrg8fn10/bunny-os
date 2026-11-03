"""PipeWire audio router (Deliverable 3).

Best-effort by design: when the helper binary is missing, every call returns
``False``/``None`` and the system keeps working exactly as before. On the Deck
target (PipeWire + wireplumber) it does two jobs:

* duck the default sink while Bun Bun speaks, so she is always audible over
  game audio, then restore the player's own volume afterwards;
* report the microphone's muted state so the agent can show the kill switch in
  the panel instead of pretending to listen.
"""
from __future__ import annotations

import logging
from typing import Optional

from .helpers import parse_volume, run

LOG = logging.getLogger("bunbun.audio.router")

DEFAULT_DUCK_FACTOR = 0.35


class AudioRouter:
    """Volume ducking around Bun Bun's lines, and kill-switch reporting."""

    def __init__(self, sink: Optional[str] = None, duck_factor: float = DEFAULT_DUCK_FACTOR):
        self.sink = sink              # None -> PipeWire default sink
        self.duck_factor = max(0.0, min(1.0, duck_factor))
        self._ducked = False
        self._saved_volume: Optional[float] = None

    # -- helpers -----------------------------------------------------------
    def _node(self, source: bool = False) -> str:
        if source:
            return "@DEFAULT_AUDIO_SOURCE@"
        return self.sink or "@DEFAULT_AUDIO_SINK@"

    def read_volume(self, source: bool = False) -> Optional[float]:
        proc = run(["wpctl", "get-volume", self._node(source)], timeout=5)
        if proc is None or proc.returncode != 0:
            return None
        return parse_volume(proc.stdout.decode("utf-8", "replace"))

    def _set_volume(self, value: float, source: bool = False) -> bool:
        proc = run(["wpctl", "set-volume", self._node(source), f"{value:.2f}"], timeout=5)
        return proc is not None and proc.returncode == 0

    # -- ducking -----------------------------------------------------------
    @property
    def ducked(self) -> bool:
        return self._ducked

    def duck(self) -> bool:
        """Lower game audio before Bun Bun speaks."""
        if self._ducked:
            return True
        volume = self.read_volume()
        if volume is None:
            LOG.info("duck skipped: no wpctl volume")
            return False
        self._saved_volume = volume
        if self._set_volume(volume * self.duck_factor):
            self._ducked = True
            return True
        self._saved_volume = None
        return False

    def unduck(self) -> bool:
        """Restore the player's own volume after Bun Bun speaks."""
        if not self._ducked:
            return True
        if self._saved_volume is None:
            self._ducked = False
            return False
        if self._set_volume(self._saved_volume):
            self._ducked = False
            self._saved_volume = None
            return True
        return False

    # -- kill switch -------------------------------------------------------
    def mic_muted(self) -> Optional[bool]:
        """True when the default source reports muted; None when unknowable."""
        proc = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"], timeout=5)
        if proc is None or proc.returncode != 0:
            return None
        return "MUTED" in proc.stdout.decode("utf-8", "replace").upper()
