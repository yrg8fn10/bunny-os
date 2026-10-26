# Bun Bun — the companion agent

Bun Bun is the voice in the corner of the couch: a cheerful, kid-like bunny who
watches the game you already launched, offers a nudge when you are stuck, and
occasionally hops into a co-op lobby — but only when you have said yes twice.

It is **not** a chatbot bolted onto a store page, not a cloud model, and not a
hot mic. Everything below runs on the machine, as your user, with no network
access beyond `127.0.0.1`.

> **Scope honesty.** v0.1 is a rule-based companion. There is no neural brain,
> no speech-to-text, and no computer vision. `ai.screen_vision` exists in the
> settings schema as a reserved toggle; nothing reads your screen yet. Hints
> come from a local JSON library and from explicit state reports. See
> [What is not implemented](#9-what-is-not-implemented).

## 1. Persona

`bunbun/data/persona.json` is the source of truth. It is data, not prompt text,
so it can be reviewed and translated without touching code.

| Property | Value |
|----------|-------|
| Name | Bun Bun |
| Species | bunny |
| Role | co-op buddy and hint giver |
| Voice style | bright, gentle, kid-like; slightly slow; high pitch |
| Utterance cap | 180 characters (configurable) |
| Default hint level | `gentle` |

The persona's own rules, enforced by `persona.py` and by review:

* Celebrate effort, not just wins.
* One hint at a time; ask before spoiling a secret.
* Never claim to be human.
* Never ask for personal information.
* If the player is frustrated, offer a break before a solution.
* Stay cheerful, but never guilt-trip or pressure.
* In multiplayer, announce itself as an AI buddy when joining.

The voice is a **fictional character**, not a recording of a child. The
forbidden list in `persona.json` bans imitating a real child or person, urging
purchases or loot boxes, pressure to keep playing, adult content, and scary
imagery. `sanitize()` truncates long lines, strips control characters, and
replaces blocked phrases with a neutral fallback.

## 2. The MAM loop

MAM stands for **Mine Action Model** — the agent's decision loop, not a model
you download:

```
OBSERVE  →  PROPOSE  →  GATE  →  ACT  →  REMEMBER
```

| Stage | Code | What happens |
|-------|------|--------------|
| Observe | `perception/`, `MAMEngine.observe()` | A game is detected or an API caller reports state. |
| Propose | `MAMEngine.tick()` | Cheap, creative candidates: greet, hint, encourage, suggest a break, offer a join. |
| Gate | `mam/policy.py` | Every candidate is checked against named rules. Default answer: no. |
| Act | `MAMEngine._act()` | Speak through TTS, publish an overlay event, or hand a confirmed join to the co-op planner. |
| Remember | `memory.py` | A local SQLite note: game started, hint shown, consent given, proposal refused. |

Proposals are sorted by priority, deduplicated for two minutes, and rate
limited. A refused proposal is still published (`bunbun.refused`) and recorded,
so the panel can explain *why* Bun Bun stayed quiet.

### Signals the engine reacts to

| State field | Trigger |
|-------------|---------|
| `game_id` change | Greeting, new memory session |
| `invite_from` | Ask the player whether to join (never automatic) |
| `secret_nearby` | Secret hint, only at `helpful`/`spoilery` |
| `stuck_seconds >= 90` | One unseen library hint, or a gentle nudge |
| `deaths_recent >= 3` or `mood=frustrated` | Suggest a break before a solution |
| `mood=victory` | Celebrate |
| `mood=excited` after 30 s | Occasional encouragement, at most every few minutes |

Game state is supplied by the watcher (Steam ACF files, Heroic/Legendary
manifests, running processes) or by an explicit `POST /v1/state`. The agent does
not read game memory and does not hook graphics APIs.

## 3. Hint library

Hints live in `bunbun/data/hints/*.json`. Each file may contain any number of
entries:

```json
{
  "hints": [
    {
      "id": "generic-look-up",
      "game": "*",
      "level": "gentle",
      "text": "Tiny hint: try looking up near the big door.",
      "where": "above the door",
      "tags": ["exploration"],
      "secret": false
    }
  ]
}
```

| Level | Meaning |
|-------|---------|
| `off` | No hints at all; speak actions still work if enabled |
| `gentle` | Nudges that do not name the solution |
| `helpful` | Specific location or mechanic |
| `spoilery` | Explicit solutions and secrets |

Rules:

* A hint is shown **once** per game; seen hints are recorded in SQLite.
* Secrets require `spoilery` **or** an explicit on-demand request.
* An on-demand hint (`POST /v1/hint`) bypasses the per-kind cooldown because a
  human asked, but still obeys the global 24-actions-per-minute limit.
* Hints are read-only. They never inject input, even in games where input is
  otherwise allowed.
* At `gentle`, a secret hint is simply not proposed.

Adding hints requires no code change: drop a JSON file in the directory and
restart the user service. Invalid entries are skipped rather than crashing the
library.

## 4. Voice and text-to-speech

`tts/backends.py` chooses a backend at startup:

| Priority | Backend | Requirement |
|----------|---------|-------------|
| 1 | Piper | `piper` binary plus a voice `.onnx` model |
| 2 | espeak-ng | `espeak-ng` package |
| 3 | Null | silent, but the overlay still shows text |

Voice models are **not** shipped in this repository or the ISO. Piper models
carry their own licences; check the model card before redistributing one. Put a
model at `/usr/share/bunbun/voices/<voice-key>.onnx` (or set
`BUNBUN_PIPER_MODEL`). Espeak is the always-available fallback and is what a
fresh image uses until a model is installed.

Both backends are invoked as argument lists, never through a shell. Synthesis
has a timeout, output is capped, and a failed synthesis publishes
`bunbun.error` instead of blocking the loop. The panel can mute voice
independently of hints; a muted Bun Bun still emits overlay text.

## 5. API and overlay stream

The service binds `127.0.0.1:8422` and refuses non-loopback `Host` headers.
There is no authentication because there is no remote surface; any local
process can call it, exactly like a desktop notification daemon.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness, voice backend, memory stats, kill switch |
| GET | `/v1/status` | Engine, watcher, co-op, policy cooldowns |
| GET | `/v1/state` | Current game state |
| GET | `/v1/events?limit=N` | Recent bus events |
| GET | `/v1/policy` | The rule table, human readable |
| GET | `/v1/stream` | Server-Sent Events for the overlay |
| POST | `/v1/state` | Report a game state observation |
| POST | `/v1/tick` | Run one MAM cycle |
| POST | `/v1/say` | Speak a caller-supplied line (sanitised) |
| POST | `/v1/hint` | Request a hint, `{"secret": true}` for secrets |
| POST | `/v1/coop/join` | Evaluate or perform a join |
| POST | `/v1/coop/leave` | Leave the active session |
| POST | `/v1/consent` | Record a consent decision |
| POST | `/v1/memory/purge` | Delete all memory |
| POST | `/v1/settings/reload` | Re-read settings and return the effective view |

Example:

```bash
curl -s http://127.0.0.1:8422/v1/status | python3 -m json.tool

curl -s -X POST http://127.0.0.1:8422/v1/state \
  -H 'Content-Type: application/json' \
  -d '{"game_id":"steam:620","title":"Portal 2","platform":"steam",
       "multiplayer":true,"stuck_seconds":120,"mood":"frustrated"}'

curl -s -X POST http://127.0.0.1:8422/v1/hint -d '{}'
```

The SSE stream is data-only: every event arrives as a `data:` frame containing
`{"topic": "...", "payload": {...}, "ts": ...}`. The overlay does not need one
listener per topic, and a slow client cannot stall the engine; the bus drops
events for that subscriber instead.

Topics you will see:

```
agent.started / agent.stopped      game.detected / game.exited
game.started / game.stopped        game.anticheat
bunbun.say / bunbun.hint           bunbun.spoken
bunbun.refused                     bunbun.consent_request / bunbun.consent
bunbun.error                       coop.refused / coop.consent_request
coop.joined / coop.left            hint.shown
```

## 6. Co-op: joining a friend

Joining is a **plan and ask** operation, because there is no universal API for
it:

| Platform | Capability |
|----------|------------|
| Steam | `steam://joinlobby/<appid>/<lobby>` when the game advertises a lobby id |
| Epic via Heroic | Launch the title; the player accepts the in-game invite |
| GOG / Lutris / RetroArch | Launch only; manual invite acceptance |

The default mode is `invite-only`. Even with `coop_opt_in` on, Bun Bun will not
join without a real invitation *and* a player confirmation. `dry_run: true`
returns the plan without launching anything.

Every join is refused outright when the title is anti-cheat protected or
competitive, regardless of settings. The allowlist is
`/etc/bunny/coop-allowlist.txt`, matched against the executable name in the
input agent and against game id / app id / lower-case title in the co-op agent.
An empty allowlist means "nothing is allowed", not "everything is allowed".

Sessions carry a 120-minute advisory cap. The status endpoint reports
`warn_over_cap`; nothing force-quits a game. `POST /v1/coop/leave` records the
exit and publishes `coop.left`.

## 7. Input assistance (opt-in, masked, root-owned)

Bun Bun cannot press buttons by itself. The only component that can is
`/usr/local/lib/bunny/bunny_input_agent.py`, a separate root service that is
**masked at build time**.

To enable it, all of the following must be true:

1. `/etc/bunny/allow-input-agent` exists. It is written only by an explicit
   `bunnyctl input-agent enable --i-consent` (or the panel's consent modal).
2. `ai.coop_opt_in` is true and the title is in the co-op allowlist.
3. The target PID is alive, owned by the desktop user (`bunny` or root), and
   its executable name is in the allowlist.
4. `/run/bunny/input.disable` does not exist (panic switch).
5. The game is multiplayer, not competitive, and not anti-cheat protected.

The agent then exposes a narrow command set over `/run/bunny/input.sock`:
`tap`, `hold`, `text`, `mouse`, `scroll`, `panic`, `status`. It supports
**keyboard and mouse only** — gamepad injection is intentionally absent. Text
is capped at 200 characters; the rate limiter allows 12 events/second with a
burst of 30; every command is appended to
`/var/log/bunny/input-audit.log` with the key or text length (not the text
itself).

Panic is immediate:

```bash
bunnyctl input-agent panic      # writes /run/bunny/input.disable
rm /run/bunny/input.disable     # re-arm after the game
```

This feature is a consent mechanism for cooperative play. It is not a bypass,
not a macro engine, and must not be used to gain an advantage in competitive or
protected titles. See [SAFETY-AND-LEGAL.md](SAFETY-AND-LEGAL.md).

## 8. Memory, privacy and kill switch

Memory is one SQLite database at
`~/.local/share/bunbun/bunbun.sqlite3`. It stores sessions, hint ids already
shown, consent decisions, and short audit notes. It never stores keystrokes,
audio, screenshots, or chat transcripts.

* `ai.memory_enabled=false` stops writes immediately.
* `POST /v1/memory/purge` deletes rows and vacuums the file.
* There is no upload path and no telemetry key in the schema.
* `privacy.local_only` is repaired to `true` if a settings edit tries to
  contradict it.

The kill switch is checked on **every** proposal:

```bash
sudo touch /run/bunny/agent.lock   # deny everything immediately
sudo rm /run/bunny/agent.lock
```

`BUNBUN_DISABLE=1` in the environment has the same effect for a manual run.
Disabling the agent (`ai.enabled=false`) is the persistent version.

## 9. What is not implemented

Stated plainly, because a companion that overpromises is worse than a quiet one:

* **No neural model.** Proposals are rule-based. A local LLM can be added
  behind `MAMEngine` without touching the policy layer, but none ships today.
* **No speech input.** There is no microphone listener and no wake word.
* **No screen vision.** `ai.screen_vision` is a reserved schema key; no pixels
  are captured. Vision-based secrets require a future adapter.
* **No gamepad injection.** Keyboard and mouse only.
* **No game-memory reading, DLL injection, or anti-cheat circumvention.**
* **No cloud TTS or cloud inference.** Bun Bun works offline; voice quality
  depends on a locally installed Piper model.
* **No automatic game joins.** Every join needs an invitation plus consent.

## 10. Running and testing

On an installed system the agent is a user service:

```bash
systemctl --user status bunny-bunbun
journalctl --user -u bunny-bunbun -f
curl -s http://127.0.0.1:8422/health
```

For development, without installing anything:

```bash
cd bunbun
python3 -m unittest discover -s tests -t . -v
python3 bunbun/service.py --port 8422 --data-dir /tmp/bunbun --no-voice
python3 bin/bunbun-cli status
python3 bin/bunbun-cli hint
```

The test suite is offline and uses only the standard library. It covers policy
denials, engine deduplication, ACF parsing, persona sanitisation, memory purge,
Steam lobby plans, and the HTTP surface. `tools/verify.py` (or `verify.ps1` on
Windows) checks the safety invariants statically.

## 11. Configuration

Precedence: built-in defaults → `/etc/bunny/settings.json` (`ai.*`) →
`~/.config/bunbun.json` → `BUNBUN_*` environment variables. Per-user overrides
are limited to keys the schema knows about; unknown keys are ignored rather
than trusted.

| Variable | Default | Effect |
|----------|---------|--------|
| `BUNBUN_HOST` | `127.0.0.1` | Loopback only; non-loopback values are refused |
| `BUNBUN_PORT` | `8422` | HTTP/SSE port |
| `BUNBUN_DATA_DIR` | `~/.local/share/bunbun` | SQLite and runtime files |
| `BUNBUN_SETTINGS` | `/etc/bunny/settings.json` | System settings path |
| `BUNBUN_TTS` | `auto` | `auto`, `piper`, `espeak`, `none` |
| `BUNBUN_PIPER_MODEL` | unset | Explicit `.onnx` model |
| `BUNBUN_DISABLE` | unset | Non-empty value acts as a kill switch |
| `BUNNY_INPUT_SOCKET` | `/run/bunny/input.sock` | Input agent socket |

## 12. Related documents

* [ARCHITECTURE.md](ARCHITECTURE.md) — where the agent sits in the system
* [SESSIONS.md](SESSIONS.md) — how the user service starts and stops
* [SAFETY-AND-LEGAL.md](SAFETY-AND-LEGAL.md) — anti-cheat, consent, licensing
