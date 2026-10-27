"""Bun Bun — the Bunny OS co-op companion.

The package is deliberately dependency-free (Python standard library only) so
that it can be audited, shipped in an immutable image, and booted without a
network.  Optional extras (Piper TTS, OCR) are discovered at runtime.
"""

__all__ = ["__version__"]
__version__ = "0.2.0"
