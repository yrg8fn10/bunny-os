"""Steam library discovery — entirely local file parsing.

We read the same manifests Steam reads:
    ~/.steam/steam/steamapps/libraryfolders.vdf
    <library>/steamapps/appmanifest_<appid>.acf

No Steam Web API key, no login, no network.  If Steam is installed elsewhere,
set ``STEAM_ROOT``.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .acf import ParseError, parse_file

STATE_FULLY_INSTALLED = 4


@dataclass(frozen=True)
class InstalledGame:
    app_id: str
    name: str
    install_dir: str
    library: Path
    platform: str = "steam"
    size_bytes: int = 0

    @property
    def path(self) -> Path:
        # Heroic/Legendary store an absolute install path; Steam stores a folder name.
        if self.install_dir.startswith("/"):
            return Path(self.install_dir)
        return self.library / "steamapps" / "common" / self.install_dir

    def as_dict(self) -> dict:
        return {
            "game_id": f"steam:{self.app_id}",
            "app_id": self.app_id,
            "title": self.name,
            "platform": self.platform,
            "install_dir": str(self.path),
            "size_bytes": self.size_bytes,
        }


def steam_roots() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("STEAM_ROOT")
    if env:
        roots.append(Path(env).expanduser())
    home = Path.home()
    for candidate in (
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        home / "snap" / "steam" / "common" / ".steam" / "steam",
        Path("/usr/share/steam"),
    ):
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def library_folders(root: Path) -> list[Path]:
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if not vdf.is_file():
        return [root]
    try:
        data = parse_file(str(vdf))
    except (OSError, ParseError):
        return [root]
    folders: list[Path] = []
    block = data.get("libraryfolders", data)
    for key, value in block.items():
        if not str(key).isdigit() or not isinstance(value, dict):
            continue
        path = value.get("path")
        if path:
            candidate = Path(str(path))
            if candidate.is_dir() and candidate not in folders:
                folders.append(candidate)
    return folders or [root]


def _parse_manifest(path: Path, library: Path) -> InstalledGame | None:
    try:
        data = parse_file(str(path))
    except (OSError, ParseError):
        return None
    app = data.get("AppState") or data.get("appstate") or {}
    if not isinstance(app, dict):
        return None
    app_id = str(app.get("appid", ""))
    name = str(app.get("name", ""))
    install_dir = str(app.get("installdir", ""))
    if not app_id or not name:
        return None
    try:
        state = int(app.get("StateFlags", "4"))
    except ValueError:
        state = STATE_FULLY_INSTALLED
    if state & STATE_FULLY_INSTALLED == 0:
        return None
    try:
        size = int(app.get("SizeOnDisk", "0"))
    except ValueError:
        size = 0
    return InstalledGame(app_id=app_id, name=name, install_dir=install_dir,
                         library=library, size_bytes=size)


def installed_games(roots: list[Path] | None = None) -> list[InstalledGame]:
    games: dict[str, InstalledGame] = {}
    for root in roots or steam_roots():
        for library in library_folders(root):
            steamapps = library / "steamapps"
            if not steamapps.is_dir():
                continue
            for manifest in steamapps.glob("appmanifest_*.acf"):
                game = _parse_manifest(manifest, library)
                if game and game.app_id not in games:
                    games[game.app_id] = game
    return sorted(games.values(), key=lambda g: g.name.lower())


def _proc_exe(pid: str) -> str | None:
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


def running_game(games: list[InstalledGame] | None = None) -> InstalledGame | None:
    """Find a running process whose executable lives inside a Steam game dir."""
    games = games if games is not None else installed_games()
    if not games:
        return None
    prefixes = [(str(g.path), g) for g in games if g.install_dir]
    proc = Path("/proc")
    if not proc.is_dir():
        return None
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        exe = _proc_exe(entry.name)
        if not exe:
            continue
        for prefix, game in prefixes:
            if exe.startswith(prefix + os.sep):
                return game
    return None


def anticheat_running() -> bool:
    """Detect common anti-cheat runtimes. Read-only, no evasion logic."""
    patterns = re.compile(
        r"(easyanticheat|beservice|battleye|vgk\.sys|vanguard|equ8|gameguard|"
        r"xigncode|nprotect|denuvo)", re.I)
    proc = Path("/proc")
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\x00", b" ").decode(
                "utf-8", "replace")
        except OSError:
            continue
        if patterns.search(cmdline):
            return True
    return False
