"""Text-to-speech backends.

Piper is preferred (neural, local, permissive voice models).  espeak-ng is the
fallback that is always present on a base Arch install.  Both are invoked as
subprocesses with an argument list — never through a shell.

Voice models are **not** shipped in this repository:
    ./scripts/fetch-sources.sh --voices
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import unicodedata
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

    def __init__(self, model: Path | None, binary: str = "piper",
                 speaker: int | None = None):
        self.model = Path(model) if model else None
        self.binary = binary
        self.speaker = speaker
        self.length_scale: float | None = None
        self.noise_scale: float | None = None

    def set_params(self, **params: float) -> None:
        """Mood-driven synth parameters (see emotion.MoodEngine.voice_params)."""
        if "length_scale" in params:
            self.length_scale = max(0.5, min(2.0, float(params["length_scale"])))
        if "noise_scale" in params:
            self.noise_scale = max(0.1, min(1.0, float(params["noise_scale"])))

    def available(self) -> bool:
        return bool(self.model and self.model.is_file()
                    and self.binary and shutil.which(self.binary))

    def synthesize(self, text: str, out: Path) -> bool:
        if not self.available():
            return False
        assert self.model is not None
        try:
            cmd = [self.binary, "--model", str(self.model)]
            if self.speaker is not None:
                cmd += ["--speaker", str(self.speaker)]
            if self.length_scale is not None:
                cmd += ["--length_scale", str(self.length_scale)]
            if self.noise_scale is not None:
                cmd += ["--noise_scale", str(self.noise_scale)]
            cmd += ["--output_file", str(out)]
            proc = subprocess.run(
                cmd,
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


class VoiceBankBackend(Backend):
    """Bun Bun's real voice as pre-rendered clips (the v2 voice bank).

    The lines Bun Bun already knows (persona pools, farewells, hints and the
    system phrases) are rendered ahead of time in her actual voice and matched
    by normalized text.  Unknown text returns False so the next backend in the
    chain can still speak it.
    """

    name = "bank"

    def __init__(self, bank_dir: Path):
        self.bank_dir = Path(bank_dir)
        self._index: dict[str, Path] | None = None

    @staticmethod
    def normalize(text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "").lower()
        text = re.sub(r"[^a-z0-9']+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _load(self) -> dict[str, Path]:
        if self._index is not None:
            return self._index
        self._index = {}
        manifest = self.bank_dir / "manifest.json"
        if not manifest.is_file():
            return self._index
        try:
            data = json.loads(manifest.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            LOG.warning("voice bank manifest unreadable: %s", exc)
            return self._index
        for key, rel in (data.get("clips") or {}).items():
            clip = self.bank_dir / str(rel)
            if clip.is_file():
                self._index[self.normalize(str(key))] = clip
        return self._index

    def available(self) -> bool:
        return bool(self._load())

    def synthesize(self, text: str, out: Path) -> bool:
        clip = self._load().get(self.normalize(text or ""))
        if clip is None:
            return False
        try:
            shutil.copyfile(clip, out)
        except OSError as exc:
            LOG.warning("voice bank clip copy failed: %s", exc)
            return False
        return out.is_file() and out.stat().st_size > 0


class QwenTTSBackend(Backend):
    """Bun Bun's official voice: Qwen3-TTS 0.6B CustomVoice, the SERENA preset.

    The engine is the bundled qwentts.cpp ``qwen-tts`` CLI, reached through
    the ``bunbun-qwen-tts`` wrapper, which pins the bundled talker and codec
    GGUFs.  Fully local, no API key, and no real child's voice is cloned:
    Serena is a synthetic CustomVoice preset.  Ava picked this voice by ear
    on Nov 27 2026; it supersedes the Kokoro af_sky color (now a fallback
    behind the pre-rendered voice bank).
    """

    name = "qwentts"

    # Delivery styles, all proven by ear (Ava approved the voice Nov 27 2026).
    INSTRUCT_DEFAULT = "cheerful playful little kid"
    INSTRUCT_SLOW = "gentle sleepy little kid"
    INSTRUCT_ENCOURAGING = "encouraging small child"

    TALKER_GGUF = "qwen-talker-0.6b-customvoice-Q4_K_M.gguf"
    CODEC_GGUF = "qwen-tokenizer-12hz-Q4_K_M.gguf"

    def __init__(self, binary: str | None = None, model: Path | None = None,
                 codec: Path | None = None, speaker: str = "serena",
                 lang: str = "English", max_new: int = 150,
                 codec_chunk: float = 4.0, timeout: float = 300.0):
        self.binary = (binary or os.environ.get("BUNBUN_QWENTTS_BIN")
                       or "bunbun-qwen-tts")
        self.model = model or self._find_model(self.TALKER_GGUF,
                                               "BUNBUN_QWENTTS_TALKER")
        self.codec = codec or self._find_model(self.CODEC_GGUF,
                                               "BUNBUN_QWENTTS_CODEC")
        self.speaker = speaker
        self.lang = lang
        self.max_new = max_new
        self.codec_chunk = codec_chunk
        self.timeout = timeout
        self.instruct = self.INSTRUCT_DEFAULT

    @staticmethod
    def _find_model(filename: str, env_key: str) -> Path | None:
        """The bundled GGUF: env override, then the standard share dirs."""
        env = os.environ.get(env_key)
        if env:
            candidate = Path(env)
            return candidate if candidate.is_file() else None
        for base in (Path("/usr/local/share/bunbun/models"),
                     Path("/usr/share/bunbun/models")):
            candidate = base / filename
            if candidate.is_file():
                return candidate
        return None

    def _find_binary(self) -> str:
        """The CLI: configured, then bunbun-qwen-tts, then the install spot."""
        if self.binary and (os.path.sep in self.binary or self.binary.startswith("/")):
            return self.binary if Path(self.binary).is_file() else ""
        found = shutil.which(self.binary)
        if found:
            return found
        # systemd services run with a minimal PATH; check the install spot
        for cand in ("/usr/local/bin/bunbun-qwen-tts", "/usr/bin/bunbun-qwen-tts"):
            if Path(cand).exists():
                return cand
        return ""

    def available(self) -> bool:
        return bool(self._find_binary() and self.model and self.model.is_file()
                    and self.codec and self.codec.is_file())

    def set_params(self, **params: float) -> None:
        """Mood-driven delivery instruct (see emotion.MoodEngine.voice_params).

        Low energy speaks slow and gentle (bedtime keeps her soft); low
        valence leans encouraging; everything else stays the cheerful
        default Ava approved.
        """
        length = params.get("length_scale")
        noise = params.get("noise_scale")
        if length is not None and float(length) >= 1.15:
            self.instruct = self.INSTRUCT_SLOW
        elif noise is not None and float(noise) >= 0.8:
            self.instruct = self.INSTRUCT_ENCOURAGING
        else:
            self.instruct = self.INSTRUCT_DEFAULT

    def synthesize(self, text: str, out: Path) -> bool:
        if not self.available():
            return False
        binary = self._find_binary()
        cmd = [binary, "--speaker", self.speaker, "--lang", self.lang,
               "--instruct", self.instruct, "--max-new", str(self.max_new),
               "--codec-chunk-dur", str(self.codec_chunk), "-o", str(out)]
        try:
            proc = subprocess.run(
                cmd,
                input=(text or "").encode("utf-8"),
                capture_output=True, timeout=self.timeout, check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            LOG.warning("qwentts failed: %s", exc)
            return False
        if proc.returncode != 0 or not out.is_file() or out.stat().st_size == 0:
            LOG.warning("qwentts produced no audio (rc=%s)", proc.returncode)
            return False
        return True


class ChainBackend(Backend):
    """Try backends in order; the first that produces audio wins."""

    name = "chain"

    def __init__(self, backends: list[Backend]):
        self.backends = list(backends)

    def available(self) -> bool:
        return any(backend.available() for backend in self.backends)

    def set_params(self, **params: float) -> None:
        for backend in self.backends:
            setter = getattr(backend, "set_params", None)
            if callable(setter):
                setter(**params)

    def synthesize(self, text: str, out: Path) -> bool:
        for backend in self.backends:
            if backend.available() and backend.synthesize(text, out):
                return True
        return False


def find_bank() -> Path | None:
    """Look for the packaged voice bank (its manifest.json marks the spot)."""
    candidates = [
        DEFAULT_VOICE_DIR / "bank",
        Path("/opt/bunbun/voices/bank"),
        Path(__file__).resolve().parents[2] / "assets" / "voice-bank",
    ]
    for candidate in candidates:
        if (candidate / "manifest.json").is_file():
            return candidate
    return None


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
    chain: list[Backend] = []
    if mode in {"auto", "qwentts"}:
        qwentts = QwenTTSBackend()
        if qwentts.available():
            chain.append(qwentts)
        elif mode == "qwentts":
            LOG.warning("qwentts requested but unavailable (binary=%s model=%s codec=%s)",
                        qwentts.binary, qwentts.model, qwentts.codec)
    if mode in {"auto", "bank"}:
        bank_dir = Path(config.voice_bank) if config.voice_bank else find_bank()
        if bank_dir:
            bank = VoiceBankBackend(bank_dir)
            if bank.available():
                chain.append(bank)
            elif mode == "bank":
                LOG.warning("voice bank requested but unavailable (dir=%s)", bank_dir)
    model = config.piper_model or find_voice(config.voice)
    if mode in {"auto", "piper"}:
        piper = PiperBackend(model, speaker=getattr(config, "voice_speaker", None))
        if piper.available():
            chain.append(piper)
        elif mode == "piper":
            LOG.warning("piper requested but unavailable (model=%s)", model)
    espeak = EspeakBackend()
    if mode in {"auto", "espeak"} and espeak.available():
        chain.append(espeak)
    if not chain:
        LOG.warning("no TTS backend available; Bun Bun will be silent")
        return NullBackend()
    return chain[0] if len(chain) == 1 else ChainBackend(chain)
