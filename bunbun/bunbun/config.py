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
    voice_speaker: int | None = None  # multi-speaker models: which speaker is Bun Bun
    hint_level: str = "gentle"
    commentary: bool = True
    coop_opt_in: bool = False
    coop_mode: str = "invite-only"
    screen_vision: bool = False
    kid_safe: bool = True
    local_only: bool = True
    memory_enabled: bool = True
    tts_backend: str = "auto"       # auto|qwentts|piper|espeak|none
    mic_enabled: bool = True        # ears on; per Ava's Nov 24 direction she listens on the desktop and in Game Mode too
    mic_push_to_talk: bool = False  # no push-to-talk per Ava's Nov 3 design
    mic_stt: str = "auto"           # auto|whisper|none (local only)
    mic_listen_mode: str = "always"  # session|always; always is the default now: ears open on the desktop and in Game Mode (Ava, Nov 24 2026)
    mic_poll_seconds: float = 1.5   # cadence of the listening loop
    whisper_model: Path | None = None  # local whisper.cpp model; never bundled
    mic_device: str = ""            # PipeWire target; empty = default source
    mam_enabled: bool = True        # the local MAM brain (bundled model, llama.cpp CLI); off = rule lines only
    mam_model_path: Path | None = None  # bundled Q4 GGUF; None = auto-find in the standard share paths
    mam_llama_cli: Path | None = None   # llama.cpp CLI binary; None = auto-find (bunbun-llama-cli, then llama-cli)
    mam_max_tokens: int = 64        # one short spoken sentence
    mam_temp: float = 0.8
    mam_timeout: float = 20.0       # seconds; a slow reply loses to the rule lines
    curiosity_enabled: bool = True  # the get-to-know-you layer (Ava, Nov 17 2026); asks are rare and local-only
    curiosity_minutes_into_session: float = 12.0  # warm-up before her first question in a session
    curiosity_max_per_week: int = 0  # 0 = unlimited (Ava's ask, Nov 17 2026); set a number to cap questions per rolling week
    piper_model: Path | None = None
    voice_bank: Path | None = None  # pre-rendered v2 voice bank; auto-found when None
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


def _optional_path(value) -> Path | None:
    if value is None or value == "":
        return None
    return Path(str(value)).expanduser()


def _optional_int(value: Any, default: int | None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
        voice_speaker=_optional_int(pick("speaker", cfg.voice_speaker), cfg.voice_speaker),
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
        voice_bank=_optional_path(pick("voice_bank", None)),
        mic_enabled=_coerce_bool(pick("mic_enabled", cfg.mic_enabled), cfg.mic_enabled),
        mic_push_to_talk=_coerce_bool(pick("mic_push_to_talk", cfg.mic_push_to_talk),
                                      cfg.mic_push_to_talk),
        mic_stt=str(pick("mic_stt", cfg.mic_stt)),
        mic_listen_mode=str(pick("mic_listen_mode", cfg.mic_listen_mode)),
        mic_poll_seconds=float(pick("mic_poll_seconds", cfg.mic_poll_seconds)),
        whisper_model=(_optional_path(pick("whisper_model", None))),
        mic_device=str(pick("mic_device", cfg.mic_device)),
        max_utterance_chars=int(pick("max_utterance_chars", cfg.max_utterance_chars)),
        curiosity_enabled=_coerce_bool(pick("curiosity_enabled", cfg.curiosity_enabled),
                                       cfg.curiosity_enabled),
        curiosity_minutes_into_session=float(pick(
            "curiosity_minutes_into_session", cfg.curiosity_minutes_into_session)),
        curiosity_max_per_week=int(pick("curiosity_max_per_week", cfg.curiosity_max_per_week)),
        mam_enabled=_coerce_bool(pick("mam_enabled", cfg.mam_enabled), cfg.mam_enabled),
        mam_model_path=_optional_path(pick("mam_model_path", None)),
        mam_llama_cli=_optional_path(pick("mam_llama_cli", None)),
        mam_max_tokens=int(pick("mam_max_tokens", cfg.mam_max_tokens)),
        mam_temp=float(pick("mam_temp", cfg.mam_temp)),
        mam_timeout=float(pick("mam_timeout", cfg.mam_timeout)),
    )

    env = os.environ
    if "BUNBUN_PORT" in env:
        cfg = replace(cfg, port=int(env["BUNBUN_PORT"]))
    if "BUNBUN_HOST" in env:
        cfg = replace(cfg, host=env["BUNBUN_HOST"])
    if "BUNBUN_DATA_DIR" in env:
        cfg = replace(cfg, data_dir=Path(env["BUNBUN_DATA_DIR"]))
    if "BUNBUN_MIC_ENABLED" in env:
        cfg = replace(cfg, mic_enabled=_coerce_bool(env["BUNBUN_MIC_ENABLED"], cfg.mic_enabled))
    if "BUNBUN_TTS" in env:
        cfg = replace(cfg, tts_backend=env["BUNBUN_TTS"])
    if "BUNBUN_PIPER_MODEL" in env:
        cfg = replace(cfg, piper_model=Path(env["BUNBUN_PIPER_MODEL"]))
    if "BUNBUN_VOICE_BANK" in env:
        cfg = replace(cfg, voice_bank=Path(env["BUNBUN_VOICE_BANK"]))
    if "BUNBUN_LOG_LEVEL" in env:
        cfg = replace(cfg, log_level=env["BUNBUN_LOG_LEVEL"])
    if "BUNBUN_DISABLE" in env:
        cfg = replace(cfg, extra={**cfg.extra, "disabled": True})

    return cfg
