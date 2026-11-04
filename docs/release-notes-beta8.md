**Bunny OS 0.2.0-beta.8-bazzite** — the first release where Bun Bun has a real voice.

## Highlights

- **Bun Bun's voice ships in the ISO.** Boots with the "THV" speaker of Piper's `en_US-l2arctic-medium` model: a real person reading English with a gentle Vietnamese accent, 100% local Piper TTS, no cloud, no microphone needed for speech output. Ships as `bunny-default.onnx` with a `VOICE-NOTE.txt` attribution file (dataset: L2-Arctic, CC BY-NC 4.0 — fine for personal use; re-check before commercial redistribution).
- **Multi-speaker support.** The Piper backend now takes a `--speaker` flag and settings expose `"speaker": N`, so any of the model's 24 voices can be selected; the self-trained custom voice stays a parked plan.
- **Advanced emotional system, phase 1.** Bun Bun reads game events (and mic prosody signals when a session explicitly opens the mic; mic stays off by default) into a live mood — valence, energy, curiosity, worry, pride — that decays over time and tunes her voice pacing and tone per mood (`--length_scale` / `--noise_scale`). New comfort lines included, including "You're not alone, you know."
- **78 tests green, 295 engine checks green** at build time.

## Known gaps (unchanged)

* The immutable/OSTree core is only partially realised; installs use Btrfs subvolumes.
* The installer is UEFI-only, whole-disk, unencrypted.
* Bun Bun is rule-based, not a neural model. No hot mic, no screen capture.
* Steam Deck LCD target is beta; OLED out of scope.

**Full Changelog**: https://github.com/yrg8fn10/bunny-os/compare/v0.2.0-beta.7-bazzite...v0.2.0-beta.8-bazzite
