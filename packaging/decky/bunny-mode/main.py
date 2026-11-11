# Bunny Mode - pre10 pillar 1: the theme follows Bun Bun across modes.
# Watches the desktop <-> Game Mode switch and flips the bunny theme with her.
# Game Mode on Bazzite runs under gamescope; desktop mode runs KDE Plasma.

import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("BunnyMode")

STATE_FILE = Path("/tmp/bunny_mode_state")
POLL_SECONDS = 2.0

# What each side does when Bun Bun crosses. The Game Mode side is where the
# CSS Loader profile gets enabled/disabled; that wiring lands in build 2.
THEME_PROFILE = "Bunny Pastel UI"


def active_session() -> str:
    """Which session is alive right now: gamemode, desktop, or unknown."""
    try:
        if subprocess.run(["pgrep", "-x", "plasmashell"],
                          capture_output=True).returncode == 0:
            return "desktop"
        if subprocess.run(["pgrep", "-x", "gamescope"],
                          capture_output=True).returncode == 0:
            return "gamemode"
    except FileNotFoundError:
        pass
    return "unknown"


class Plugin:
    def __init__(self):
        self._watch_task = None
        self._current = "unknown"

    async def _mode_watch(self):
        logger.info("Bunny Mode watching for mode switches")
        while True:
            mode = await asyncio.to_thread(active_session)
            if mode != "unknown" and mode != self._current:
                await self._on_mode_change(self._current, mode)
                self._current = mode
            await asyncio.sleep(POLL_SECONDS)

    async def _on_mode_change(self, old: str, new: str):
        logger.info("Bun Bun crossed: %s -> %s", old, new)
        STATE_FILE.write_text(new)
        if new == "gamemode":
            # TODO(pre10 build 2): enable the CSS Loader profile so the
            # bunny theme comes on with her, and raise the Game Mode
            # presence layer.
            await self._apply_theme_profile(THEME_PROFILE, True)
        elif new == "desktop":
            # TODO(pre10 build 2): re-target the theme for desktop.
            await self._apply_theme_profile(THEME_PROFILE, False)

    async def _apply_theme_profile(self, profile: str, enabled: bool):
        # Placeholder write so the state is observable from the shell while
        # the real CSS Loader hook is built. Nothing user-visible yet.
        STATE_FILE.with_suffix(".theme").write_text(
            f"{profile}:{'on' if enabled else 'off'}")
        logger.info("theme profile %s -> %s", profile,
                    "enabled" if enabled else "disabled")

    # -- frontend-facing endpoints (used by the bunny UI in a later build) --
    async def get_mode(self) -> str:
        return await asyncio.to_thread(active_session)

    async def get_state(self) -> dict:
        state = {"mode": self._current}
        if STATE_FILE.with_suffix(".theme").exists():
            state["theme"] = STATE_FILE.with_suffix(".theme").read_text().strip()
        return state

    async def on_unload(self):
        if self._watch_task:
            self._watch_task.cancel()

    async def _main(self):
        self._watch_task = asyncio.create_task(self._mode_watch())
