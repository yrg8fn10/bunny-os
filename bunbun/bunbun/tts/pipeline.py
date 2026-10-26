"""TTS orchestration: sanitise -> synthesise -> duck -> play.

One worker thread and a small bounded queue keep Bun Bun from ever flooding
the audio device, even if a game spams events.  Speaking is cancellable: a new
high-priority line (or the player pressing the overlay) clears the queue.
"""
from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .backends import Backend, NullBackend, detect

LOG = logging.getLogger("bunbun.tts")

PLAYERS = (
    ("pw-play", ["--volume"]),
    ("paplay", []),
    ("aplay", ["-q"]),
)


@dataclass(order=True)
class Utterance:
    priority: int
    seq: int
    text: str


class TTSPipeline:
    def __init__(self, config, backend: Backend | None = None,
                 on_spoken: Callable[[str], None] | None = None,
                 max_queue: int = 8):
        self.config = config
        self.backend = backend or detect(config)
        self.on_spoken = on_spoken
        self.queue: queue.Queue[Utterance] = queue.Queue(maxsize=max_queue)
        self._seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._current: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._last_text = ""
        self._last_at = 0.0
        self.runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "bunbun"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.stats = {"queued": 0, "spoken": 0, "dropped": 0, "failed": 0}

    # -- public ------------------------------------------------------------
    @property
    def available(self) -> bool:
        return not isinstance(self.backend, NullBackend) and self.backend.available()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="bunbun-tts", daemon=True)
        self._thread.start()

    def say(self, text: str, priority: int = 50) -> bool:
        text = (text or "").strip()
        if not text or not self.available:
            return False
        now = time.monotonic()
        if text == self._last_text and now - self._last_at < 5:
            return False
        with self._lock:
            self._seq += 1
            item = Utterance(priority=-int(priority), seq=self._seq, text=text)
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            # Drop the oldest low-priority item, not the newest emergency.
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(item)
                self.stats["dropped"] += 1
            except queue.Empty:
                self.stats["dropped"] += 1
                return False
        self.stats["queued"] += 1
        self._last_text, self._last_at = text, now
        if not self._thread or not self._thread.is_alive():
            self.start()
        return True

    def interrupt(self) -> None:
        """Barge-in: silence current audio and flush pending lines."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
        proc = self._current
        if proc and proc.poll() is None:
            proc.terminate()

    def close(self) -> None:
        self._stop.set()
        self.interrupt()
        if self._thread:
            self._thread.join(timeout=3)
        self._cleanup()

    # -- worker ------------------------------------------------------------
    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                item = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if self._stop.is_set():
                break
            try:
                self._speak_now(item)
            except Exception:
                LOG.exception("utterance failed")
                self.stats["failed"] += 1

    def _speak_now(self, item: Utterance) -> None:
        text = self._clean_for_speech(item.text)
        if not text:
            return
        with tempfile.NamedTemporaryFile(dir=self.runtime_dir, suffix=".wav", delete=False) as fh:
            wav = Path(fh.name)
        try:
            if not self.backend.synthesize(text, wav):
                self.stats["failed"] += 1
                return
            self._play(wav)
            self.stats["spoken"] += 1
            if self.on_spoken:
                try:
                    self.on_spoken(text)
                except Exception:
                    LOG.debug("on_spoken callback failed", exc_info=True)
        finally:
            wav.unlink(missing_ok=True)

    def _play(self, wav: Path) -> None:
        volume = float(getattr(self.config, "extra", {}).get("volume", 0.85) or 0.85)
        for binary, extra in PLAYERS:
            if not shutil.which(binary):
                continue
            argv = [binary, *extra]
            if binary == "pw-play":
                argv.append(f"--volume={max(0.0, min(volume, 1.0)):.2f}")
            argv.append(str(wav))
            try:
                proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)
                self._current = proc
                proc.wait(timeout=60)
                self._current = None
                if proc.returncode == 0:
                    return
            except (OSError, subprocess.SubprocessError) as exc:
                LOG.warning("playback with %s failed: %s", binary, exc)
        LOG.debug("no working audio player found")

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        # TTS engines read "~" as "tilde" in some locales.
        text = re.sub(r"~", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:400]

    def _cleanup(self) -> None:
        for leftover in self.runtime_dir.glob("*.wav"):
            try:
                leftover.unlink()
            except OSError:
                pass
