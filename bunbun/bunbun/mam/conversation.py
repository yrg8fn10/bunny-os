"""Conversation layer for the MAM engine (pre10 pillar 3).

The rule-based core answers what a companion actually gets asked mid-game:
who she is, how she is doing, praise, comfort, and a nudge back toward the
game. A *local* model can be plugged in behind the same safety layer with
``mam_model_path`` + ``mam_llama_cli`` (llama.cpp CLI). Nothing here touches
a network: no API keys, no cloud calls, ever. If the model or binary is
missing, the rule lines carry the conversation and she stays honest about
what she is.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

# Topic routers, checked in order. Deliberately small: a companion, not a
# search engine.
_SELF = re.compile(r"\b(who are you|what are you|your name)\b", re.I)
_FEELING = re.compile(r"\b(how are you|how'?s it going|you okay|are you ok)\b", re.I)
_THANKS = re.compile(r"\b(thank(s| you)|thanks bun|good (job|girl)|well done|nice work)\b", re.I)
_SAD = re.compile(r"\bi (?:am|'m|feel)\s+(?:so |really |very |kinda )?(sad|tired|stuck|frustrated|bad)\b|this game sucks|i give up", re.I)
_BORED = re.compile(r"\b(i'?m bored|boring|nothing to do)\b", re.I)
_LORE = re.compile(r"\b(earwicks?|protocol seven|species 116|quantum influx)\b", re.I)
# v0.2 topics (Nov 26, 2026): warmth, humor, capability, time, memory.
_COMPLIMENT = re.compile(r"\b(you'?re (so |really |very )?(cute|sweet|adorable|the best|awesome|cool|smart|funny)|you'?re great|i like you)\b", re.I)
_JOKE = re.compile(r"\b(tell (me |us )?(a |another |your )?joke|make me laugh|say something funny)\b", re.I)
_AFFECTION = re.compile(r"\b(i love you|love you bun|love ya)\b", re.I)
_HELP = re.compile(r"\b(what can you do|what do you do|how can you help|what are your (skills|features))\b", re.I)
_TIME = re.compile(r"\b(what time is it|what'?s the time|time check|current time)\b", re.I)
_DATE = re.compile(r"\b(what'?s (today|the date)|what day is it|today'?s date)\b", re.I)
_REMEMBER = re.compile(r"\b(what do you (know|remember) about me|do you remember me|remember about me)\b", re.I)

_HISTORY = 8


class LocalBrain:
    """An optional on-device model, driven through the llama.cpp CLI."""

    def __init__(self, model_path: str | Path | None = None,
                 cli_path: str | Path | None = None,
                 max_tokens: int = 64, temp: float = 0.8,
                 timeout: float = 20.0):
        self.model_path = Path(model_path) if model_path else None
        self.cli = str(cli_path) if cli_path else shutil.which("llama-cli") or ""
        self.max_tokens = int(max_tokens)
        self.temp = float(temp)
        self.timeout = float(timeout)
        self.calls = 0
        self.failures = 0

    def command(self, prompt: str) -> list[str]:
        """The llama.cpp CLI invocation for one reply (kept testable)."""
        # -st: single turn, then exit (the bundled llama.cpp CLI defaults to
        # interactive conversation mode, which would hang until the timeout).
        return [self.cli, "-m", str(self.model_path),
                "-p", prompt, "-n", str(self.max_tokens),
                "--temp", str(self.temp), "--no-display-prompt", "-e", "-st"]

    def available(self) -> bool:
        if not self.cli or not self.model_path:
            return False
        return Path(self.cli).exists() and Path(self.model_path).is_file()

    def reply(self, text: str, history: list[dict[str, str]],
              persona_prompt: str = "") -> str | None:
        if not self.available():
            return None
        turns = "\n".join(f"{t['who']}: {t['text']}" for t in list(history)[-_HISTORY:])
        prompt = (persona_prompt + "\n" if persona_prompt else "") + \
            (turns + "\n" if turns else "") + f"Player: {text}\nBun Bun:"
        try:
            proc = subprocess.run(self.command(prompt),
                capture_output=True, text=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            self.failures += 1
            return None
        self.calls += 1
        out = (proc.stdout or "")
        if not out.strip() or proc.returncode != 0:
            self.failures += 1
            return None
        # The CLI prints its own chrome on stdout: a loading spinner, the
        # ascii logo, the session echo and timing stats. Strip all of it and
        # keep the generated text after the prompt's trailing speaker tag.
        out = out.replace("\x08", "").replace("\u2592", "")
        out = out.rsplit("Bun Bun:", 1)[-1]
        noise = re.compile(r"^(?:>\s|/|available commands|/exit|/regen"
                           r"|/clear|/read|/glob|\[|Loading|build\s"
                           r"|model\s|ftype\s|modalities\s"
                           r"|Prompt:|Generation:|Exiting)")
        keep = []
        for ln in out.splitlines():
            ln = ln.strip()
            if not ln or re.search(r"[\u2580-\u259f]", ln):
                continue
            if noise.match(ln):
                continue
            keep.append(ln)
        out = keep[0] if keep else ""
        # one short spoken sentence; strip any speaker tags the model adds
        out = re.sub(r"^(Bun ?Bun|Player)\s*:", "", out, flags=re.I).strip()
        return out or None


class ConversationEngine:
    """The talk half of the companion. Rules first; the brain, if any, leads."""

    def __init__(self, persona, brain: LocalBrain | None = None,
                 rng: random.Random | None = None,
                 facts_provider=None):
        self.persona = persona
        self.brain = brain
        self.rng = rng or random.Random()
        # facts_provider(): the get-to-know-you answers Bun Bun remembers
        # (the curiosity layer's known_facts). Feeds "what do you remember
        # about me" without coupling this module to the store.
        self.facts_provider = facts_provider
        self.history: deque = deque(maxlen=_HISTORY)
        self.turns = 0

    def reply(self, text: str, now: float = 0.0) -> str:
        self.turns += 1
        answer = self._route(text)
        self.history.append({"who": "player", "text": text})
        self.history.append({"who": "bunbun", "text": answer})
        return answer

    def _route(self, text: str) -> str:
        if self.brain and self.brain.available():
            persona_prompt = ("You are Bun Bun, a warm, cute, all-ages bunny "
                              "companion. Reply in one short friendly sentence.")
            facts = self._facts()
            if facts:
                picks = "; ".join(f"{k}: {v}" for k, v in list(facts.items())[:5])
                persona_prompt += f"\nKnown facts about the player: {picks}"
            answer = self.brain.reply(text, list(self.history),
                                      persona_prompt=persona_prompt)
            if answer:
                return self.persona.sanitize(answer)
        if _SELF.search(text):
            return self.persona.line("chat_self")
        if _FEELING.search(text):
            return self.persona.line("chat_feel_good")
        if _SAD.search(text):
            return self.persona.line("chat_feel_bad")
        if _THANKS.search(text):
            return self.persona.line("chat_praise")
        if _BORED.search(text):
            return self.persona.line("chat_bored")
        if _LORE.search(text):
            return self.persona.line("chat_lore")
        if _COMPLIMENT.search(text):
            return self.persona.line("chat_compliment")
        if _AFFECTION.search(text):
            return self.persona.line("chat_love")
        if _JOKE.search(text):
            return self.persona.line("chat_joke")
        if _HELP.search(text):
            return self.persona.line("chat_help")
        if _REMEMBER.search(text):
            return self._remember_reply()
        if _TIME.search(text):
            stamp = datetime.now().strftime("%I:%M %p").lstrip("0")
            return self.persona.line("chat_time", time=stamp)
        if _DATE.search(text):
            n = datetime.now()
            return self.persona.line("chat_date", date=f"{n:%A}, {n:%B} {n.day}")
        # v0.2: curiosity recall as regular chat flavor — half the time an
        # un-routed turn becomes a warm recall line instead of a generic one.
        facts = self._facts()
        if facts and self.rng.random() < 0.5:
            values = list(facts.values())
            return self.persona.line(
                "chat_curious", fact=str(values[self.rng.randrange(len(values))]))
        return self.persona.line("chat_fallback")

    def _facts(self) -> dict[str, str]:
        """The curiosity layer's known facts; empty when the layer is off."""
        if self.facts_provider is None:
            return {}
        try:
            return self.facts_provider() or {}
        except Exception:
            return {}

    def _remember_reply(self) -> str:
        facts = self._facts()
        if not facts:
            return self.persona.line("chat_remember_none")
        picks = ", ".join(str(v) for v in list(facts.values())[:2])
        return self.persona.line("chat_remember", facts=picks)


_CLI_NAMES = ("bunbun-llama-cli", "llama-cli")
_MODEL_DIRS = (
    Path("/usr/local/share/bunbun/models"),
    Path("/usr/share/bunbun/models"),
    Path(__file__).resolve().parent.parent / "data" / "models",
)
# $HOME path is computed at call time so tests can relocate HOME.

def _model_dirs() -> tuple[Path, ...]:
    return _MODEL_DIRS + (Path.home() / ".local/share/bunbun/models",)


def find_bundled_model(explicit) -> Path | None:
    """The GGUF to run: the configured path, else the bundled one."""
    if explicit:
        return Path(explicit)
    for d in _model_dirs():
        if d.is_dir():
            hits = sorted(d.glob("*.gguf"))
            if hits:
                return hits[0]
    return None


def find_bundled_cli(explicit) -> str:
    """The llama.cpp CLI: configured, then bunbun-llama-cli, then llama-cli."""
    if explicit:
        return str(explicit)
    for name in _CLI_NAMES:
        found = shutil.which(name)
        if found:
            return found
    # systemd services run with a minimal PATH; check the install spot directly
    for cand in ("/usr/local/bin/bunbun-llama-cli", "/usr/bin/llama-cli"):
        if Path(cand).exists():
            return cand
    return ""


def build_brain(config) -> LocalBrain | None:
    """Wire the local model from settings; auto-finds the bundled pair."""
    if not getattr(config, "mam_enabled", True):
        return None
    model = find_bundled_model(getattr(config, "mam_model_path", None))
    cli = find_bundled_cli(getattr(config, "mam_llama_cli", None))
    if not model or not cli:
        return None
    return LocalBrain(model_path=model, cli_path=cli,
                      max_tokens=int(getattr(config, "mam_max_tokens", 64) or 64),
                      temp=float(getattr(config, "mam_temp", 0.8) or 0.8),
                      timeout=float(getattr(config, "mam_timeout", 20.0) or 20.0))


def persona_pools() -> dict[str, Any]:
    """The conversation line pools this module expects in persona.json."""
    return {key: [] for key in
            ("chat_self", "chat_feel_good", "chat_feel_bad", "chat_praise",
             "chat_bored", "chat_lore", "chat_compliment", "chat_joke",
             "chat_love", "chat_help", "chat_remember", "chat_remember_none",
             "chat_time", "chat_date", "chat_curious", "chat_fallback")}
