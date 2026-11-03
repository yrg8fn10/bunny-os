# Audio routing layer (Deliverable 3)

Deliverable 2 stopped at playback ("the shell never opens the microphone").
This deliverable adds the two missing halves of the sound path and keeps the
house rule intact: **the microphone is off by default and never runs hot.**

## 1. What ships

| Piece | File | Role |
|---|---|---|
| Mic capture | `bunbun/bunbun/audio/mic.py` | Push-to-talk capture through PipeWire, gated three times |
| STT backend | `bunbun/bunbun/audio/mic.py` (`WhisperBackend`) | Local whisper.cpp when installed; otherwise silence |
| Audio router | `bunbun/bunbun/audio/router.py` | Duck the game while Bun Bun speaks; report the mic's muted state |
| Helpers | `bunbun/bunbun/audio/helpers.py` | Argument-list subprocesses only, never a shell |

## 2. The three gates (in order)

1. `mic_enabled` in settings. Default **False**. The agent never enables it on
   its own; only the owner does, in the control panel or `settings.json`.
2. An open listening window. Push-to-talk semantics: capture happens only
   between an explicit open and close (button press / panel consent). No window,
   no recording, even when gate 1 is open.
3. The PipeWire source itself. `wpctl get-volume @DEFAULT_AUDIO_SOURCE@`
   reports the hardware kill switch: if it says `[MUTED]`, or the state cannot
   be read at all, capture refuses. **Unknown is treated as unavailable, never
   as available.**

Captured clips are short (0.5-15 s), 16 kHz mono WAV files in the system temp
directory, fed only to the local STT backend. Nothing leaves the machine; the
text lands in the MAM engine as a player-speech event, same as game state.

## 3. Voice and routing

- Bun Bun speaks through the existing TTS pipeline (Piper preferred, espeak-ng
  fallback). The persona voice is bright, gentle, kid-like, slightly slow, high
  pitch, with a **soft East-Asian-accented English** delivery that stays cute
  and kid-friendly.
- `AudioRouter.duck()` lowers the default sink to 35% while she speaks and
  `unduck()` restores the player's own volume. Every call is best-effort: when
  `wpctl` is missing, nothing changes and the call reports failure, so a bare
  box behaves exactly like before.

## 4. Bun Bun in games

- **Multiplayer:** the co-op agent (`action/coop.py`) can hop into a session as
  an AI buddy. She is never added to a real friends list and always announces
  herself as an AI when joining; joining still needs the player's explicit yes.
  The player turns multiplayer participation on for a session; it is never
  automatic.
- **Single-player:** in games with no multiplayer at all (Subnautica, Below
  Zero, anything else the watcher sees), Bun Bun sits on the sidelines: she
  watches the state the watcher reports, cheers you on, and offers hints. She
  never takes the controls unless asked.

## 5. Settings keys (`ai.*`)

| Key | Default | Meaning |
|---|---|---|
| `mic_enabled` | `false` | master switch for capture |
| `mic_push_to_talk` | `true` | capture only inside an explicit window |
| `mic_stt` | `auto` | `auto` \| `whisper` \| `none` |
| `mic_device` | empty | PipeWire target; empty = default source |

Environment: `BUNBUN_MIC_ENABLED=1` for development.

## 6. Verify hooks

- `bunbun/tests/test_audio.py`: default-off, window gate, kill switch outranks
  everything, unknown-means-unavailable, duck restores, router refuses cleanly.
- Next steps (not in this commit): wiring `duck()`/`unduck()` around the TTS
  pipeline's speak calls, and a push-to-talk button mapping in the d-pad
  contract.
