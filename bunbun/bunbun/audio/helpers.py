"""Shared subprocess helpers for the audio layer."""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional, Sequence

LOG = logging.getLogger("bunbun.audio")


def run(argv: Sequence[str], timeout: float = 10.0) -> Optional[subprocess.CompletedProcess]:
    """Run a helper with an argument list. Never a shell, never the network.

    Returns ``None`` when the binary is missing or the call fails; callers treat
    that as "no audio subsystem here" and leave everything alone.
    """
    argv = list(argv)
    if not argv or not shutil.which(argv[0]):
        return None
    try:
        return subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        LOG.warning("audio helper %s failed: %s", argv[0], exc)
        return None


def parse_volume(text: str) -> Optional[float]:
    """``wpctl get-volume`` prints 'Volume: 0.65' (optionally with '[MUTED]')."""
    for token in text.replace("[MUTED]", "").split():
        try:
            return float(token)
        except ValueError:
            continue
    return None
