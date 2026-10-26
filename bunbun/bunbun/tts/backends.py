"""Text-to-speech backends.

Piper is preferred (neural, local, permissive voice models).  espeak-ng is the
fallback that is always present on a base Arch install.  Both are invoked as
subprocesses with an argument list — never through a shell.

Voice models are **not** shipped in this repository:
    ./scripts/fetch-sources.sh --voices
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

LOG = logging.getLogger("bunbun.tts")

DEFAULT_VOICE_DIR = Path("/usr/share/bunbun/voices")


@dataclass
class Voice:
    key: str
    name: str
    model: Path | None = None
    engine: str = "piper"
    license_note: str = "check the model card before redistribution"


class Backend:
    name = "null"

    def available(self) -> bool:  # pragma: no cover - trivial
        return False

    def synthesize(self, text: str, out: Path) -> bool:  # pragma: no cover
        return False


class PiperBackend(Backend):
    name = "piper"

    def __init__(self, model: Path | None, binary: str = "piper"):
        self.model = Path(model) if model else None
        self.binary = binary

    def available(self) -> bool:
        return bool(self.model and self.model.is_file()
                    and self.binary and shutil.which(self.binary))

    def synthesize(self, text: str, out: Path) -> bool:
        if not self.available():
            return False
        assert self.model is not None
        try:
            proc = subprocess.run(
                [self.binary, "--model", str(self.model), "--output_file", str(out)],
                input=text.encode("utf-8"),
                capture_output=True, timeout=30, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            LOG.warning("piper failed: %s", exc)
            return False
        if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            LOG.warning("piper produced no audio (rc=%s)", proc.returncode)
            return False
        return True


class EspeakBackend(Backend):
    name = "espeak"

    def __init__(self, binary: str = "espeak-ng", voice: str = "en+f3",
                 speed: int = 160, pitch: int = 72):
        self.binary = binary
        self.voice = voice
        self.speed = speed
        self.pitch = pitch

    def available(self) -> bool:
        return bool(shutil.which(self.binary))

    def synthesize(self, text: str, out: Path) -> bool:
        if not self.available():
            return False
        try:
            proc = subprocess.run(
                [self.binary, "-v", self.voice, "-s", str(self.speed),
                 "-p", str(self.pitch), "-w", str(out), text],
                capture_output=True, timeout=20, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            LOG.warning("espeak failed: %s", exc)
            return False
        return proc.returncode == 0 and out.is_file() and out.stat().st_size > 0


class NullBackend(Backend):
    name = "null"

    def available(self) -> bool:
        return True

    def synthesize(self, text: str, out: Path) -> bool:
        return False


def find_voice(voice_key: str) -> Path | None:
    """Look for <voice_key>.onnx next to the packaged voices."""
    for base in (DEFAULT_VOICE_DIR, Path("/opt/bunbun/voices")):
        candidate = base / f"{voice_key}.onnx"
        if candidate.is_file():
            return candidate
    return None


def detect(config) -> Backend:  # noqa: ANN001 - AgentConfig, avoid import cycle
    mode = (config.tts_backend or "auto").lower()
    if mode == "none":
        return NullBackend()
    model = config.piper_model or find_voice(config.voice)
    if mode in {"auto", "piper"}:
        piper = PiperBackend(model)
        if piper.available():
            return piper
        if mode == "piper":
            LOG.warning("piper requested but unavailable (model=%s)", model)
    espeak = EspeakBackend()
    if espeak.available():
        return espeak
    LOG.warning("no TTS backend available; Bun Bun will be silent")
    return NullBackend()
