"""Heroic / Legendary / Lutris discovery.

Heroic (Epic + GOG) is installed as a Flatpak, so its config lives under
``~/.var/app/com.heroicgameslauncher.hgl``.  We read installed-game metadata
only — never tokens or account credentials.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .steam import InstalledGame


def _heroic_bases() -> Iterable[Path]:
    home = Path.home()
    yield home / ".config" / "heroic"
    yield home / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "heroic"


def _legendary_bases() -> Iterable[Path]:
    home = Path.home()
    yield home / ".config" / "legendary"
    yield home / ".var" / "app" / "com.heroicgameslauncher.hgl" / "config" / "legendary"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def legendary_installed() -> list[InstalledGame]:
    games: dict[str, InstalledGame] = {}
    for base in _legendary_bases():
        data = _load_json(base / "installed.json")
        if not isinstance(data, dict):
            continue
        for app_name, meta in data.items():
            if not isinstance(meta, dict):
                continue
            title = str(meta.get("title") or app_name)
            install_path = Path(str(meta.get("install_path", "")))
            games[app_name] = InstalledGame(
                app_id=str(app_name),
                name=title,
                install_dir=str(install_path),
                library=install_path.parent,
                platform="epic",
                size_bytes=int(meta.get("install_size", 0) or 0),
            )
    return list(games.values())


def heroic_gog_installed() -> list[InstalledGame]:
    games: dict[str, InstalledGame] = {}
    for base in _heroic_bases():
        data = _load_json(base / "gog_store" / "installed.json")
        if not isinstance(data, dict):
            continue
        for entry in data.get("installed", []):
            if not isinstance(entry, dict):
                continue
            app_name = str(entry.get("appName", ""))
            if not app_name:
                continue
            install_path = Path(str(entry.get("install_path", "")))
            games[app_name] = InstalledGame(
                app_id=app_name,
                name=str(entry.get("title") or app_name),
                install_dir=str(install_path),
                library=install_path.parent,
                platform="gog",
                size_bytes=int(entry.get("install_size", 0) or 0),
            )
    return list(games.values())


def all_installed() -> list[InstalledGame]:
    return legendary_installed() + heroic_gog_installed()


def lutris_games() -> list[dict[str, Any]]:
    """Lutris keeps a sqlite DB; parsing it is out of scope for v0.1.

    We expose the config directory so the Control Panel can hand off to the
    ``lutris`` CLI, which is the supported integration surface.
    """
    path = Path.home() / ".config" / "lutris"
    return [{"platform": "lutris", "config": str(path)}] if path.is_dir() else []
