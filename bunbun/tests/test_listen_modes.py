"""Gate 2 of the ears: session vs always listening (pre10 pillar 5)."""
import unittest
from pathlib import Path
from unittest import mock

from bunbun.audio.mic import MicCapture, build_stt


class FakeConfig:
    def __init__(self, mic_enabled=True, push_to_talk=False,
                 listen_mode="session", mic_stt="none", whisper_model=None):
        self.mic_enabled = mic_enabled
        self.mic_push_to_talk = push_to_talk
        self.mic_listen_mode = listen_mode
        self.mic_stt = mic_stt
        self.whisper_model = whisper_model


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.gate = mock.MagicMock()
        self.gate.muted.return_value = False

    def mic(self, **kwargs):
        return MicCapture(FakeConfig(**kwargs))

    def test_session_mode_stays_out_of_desktop(self):
        mic = self.mic()
        self.assertFalse(mic._scope_open())
        mic.set_session_active(True)
        self.assertTrue(mic._scope_open())
        mic.set_session_active(False)
        self.assertFalse(mic._scope_open())

    def test_always_mode_covers_desktop(self):
        mic = self.mic(listen_mode="always")
        self.assertTrue(mic._scope_open())

    def test_push_to_talk_still_gates(self):
        mic = self.mic(push_to_talk=True, listen_mode="always")
        self.assertFalse(mic._scope_open())
        self.assertTrue(mic.open_window())
        self.assertTrue(mic._scope_open())
        mic.close_window()
        self.assertFalse(mic._scope_open())

    def test_mic_disabled_blocks_even_always(self):
        mic = self.mic(mic_enabled=False, listen_mode="always")
        self.assertIsNone(mic.capture())

    def test_privacy_gate_blocks_in_always_mode(self):
        mic = self.mic(listen_mode="always")
        mic.privacy = self.gate
        self.gate.muted.return_value = True
        self.assertIsNone(mic.capture())
        self.assertEqual(mic.stats["gated"], 1)

    def test_listen_mode_read(self):
        self.assertEqual(self.mic().listen_mode, "session")
        self.assertEqual(self.mic(listen_mode="always").listen_mode, "always")

    def test_build_stt_none_when_disabled(self):
        self.assertIsNone(build_stt(FakeConfig(mic_stt="none")))

    def test_build_stt_none_without_whisper(self):
        with mock.patch.object(Path, "is_file", lambda self: False), \
             mock.patch("bunbun.audio.mic.shutil.which", lambda name: None):
            self.assertIsNone(build_stt(FakeConfig(mic_stt="auto")))


if __name__ == "__main__":
    unittest.main()
