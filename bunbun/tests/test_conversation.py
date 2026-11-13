"""Pillar 3: the conversation half of the MAM engine."""
import unittest
from unittest import mock

from bunbun.mam.conversation import ConversationEngine, LocalBrain


class FakePersona:
    def __init__(self):
        self.pools = {"chat_self": ["I am Bun Bun!"],
                      "chat_feel_good": ["Doing great!"],
                      "chat_feel_bad": ["I am here with you."],
                      "chat_praise": ["Thank you!"],
                      "chat_bored": ["Let's play!"],
                      "chat_lore": ["Nice lore!"],
                      "chat_fallback": ["I am listening!"]}

    def line(self, kind, **_):
        return self.pools.get(kind, [""])[0]

    def sanitize(self, text):
        return text


class FakeBrain(LocalBrain):
    def __init__(self):
        self.calls = 0
        self.failures = 0

    def available(self):
        return True

    def reply(self, text, history, persona_prompt=""):
        self.calls += 1
        return f"local brain heard: {text}"


class ConversationTests(unittest.TestCase):
    def test_identity_routes_to_self(self):
        c = ConversationEngine(FakePersona())
        self.assertEqual(c.reply("wait who are you"), "I am Bun Bun!")

    def test_feeling_routes(self):
        c = ConversationEngine(FakePersona())
        self.assertEqual(c.reply("how are you today"), "Doing great!")

    def test_sad_gets_comfort(self):
        c = ConversationEngine(FakePersona())
        self.assertEqual(c.reply("I am so stuck on this boss"), "I am here with you.")

    def test_fallback_when_no_match(self):
        c = ConversationEngine(FakePersona())
        self.assertEqual(c.reply("did you see that jump"), "I am listening!")

    def test_history_keeps_turns(self):
        c = ConversationEngine(FakePersona())
        c.reply("who are you")
        c.reply("how are you")
        self.assertEqual(c.turns, 2)
        self.assertEqual(len(c.history), 4)
        self.assertEqual(c.history[-1]["who"], "bunbun")

    def test_local_brain_leads_when_available(self):
        brain = FakeBrain()
        c = ConversationEngine(FakePersona(), brain=brain)
        answer = c.reply("tell me something random")
        self.assertEqual(answer, "local brain heard: tell me something random")
        self.assertEqual(brain.calls, 1)

    def test_brain_failure_falls_back_to_rules(self):
        brain = FakeBrain()
        brain.reply = lambda *a, **k: None
        c = ConversationEngine(FakePersona(), brain=brain)
        self.assertEqual(c.reply("how are you"), "Doing great!")

    def test_brain_unavailable_means_rules(self):
        brain = FakeBrain()
        brain.available = lambda: False
        c = ConversationEngine(FakePersona(), brain=brain)
        self.assertEqual(c.reply("who are you"), "I am Bun Bun!")


if __name__ == "__main__":
    unittest.main()
