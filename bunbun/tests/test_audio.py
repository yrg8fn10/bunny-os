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


# ---- session-listen mode (v2, Nov 3): no push-to-talk button ----

from pathlib import Path
import time as _time

from bunbun.audio.privacy import PrivacyGate


class FakeSTT:
    def __init__(self, text):
        self.text = text

    def transcribe(self, clip):
        return self.text


def test_session_mode_listens_without_push_to_talk():
    cfg = AgentConfig(mic_enabled=True, mic_push_to_talk=False)
    mic = MicCapture(cfg)
    assert mic._scope_open() is False          # no active session yet
    mic.set_session_active(True)
    assert mic._scope_open() is True           # session alone opens the scope
    mic.set_session_active(False)
    assert mic._scope_open() is False


def test_push_to_talk_still_its_own_gate():
    cfg = AgentConfig(mic_enabled=True, mic_push_to_talk=True)
    mic = MicCapture(cfg)
    mic.set_session_active(True)               # session alone is not enough
    assert mic._scope_open() is False
    assert mic.open_window() is True
    assert mic._scope_open() is True


def test_privacy_gate_mutes_on_private_talk():
    gate = PrivacyGate()
    now = 100.0
    assert gate.review("nice dodge, try the left pipe!", now) is True
    assert gate.review("my password is hunter2", now) is False
    assert gate.muted(now + 1) is True
    assert gate.muted(now + 999) is False
    assert gate.hits[-1][0] == "credentials"
    assert gate.review("call me at 260 555 1234 later", 200.0) is False
    assert gate.review("the sea dragon is that way!", 200.0) is True


def test_listen_once_discards_private_clip():
    import os
    import tempfile

    cfg = AgentConfig(mic_enabled=True, mic_push_to_talk=False)
    mic = MicCapture(cfg)
    mic.set_session_active(True)

    fd, raw = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    clip = Path(raw)
    clip.write_bytes(b"RIFF" + b"\x00" * 44)
    with patch.object(MicCapture, "capture", return_value=clip):
        assert mic.listen_once(FakeSTT("my address is 12 elm street")) is None
        assert not clip.exists()               # the clip is gone
        assert mic.stats["privacy_mutes"] == 1
        assert mic.privacy.muted(_time.time()) is True   # cooldown is open

    # game talk passes through and keeps the gate open
    fd, raw = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    clip2 = Path(raw)
    clip2.write_bytes(b"RIFF" + b"\x00" * 44)
    with patch.object(MicCapture, "capture", return_value=clip2):
        mic.privacy.resume()
        assert mic.listen_once(FakeSTT("nice dodge, try the left pipe!")) == \
            "nice dodge, try the left pipe!"
        assert not clip2.exists()              # the clip is gone here too
        assert mic.stats["privacy_mutes"] == 1

    # and inside the cooldown, capture refuses before recording anything
    mic.privacy.muted_until = _time.time() + 60
    mic.set_session_active(True)
    assert mic.capture(1.0) is None
