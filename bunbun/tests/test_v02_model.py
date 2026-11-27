"""v0.2 model wiring: config keys, auto-discovery, brain knobs, curious flavor."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bunbun import config as cfgmod
from bunbun.mam.conversation import (ConversationEngine, LocalBrain,
                                     build_brain, persona_pools)


class _Persona:
    def __init__(self):
        self.pools = {
            "chat_curious": ["curious line about {fact}"],
            "chat_fallback": ["fallback line"],
        }

    def line(self, name, **kw):
        return self.pools[name][0].format(**kw) if kw else self.pools[name][0]

    def sanitize(self, text):
        return text


class _FakeBrain:
    def __init__(self):
        self.prompts = []

    def available(self):
        return True

    def reply(self, text, history, persona_prompt=""):
        self.prompts.append(persona_prompt)
        return "hello from the model"


def _fake_cli(tmp: Path) -> Path:
    p = tmp / "llama-cli"
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


class BuildBrain(unittest.TestCase):
    def test_explicit_paths_wire_the_brain(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            model = tmp / "m.gguf"
            model.write_bytes(b"x")
            cfg = cfgmod.AgentConfig(mam_model_path=model, mam_llama_cli=_fake_cli(tmp))
            brain = build_brain(cfg)
            self.assertIsInstance(brain, LocalBrain)
            self.assertTrue(brain.available())

    def test_mam_enabled_false_disables_the_brain(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = cfgmod.AgentConfig(mam_enabled=False,
                                     mam_model_path=tmp / "m.gguf",
                                     mam_llama_cli=_fake_cli(tmp))
            self.assertIsNone(build_brain(cfg))

    def test_auto_discovery_finds_bundled_pair(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            models = tmp / ".local/share/bunbun/models"
            models.mkdir(parents=True)
            (models / "bundled.gguf").write_bytes(b"x")
            bindir = tmp / "bin"
            bindir.mkdir()
            _fake_cli(bindir)
            env = {"HOME": str(tmp), "PATH": f"{bindir}:{os.environ['PATH']}"}
            with mock.patch.dict(os.environ, env):
                brain = build_brain(cfgmod.AgentConfig())
            self.assertIsInstance(brain, LocalBrain)
            self.assertEqual(brain.model_path.name, "bundled.gguf")
            self.assertEqual(Path(brain.cli).name, "llama-cli")

    def test_no_model_no_brain(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            env = {"HOME": str(tmp), "PATH": f"{tmp}:{os.environ['PATH']}"}
            with mock.patch.dict(os.environ, env):
                self.assertIsNone(build_brain(cfgmod.AgentConfig()))


class BrainKnobs(unittest.TestCase):
    def test_command_carries_knobs(self):
        brain = LocalBrain(model_path="m.gguf", cli_path="/bin/true",
                           max_tokens=32, temp=0.3)
        argv = brain.command("hi")
        self.assertIn("-n", argv)
        self.assertEqual(argv[argv.index("-n") + 1], "32")
        self.assertEqual(argv[argv.index("--temp") + 1], "0.3")

    def test_config_knobs_flow_through_build_brain(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            cfg = cfgmod.AgentConfig(mam_model_path=tmp / "m.gguf",
                                     mam_llama_cli=_fake_cli(tmp),
                                     mam_max_tokens=48, mam_temp=0.5,
                                     mam_timeout=7.5)
            brain = build_brain(cfg)
            self.assertEqual(brain.max_tokens, 48)
            self.assertEqual(brain.temp, 0.5)
            self.assertEqual(brain.timeout, 7.5)


class CuriousFlavor(unittest.TestCase):
    def _engine(self, facts):
        return ConversationEngine(_Persona(), None,
                                  rng=__import__("random").Random(),
                                  facts_provider=lambda: facts)

    def test_curious_line_carries_the_fact(self):
        eng = self._engine({"q1": "pizza"})
        with mock.patch.object(eng.rng, "random", return_value=0.1), \
             mock.patch.object(eng.rng, "randrange", return_value=0):
            out = eng.reply("tell me something random")
        self.assertIn("pizza", out)

    def test_fallback_when_no_fact_or_no_luck(self):
        eng = self._engine({})
        with mock.patch.object(eng.rng, "random", return_value=0.1):
            self.assertEqual(eng.reply("hmm what"), "fallback line")
        eng = self._engine({"q1": "pizza"})
        with mock.patch.object(eng.rng, "random", return_value=0.9):
            self.assertEqual(eng.reply("hmm what"), "fallback line")

    def test_brain_prompt_includes_facts(self):
        brain = _FakeBrain()
        eng = ConversationEngine(_Persona(), brain,
                                 facts_provider=lambda: {"favorite food": "pizza"})
        eng.reply("hey there")
        self.assertIn("Known facts about the player", brain.prompts[-1])
        self.assertIn("pizza", brain.prompts[-1])


class PersonaPools(unittest.TestCase):
    def test_chat_curious_is_expected_and_shipped(self):
        self.assertIn("chat_curious", persona_pools())
        shipped = json.loads(Path("bunbun/data/persona.json").read_text("utf-8"))
        self.assertIn("chat_curious", shipped)
        self.assertTrue(shipped["chat_curious"])


if __name__ == "__main__":
    unittest.main()


class ReplyParsing(unittest.TestCase):
    RAW = ("\nLoading model... |\x08-\x08\\\x08/\x08 \b\n\n"
           "\u2584\u2584 \u2584\u2584\n\u2588\u2588 \u2588\u2588  \u2588\u2588\u2588\n"
           "build      : b12803-492d23cc9\n"
           "model      : m.gguf\n"
           "ftype      : Q4_K - Medium\n"
           "modalities : text\n\n"
           "available commands:\n"
           "  /exit or Ctrl+C     stop or exit\n"
           "  /regen              regenerate the last response\n\n"
           "\u003e You are Bun Bun, a warm, cute, all-ages bunny companion.\n"
           "Player: good morning bun\n"
           "Bun Bun:\n"
           "Good morning! What can I help you with today?\n"
           "\n[ Prompt: 109.4 t/s | Generation: 28.2 t/s ]\n\n"
           "Exiting...\n")

    def _brain(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        model = tmp / "m.gguf"
        model.write_bytes(b"x")
        return LocalBrain(model_path=model, cli_path="/bin/true")

    def test_chrome_is_stripped_from_cli_output(self):
        brain = self._brain()
        with mock.patch("bunbun.mam.conversation.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=self.RAW,
                                         stderr="")
            out = brain.reply("good morning bun", [])
        self.assertEqual(out, "Good morning! What can I help you with today?")
        self.assertEqual(brain.failures, 0)

    def test_command_uses_single_turn_flag(self):
        brain = self._brain()
        self.assertIn("-st", brain.command("hi"))
