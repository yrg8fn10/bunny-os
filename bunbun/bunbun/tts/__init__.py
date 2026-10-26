"""Speech backends for Bun Bun."""

from .backends import Backend, EspeakBackend, NullBackend, PiperBackend, Voice, detect, find_voice
from .pipeline import TTSPipeline

__all__ = [
    "Backend", "EspeakBackend", "NullBackend", "PiperBackend", "TTSPipeline",
    "Voice", "detect", "find_voice",
]
