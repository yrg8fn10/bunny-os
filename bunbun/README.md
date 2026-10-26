# Bun Bun — AI co-op companion (MAM engine)

Bun Bun is the local companion agent behind the Bunny OS Control Panel.  It is
a **standard-library-only Python service**: no cloud calls, no API keys, no
telemetry.  It observes local game state, offers encouragement and hints, and —
only with explicit, revocable consent — can join allowlisted co-op sessions and
press keys through a separate root-owned input agent.

## Run it

```bash
cd bunbun
python3 -m unittest discover -s tests -t . -v      # 100% offline test suite
python3 bunbun/service.py --port 8422 --data-dir /tmp/bunbun --no-voice
python3 bin/bunbun-cli status
```

## Layout

| Path | Responsibility |
| --- | --- |
| `bunbun/mam/policy.py` | the gate: every irreversible action is a named rule |
| `bunbun/mam/engine.py` | observe → propose → gate → act → remember |
| `bunbun/persona.py` | voice lines + sanitisation + blocklist |
| `bunbun/tts/` | Piper (preferred) / espeak-ng fallback, bounded queue |
| `bunbun/perception/` | Steam ACF, Heroic/Legendary, game watcher |
| `bunbun/action/` | co-op join planner, input-agent client |
| `bunbun/memory.py` | SQLite, local only, `purge()` really deletes |
| `bunbun/service.py` | loopback HTTP API + SSE overlay stream |

## The five safety invariants

1. **No input without a token.** `ai.coop_opt_in` *and* a root-owned
   `/etc/bunny/allow-input-agent` file are required.
2. **No anti-cheat, no competitive.** Hard-coded denies, not configuration.
3. **No joining without an invitation** in `invite-only` mode (the default).
4. **No stranger chat** while the kid-safe persona is active.
5. **No silent memory.** Everything is in one SQLite file the panel can erase.

These are enforced in `policy.py` and covered by `tests/test_policy.py`.  The
engine cannot bypass them: it has no other path to an executor.

## What is *not* implemented

* Gamepad injection (keyboard/mouse only in v0.1).
* Reading game memory or hooks into anti-cheat protected processes.
* Any speech-to-text; Bun Bun listens through explicit API calls, not a hot mic.
* A neural brain.  Proposals are rule-based; a local LLM can be added behind
  `MAMEngine` without touching the policy layer.

See `../docs/BUNBUN.md` and `../docs/SAFETY-AND-LEGAL.md`.
