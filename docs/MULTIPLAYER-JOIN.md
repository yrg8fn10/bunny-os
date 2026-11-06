# MULTIPLAYER JOIN (EXPERIMENTAL)

Status: **experimental, ships in the next pre-release cut (beta 9 pre2 era),
untested in game yet.** Real testing needs hardware: a second machine on the
same LAN with Subnautica + Nitrox installed.

## What it is

Bun Bun joins your multiplayer save as a real player. Phase one is the join
system:

- `bunbun-join doctor` checks the local pieces and prints a readiness report
  (game found in the Steam library, server host set, launch template set).
- `bunbun-join join` launches the second game client on the machine that owns
  the game (Ava's mini PC in the first demo), auto-configured to connect to
  the LAN server as **BunBun**.
- Session farewell: when the player says "alright, I'm done for today" (or
  "time to quit", "calling it"), Bun Bun gives one short wag-off goodbye
  before anything closes. `bunbun-join farewell` prints one for wiring tests.

## LAN only

The server must be on the player's own local network. The config file
(`~/.config/bunbun-multiplayer.json`, see `bunbun-join config`) never leaves
the machine; there is no cloud, no API key, no telemetry anywhere in this
path.

## First real join (honest steps)

The join command never invents a game's command-line flags. The first time:

1. Run the Nitrox server on the host machine.
2. Join it once by hand from the second machine.
3. Put the working launch command into `launch_args_template` in the config,
   with `{host} {port} {player} {password}` placeholders where the server
   address and player name go.
4. Run `bunbun-join join --dry-run` to check the final command, then
   `bunbun-join join`.

## Roadmap

- Phase 1 (this release): join + presence (BunBun appears in the player list,
  stays in the world), farewell line on session end.
- Phase 2 (needs in-game testing with Ava): active behavior, swimming along,
  reacting to the game, the commentary voice layer.
