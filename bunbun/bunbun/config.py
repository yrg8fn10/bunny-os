"""Configuration loading for Bun Bun.

Precedence (lowest to highest):
    built-in defaults -> /etc/bunny/settings.json (ai.*) -> ~/.config/bunbun.json
    -> environment variables (BUNBUN_*)

Nothing here ever reads the network.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

SYSTEM_SETTINGS = Path("/etc/bunny/settings.json")
USER_SETTINGS = Path("~/.config/bunbun.json")
PACKAGE_DATA = Path(__file__).parent / "data"


@dataclass(frozen=True)
class AgentConfig:
    host: str = "127.0.0.1"
    port: int = 8422
    data_dir: Path = Path("~/.local/share/bunbun")
    settings_file: Path = SYSTEM_SETTINGS
    voice_enabled: bool = True
    voice: str = "bunny-default"
    hint_level: str = "gentle"
    commentary: bool = True
    coop_opt_in: bool = False
    coop_mode: str = "invite-only"
    screen_vision: bool = False
    kid_safe: bool = True
    local_only: bool = True
    memory_enabled: bool = True
    tts_backend: str = "auto"       # auto|piper|espeak|none
    piper_model: Path | None = None
    tick_seconds: float = 4.0
    max_utterance_chars: int = 180
    log_level: str = "INFO"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir.expanduser() / "bunbun.sqlite3"

    @property
    def log_path(self) -> Path:
        return self.data_dir.expanduser() / "bunbun.log"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.expanduser().read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return default


def load_config(settings_file: Path | None = None,
                user_file: Path | None = None) -> AgentConfig:
    cfg = AgentConfig()
    system = _read_json(settings_file or cfg.settings_file)
    user = _read_json(user_file or USER_SETTINGS)

    ai = system.get("ai", {}) if isinstance(system.get("ai"), dict) else {}
    merged: dict[str, Any] = {**ai, **user}

    def pick(key: str, default: Any) -> Any:
        return merged.get(key, default)

    cfg = replace(
        cfg,
        voice_enabled=_coerce_bool(pick("voice_enabled", cfg.voice_enabled), cfg.voice_enabled),
        voice=str(pick("voice", cfg.voice)),
        hint_level=str(pick("hint_level", cfg.hint_level)),
        commentary=_coerce_bool(pick("commentary", cfg.commentary), cfg.commentary),
        coop_opt_in=_coerce_bool(pick("coop_opt_in", cfg.coop_opt_in), cfg.coop_opt_in),
        coop_mode=str(pick("coop_mode", cfg.coop_mode)),
        screen_vision=_coerce_bool(pick("screen_vision", cfg.screen_vision), cfg.screen_vision),
        kid_safe=_coerce_bool(pick("kid_safe", cfg.kid_safe), cfg.kid_safe),
        local_only=_coerce_bool(pick("local_only", cfg.local_only), cfg.local_only),
        memory_enabled=_coerce_bool(pick("memory_enabled", cfg.memory_enabled),
                                    cfg.memory_enabled),
        tts_backend=str(pick("tts_backend", cfg.tts_backend)),
        max_utterance_chars=int(pick("max_utterance_chars", cfg.max_utterance_chars)),
    )

    env = os.environ
    if "BUNBUN_PORT" in env:
        cfg = replace(cfg, port=int(env["BUNBUN_PORT"]))
    if "BUNBUN_HOST" in env:
        cfg = replace(cfg, host=env["BUNBUN_HOST"])
    if "BUNBUN_DATA_DIR" in env:
        cfg = replace(cfg, data_dir=Path(env["BUNBUN_DATA_DIR"]))
    if "BUNBUN_TTS" in env:
        cfg = replace(cfg, tts_backend=env["BUNBUN_TTS"])
    if "BUNBUN_PIPER_MODEL" in env:
        cfg = replace(cfg, piper_model=Path(env["BUNBUN_PIPER_MODEL"]))
    if "BUNBUN_LOG_LEVEL" in env:
        cfg = replace(cfg, log_level=env["BUNBUN_LOG_LEVEL"])
    if "BUNBUN_DISABLE" in env:
        cfg = replace(cfg, extra={**cfg.extra, "disabled": True})

    return cfg
