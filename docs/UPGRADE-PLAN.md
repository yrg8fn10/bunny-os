# Upgrade plan: SteamOS-style boot, panel-first session, Bun Bun 2

This document answers the "SteamOS foundation / Big Picture replacement / Bun Bun
MAM overhaul" request. It separates three things that are easy to conflate:

1. what is **already implemented** and testable in this tree,
2. what can be **implemented on Arch with stock packages** (the rule this repo
   was built under),
3. what **cannot be delivered as described** without changing that rule or
   shipping per-game code.

Read section 0 before the rest: one requirement conflicts with the project's
own hard constraint, and that needs a decision, not code.

---

## 0. The one decision: SteamOS base vs. stock Arch

"Port Bunny OS onto a SteamOS structure" and "official Arch packages only, no
Valve kernel patches, no AUR" cannot both hold. SteamOS is not a theme on Arch:

| SteamOS piece | What it actually is | Consequence for this repo |
|---|---|---|
| `holo` repo | Valve-built kernels, Mesa, gamescope-session-plus | requires Valve's repos and keys; breaks the stock-Arch rule |
| A/B immutable image | read-only root + atomic updates (`steamos-update`) | needs an image-update service, not `pacman -Syu` |
| `gamescope-session-plus` | Valve's session manager + Steam Big Picture as the compositor client | AUR/Valve packaging |
| `steam-jupiter` / `jupiter-*` | Deck-specific patches and firmware glue | not in Arch |

**Recommendation (and what this tree does):** adopt SteamOS's *architecture*
without its *repositories*:

* immutable-feeling core: Btrfs `@` root + snapshots, `/home` and `/var`
  preserved across updates (already in `installer/bunny-install`);
* gaming-first session: SDDM autologin into a gamescope session that runs our
  panel (already in `bunny-session`), Plasma available as Desktop Mode;
* Big Picture replaced at the session level, not inside Steam.

**If you want the actual Valve stack** (Steam Big Picture, `gamescope-session-plus`,
Valve kernel/Mesa), that is a different build: it needs the `holo` repo, Valve's
kernel packages, and it gives up reproducible stock-Arch builds. Say the word and
it becomes a second profile (`--target steamos`), not a change to the current one.

---

## 1. Boot sequence: panel first, Steam after setup

Current, working order:

```
UEFI/systemd-boot
  └─ archiso initramfs (live) or btrfs root (installed)
      └─ systemd → multi-user.target
          ├─ bunny-setup.service      account exists? prompt on tty1 if not
          ├─ bunny-firstboot.service  time-boxed provisioning (offline-safe)
          └─ sddm.service
              └─ autologin → bunny-session gaming
                  └─ gamescope → bunny-panel --kiosk (our Big Picture)
                      └─ Steam / Desktop Mode switch
```

The "automated boot-to-Big-Picture replacement" is therefore already the
architecture: our Chromium/Tauri panel is the compositor client, not Steam's
Big Picture. What is missing is a **first-run gate** inside the panel:

```
bunny-panel --kiosk
  ├─ /var/lib/bunny/.setup-complete ?  → main panel (games, platforms)
  └─ otherwise                        → setup wizard:
        network → account → updates → "Start gaming"
```

Hooks for that gate (small, additive):

| Hook | Where | Contract |
|---|---|---|
| `bunny.setup.complete` | `/var/lib/bunny/.setup-complete` | marker written by the wizard; the panel reads it at start |
| setup wizard route | `control-panel/ui` (`#/setup`) | calls the same bridge endpoints as the settings pages |
| update gate | `bunny-update.service` | wizard waits for `systemctl is-active bunny-update` to finish, with a 10 min cap, then continues |
| hand-off to Steam | `bunnyctl` / bridge | after setup, panel shows the platforms view; Steam is launched from there, never as the session |

That keeps the Deck in our UI at boot (SteamOS-like), and makes "safely
transition into the normal Deck-style environment" a panel state change instead
of a session restart — no login loop is possible because the session never exits.

---

## 2. Session handoff and the crash loop

**Symptom:** authentication succeeds, the greeter disappears, the session dies,
the greeter returns.

**Cause:** `bunny-session gaming` used `exec gamescope …`. If gamescope or the
panel exited — no DRM master, missing `/dev/uinput` for `--force-grab-cursor`,
chromium failing under Wayland — the session process exited. SDDM interprets
that as "session ended" and repaints the greeter. With autologin on, that is a
loop.

**Fix (implemented, `system/bin/bunny-session`):**

* no `exec` for the compositor; every attempt is supervised;
* preflight: `/dev/dri/card*` present, panel executable, `force-desktop` escape
  hatch, gamescope installed;
* `/dev/uinput` missing → drop `--force-grab-cursor` instead of aborting;
* `uinput` is now loaded at boot (`/etc/modules-load.d/bunny-gamescope.conf`);
* fallback chain `gamescope → gamescope (minimal args) → cage → Plasma`, so the
  user always lands somewhere usable;
* consecutive-failure counter (`~/.local/state/bunny/gaming-failures`): two
  failures disable the gaming path for later logins until it is cleared;
* full log at `~/.local/state/bunny/session.log` plus the journal, so the next
  failure names itself instead of looking like a loop.

Verification: `tools/verify.py` asserts the fallback, the counter, the uinput
handling and the absence of `exec gamescope`.

Escape hatches for a broken session:

```
touch /etc/bunny/force-desktop        # skip the gaming session entirely
rm ~/.local/state/bunny/gaming-failures   # retry gaming after a fix
bunnyctl mode desktop                 # switch the default session
```

---

## 3. Desktop Mode transition listener and the voice greeting

Two different events, deliberately handled separately:

| Event | Hook | Behaviour |
|---|---|---|
| login into Desktop Mode | `bunny-session desktop` → `play_greeting` → `bunny-desktop-greeting` | one spoken line, 4 s after Plasma starts |
| runtime switch (panel button / `bunnyctl`) | `bunny-sessiond` `set_mode` + SDDM restart | the next login is Desktop, and the greeting fires then |

`bunny-desktop-greeting` is real and shipped:

* speaks a line from `bunbun/data/persona.json` → `lines.desktop_greeting`;
* `piper` neural voice when a model exists under `/usr/share/bunbun/voices`,
  otherwise **espeak-ng** (`en+f3`, pitch 78, 168 wpm) — offline, no download;
* plays through `pw-play`/`paplay`/`aplay`; silent no-op if audio is absent;
* one greeting per boot (stamp in `XDG_RUNTIME_DIR`), so mode churn cannot
  repeat the line;
* never blocks or delays the session.

Honest limitation: espeak-ng is a formant synthesiser. It is bright and
child-like in pitch, but it is not "classic interactive toy" voice acting. For
that, ship a licensed neural voice model (piper `.onnx`) — the code path exists,
the model is a distribution decision, not a code one.

---

## 4. Bun Bun MAM as an in-game companion

Bun Bun today is: perception (Steam/Heroic/ACF watchers), a policy engine with
persona rules, memory, TTS, and an action layer (`bunbun/action/coop.py`,
`input_client.py`). That is a *companion that watches, talks and suggests*.

"Capable of moving, learning and playing alongside the user as a real teammate"
is not a model change; it is a **game-integration** change. A generic OS layer
cannot move a character inside an arbitrary game — there is no portable API for
it. Two honest paths:

### Path A — companion that plays *with* you (buildable, no game code)

* acts through a virtual gamepad (`uinput`): it can drive a co-op character in
  split-screen/local multiplayer games that accept a second controller;
* needs per-game input scripts, because "walk left and follow the player" is
  game-specific;
* consent is explicit: `/etc/bunny/allow-input-agent` (already the gate in
  `bunny-input-agent.service`), an on-screen indicator, and a kill switch.

Pipeline:

```
GameWatcher (perception/watcher.py)
   → MAM engine (mam/engine.py): state = {game, scenario, player_state}
   → policy (mam/policy.py): allowed actions, persona tone, safety limits
   → action (action/input_client.py → uinput virtual pad)
   → memory (memory.py): what worked, what the player liked
```

What must be added for Path A to be real:

1. `action/virtual_pad.py` — create an evdev/uinput gamepad, named
   `Bun Bun (AI buddy)`, with a rate limit and a panic stop;
2. per-game profiles in `bunbun/data/companions/<appid>.json` — button maps and
   a small behaviour script (follow, revive, emote);
3. a scene reader: screen capture + OCR/vision is the only generic option and is
   slow and fragile; per-game memory reading is precise but per-game work;
4. a supervisor that refuses to act when the player is in a menu, in a cutscene,
   or has not opted in.

### Path B — companion as an overlay (partly buildable today)

Voice callouts, hints, reactions and co-op invites over the game, driven by
window titles and log files. No input injection, no game-specific code. This is
the safe default and it is what the current tree does.

**Recommendation:** ship Path B now, gate Path A behind an explicit opt-in and
one supported game at a time. Claiming a general "plays any game with you"
companion would be false, and it is the kind of claim that gets a project
laughed at.

### Persona in the behaviour loop

The persona is already data (`persona.json`) rather than prompt text. To make it
drive reactions and movement:

* `reaction_loop`: map game events (`death`, `objective`, `idle 90s`) to persona
  line categories (`stuck`, `encouragement`, `victory`) — `persona.py` already
  exposes categories, the watcher already emits events;
* `movement_style`: for Path A, express it as *timing and jitter* around scripted
  actions (a little hop when celebrating, a pause before following), not as a
  learned controller policy. Learned play needs a training environment per game;
  that is a research project, not an OS feature;
* `coop.py` already announces Bun Bun as an AI buddy when joining — keep that
  rule; it is the ethical baseline for an agent that plays with humans.

---

## 5. Phases and acceptance

| Phase | Deliverable | Acceptance |
|---|---|---|
| 1 (this build) | session supervisor, uinput, desktop greeting, recovery menu, account setup | login never returns to the greeter; greeting speaks once per boot |
| 2 | panel first-run gate + update gate | fresh install boots to the wizard, then the panel; no session restart |
| 3 | `bunny-mode-watch` runtime listener | switching mode from the panel speaks the greeting and restarts only SDDM |
| 4 | Path A virtual pad + one game profile | Bun Bun joins a local co-op match as a pad, with a visible indicator and kill switch |
| 5 | optional `--target steamos` | Valve stack build, separate from the stock-Arch profile |

Phase 1 is in this tree. Phase 2 needs UI work in `control-panel/ui` and a
bridge endpoint; phase 4 needs a supported game chosen first.
