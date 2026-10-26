"""bunbun command line client.

Talks to the local agent over HTTP.  No cloud, no API keys.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8422"


class ApiError(RuntimeError):
    pass


def request(base: str, method: str, path: str, body: dict | None = None,
            timeout: float = 10.0) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise ApiError(f"{exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise ApiError(
            f"cannot reach Bun Bun at {base} ({exc.reason}). "
            "Start it with: systemctl --user start bunny-bunbun"
        ) from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bunbun", description="Bun Bun CLI")
    parser.add_argument("--api", default=DEFAULT_BASE, help="agent base URL")
    parser.add_argument("--json", action="store_true", help="raw JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="agent, game, memory and co-op status")
    sub.add_parser("policy", help="list the safety rules")

    p_say = sub.add_parser("say", help="speak a line")
    p_say.add_argument("text")

    p_hint = sub.add_parser("hint", help="request a hint for the current game")
    p_hint.add_argument("--secret", action="store_true")

    p_ask = sub.add_parser("ask", help="ask Bun Bun something (keyword routing)")
    p_ask.add_argument("text")

    p_state = sub.add_parser("state", help="push a game state observation")
    p_state.add_argument("json", help="state object as JSON")

    p_join = sub.add_parser("coop", help="co-op invitation handling")
    p_join.add_argument("action", choices=["join", "leave", "status"])
    p_join.add_argument("--game", default="")
    p_join.add_argument("--friend", default="a friend")
    p_join.add_argument("--lobby", default="")
    p_join.add_argument("--confirm", action="store_true",
                        help="the player has agreed to join")

    p_mem = sub.add_parser("memory", help="inspect or erase local memory")
    p_mem.add_argument("action", choices=["show", "purge"])

    args = parser.parse_args(argv)

    try:
        if args.command == "status":
            data = request(args.api, "GET", "/v1/status")
            if args.json:
                print(json.dumps(data, indent=2))
                return 0
            agent = data["agent"]
            state = data["engine"]["state"]
            print(f"Bun Bun {agent['version']}  voice={agent['voice_backend']}  "
                  f"uptime={agent['uptime_seconds']}s")
            print(f"  game   : {state.get('title') or '(none)'}")
            print(f"  hints  : {data['engine']['hints']['shown']} shown, "
                  f"level={data['engine']['settings']['hint_level']}")
            print(f"  co-op  : {'on' if data['engine']['settings']['coop_opt_in'] else 'off'} "
                  f"({data['engine']['settings']['coop_mode']})")
            memory = agent.get("memory", {})
            if memory.get("enabled"):
                print(f"  memory : {memory.get('events', 0)} events, local only")
            return 0

        if args.command == "policy":
            data = request(args.api, "GET", "/v1/policy")
            for rule in data["rules"]:
                print(f"{rule['rule']:24s} {rule['effect']}")
            return 0

        if args.command == "say":
            print(json.dumps(request(args.api, "POST", "/v1/say", {"text": args.text}), indent=2))
            return 0

        if args.command == "hint":
            data = request(args.api, "POST", "/v1/hint", {"secret": args.secret})
            print(json.dumps(data, indent=2))
            return 0

        if args.command == "ask":
            text = args.text.lower()
            if any(word in text for word in ("hint", "stuck", "help", "secret")):
                return main(["--api", args.api, "hint", *(["--secret"] if "secret" in text else [])])
            if "status" in text:
                return main(["--api", args.api, "status"])
            reply = request(args.api, "POST", "/v1/say", {"text": args.text})
            print(json.dumps(reply, indent=2))
            return 0

        if args.command == "state":
            try:
                payload = json.loads(args.json)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"invalid JSON: {exc}") from None
            print(json.dumps(request(args.api, "POST", "/v1/state", payload), indent=2))
            return 0

        if args.command == "coop":
            if args.action == "status":
                print(json.dumps(request(args.api, "GET", "/v1/status")["coop"], indent=2))
                return 0
            if args.action == "leave":
                print(json.dumps(request(args.api, "POST", "/v1/coop/leave", {}), indent=2))
                return 0
            payload = {
                "invite": {"game_id": args.game, "friend": args.friend,
                           "lobby_id": args.lobby, "platform": "steam"},
                "confirmed": args.confirm,
                "dry_run": False,
            }
            print(json.dumps(request(args.api, "POST", "/v1/coop/join", payload), indent=2))
            return 0

        if args.command == "memory":
            if args.action == "purge":
                print(json.dumps(request(args.api, "POST", "/v1/memory/purge", {}), indent=2))
            else:
                print(json.dumps(request(args.api, "GET", "/v1/status")["engine"]["memory"],
                                 indent=2))
            return 0

        parser.error("unknown command")
        return 2
    except ApiError as exc:
        print(f"bunbun: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
