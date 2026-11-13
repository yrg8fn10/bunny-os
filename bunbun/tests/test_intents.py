"""Voice-command intent parsing and fuzzy library matching (pre10)."""
import unittest

from bunbun.intents import Command, best_match, parse_command


class Fake:
    def __init__(self, name):
        self.name = name
        self.app_id = "1"


class IntentParsingTests(unittest.TestCase):
    def test_link_library_phrasings(self):
        for text in ("link up my steam", "connect my steam account",
                     "hook up the library", "sync my steam games",
                     "Bun Bun, link up my steam"):
            self.assertEqual(parse_command(text).kind, "link_library", text)

    def test_list_games_phrasings(self):
        for text in ("what games do we have", "what can we play",
                     "what's in my library", "show my games"):
            self.assertEqual(parse_command(text).kind, "list_games", text)

    def test_launch_phrasings(self):
        command = parse_command("let's play Subnautica")
        self.assertEqual(command.kind, "launch")
        self.assertEqual(command.arg, "subnautica")
        self.assertEqual(parse_command("start Black Mesa").kind, "launch")
        self.assertEqual(parse_command("open the catalog").kind, "launch")

    def test_launch_word_cap(self):
        short = "play one two three four five six seven eight"
        long = "play one two three four five six seven eight nine"
        self.assertEqual(parse_command(short).kind, "launch")
        self.assertEqual(parse_command(long).kind, "unknown")

    def test_greeting(self):
        self.assertEqual(parse_command("hii buddy").kind, "greet")
        self.assertEqual(parse_command("hey bun bun!").kind, "greet")
        # A sentence that merely contains "hey" is not a greeting.
        self.assertEqual(parse_command("hey did you finish the hint yet").kind,
                         "unknown")

    def test_unknown(self):
        self.assertEqual(parse_command("").kind, "unknown")
        self.assertEqual(parse_command("the weather is nice today").kind,
                         "unknown")

    def test_command_dict(self):
        self.assertEqual(Command(kind="launch", arg="x").to_dict(),
                         {"kind": "launch", "arg": "x"})


class BestMatchTests(unittest.TestCase):
    def setUp(self):
        self.games = [Fake("Subnautica"), Fake("Subnautica Below Zero"),
                      Fake("Black Mesa")]

    def test_exact_and_prefix(self):
        game, score = best_match("subnautica", self.games)
        self.assertEqual(game.name, "Subnautica")
        self.assertGreaterEqual(score, 0.9)
        game, _ = best_match("black mesa", self.games)
        self.assertEqual(game.name, "Black Mesa")

    def test_fuzzy(self):
        game, _ = best_match("black messa", self.games)
        self.assertEqual(game.name, "Black Mesa")

    def test_none(self):
        game, score = best_match("zzzzqqqq", self.games)
        self.assertIsNone(game)
        self.assertLess(score, 0.42)
        self.assertEqual(best_match("", self.games), (None, 0.0))
        self.assertEqual(best_match("subnautica", []), (None, 0.0))


if __name__ == "__main__":
    unittest.main()
