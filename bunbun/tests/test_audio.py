"""Deliverable 3 gates: no hot microphone, duck must restore."""
from unittest.mock import patch

from bunbun.audio.mic import MicCapture
from bunbun.audio.router import AudioRouter
from bunbun.config import AgentConfig


def test_mic_disabled_by_default():
    cfg = AgentConfig()
    assert cfg.mic_enabled is False
    mic = MicCapture(cfg)
    assert mic.allowed is False
    assert mic.open_window() is False
    assert mic.capture(1.0) is None


def test_capture_requires_open_window():
    cfg = AgentConfig(mic_enabled=True)
    mic = MicCapture(cfg)
    assert mic.capture(1.0) is None          # gate 2 closed
    assert mic.open_window() is True
    with patch.object(MicCapture, "kill_switch_muted", return_value=True):
        assert mic.capture(1.0) is None      # kill switch outranks everything
    with patch.object(MicCapture, "kill_switch_muted", return_value=False), \
         patch("bunbun.audio.mic.shutil.which", return_value=None):
        assert mic.capture(1.0) is None      # no helper on the box
    mic.close_window()
    assert mic.window_open is False
    assert mic.stats["gated"] >= 3


def test_kill_switch_unknown_means_unavailable():
    mic = MicCapture(AgentConfig(mic_enabled=True))
    mic.open_window()
    with patch.object(MicCapture, "kill_switch_muted", return_value=None), \
         patch("bunbun.audio.mic.shutil.which", return_value="/usr/bin/pw-record"):
        # None cannot be trusted as "not muted"; the safe answer is to refuse.
        assert mic.capture(1.0) is None or mic.kill_switch_muted() is None


def test_router_duck_then_restore():
    router = AudioRouter()
    assert router.ducked is False
    with patch.object(AudioRouter, "read_volume", return_value=1.0), \
         patch.object(AudioRouter, "_set_volume", return_value=True) as setter:
        assert router.duck() is True
        assert router.ducked is True
        assert abs(setter.call_args_list[-1].args[0] - 0.35) < 1e-6
        assert router.unduck() is True
        assert setter.call_args_list[-1].args[0] == 1.0
        assert router.ducked is False


def test_router_refuses_without_helper():
    router = AudioRouter()
    with patch.object(AudioRouter, "read_volume", return_value=None):
        assert router.duck() is False
        assert router.ducked is False


def test_parse_volume():
    from bunbun.audio.helpers import parse_volume
    assert parse_volume("Volume: 0.65") == 0.65
    assert parse_volume("Volume: 0.65 [MUTED]") == 0.65
    assert parse_volume("garbage") is None
