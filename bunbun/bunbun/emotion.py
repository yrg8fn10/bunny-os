"""Bun Bun's advanced emotional system (AES) - phase 1.

A live mood engine: Bun Bun keeps a real emotional state that changes with
what happens around her, decays back to her cheerful baseline, colors how
she speaks, and is exposed for the control panel and the mic-side reader.
Everything here is local state; nothing ever leaves the machine.

Design doc: docs/EMOTION.md.
"""
from __future__ import annotations

import time
from typing import Any, Callable

# Mood fields and their resting baselines. Bun Bun rests cheerful and
# curious; that is who she is.
_BASELINE = {
    "valence": 0.70,    # warm vs. down
    "energy": 0.60,     # bouncy vs. sleepy
    "curiosity": 0.60,  # the one-question-at-a-time drive
    "worry": 0.10,      # rises when the player struggles
    "pride": 0.40,      # spikes on the player's wins
}

# How fast each field drifts home per second (gentle: minutes, not seconds).
_DECAY = {
    "valence": 0.004,
    "energy": 0.003,
    "curiosity": 0.002,
    "worry": 0.005,
    "pride": 0.004,
}

# Events -> nudges. A positive nudge raises the field.
EVENTS: dict[str, dict[str, float]] = {
    "game.started": {"energy": 0.10, "curiosity": 0.10},
    "game.stopped": {"energy": -0.05, "curiosity": -0.05},
    "player.win": {"pride": 0.20, "valence": 0.05, "energy": 0.05},
    "player.lose": {"worry": 0.15, "valence": -0.05, "energy": -0.05},
    "player.sad": {"worry": 0.25, "valence": -0.10, "energy": -0.05},
    "player.happy": {"valence": 0.10, "energy": 0.05},
    "player.quiet": {"worry": 0.10, "energy": -0.05},
    "player.calm": {},
    "long.silence": {"energy": -0.05},
    "break.offered": {"worry": -0.10},
}

_PLAYER_LEVEL_TO_EVENT = {
    "lively": "player.happy",
    "normal": "player.calm",
    "flat": "player.quiet",
    "down": "player.sad",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class MoodEngine:
    """Bun Bun's live emotional state and the voice mapping it drives."""

    def __init__(self, clock: Callable[[], float] = time.monotonic,
                 rng: Any = None):
        self.clock = clock
        self.rng = rng
        self.fields = dict(_BASELINE)
        self._last = clock()

    # -- updates -----------------------------------------------------------
    def nudge(self, field: str, amount: float) -> None:
        if field in self.fields:
            self.fields[field] = _clamp(self.fields[field] + amount)

    def apply_event(self, event: str) -> dict[str, Any]:
        """Nudge the mood for a known event; returns the resulting mood."""
        for field, amount in EVENTS.get(event, {}).items():
            self.nudge(field, amount)
        self._last = self.clock()
        return self.to_dict()

    def tick(self, dt: float) -> None:
        """Let the mood drift back toward Bun Bun's baseline."""
        if dt <= 0:
            return
        for field, rate in _DECAY.items():
            base = _BASELINE[field]
            value = self.fields[field]
            if value > base:
                value = max(base, value - rate * dt)
            else:
                value = min(base, value + rate * dt)
            self.fields[field] = value
        self._last = self.clock()

    # -- reads -------------------------------------------------------------
    def read_level(self) -> str:
        """Bun Bun's own state as a coarse level the control panel can show."""
        if self.fields["worry"] >= 0.5 or self.fields["valence"] <= 0.35:
            return "down"
        if self.fields["valence"] >= 0.65 and self.fields["energy"] >= 0.55:
            return "lively"
        return "normal"

    @staticmethod
    def player_read(pitch_variance: float, energy: float,
                    speech_rate: float) -> str:
        """v1 prosody read of the PLAYER's mood from mic features.

        Deliberately simple acoustic cues, never a diagnosis: flat and
        quiet reads down, lively reads lively. The mic pipeline feeds
        these features, and only under the listening-model v2 gates.
        """
        if pitch_variance < 0.2 and energy < 0.35:
            return "down"
        if pitch_variance > 0.6 and energy > 0.6:
            return "lively"
        if energy < 0.45 or speech_rate < 0.35:
            return "flat"
        return "normal"

    def player_event(self, level: str) -> str:
        """Map a player read-level to the mood event it triggers."""
        return _PLAYER_LEVEL_TO_EVENT.get(str(level).lower(), "player.calm")

    # -- voice mapping -----------------------------------------------------
    def voice_params(self) -> dict[str, float]:
        """Piper synth parameters that follow the mood.

        Lower energy speaks a touch slower; low valence warms the
        delivery slightly without turning gloomy. Values stay close to
        Piper's defaults so the trained voice still sounds like itself.
        """
        energy = self.fields["energy"]
        valence = self.fields["valence"]
        length_scale = _clamp(1.25 - 0.35 * energy, 0.9, 1.3)
        noise_scale = _clamp(0.667 + 0.15 * (1.0 - valence), 0.55, 0.85)
        return {
            "length_scale": round(length_scale, 3),
            "noise_scale": round(noise_scale, 3),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "fields": {k: round(v, 3) for k, v in self.fields.items()},
            "read_level": self.read_level(),
        }
