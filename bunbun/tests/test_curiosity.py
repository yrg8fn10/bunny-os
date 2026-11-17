"""Tests for the curiosity layer (get-to-know-you, v0)."""
import json
import time
import unittest
from types import SimpleNamespace

from bunbun.curiosity import Curiosity, _ANSWER_EVENT, _ASKED_EVENT


class FakeStore:
    def __init__(self):
        self.enabled = True
        self.events = []

    def record(self, kind, payload, game_id=None):
        self.events.append({"kind": kind, "payload": payload,
                            "ts": time.time(), "game_id": game_id})

    def recent(self, limit=20):
        return list(reversed(self.events))[:limit]


def make(store=None, **overrides):
    defaults = dict(curiosity_enabled=True,
                    curiosity_minutes_into_session=10.0,
                    curiosity_max_per_week=5)
    defaults.update(overrides)
    cfg = SimpleNamespace(**defaults)
    rng = __import__("random").Random(7)
    return Curiosity(store or FakeStore(), cfg, rng=rng)


class TestCuriosity(unittest.TestCase):
    def test_no_ask_during_warmup(self):
        c = make()
        c.session_start("mc", now=1000.0)
        self.assertIsNone(c.maybe_ask(now=1000.0))
        self.assertIsNone(c.maybe_ask(now=1000.0 + 9 * 60))
        q = c.maybe_ask(now=1000.0 + 10 * 60 + 1)
        self.assertTrue(q and q.endswith("?"))

    def test_asks_at_most_once_per_session(self):
        c = make()
        c.session_start("mc", now=1000.0)
        q = c.maybe_ask(now=2000.0)
        self.assertIsNotNone(q)
        self.assertIsNone(c.maybe_ask(now=2600.0))

    def test_never_repeats_a_question(self):
        c = make()
        seen = set()
        for i in range(3):
            c.session_start("mc", now=1000.0 + i * 100000)
            q = c.maybe_ask(now=1000.0 + i * 100000 + 700)
            self.assertIsNotNone(q)
            self.assertNotIn(q, seen)
            seen.add(q)
            self.assertIsNotNone(c.absorb("whatever", now=1001.0))

    def test_absorb_stores_and_recall_works(self):
        c = make()
        c.session_start("mc", now=1000.0)
        q = c.maybe_ask(now=2000.0)
        ack = c.absorb("redstone all the way", now=2005.0)
        self.assertTrue(ack)
        self.assertIsNone(c.pending)
        asked_qid = c.store.events[-1]["payload"]["qid"]
        self.assertEqual(c.recall(asked_qid), "redstone all the way")

    def test_silence_closes_the_question(self):
        c = make()
        c.session_start("mc", now=1000.0)
        c.maybe_ask(now=2000.0)
        self.assertIsNone(c.absorb("k", now=2005.0))
        self.assertIsNone(c.pending)

    def test_weekly_cap(self):
        c = make(curiosity_max_per_week=1)
        c.session_start("mc", now=1000.0)
        self.assertIsNotNone(c.maybe_ask(now=2000.0))
        c.absorb("hi", now=2001.0)
        c.session_end()
        c.session_start("mc", now=2000.0)  # same week
        self.assertIsNone(c.maybe_ask(now=2100.0))

    def test_off_switch(self):
        c = make(curiosity_enabled=False)
        c.session_start("mc", now=1000.0)
        self.assertIsNone(c.maybe_ask(now=2000.0))

    def test_memory_disabled_means_silence(self):
        store = FakeStore()
        store.enabled = False
        c = make(store=store)
        c.session_start("mc", now=1000.0)
        self.assertIsNone(c.maybe_ask(now=2000.0))

    def test_bank_is_wholesale(self):
        bank = json.load(open("bunbun/bunbun/data/curiosity.json"))
        forbidden = ("health", "money", "address", "phone", "family",
                     "religion", "politics", "school", "job")
        for q in bank["questions"]:
            text = q["text"].lower()
            for word in forbidden:
                self.assertNotIn(word, text, q["id"])


if __name__ == "__main__":
    unittest.main()
