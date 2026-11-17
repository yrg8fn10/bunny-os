# Native updater design (Bunny OS 2.0 native)

Ava's rule, Nov 14 2026: after the one-time rebase/install, Bun Bun updates
**herself through the channel**, Windows-Update style. No console commands, ever —
not for Ava, not for the public. The current-line updater (`bunny-update`,
`bunny-update-payload`, the image channel from b580628/8eefaac) already works on
the Bazzite-based line. This document designs the **native** updater that ships
inside Bunny OS 2.0: the same promise, owned by us end to end, working over any
swap-able base.

## What must be true

1. **Zero console.** The user sees Bun Bun say it and one button. That's it.
2. **Atomic.** The running boot never mutates. Stage to the second boot entry;
   the old one stays as rollback until the new one is proven.
3. **Digest-verified.** Nothing stages without a sha256 match against the
   published manifest. Signature verification arrives with v0.1 alpha.
4. **Watchdog protocol.** A download that dies resumes from its exact byte
   offset. Never restart a long pull from zero.
5. **Bun Bun announces.** Voice + panel toast at check, at stage, and at reboot
   ask. She speaks before anything moves.
6. **Home untouched.** `/var/home`, saves, settings, game libraries survive
   every update, including the one-time native install.

## Channel surface

| Tag | Meaning |
|-----|---------|
| `deck-stable` | Deck LCD/OLED stable builds |
| `deck-nvidia-stable` | RTX desktop builds, proprietary driver baked in |

The manifest (JSON, published with every image) carries: version, tag, sha256,
size, min-updater, and a short Bun Bun changelog line she can read aloud.

## Phases (state machine, crash-safe)

```
IDLE ──timer──► CHECK ──new──► PULL ──done──► VERIFY ──ok──► STAGE ──ok──► READY
                 │               │ resumable    │ mismatch→PULL retry     │
                 │               └─resume from exact offset                ▼
                 └─none→ IDLE                                     ANNOUNCE ──consent──► REBOOT
                                                                          └─declined→ stays READY
                                                     (REBOOT ok) HEALTH ──fail──► ROLLBACK
```

- **CHECK** — timer (default 4h, quiet hours respected) reads the manifest,
  compares against the running version. No network → stay IDLE, log, retry next
  tick. A failed check must never break the timer (same rule as today's payload).
- **PULL** — background, low-IO-priority fetch to `/var/cache/bunny-update/<ver>`.
  Resume via byte offset + expected size. Partial file is never trusted.
- **VERIFY** — sha256 against the manifest. Mismatch → delete, re-PULL (max 3,
  then surface to the panel and to Bun Bun's voice, never silently).
- **STAGE** — deploy into the second boot entry (OSTree deployment on the OSTree
  base; Btrfs snapshot + boot entry swap on the Arch/pacstrap base). Old boot
  retained. Stage is fully reversible until REBOOT.
- **ANNOUNCE** — Bun Bun (TTS + panel): "version 0.2.0-beta10 is staged and
  verified. I can restart when you're ready." Consent is required from the panel
  button or her voice. Optional auto-restart inside user-set quiet hours.
- **REBOOT** — single reboot into the new entry.
- **HEALTH** — after boot: bunny-session up, Bun Bun agent answering on
  127.0.0.1:8422, bunhud running. Fail within the grace window → automatic
  rollback to the previous deployment + one voice apology line.
- **ROLLBACK** — select previous boot entry, mark the bad image in the manifest
  state so CHECK won't re-offer it.

## What carries the state

`/var/lib/bunny-update/state.json` — phase, version, offsets, last result.
Written atomically every transition, so a power cut lands the machine back in a
known phase, exactly like the watchdog protocol we already run on builds.

## Working prototype (Mon Nov 16, 2026, prototype-night milestone)

- `system/bin/bunny-update-native` — all legs implemented for real:
  CHECK (manifest read + version compare, offline stays IDLE), PULL
  (resumable ranged fetch, byte-offset checkpoints, watchdog-safe), VERIFY
  (sha256 gate, 3-attempt retry then surface, never stages a bad image),
  STAGE (bootc on the OSTree base; Btrfs rollback snapshot + staged boot
  entry on the pacstrap base; old boot always retained, reversible until
  APPLY), APPLY (Bun Bun asks first, `--yes` reboots), HEALTH (post-boot
  agent + session probe, auto-rollback on 3 consecutive failures), ROLLBACK
  (previous boot restored, bad version marked so CHECK skips it).
- `system/units/bunny-update-native.{service,timer}` — the 4h timer + oneshot,
  quiet-hour aware, wired to the same settings file as today's updater.
- `system/units/bunny-update-native-health.service` — post-boot health check,
  wired for auto-rollback.
- `tests/native-updater-test.sh` — offline harness (fake channel + stub
  backend): 23 checks covering the full machine, resume-from-offset,
  digest-mismatch surfacing, consent gate, auto-rollback, bad-version skip
  and recovery. All green.

## Milestones

- **Mon Nov 16** — working end-to-end prototype: CHECK→PULL→VERIFY→STAGE→REBOOT
  on a test VM against a private manifest.
- **Wed Nov 18** — v0.1 alpha native ISO with the updater baked in, published to
  archive.org (after the updater milestone, per Ava's ordering).
