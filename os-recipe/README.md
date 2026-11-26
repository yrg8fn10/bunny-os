# Bunny OS — our own OS recipe (off Bazzite)

Ava's call, Nov 26, 2026: Bunny OS becomes fully ours. No Bazzite anywhere:
our own image recipe, our own package list, our own builder, our own
branding, our own name. The shared kernel, GPU drivers and Proton stay —
that is infrastructure every OS rides on (SteamOS is Arch underneath).
Ownership lives in everything people see and touch, and all of it is ours.

Everything we already built carries over: taskbar, updater channel,
wallpapers, Game Mode theme, Bun Bun's voice, the whole Bun Bun structure.

Locked requirements (Nov 26):
- Steam Deck (both models) first, then other hardware
- AMD or RTX GPU required; "continue anyway, graphics may differ" path
- cute gamer look; NO time-out phase; fully local, no API keys

Phases: recipe -> first own-base ISO -> identity pass -> own channel ->
one-time reflash migration (Ava runs it), then in-place updates again.
