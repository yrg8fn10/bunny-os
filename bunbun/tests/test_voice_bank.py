"""Tests for the v2 voice bank backend and the auto backend chain."""
import json
import tempfile
import unittest
from pathlib import Path

from bunbun.tts.backends import (ChainBackend, NullBackend, VoiceBankBackend)


def _bank(tmp):
    d = Path(tmp) / "bank"
    d.mkdir()
    clip = d / "greeting.wav"
    clip.write_bytes(b"RIFF")
    (d / "manifest.json").write_text(json.dumps({
        "clips": {"Hi hi! I'm Bun Bun! Let's play something cozy~": "greeting.wav"},
    }))
    return d, clip


class _Yes(NullBackend):
    name = "yes"

    def available(self):
        return True

    def synthesize(self, text, out):
        out.write_bytes(b"RIFF")
        return True


class TestVoiceBank(unittest.TestCase):
    def test_normalize(self):
        n = VoiceBankBackend.normalize("Hi hi! I'm Bun Bun!  Let's play something cozy~")
        self.assertEqual(n, "hi hi i'm bun bun let's play something cozy")

    def test_hit_copies_the_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, clip = _bank(tmp)
            bank = VoiceBankBackend(d)
            self.assertTrue(bank.available())
            out = Path(tmp) / "out.wav"
            self.assertTrue(bank.synthesize("Hi hi! I'm Bun Bun! Let's play something cozy~", out))
            self.assertEqual(out.read_bytes(), b"RIFF")

    def test_miss_falls_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, _ = _bank(tmp)
            bank = VoiceBankBackend(d)
            out = Path(tmp) / "out.wav"
            self.assertFalse(bank.synthesize("something brand new", out))
            self.assertFalse(out.exists())

    def test_missing_manifest_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(VoiceBankBackend(Path(tmp)).available())


class TestChain(unittest.TestCase):
    def test_chain_falls_through_to_the_next_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, _ = _bank(tmp)
            chain = ChainBackend([VoiceBankBackend(d), _Yes()])
            out = Path(tmp) / "out.wav"
            self.assertTrue(chain.available())
            self.assertTrue(chain.synthesize("a line the bank never heard", out))
            self.assertEqual(out.read_bytes(), b"RIFF")

    def test_chain_bank_first_still_wins_for_known_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, clip = _bank(tmp)
            chain = ChainBackend([VoiceBankBackend(d), _Yes()])
            out = Path(tmp) / "out.wav"
            self.assertTrue(chain.synthesize("hi hi i'm bun bun let's play something cozy", out))
            self.assertEqual(out.read_bytes(), clip.read_bytes())


if __name__ == "__main__":
    unittest.main()
