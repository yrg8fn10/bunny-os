"""Co-op companion.

Reality check
-------------
Joining a friend's lobby is not a generic capability.  It depends on the game
and the store:

  * Steam games can be joined through ``steam://joinlobby/<appid>/<lobby>/...``
    when the game advertises a lobby id.  We support that.
  * Epic games have no equivalent deep link.  Heroic can launch the title, and
    an in-game invite must be accepted by the player (or, in allowlisted games
    only and with explicit consent, by the input agent).
  * Anti-cheat protected and competitive titles are refused outright.

This module therefore *plans and asks*, and only performs a join when the
player says yes.  It never disguises itself, never spoofs a human player, and
never touches memory or network traffic of the game.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..bus import EventBus

LOG = logging.getLogger("bunbun.coop")
ALLOWLIST = Path("/etc/bunny/coop-allowlist.txt")
MAX_SESSION_MINUTES = 120


@dataclass
class JoinInvite:
    friend: str
    game_id: str
    title: str = ""
    platform: str = "steam"
    app_id: str = ""
    lobby_id: str = ""
    anticheat: bool = False
    competitive: bool = False
    allowlisted: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JoinInvite":
        game_id = str(data.get("game_id", ""))
        app_id = str(data.get("app_id") or (game_id.split(":", 1)[1] if ":" in game_id else ""))
        return cls(
            friend=str(data.get("friend", "a friend")),
            game_id=game_id,
            title=str(data.get("title", "")),
            platform=str(data.get("platform", "steam")),
            app_id=app_id,
            lobby_id=str(data.get("lobby_id", "")),
            anticheat=bool(data.get("anticheat", False)),
            competitive=bool(data.get("competitive", False)),
            allowlisted=bool(data.get("allowlisted", False)),
        )


@dataclass
class JoinDecision:
    allowed: bool
    reason: str
    requires_consent: bool = True
    steps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "requires_consent": self.requires_consent,
            "steps": self.steps,
        }


def read_allowlist(path: Path = ALLOWLIST) -> set[str]:
    try:
        lines = path.read_text("utf-8").splitlines()
    except OSError:
        return set()
    return {ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")}


class CoopAgent:
    def __init__(self, bus: EventBus, allowlist_path: Path = ALLOWLIST,
                 launcher: str = "/usr/local/bin/bunny-launcher",
                 opener: str = "xdg-open"):
        self.bus = bus
        self.allowlist_path = allowlist_path
        self.launcher = launcher
        self.opener = opener
        self.active_invite: JoinInvite | None = None
        self.joined_at: float | None = None
        self._audit: list[dict[str, Any]] = []

    # -- capability check --------------------------------------------------
    def allowlisted(self, invite: JoinInvite) -> bool:
        allowed = read_allowlist(self.allowlist_path)
        if not allowed:
            return invite.allowlisted
        names = {invite.game_id, invite.app_id, invite.title.lower()}
        return any(name and name in allowed for name in names)

    def evaluate(self, invite: JoinInvite, settings: dict[str, Any]) -> JoinDecision:
        ai = settings.get("ai", {}) if isinstance(settings.get("ai"), dict) else {}
        steps = self.build_plan(invite)

        if not ai.get("coop_opt_in", False):
            return JoinDecision(False, "multiplayer assist is off", True, steps)
        if ai.get("coop_mode") == "off":
            return JoinDecision(False, "co-op mode is off", False, steps)
        if invite.anticheat:
            return JoinDecision(False, "anti-cheat protected title", False, steps)
        if invite.competitive:
            return JoinDecision(False, "competitive mode is out of scope", False, steps)
        if not self.allowlisted(invite):
            return JoinDecision(
                False,
                "title is not in /etc/bunny/coop-allowlist.txt",
                False,
                steps,
            )
        if invite.platform != "steam" and not invite.lobby_id:
            return JoinDecision(
                True,
                "launch-only join: the player must accept the in-game invite",
                True,
                steps,
            )
        return JoinDecision(True, "join is possible", True, steps)

    def build_plan(self, invite: JoinInvite) -> list[str]:
        if invite.platform == "steam" and invite.lobby_id and invite.app_id:
            return [
                f"Open the Steam lobby deep link for {invite.title or invite.app_id}",
                "Wait for the game to reach the main menu",
                "Confirm arrival with the player",
            ]
        return [
            f"Launch {invite.title or invite.game_id} through bunny-launcher",
            "Ask the player to accept the in-game invitation",
            "Only offer input assistance if the player explicitly enables it",
        ]

    # -- actions -----------------------------------------------------------
    def join(self, invite: JoinInvite, settings: dict[str, Any],
             player_confirmed: bool = False, dry_run: bool = False) -> dict[str, Any]:
        decision = self.evaluate(invite, settings)
        if not decision.allowed:
            self._record(invite, "refused", decision.reason)
            self.bus.publish("coop.refused", {"game_id": invite.game_id,
                                              "reason": decision.reason})
            return decision.as_dict()
        if not player_confirmed:
            self._record(invite, "consent-requested", decision.reason)
            self.bus.publish("coop.consent_request", {
                "game_id": invite.game_id, "friend": invite.friend,
                "title": invite.title, "steps": decision.steps,
            })
            return {**decision.as_dict(), "status": "awaiting_player_consent"}

        if dry_run:
            return {**decision.as_dict(), "status": "dry-run", "steps": decision.steps}

        argv = self._join_argv(invite)
        if argv is None:
            return {**decision.as_dict(), "status": "manual",
                    "steps": decision.steps,
                    "message": "no deep link available; follow the steps manually"}

        try:
            subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)  # noqa: S603 - allowlisted argv
        except OSError as exc:
            LOG.error("join failed: %s", exc)
            self._record(invite, "failed", str(exc))
            return {"status": "error", "error": str(exc)}

        self.active_invite = invite
        self.joined_at = time.time()
        self._record(invite, "joined", "player consented")
        self.bus.publish("coop.joined", {
            "game_id": invite.game_id, "friend": invite.friend,
            "title": invite.title, "platform": invite.platform,
            "ai_label": "Bun Bun (AI buddy)",
        })
        return {**decision.as_dict(), "status": "joined",
                "steps": decision.steps, "argv": argv}

    def leave(self, reason: str = "player request") -> dict[str, Any]:
        if not self.active_invite:
            return {"status": "not_joined"}
        invite = self.active_invite
        self.active_invite = None
        self.joined_at = None
        self._record(invite, "left", reason)
        self.bus.publish("coop.left", {"game_id": invite.game_id, "reason": reason})
        return {"status": "left", "game_id": invite.game_id}

    def status(self) -> dict[str, Any]:
        minutes = None
        if self.joined_at:
            minutes = round((time.time() - self.joined_at) / 60, 1)
        return {
            "allowlist": sorted(read_allowlist(self.allowlist_path)),
            "active": self.active_invite.game_id if self.active_invite else None,
            "minutes": minutes,
            "session_cap_minutes": MAX_SESSION_MINUTES,
            "warn_over_cap": bool(minutes and minutes > MAX_SESSION_MINUTES),
            "audit": self._audit[-10:],
        }

    # -- helpers -----------------------------------------------------------
    def _join_argv(self, invite: JoinInvite) -> list[str] | None:
        if invite.platform == "steam" and invite.lobby_id and invite.app_id:
            lobby = urllib.parse.quote(invite.lobby_id, safe="")
            app = urllib.parse.quote(invite.app_id, safe="")
            uri = f"steam://joinlobby/{app}/{lobby}"
            if shutil.which(self.opener):
                return [self.opener, uri]
        if shutil.which(self.launcher):
            # bunny-launcher consumes --game-id itself; everything after `--`
            # would be forwarded to the store client verbatim.
            return [self.launcher, invite.platform, "--game-id", invite.game_id]
        return None

    def _record(self, invite: JoinInvite, action: str, note: str) -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "game_id": invite.game_id,
            "friend": invite.friend,
            "action": action,
            "note": note,
        }
        self._audit.append(entry)
        LOG.info("coop %s: %s (%s)", action, invite.game_id, note)
