# Safety, consent and legal notes

Bunny OS ships a companion that can talk, watch which game is running, and — if
you explicitly enable it — press keys. That is enough capability to cause real
harm if it is designed carelessly, so this document states the boundaries we
enforce, the boundaries we cannot enforce, and the legal ground the project
stands on.

> This is engineering documentation, not legal advice. Laws, store agreements
> and anti-cheat policies change and vary by country. If you distribute Bunny OS
> or ship a modified build, have counsel review your obligations.

## 1. Design principles

1. **Consent is explicit, specific and revocable.** A global "AI enabled" switch
   is not consent to join a lobby or press keys.
2. **Fail closed.** Missing files, unknown settings, stale PIDs and ambiguous
   game state all resolve to "no".
3. **No competitive advantage.** The companion is for single-player hints and
   consensual co-op, never for ranked play, automation, or bypassing a game's
   rules.
4. **No anti-cheat circumvention.** We do not read protected process memory,
   inject libraries, spoof hardware, or evade detection.
5. **Local by default.** No account, no cloud inference, no telemetry.
6. **Say what is not built.** A missing feature is documented, not simulated.

## 2. Hard denials

These are code-level rules in `bunbun/bunbun/mam/policy.py` and
`bunbun/bunbun/action/coop.py`. They are not preferences and cannot be turned
off from the Control Panel.

| Rule | Effect |
|------|--------|
| `anticheat` | No input injection or lobby join in anti-cheat protected titles |
| `competitive` | No input injection in competitive modes |
| `coop-off` | Input, join and chat require `ai.coop_opt_in=true` |
| `allowlist` | The title must appear in `/etc/bunny/coop-allowlist.txt` |
| `input-token` | Input additionally requires the root-owned consent file |
| `invite-only` | Joins require a real invitation in the default mode |
| `kid-safe-chat` | The kid-safe persona never messages strangers |
| `singleplayer-only` | Single-player titles never receive synthetic input |
| `rate-limit` | 24 actions/minute and per-kind cooldowns |

The policy engine is the only path to an executor. `MAMEngine` cannot construct
a raw input device, call a launcher, or open a lobby by itself; it can only
produce a `Proposal`.

### What "anti-cheat protected" means here

The watcher treats a running anti-cheat process as a property of the current
game session. If an anti-cheat process is detected while a game is running:

* hints remain available (they are read-only), but secret hints are refused;
* lobby joins are refused;
* input injection is refused, even with every consent flag set;
* the event `game.anticheat` is published so the panel can explain why.

This is a conservative signal, not a guarantee of any game's policy. Some
titles enable protection only in multiplayer, some use kernel drivers, and some
change behaviour between patches. **The absence of a detected anti-cheat
process does not make automation permitted.** The game's own terms always win.

## 3. The consent model

There are three separate keys, and all are required for input assistance:

```
ai.coop_opt_in = true          (settings, panel modal, audited)
ai.coop_mode  != "off"         (settings)
/etc/bunny/allow-input-agent   (root file, written by an explicit command)
```

Joining a lobby needs a fourth: a per-invite `confirmed` flag from the player.
The API makes that explicit:

```bash
# Plan only — no launch:
curl -s -X POST http://127.0.0.1:8422/v1/coop/join \
  -d '{"friend":"Ada","game_id":"steam:620","lobby_id":"...","app_id":"620",
       "confirmed":false,"dry_run":true}'

# Confirm one specific invite:
curl -s -X POST http://127.0.0.1:8422/v1/coop/join \
  -d '{"friend":"Ada","game_id":"steam:620","lobby_id":"...","app_id":"620",
       "confirmed":true}'
```

### Revoking

| Action | Command |
|--------|---------|
| Mute voice | `bunnyctl set ai.voice_enabled=false` |
| Turn off hints | `bunnyctl set ai.hint_level=off` |
| Disable co-op | `bunnyctl set ai.coop_opt_in=false` |
| Disable the agent | `bunnyctl set ai.enabled=false` |
| Kill switch (immediate) | `sudo touch /run/bunny/agent.lock` |
| Disable input agent | `bunnyctl input-agent disable` |
| Panic (input) | `bunnyctl input-agent panic` |
| Erase memory | `curl -X POST http://127.0.0.1:8422/v1/memory/purge` |

The input agent is **masked at image build time**
(`systemctl mask bunny-input-agent`). Enabling it requires the explicit
`--i-consent` flag, and the unit refuses to start without the token file, a
working `/dev/uinput`, and root.

## 4. Input injection: capabilities and limits

The agent exposes keyboard and relative mouse events only. It does not inject
gamepad events, create virtual gamepads, modify process memory, capture the
screen, or open a network socket.

| Control | Value |
|---------|-------|
| Target validation | PID alive, owned by `bunny` or root, executable allowlisted |
| Command set | `tap`, `hold`, `text`, `mouse`, `scroll`, `panic`, `status` |
| Key set | Fixed Linux keycode table; no arbitrary codes |
| Text cap | 200 characters |
| Rate limit | 12 events/s sustained, burst 30 |
| Audit | `/var/log/bunny/input-audit.log`, one JSON line per command |
| Panic | `/run/bunny/input.disable` checked before every command |
| Socket | `/run/bunny/input.sock`, mode `0660`, owner `root:bunny` |

**Residual risk.** A local process in the `bunny` group can ask the agent to
type into an allowlisted game while it is running. That is the feature. Protect
the account, keep the allowlist small, and disable the agent when you are not
using it. The audit log records what happened; it cannot undo it.

**Never point the allowlist at:** a web browser, a password manager, a shell, a
chat client, a store client, or an anti-cheat protected game. The agent checks
the executable name, not the window title or the content on screen.

## 5. Anti-cheat, competitive play and store terms

Bunny OS does not ship cheats, trainers, memory editors, aim assist, macros for
ranked play, or DRM circumvention. It does not patch game binaries. It does not
attempt to hide from anti-cheat.

What the companion does in single-player — read local install metadata, speak a
hint, show an overlay — is analogous to a guide, a stream overlay, or a
second monitor. What it does in multiplayer — join a lobby, type a message,
press an allowlisted key — is automation, and automation is where store terms
become relevant:

* **Steam Subscriber Agreement** and individual game rules may prohibit
  automation or unauthorised third-party tools. Steam lobby deep links are a
  documented client feature, but using them to join on a player's behalf may
  still be restricted by the game.
* **Epic Games / Heroic** have no public lobby deep link. The plan is
  launch-only; the player accepts the invite in-game. Do not script the Epic
  client.
* **Anti-cheat vendors** (Easy Anti-Cheat, BattlEye, Ricochet, Vanguard and
  others) make their own determinations. A kernel-level anti-cheat may treat
  any virtual input device as suspicious. Bunny OS refuses input in titles it
  detects as protected, but it cannot promise a vendor will agree.
* **Competitive modes** are hard-denied for input even in otherwise allowed
  titles.
* **Streaming and capture** may have their own rules; the overlay is local and
  does not capture or transmit gameplay.

If a game's terms prohibit a behaviour, **do not use Bunny OS to do it**. The
hard denials reduce accidental harm; they do not transfer responsibility away
from the person pressing the buttons.

### If a game or vendor objects

1. Disable the input agent and remove the title from the co-op allowlist.
2. Keep the audit log; it shows exactly what was requested.
3. Do not argue with an anti-cheat ban using this project as a defence. We do
   not guarantee that any configuration is permitted.
4. Report a false positive in our issue tracker with the game id and the
   detection signal, not with a request to evade it.

## 6. Voice, persona and AI transparency

Bun Bun's voice is a **fictional bunny character** performed by a local
synthesiser. It is not a recording of a child, and the persona explicitly
forbids imitating a real child or person. Do not clone a real person's voice for
a fork.

In multiplayer, the persona is required to announce itself as an AI buddy when
joining, and the join event carries `ai_label: "Bun Bun (AI buddy)"`. If you
modify the persona, keep that disclosure. Passing an AI companion off as a human
teammate is deceptive and out of scope for this project.

Voice models are third-party artefacts with their own licences. The repository
does not ship one. Check the model card before redistribution; some models are
non-commercial or require attribution.

## 7. Privacy and data protection

Bunny OS has no account system, no analytics endpoint and no telemetry key.
`privacy.telemetry` exists in the schema and defaults to `false`; enabling it
does nothing in v0.1. `privacy.local_only` is repaired to `true` by the daemon's
invariant check if an edit tries to contradict it.

| Data | Where | Retention | Removal |
|------|-------|-----------|---------|
| Settings | `/etc/bunny/settings.json` | Until changed | Edit or reset |
| Agent memory | `~/.local/share/bunbun/bunbun.sqlite3` | Until purged | `POST /v1/memory/purge` |
| Session audit | `/var/log/bunny/sessiond-audit.log` | Rotated by journald/logrotate | Root deletion |
| Input audit | `/var/log/bunny/input-audit.log` | Rotated | Root deletion |
| Health snapshot | `/var/lib/bunny/health.json` | Overwritten | Delete |
| Game libraries | Steam/Heroic metadata, read-only | Untouched | Managed by the store |

What is **never** collected: keystrokes outside synthetic input, microphone
audio, screenshots, game memory, chat transcripts, contacts, location, or
hardware fingerprints. There is no hot mic and no speech-to-text.

### Children and the kid-safe persona

`ai.kid_safe=true` by default. It blocks stranger chat and applies the persona's
content rules. It is **not** a parental-control system, a COPPA/GDPR-K
compliance feature, or a substitute for supervision. A child with access to the
Control Panel can change settings, and autologin means physical access is full
access. Use OS accounts, firmware passwords and disk encryption if that matters
in your household.

### GDPR / data-subject requests

Because there is no central service, there is nothing for us to disclose or
delete on your behalf. Everything is on your device, under your control. If you
operate a fleet, you are the controller; document the paths in the table above.

## 8. Licensing and third-party components

| Component | Licence / status |
|-----------|------------------|
| Bunny OS original code, units, UI, docs | MIT (see `LICENSE`) |
| Bun Bun persona text and SVG art | Original to this project, MIT |
| Arch Linux packages | Their own licences; Arch trademark rules apply |
| Steam client | Proprietary, Valve; not redistributed |
| Heroic Games Launcher | GPL-3.0; installed from Flathub, not vendored |
| Lutris | GPL-3.0; installed from Flathub, not vendored |
| RetroArch | GPL-3.0; cores have individual licences |
| KDE Plasma | GPL/LGPL; distribution packaging applies |
| Piper voices | Per-model licence; not shipped |
| espeak-ng | GPL-3.0 |

Bunny OS is **not affiliated with or endorsed by** Valve, Epic Games, GOG, KDE,
Arch Linux, Nintendo, Sony, Microsoft, or any anti-cheat vendor. Product names
are used descriptively.

### Emulation

RetroArch is a frontend. Bunny OS ships **no ROMs, no BIOS files, no keys and no
decryption tools**. Dumping games you own may be legal where you live and
illegal elsewhere; downloading ROMs you do not own is copyright infringement in
most jurisdictions. The project takes no position beyond "we do not ship them".

### DRM and compatibility layers

Proton, Wine, DXVK and similar are legitimate compatibility projects. Bunny OS
does not include DRM circumvention, piracy tools, or patches that defeat
authentication. Do not add them to a fork and call it Bunny OS.

## 9. Installer, partitioning and overclocking

`bunny-install` is destructive **by design**:

* It erases an entire disk. There is no dual-boot wizard in this version.
* It requires typing `ERASE` and refuses to target the running live media.
* It is UEFI-only. BIOS installs are refused, not degraded.
* It does **not** encrypt the disk. LUKS is a known gap; do not treat an
  installed Bunny OS as confidential without adding encryption yourself.
* Secure Boot must be disabled for the current unsigned image.

Back up first. A wrong device node destroys data with no undo.

Overclocking, TDP changes and fan curves are hardware-dependent and can cause
instability, data loss, or damage. `performance.allow_overclock` is an opt-in
consent flag: v0.1 records it and the requested values but performs **no clock,
voltage, TDP or fan write**. Firmware thermal limits remain in full control.
Any future backend must probe the device and refuse unsupported hardware rather
than writing a value that does nothing. Until then, use vendor tools manually
and at your own risk; warranties may be voided.

## 10. Security reporting

If you find a vulnerability — a way to make the daemon execute arbitrary argv, a
way to bypass the input agent's PID or allowlist checks, a path traversal in the
bridge, or a secret in the repository — please report it privately to the
maintainers rather than opening a public exploit issue. Include:

* affected version and commit,
* the smallest reproduction you can manage,
* whether the daemon, bridge, agent or installer is involved,
* your assessment of impact.

Do not test against systems you do not own. Do not use a discovered bypass to
play a game online.

## 11. Distribution checklist

If you ship a modified ISO:

- [ ] Keep the safety rules enabled; do not remove `anticheat`, `competitive`,
      `allowlist`, `input-token` or `invite-only` checks.
- [ ] Keep the input agent masked by default and keep the consent token flow.
- [ ] Keep the local-only bind and the Host-header check.
- [ ] Replace the MIT notice only if your changes require it; preserve upstream
      attribution.
- [ ] Audit every third-party asset and voice model for redistribution rights.
- [ ] Do not ship ROMs, BIOS files, keys, or DRM circumvention.
- [ ] Re-read the store agreements for every platform you preinstall or
      integrate.
- [ ] State plainly which features are stubs. This project tries to.

## 12. Summary

Bunny OS is a hobbyist, controller-first Linux distribution with a local
companion. It is built to be honest about its limits: no cloud brain, no hot
mic, no screen capture, no anti-cheat bypass, no encryption yet. The safety
model is "fail closed, ask twice, log everything, and let the player revoke it".

If that is not the trade-off you want, fork it — but keep the denials.
