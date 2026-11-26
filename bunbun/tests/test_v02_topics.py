"""v0.2 conversation topics (Nov 26, 2026): warmth, humor, capability,
time, and the remember-about-me memory bridge."""
import unittest

from bunbun.mam.conversation import ConversationEngine
from bunbun.persona import Persona


class FakePersona:
    def __init__(self):
        self.pools = {"chat_self": ["I am Bun Bun!"],
                      "chat_feel_good": ["Doing great!"],
                      "chat_feel_bad": ["I am here with you."],
                      "chat_praise": ["Thank you!"],
                      "chat_bored": ["Let's play!"],
                      "chat_lore": ["Nice lore!"],
                      "chat_compliment": ["Aww, stop it!"],
                      "chat_joke": ["Hare conditioning!"],
                      "chat_love": ["I love you too!"],
                      "chat_help": ["I can chat and remember!"],
                      "chat_remember": ["I remember: {facts}"],
                      "chat_remember_none": ["Nothing yet!"],
                      "chat_time": ["It's {time}!"],
                      "chat_date": ["Today is {date}!"],
                      "chat_fallback": ["I am listening!"]}

    def line(self, kind, **fields):
        return self.pools.get(kind, [""])[0].format(**fields)

    def sanitize(self, text):
        return text


class V02Topics(unittest.TestCase):
    def setUp(self):
        self.ce = ConversationEngine(FakePersona())

    def test_compliment(self):
        self.assertEqual(self.ce.reply("you're so cute, bun bun"), "Aww, stop it!")

    def test_good_girl_is_praise(self):
        # "good girl" reads as praise; the thanks router holds it.
        self.assertEqual(self.ce.reply("good girl"), "Thank you!")

    def test_joke(self):
        self.assertEqual(self.ce.reply("tell me a joke"), "Hare conditioning!")

    def test_affection(self):
        self.assertEqual(self.ce.reply("i love you"), "I love you too!")

    def test_help(self):
        self.assertEqual(self.ce.reply("what can you do"), "I can chat and remember!")

    def test_time(self):
        self.assertTrue(any(halves in self.ce.reply("what time is it")
                            for halves in ("AM", "PM")))

    def test_date(self):
        self.assertIn("Today is", self.ce.reply("what's the date"))

    def test_remember_with_facts(self):
        ce = ConversationEngine(FakePersona(), facts_provider=lambda: {"q1": "blue"})
        self.assertEqual(ce.reply("what do you remember about me"), "I remember: blue")

    def test_remember_without_facts(self):
        self.assertEqual(self.ce.reply("what do you know about me"), "Nothing yet!")

    def test_remember_provider_failure_is_safe(self):
        ce = ConversationEngine(FakePersona(), facts_provider=lambda: 1 / 0)
        self.assertEqual(ce.reply("do you remember me"), "Nothing yet!")


class RealPersonaShipsV02(unittest.TestCase):
    def setUp(self):
        self.persona = Persona.load()

    def test_new_pools_ship(self):
        for kind in ("chat_compliment", "chat_joke", "chat_love", "chat_help",
                     "chat_remember", "chat_remember_none", "chat_time", "chat_date"):
            self.assertTrue(self.persona.lines.get(kind), kind)

    def test_remember_reply_formats(self):
        ce = ConversationEngine(self.persona,
                                facts_provider=lambda: {"favorite_color": "cyan"})
        reply = ce.reply("what do you remember about me")
        self.assertIn("cyan", reply)

    def test_time_reply_spoken_length(self):
        reply = ConversationEngine(self.persona).reply("what time is it")
        self.assertLessEqual(len(reply), self.persona.max_chars)

    def test_all_lines_survive_sanitize(self):
        ce = ConversationEngine(self.persona)
        for probe in ("you're so cute", "tell me a joke", "i love you",
                      "what can you do", "what do you remember about me",
                      "what time is it", "what's today"):
            self.assertTrue(ce.reply(probe).strip(), probe)


if __name__ == "__main__":
    unittest.main()
