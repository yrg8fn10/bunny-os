"""Consent-gated microphone capture (Deliverable 3).

Ava's listening model, v2 (Nov 3, 2026): **no push-to-talk button.** While a
game session is active, Bun Bun listens like a companion beside you, and she
polices herself: the privacy gate closes her ears on private topics, deletes
the audio, and she only comes back for game talk.

Capture still passes gates, in order:

1. ``mic_enabled`` in settings (default: **False**);
2. scope: in push-to-talk mode an open listening window; in session mode an
   *active game session* (never the desktop, never while idle);
3. the privacy cooldown after a private-topic hit;
4. the PipeWire source itself: muted (hardware kill switch) or unreadable means
   refuse. **Unknown is treated as unavailable, never as available.**

Clips are short 16 kHz mono WAV temp files, fed only to the local STT backend,
and discarded immediately after transcription. Nothing leaves the machine.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from .helpers import run
from .privacy import PrivacyGate

LOG = logging.getLogger("bunbun.audio.mic")

MAX_CLIP_SECONDS = 15.0


class MicCapture:
    """Listens like a companion during sessions; the kill switch always wins."""

    def __init__(self, config, source: Optional[str] = None):
        self.config = config
        self.source = source          # None -> PipeWire default source
        self._window = threading.Event()   # push-to-talk mode only
        self._session_active = False       # session-listen mode only
        self._lock = threading.Lock()
        self._last_clip: Optional[Path] = None
        self._last_text: Optional[str] = None
        self.privacy = PrivacyGate()
        self.stats = {"requested": 0, "gated": 0, "captured": 0, "failed": 0,
                      "privacy_mutes": 0}

    # -- gates -------------------------------------------------------------
    @property
    def allowed(self) -> bool:
        """Gate 1: the owner turned the microphone on in settings."""
        return bool(getattr(self.config, "mic_enabled", False))

    @property
    def push_to_talk(self) -> bool:
        return bool(getattr(self.config, "mic_push_to_talk", True))

    @property
    def session_active(self) -> bool:
        return self._session_active

    @property
    def listen_mode(self) -> str:
        """session (companion while playing) or always (pre10: ears stay open).

        In always mode the desktop is in scope too. The privacy gate, the
        kill switch and the settings switch still close her ears exactly the
        same way they always did; only the *scope* widens.
        """
        return str(getattr(self.config, "mic_listen_mode", "session"))

    def set_session_active(self, active: bool) -> None:
        """Gate 2 (session mode): mark whether a game session is running.

        The watcher's game state drives this; the desktop and idle time are
        always out of scope for listening.
        """
        self._session_active = bool(active)
        if not active:
            self._window.clear()

    @property
    def window_open(self) -> bool:
        return self._window.is_set()

    def open_window(self) -> bool:
        """Gate 2 (push-to-talk mode). Refuses while disabled."""
        if not self.allowed or not self.push_to_talk:
            return False
        self._window.set()
        return True

    def close_window(self) -> None:
        self._window.clear()

    # -- kill switch -------------------------------------------------------
    def kill_switch_muted(self) -> Optional[bool]:
        """Gate 4 mirror: True when the source reports muted.

        ``None`` means "cannot check" (no wpctl, or it failed). A caller that
        cannot check must treat the microphone as unavailable, never available.
        """
        proc = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SOURCE@"], timeout=5)
        if proc is None or proc.returncode != 0:
            return None
        return "MUTED" in proc.stdout.decode("utf-8", "replace").upper()

    # -- capture -----------------------------------------------------------
    def _scope_open(self) -> bool:
        """Gate 2: the mode's own scope."""
        if self.push_to_talk:
            return self.window_open
        if self.listen_mode == "always":
            return True
        return self._session_active

    def capture(self, seconds: float = 4.0) -> Optional[Path]:
        """Record one short clip into a temp WAV. ``None`` when any gate is closed."""
        self.stats["requested"] += 1
        if not self.allowed or not self._scope_open():
            self.stats["gated"] += 1
            return None
        if self.privacy.muted(time.time()):
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

    def listen_once(self, stt) -> Optional[str]:
        """Capture, transcribe, then apply the privacy gate.

        Returns the text for game talk, ``None`` when nothing was heard or the
        clip was private. In both cases the WAV is deleted right away: the clip
        never lives longer than this call.
        """
        clip = self.capture()
        if clip is None:
            return None
        try:
            text = stt.transcribe(clip) if stt is not None else None
        finally:
            try:
                clip.unlink(missing_ok=True)
            except OSError:
                pass
            self._last_clip = None
        self._last_text = text
        now = time.time()
        if not self.privacy.review(text, now):
            self.stats["privacy_mutes"] += 1
            return None
        return text

    @property
    def last_text(self) -> Optional[str]:
        """The most recent reviewed transcript, for debugging and tests."""
        return self._last_text


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


def build_stt(config):
    """Build the local STT backend from settings; None when unavailable.

    Nothing here talks to a network. If whisper.cpp or its model is missing,
    the ears simply stay quiet (capture still happens for stats but
    transcription returns None and the loop says nothing).
    """
    which = str(getattr(config, "mic_stt", "auto") or "auto")
    if which in {"none", "off"}:
        return None
    model = getattr(config, "whisper_model", None)
    backend = WhisperBackend(model=model)
    return backend if backend.available() else None
