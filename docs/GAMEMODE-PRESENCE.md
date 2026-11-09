# Game Mode presence: Bun Bun over running games

## The goal

Today Bun Bun only appears when she is pulled up. The change she needs:
she spawns inside actual Game Mode games, present over whatever is
running, and her brain grows past the rule-based v0.1. Both stay fully
local: no cloud calls, no API keys, ever.

## Approach: compositor-level presence (never a game injection)

Bun Bun is drawn as a **wlr-layer-shell overlay** owned by the
compositor (gamescope). This is the same relationship a notification
has to the game underneath:

* she is **never injected into the game process**, so there is no
  anti-cheat surface to touch;
* she never takes keyboard or mouse input (keyboard interactivity 0,
  empty input region, clicks fall through to the game);
* she reserves no screen space (`exclusive_zone -1`).

## bunhud (v0, tonight)

`tools/bunhud/bunhud.py` is the presence daemon:

* connects to the Wayland display, binds `zwlr_layer_shell_v1` (v1..4);
* draws a sprite (PNG with alpha) in a chosen screen corner, overlay
  layer, premultiplied-ARGB shared-memory buffer;
* control socket at `$XDG_RUNTIME_DIR/bunhud.sock`: `show`, `hide`,
  `ping`, `quit`;
* exits cleanly with a message when there is no layer-shell
  compositor (desktop mode), instead of crashing anything.

Files:

| Path | What |
|------|------|
| `tools/bunhud/bunhud.py` | the daemon |
| `tools/bunhud/wlr_layer_shell_unstable_v1.py` | vendored layer-shell binding (pywayland scanner) |
| `tools/bunhud/generate_protocols.sh` | regenerates the binding from XML |
| `tools/bunhud/placeholder_sprite.py` | draws the stand-in sprite |
| `tools/bunhud/assets/bunhud-placeholder.png` | stand-in sprite |

Status: written and import-checked, sprite conversion unit-verified.
**Not yet run against a real compositor**; the build sandbox has no
Wayland session. First test belongs on the Deck in Game Mode.

## What is not in v0

* animation (idle hop, blink) — needs frame art and a timer;
* hint bubbles / speech bubbles — needs text layout (the bridge
  already receives `bunbun.spoken` events);
* real art — the placeholder is procedural; final look is a separate
  decision.

## MAM hookup (v0 sketch)

`tools/bunhud/mam_bridge.py` connects bunhud to the companion
service's local SSE stream (`127.0.0.1:8422/v1/stream`). Started with
`--mam`, bunhud maps bus topics to presence commands:

| topic | command |
|-------|---------|
| `game.started` | show |
| `agent.started` | show |
| `bunbun.spoken` | show |
| `agent.stopped` | hide |

The mapping is provisional (pinned to the topics service.py publishes
today). The bridge retries with a growing backoff when the companion
service is not up yet, and bunhud keeps drawing either way. Localhost
only; bunhud never touches the network.

## Packaging

| Piece | Status |
|-------|--------|
| `system/user-units/bunny-bunhud.service` | written; autostarts in any session with a layer-shell compositor, exits cleanly (status 0) in desktop mode so nothing restart-loops |
| `just/bunhud.just` | ujust recipes: status, show, hide, start/stop, enable/disable, logs; import from the main ujust file |
| `scripts/stage-profile.sh` | stages `tools/bunhud` into `/opt/bunbun/tools/bunhud` with a staging-completeness check |

Open packaging question: bunhud needs `pywayland` and `Pillow`
importable by the system Python on the image. A CPython 3.11 wheel of
pywayland was built during development but is ABI-locked to 3.11; the
right fix is to add `python-pywayland` to the target's
`packages.x86_64` if it is in the Arch repos, or build a wheel for the
image's exact Python during ISO assembly. Unresolved on purpose until
the next ISO build is in scope (Ava's Nov 8 decision: no new ISO
right now).

## The brain path (MAM upgrade, separate task)

v0.1's brain is rule-based. The upgrade path: keep the rule-based
fallback, add a small **on-device** model behind the same MAM loop so
nothing about privacy changes. Honest scope: a simple companion
conversation, not a frontier chatbot. The Steam Deck (LCD, 8 GB
shared) caps model size; quantized sub-1B-class local models are the
realistic ceiling, possibly running only while plugged in.

## Risks / open questions

* gamescope's layer-shell version support (binding caps at 4, methods
  used are all v1);
* Deck OLED vs LCD differences (none expected for layer-shell);
* hide via zero-size unmap is the standard pattern but is untested
  here — verify on the Deck;
* sprite art: procedural placeholder now, real art later.
