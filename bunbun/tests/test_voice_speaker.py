"""Tests for multi-speaker voice configuration (the l2arctic pick)."""
import tempfile
import unittest
from pathlib import Path

from bunbun.config import AgentConfig, load_config
from bunbun.tts.backends import PiperBackend


class TestVoiceSpeaker(unittest.TestCase):
    def test_default_has_no_speaker(self):
        self.assertIsNone(AgentConfig().voice_speaker)

    def test_settings_file_selects_the_speaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"ai": {"speaker": "1"}}')
            cfg = load_config(settings_file=path)
        self.assertEqual(cfg.voice_speaker, 1)

    def test_bad_speaker_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"ai": {"speaker": "bunny"}}')
            cfg = load_config(settings_file=path)
        self.assertIsNone(cfg.voice_speaker)

    def test_backend_carries_the_speaker(self):
        backend = PiperBackend(None, speaker=1)
        self.assertEqual(backend.speaker, 1)
        backend.set_params(length_scale=1.1)
        self.assertEqual(backend.length_scale, 1.1)


if __name__ == "__main__":
    unittest.main()
