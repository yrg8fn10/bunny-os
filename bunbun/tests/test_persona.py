"""Persona safety: what Bun Bun is allowed to say, and how it is spoken."""
from __future__ import annotations

import random
import unittest

from bunbun.persona import Persona, UnsafeText


def persona(max_chars: int = 180) -> Persona:
    return Persona.load(rng=random.Random(3), max_chars=max_chars)


class SanitizeTests(unittest.TestCase):
    def test_strips_markup_and_emoji(self):
        p = persona()
        self.assertEqual(p.sanitize("**Hi** 🐰 there"), "Hi there.")

    def test_collapses_whitespace(self):
        self.assertEqual(persona().sanitize("a   b\n\tc"), "a b c.")

    def test_keeps_single_tilde(self):
        self.assertTrue(persona().sanitize("Yay~~").endswith("~"))

    def test_caps_length(self):
        p = persona(max_chars=60)
        out = p.sanitize("word " * 100)
        self.assertLessEqual(len(out), 61)
        self.assertTrue(out.endswith((".", "!", "?", "~")))

    def test_blocks_purchase_pressure(self):
        with self.assertRaises(UnsafeText):
            persona().sanitize("Quick, buy the battle pass now!")

    def test_blocks_personal_data_requests(self):
        with self.assertRaises(UnsafeText):
            persona().sanitize("What is your password?")


class LineTests(unittest.TestCase):
    def test_all_persona_lines_are_safe(self):
        p = persona()
        for kind in p.lines:
            text = p.line(kind)
            self.assertLessEqual(len(text), 180)
            self.assertTrue(text)

    def test_hint_templates_receive_where(self):
        p = persona()
        text = p.hint("the pond by the mill")
        self.assertIn("pond by the mill", text)

    def test_greeting_is_deterministic_with_seed(self):
        a, b = persona(), persona()
        self.assertEqual(a.greet(), b.greet())

    def test_unknown_kind_falls_back(self):
        self.assertTrue(persona().line("does-not-exist"))


if __name__ == "__main__":
    unittest.main()
