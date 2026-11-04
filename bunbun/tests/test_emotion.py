"""Tests for the advanced emotional system (AES) phase 1."""
import unittest

from bunbun.config import PACKAGE_DATA
from bunbun.emotion import MoodEngine
from bunbun.hints import HintLibrary
from bunbun.mam.engine import MAMEngine
from bunbun.persona import Persona


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class TestMoodEngine(unittest.TestCase):
    def test_baseline_is_cheerful_and_curious(self):
        mood = MoodEngine()
        self.assertEqual(mood.read_level(), "lively")
        self.assertGreater(mood.fields["curiosity"], 0.5)

    def test_nudge_clamps(self):
        mood = MoodEngine()
        mood.nudge("pride", 5.0)
        self.assertEqual(mood.fields["pride"], 1.0)
        mood.nudge("valence", -5.0)
        self.assertEqual(mood.fields["valence"], 0.0)
        self.assertEqual(mood.read_level(), "down")

    def test_unknown_event_is_a_no_op(self):
        mood = MoodEngine()
        before = dict(mood.fields)
        mood.apply_event("not-a-real-event")
        self.assertEqual(before, mood.fields)

    def test_sad_event_then_decay_back_home(self):
        clock = FakeClock()
        mood = MoodEngine(clock=clock)
        mood.apply_event("player.sad")
        self.assertLess(mood.fields["valence"], 0.65)
        self.assertGreater(mood.fields["worry"], 0.2)
        clock.advance(3600.0)
        mood.tick(3600.0)
        self.assertGreaterEqual(mood.fields["valence"], 0.69)
        self.assertLessEqual(mood.fields["worry"], 0.11)

    def test_win_spikes_pride(self):
        mood = MoodEngine()
        mood.apply_event("player.win")
        self.assertGreater(mood.fields["pride"], 0.55)

    def test_player_read_levels(self):
        read = MoodEngine.player_read
        self.assertEqual(read(0.1, 0.2, 0.5), "down")
        self.assertEqual(read(0.8, 0.8, 0.6), "lively")
        self.assertEqual(read(0.4, 0.3, 0.5), "flat")
        self.assertEqual(read(0.4, 0.6, 0.6), "normal")

    def test_player_event_mapping(self):
        mood = MoodEngine()
        self.assertEqual(mood.player_event("down"), "player.sad")
        self.assertEqual(mood.player_event("weird"), "player.calm")

    def test_voice_params_follow_mood(self):
        mood = MoodEngine()
        lively = mood.voice_params()
        mood.nudge("energy", -0.6)
        mood.nudge("valence", -0.6)
        low = mood.voice_params()
        self.assertGreater(low["length_scale"], lively["length_scale"])
        self.assertGreater(low["noise_scale"], lively["noise_scale"])
        for value in list(lively.values()) + list(low.values()):
            self.assertGreater(value, 0.0)
            self.assertLess(value, 2.0)

    def test_to_dict_shape(self):
        mood = MoodEngine()
        data = mood.to_dict()
        self.assertIn("fields", data)
        self.assertIn("read_level", data)
        self.assertEqual(set(data["fields"]), {
            "valence", "energy", "curiosity", "worry", "pride"})


class TestEngineIntegration(unittest.TestCase):
    def test_engine_has_mood_and_reports_it(self):
        engine = MAMEngine(
            persona=Persona.load(),
            hints=HintLibrary.from_directory(PACKAGE_DATA / "hints"),
            settings_provider=lambda: {},
        )
        self.assertIn("mood", engine.status())
        self.assertEqual(engine.status()["mood"]["read_level"], "lively")
        # ticking without a game still advances the mood without crashing
        self.assertEqual(engine.tick(), [])

    def test_observe_mood_event(self):
        engine = MAMEngine(
            persona=Persona.load(),
            hints=HintLibrary.from_directory(PACKAGE_DATA / "hints"),
            settings_provider=lambda: {},
        )
        result = engine.observe_mood("down")
        self.assertGreater(result["fields"]["worry"], 0.2)
        self.assertEqual(engine.status()["mood"]["read_level"], "down")


if __name__ == "__main__":
    unittest.main()
