"""Minecraft (Prism Launcher and friends) game detection.

Bun Bun listens during game sessions, and the session gate is driven by
the game watcher. Steam and Heroic cover the launcher stores, but
Minecraft run from Prism Launcher is invisible to both, so her ears and
her presence never woke for it. This module scans /proc for the Java
process actually running Minecraft (the launcher menu alone is not a
game session) and reports it as one, so Minecraft counts like any other
game.

Deliberately cheap: one /proc pass per watcher poll, nothing written.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

# Java launchers whose games we treat as sessions when their game runs.
LAUNCHERS = ("prismlauncher", "multimc", "polymc", "atlauncher", "modrinth-app")


def _cmdlines():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                raw = f.read()
        except OSError:
            continue
        parts = [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]
        if parts:
            yield " ".join(parts).lower()


def running_game():
    """The running Minecraft session, or None.

    Matches the shape the watcher's Steam path returns (name, app_id,
    platform, path) so the rest of the pipeline cannot tell the
    difference.
    """
    launcher_up = False
    game_up = False
    for line in _cmdlines():
        if not game_up and "minecraft" in line and "java" in line:
            game_up = True
        if not launcher_up and any(m in line for m in LAUNCHERS):
            launcher_up = True
    if not game_up:
        return None
    return SimpleNamespace(
        name="Minecraft",
        app_id="minecraft",
        platform="prism" if launcher_up else "java",
        path="",
    )
