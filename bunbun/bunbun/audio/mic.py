"""Consent-gated microphone capture (Deliverable 3).

The microphone never runs hot. Every capture call passes three gates, in order:

1. ``mic_enabled`` in settings (default: **False**);
2. an open listening window - a push-to-talk press or an explicit one-shot
   consent from the control panel;
3. the PipeWire source itself: if ``wpctl`` reports it muted (the hardware kill
   switch) or the capture helper is missing, nothing is recorded.

Recorded clips are short 16 kHz mono WAV files in the system temp directory.
They are fed only to a local STT backend (whisper.cpp when installed); there is
no network access on this path, ever.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Optional

from .helpers import run

LOG = logging.getLogger("bunbun.audio.mic")

MAX_CLIP_SECONDS = 15.0


class MicCapture:
    """One listening window at a time; the kill switch always wins."""

    def __init__(self, config, source: Optional[str] = None):
        self.config = config
        self.source = source          # None -> PipeWire default source
        self._window = threading.Event()
        self._lock = threading.Lock()
        self._last_clip: Optional[Path] = None
        self.stats = {"requested": 0, "gated": 0, "captured": 0, "failed": 0}

    # -- gates -------------------------------------------------------------
    @property
    def allowed(self) -> bool:
        """Gate 1: the owner turned the microphone on in settings."""
        return bool(getattr(self.config, "mic_enabled", False))

    @property
    def window_open(self) -> bool:
        return self._window.is_set()

    def open_window(self) -> bool:
        """Gate 2: open one listening window. Refuses while gate 1 is closed."""
        if not self.allowed:
            LOG.debug("mic window refused: capture disabled in settings")
            return False
        self._window.set()
        return True

    def close_window(self) -> None:
        """Close the listening window (button up, or the key released)."""
        self._window.clear()

    # -- kill switch -------------------------------------------------------
    def kill_switch_muted(self) -> Optional[bool]:
        """Gate 3 mirror: True when the source reports muted.

        ``None`` means "cannot check" (no wpctl, or it failed). A caller that
        cannot check must treat the microphone as unavailable, never available.
        """
        proc = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"], timeout=5)
        if proc is None or proc.returncode != 0:
            return None
        return "MUTED" in proc.stdout.decode("utf-8", "replace").upper()

    # -- capture -----------------------------------------------------------
    def capture(self, seconds: float = 4.0) -> Optional[Path]:
        """Record one short clip into a temp WAV. ``None`` when any gate is closed."""
        self.stats["requested"] += 1
        if not self.allowed or not self.window_open:
            self.stats["gated"] += 1
            return None
        muted = self.kill_switch_muted()
        if muted is True:
            self.stats["gated"] += 1
            return None
        recorder = shutil.which("pw-record") or shutil.which("pw-cat")
        if not recorder:
            LOG.info("no PipeWire capture helper found; capture skipped")
            self.stats["gated"] += 1
            return None

        seconds = max(0.5, min(MAX_CLIP_SECONDS, float(seconds)))
        with self._lock:
            fd, raw = tempfile.mkstemp(prefix="bunbun-mic-", suffix=".wav")
            os.close(fd)
            clip = Path(raw)
            argv = [recorder, "--rate", "16000", "--channels", "1",
                    "--duration", str(int(seconds))]
            if self.source:
                argv += ["--target", self.source]
            argv.append(str(clip))
            proc = run(argv, timeout=seconds + 5.0)
            ok = (proc is not None and proc.returncode == 0 and clip.is_file()
                  and clip.stat().st_size > 44)
            if ok:
                self._last_clip = clip
                self.stats["captured"] += 1
                return clip
            try:
                clip.unlink(missing_ok=True)
            except OSError:
                pass
            self.stats["failed"] += 1
            return None

    def discard(self) -> None:
        """Delete the last clip without transcribing it."""
        if self._last_clip is not None:
            try:
                self._last_clip.unlink(missing_ok=True)
            except OSError:
                pass
            self._last_clip = None


class WhisperBackend:
    """Local speech-to-text via whisper.cpp. Optional; the fallback is silence.

    The model is **not** shipped in this repository (see
    ``scripts/fetch-sources.sh --voices``). Transcription happens on the
    machine; the text goes to the MAM engine as a player-speech event and
    nowhere else.
    """

    def __init__(self, binary: str = "whisper-cli",
                 model: Optional[Path] = None, language: str = "en"):
        self.binary = binary
        self.model = model
        self.language = language

    def available(self) -> bool:
        return bool(self.model and Path(self.model).is_file()
                    and shutil.which(self.binary))

    def transcribe(self, clip: Path) -> Optional[str]:
        if not self.available() or not clip.is_file():
            return None
        proc = run([self.binary, "-m", str(self.model), "-l", self.language,
                    "-nt", "-f", str(clip)], timeout=60)
        if proc is None or proc.returncode != 0:
            return None
        text = proc.stdout.decode("utf-8", "replace").strip()
        return text or None
