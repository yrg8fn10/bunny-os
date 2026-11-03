# Bun Bun OS shell integration (Deliverable 2)

Status: draft v1 (2026-11-03). This is the UI skinning / shell integration
framework for the cozy pastel sci-fi look on top of Bazzite, with d-pad-only
navigation and bilingual (zh_CN / en) presentation.

## 1. Ground rules

- Steam Big Picture Mode (BPM) and the Steam client are Valve's. We do not
  patch, decompile, or skin-inject the Steam binary, and nothing here depends
  on Steam internals that an update can silently break. Everything is layered
  *around* Steam.
- The base image is immutable. Every shell change ships inside the payload
  image (see `packaging/bazzite/`), layered at build time, never written to
  `/usr` at runtime.
- Failure containment: if any theme or session piece fails, the machine must
  still boot into a working shell. `bunny-verify.service` runs the shell
  checks and marks VERIFY-FAILED without blocking boot.

## 2. The compatibility ladder

Because stock BPM cannot be re-themed safely, the look is delivered in three
layers, each independently installable:

**Layer A - everything around Steam (always installed).**
- Plymouth boot splash: pastel gradient, soft Bun Bun silhouette, no text
  (avoids font/locale issues at the earliest boot stage).
- SDDM login theme on desktop-mode targets.
- KDE Plasma desktop theming shipped as one Global Theme package
  (`bunbun-look-and-feel`): color scheme, Plasma style, Kvantum widget theme,
  Aurorae window decoration, icon subset, cursor, wallpaper.
- Steam itself, launched from the themed desktop.

**Layer B - the Bun Bun shelf (default on Deck targets).**
Game Mode (gamescope + BPM) stays stock. `bunny-session` wraps the gaming
session with two d-pad-navigable overlays owned by us:
- a pre-session splash (2-3 s) as the session starts;
- a post-session overlay on returning to the desktop: last game, resume hint,
  Bun Bun's line, quick actions. Implemented as a fullscreen KWin script
  window; no compositor hacks.
`bunny-sessiond` (systemd user unit) owns the session lifecycle hooks.

**Layer C - the Bun Bun launcher (experimental, opt-in).**
A fullscreen, d-pad-first home menu that can be selected as the return target
in place of the stock desktop hand-off. Shipped behind
`BUNNY_SHELL=launcher` because guaranteeing d-pad-only navigation requires
owning the whole surface, which Layer C does. Not the default until it
survives a full release cycle.

## 2b. The Decky Loader route (real BPM skinning)

Suggested by the owner, and it unlocks the layer we ruled out: BPM itself.
Decky Loader injects plugins into Steam's Game Mode UI at runtime (it hooks
the Steam client's web renderer). It is the community-standard tool, it is
explicitly supported on Bazzite, and it makes two things possible:

- `bunbun-bpm-theme` (CSS Loader theme): restyles Game Mode's Big Picture
  surfaces with the Bun Bun tokens (palette, radius, fonts) instead of only
  the desktop around Steam.
- `bunny-shelf` (Decky plugin): the d-pad-navigable Bun Bun shelf and quick
  actions live *inside* Game Mode rather than beside it.

Payload integration:
- install Decky Loader at build time from its upstream release into the
  image's `/home` template, no network at first boot;
- ship both packages with the image; enable the plugin by default on Deck
  targets, optional elsewhere;
- keep the Layer B KWin wrapper as the fallback: if a Steam client update
  breaks the theme or plugin until their next update, `bunny-session` still
  provides a usable Bun Bun surface.

Caveats we design for:
- Steam updates can invalidate theme selectors temporarily; CSS Loader
  themes are updated by their maintainers after client updates, and our
  verify hooks check the theme loaded, never assume it did.
- Decky and CSS Loader are third-party open source: pinned upstream releases
  only, no vendored forks, and the build records the exact version used.

## 3. D-pad-only navigation contract

Layer B and C surfaces never require a pointer:
- D-pad: focus movement (grid order, left/up/down/right).
- A: select. B: back. X: quick settings. Y: call Bun Bun.
- Everything reachable in <= 3 presses from the home screen.
- Focus is always visible (never pointer-only hover); text sizes pass the
  couch-distance test.
- Input is read through KWin's scripting API (Layer B) or libinput grab
  (Layer C); the touch screen and mouse still work but are never required.

## 4. Theming tokens

Single source of truth: `packaging/bazzite/shell/tokens.json`.
- palette: cream `#FFF7EC`, blossom `#F7D6E0`, sky `#C7E9F7`, lavender
  `#D9C7F7`, ink `#2B2E4A`.
- corner radius, blur strength, focus glow, icon geometry, font scale.
Kvantum config, color schemes, and Plymouth gradients are all generated from
the tokens at build time, so a restyle is one file edit.

## 5. Bilingual strings and voice

- All user-visible strings live in `shell/locale/bunbun-strings.{en,zh_CN}.json`
  and are resolved at render time. No hardcoded text in layouts.
- Voice cues are short pre-rendered audio lines under `shell/voice-cues/`
  (en + zh_CN), including the boot greeting "I'm waiting for you. Let's
  choose a game!" and its Chinese counterpart.
- Playback only. The shell never opens the microphone; capture belongs to the
  audio routing layer (Deliverable 3) and the hardware kill switch.

## 6. Repository layout added by this deliverable

```
packaging/bazzite/shell/
  tokens.json
  plymouth-theme-bunbun/
  sddm-theme-bunbun/
  bunbun-look-and-feel/        (KDE Global Theme package)
  kwin/bunny-shelf.kwinapp
  locale/bunbun-strings.{en,zh_CN}.json
  voice-cues/*.ogg
  bin/bunny-session
  systemd/bunny-sessiond.service (user unit)
```

## 7. Verify hooks

Extended `bunny-verify` checks (image build + first boot):
- every theme file present and owned by root;
- Plasma look-and-feel applied (`kreadconfig` round-trip);
- Plymouth default theme is `bunbun`;
- d-pad smoke test: scripted focus walk of the shelf, A/B round trip;
- rollback path: `rpm-ostree rollback` documented in BUILD.md if a theme
  leaves the session unusable.

`tools/verify.py --strict` gains the repo-side equivalents (files exist,
tokens parse, locale keys match across languages).

## 8. Rollout

- v0.2 payload: Layer A complete, Layer B flag-gated default-on.
- Layer C stays experimental until a full cycle passes on the Deck targets.

## 9. Open questions for the owner

1. Final art direction: how pastel, how much glow, any specific reference
   shots to match?
2. Is the boot greeting voice the same runtime Bun Bun TTS voice, or a
   pre-recorded performer line?
3. OLED variant: does the pastel palette need an HDR / brightness pass?
