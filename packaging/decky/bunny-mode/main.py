# Bunny Mode - pre10 pillar 1: the theme follows Bun Bun across modes.
# Watches the desktop <-> Game Mode switch and flips the bunny theme with her.
# Game Mode on Bazzite runs under gamescope; desktop mode runs KDE Plasma.
#
# When she crosses INTO Game Mode:
#   * the bunny-cute CSS Loader theme is switched on (CSS Loader's local
#     server, 127.0.0.1:35821/req -> set_theme_state; verified against
#     SDH-CssLoader's css_server.py), and
#   * the bunhud presence layer is started so her overlay comes up with her.
# When she crosses back to the desktop:
#   * the Game Mode theme is switched off again (the user's choice always
#     wins if they disabled it themselves in CSS Loader), and
#   * the overlay service is stopped.

import asyncio
import logging
import subprocess
import urllib.request
import json
from pathlib import Path

logger = logging.getLogger("BunnyMode")

STATE_FILE = Path("/tmp/bunny_mode_state")
POLL_SECONDS = 2.0

# Installed by the bunny-cute Decky theme payload (theme.json "name").
CSS_LOADER_THEME = "Bunny OS Cute"
CSS_LOADER_URL = "http://127.0.0.1:35821/req"
BUNHUD_UNIT = "bunny-bunhud.service"

# Cooldown so a Steam restart (mode flaps) doesn't hammer CSS Loader.
RETRY_COOLDOWN = 30.0


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
        self._last_css_attempt = 0.0

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
            await self._apply_theme_profile(True)
            await self._set_bunhud(True)
        elif new == "desktop":
            await self._apply_theme_profile(False)
            await self._set_bunhud(False)

    async def _apply_theme_profile(self, enabled: bool):
        """Ask CSS Loader (if it is running) to toggle the bunny theme."""
        import time
        now = time.monotonic()
        if now - self._last_css_attempt < RETRY_COOLDOWN:
            return
        self._last_css_attempt = now
        payload = json.dumps({
            "method": "set_theme_state",
            "args": {"name": CSS_LOADER_THEME, "state": bool(enabled)},
        }).encode()
        try:
            await asyncio.to_thread(self._post, payload, 4.0)
        except Exception as exc:  # CSS Loader not installed/running: harmless
            logger.info("CSS Loader not reachable (%s); theme stays as-is", exc)
            return
        STATE_FILE.with_suffix(".theme").write_text(
            f"{CSS_LOADER_THEME}:{'on' if enabled else 'off'}")
        logger.info("CSS Loader theme %s -> %s", CSS_LOADER_THEME,
                    "enabled" if enabled else "disabled")

    @staticmethod
    def _post(payload: bytes, timeout: float) -> dict:
        req = urllib.request.Request(
            CSS_LOADER_URL, data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())

    async def _set_bunhud(self, on: bool):
        """The Game Mode presence layer starts/stops with her."""
        verb = "start" if on else "stop"
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["systemctl", "--user", verb, BUNHUD_UNIT],
                capture_output=True, timeout=8)
            if result.returncode == 0:
                logger.info("bunhud %s: ok", verb)
            else:
                logger.info("bunhud %s: rc=%s %s", verb, result.returncode,
                            result.stderr.decode(errors="replace").strip())
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.info("bunhud %s skipped: %s", verb, exc)

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
