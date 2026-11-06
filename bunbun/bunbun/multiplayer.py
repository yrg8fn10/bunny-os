"""Bun Bun multiplayer join (EXPERIMENTAL).

v0 scope: discover the local game install, load the join config, and build
the launch command for a second game client that joins a LAN server as
BunBun.  The config file lives in the player's home directory; the server
password never leaves the machine.  Nothing here talks to the internet.
"""
from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

DEFAULT_PORT = 11000
DEFAULT_PLAYER = "BunBun"
DEFAULT_GAME = "subnautica"
DEFAULT_CONFIG_PATH = Path("~/.config/bunbun-multiplayer.json")


class MultiplayerConfigError(ValueError):
    """Raised when the join config is malformed."""


@dataclass(frozen=True)
class JoinConfig:
    player_name: str = DEFAULT_PLAYER
    game: str = DEFAULT_GAME
    server_host: str = ""
    server_port: int = DEFAULT_PORT
    server_password: str = ""  # LAN password; lives only in the local config file
    launcher_path: str = ""
    launch_args_template: str = ""


def load_config(path: str | Path | None = None) -> JoinConfig:
    """Load the join config, falling back to built-in defaults."""
    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH.expanduser()
    data: dict[str, Any] = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MultiplayerConfigError(f"cannot read {config_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise MultiplayerConfigError(f"{config_path} must contain a JSON object")
    player_name = str(data.get("player_name") or DEFAULT_PLAYER)
    game = str(data.get("game") or DEFAULT_GAME)
    server_host = str(data.get("server_host") or "")
    raw_port = data.get("server_port", DEFAULT_PORT)
    try:
        server_port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise MultiplayerConfigError(f"server_port must be a number: {raw_port!r}") from exc
    if not 1 <= server_port <= 65535:
        raise MultiplayerConfigError(f"server_port out of range: {server_port}")
    server_password = str(data.get("server_password") or "")
    launcher_path = str(data.get("launcher_path") or "")
    launch_args_template = str(data.get("launch_args_template") or "")
    return JoinConfig(
        player_name=player_name,
        game=game,
        server_host=server_host,
        server_port=server_port,
        server_password=server_password,
        launcher_path=launcher_path,
        launch_args_template=launch_args_template,
    )


def _display_name(game: Any) -> str:
    for attr in ("name", "display_name", "game_name"):
        value = getattr(game, attr, None)
        if isinstance(value, str):
            return value
    if isinstance(game, dict):
        for key in ("name", "display_name", "game_name"):
            if isinstance(game.get(key), str):
                return game[key]
    return ""


def match_game(games: Iterable[Any], needle: str = DEFAULT_GAME) -> Any | None:
    """Return the first installed game whose name contains `needle`."""
    for game in games:
        if needle.lower() in _display_name(game).lower():
            return game
    return None


def build_launch_command(cfg: JoinConfig, extra: Iterable[str] | None = None) -> list[str] | None:
    """Build the second-client launch command from the configured template.

    Placeholders: {host} {port} {player} {password}.  Returns None when no
    template is set yet: the player must run one manual join first and copy
    the working command into the config, because we never invent vendor
    command-line flags.
    """
    if not cfg.launch_args_template.strip():
        return None
    fmt = {
        "host": cfg.server_host,
        "port": str(cfg.server_port),
        "player": cfg.player_name,
        "password": cfg.server_password,
    }
    parts = [part.format(**fmt) for part in shlex.split(cfg.launch_args_template)]
    command = [cfg.launcher_path] if cfg.launcher_path else []
    command.extend(parts)
    command.extend(extra or [])
    return command


def doctor(cfg: JoinConfig, games: Iterable[Any] | None = None) -> dict[str, Any]:
    """Local readiness report.  No network calls."""
    from bunbun.perception.steam import installed_games  # local Steam library scan

    found = match_game(list(games) if games is not None else installed_games(), cfg.game)
    return {
        "player_name": cfg.player_name,
        "game": cfg.game,
        "game_found": found is not None,
        "game_name": _display_name(found) or None,
        "game_path": str(getattr(found, "path", "")) or None,
        "server_host": cfg.server_host or None,
        "server_port": cfg.server_port,
        "launcher_set": bool(cfg.launcher_path),
        "launch_template_set": bool(cfg.launch_args_template.strip()),
        "ready_to_join": bool(cfg.server_host and cfg.launch_args_template.strip()),
    }
