"""Tests for the session-end farewell lines."""
from __future__ import annotations

import random
import unittest

from bunbun.farewell import FAREWELL_LINES, pick, said_done


class SaidDoneTests(unittest.TestCase):
    def test_detects_done_phrases(self):
        self.assertTrue(said_done("Alright, I'm done for today."))
        self.assertTrue(said_done("okay im done for tonight"))
        self.assertTrue(said_done("Let's call it, good game."))
        self.assertTrue(said_done("Time to quit!"))

    def test_ignores_ordinary_talk(self):
        self.assertFalse(said_done("What should I do today?"))
        self.assertFalse(said_done("I'm not done yet, one more dive."))
        self.assertFalse(said_done(""))
        self.assertFalse(said_done(None))


class PickTests(unittest.TestCase):
    def test_returns_from_library(self):
        line = pick(random.Random(1))
        self.assertIn(line, FAREWELL_LINES)

    def test_seen_lines_skipped(self):
        seen = set(FAREWELL_LINES[:-1])
        self.assertEqual(pick(random.Random(2), seen=seen), FAREWELL_LINES[-1])

    def test_all_seen_recycles(self):
        line = pick(random.Random(3), seen=set(FAREWELL_LINES))
        self.assertIn(line, FAREWELL_LINES)

    def test_lines_fit_persona_budget(self):
        for line in FAREWELL_LINES:
            self.assertLessEqual(len(line), 180)


if __name__ == "__main__":
    unittest.main()
