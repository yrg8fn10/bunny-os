#!/usr/bin/env python3
"""bunny-sessiond — session, settings and power broker for Bunny OS.

Why a daemon?
    The Control Panel runs as the desktop user.  Switching between Gaming Mode
    (gamescope + panel) and Desktop Mode (Plasma) means rewriting SDDM's
    autologin session and restarting the display manager, which is a root
    operation.  Rather than handing the panel a passwordless sudo rule, all
    privileged actions go through this small, auditable broker.

Security model
    * AF_UNIX socket, mode 0660, owned root:bunny.
    * SO_PEERCRED is checked on every connection; only uid 0 and members of
      group ``bunny`` may talk to us.
    * Commands are split into read-only and state-changing.  State-changing
      commands are appended to an audit log.
    * Settings are validated against an explicit schema; unknown keys are
      rejected.  Opt-in actions (multiplayer co-op, screen vision, overclock)
      additionally require a confirmation token.
    * No command executes arbitrary user-supplied commands.  ``launch`` is an
      allowlist, not a shell.

Protocol
    Newline-delimited JSON over the socket:
        -> {"id": 1, "cmd": "status", "args": {}}
        <- {"id": 1, "ok": true, "result": {...}}
"""
from __future__ import annotations

import argparse
import grp
import json
import logging
import os
import pwd
import re
import shutil
import socket
import socketserver
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

VERSION = "0.1.0"
MAX_REQUEST = 64 * 1024
SOCKET_TIMEOUT = 10.0

LOG = logging.getLogger("bunny-sessiond")


# ---------------------------------------------------------------------------
# Paths — overridable for tests
# ---------------------------------------------------------------------------
@dataclass
class Paths:
    settings: Path = Path("/etc/bunny/settings.json")
    session_conf: Path = Path("/etc/bunny/session.conf")
    sddm_dropin: Path = Path("/etc/sddm.conf.d/20-bunny-session.conf")
    state: Path = Path("/var/lib/bunny/state.json")
    socket: Path = Path("/run/bunny/sessiond.sock")
    audit: Path = Path("/var/log/bunny/sessiond-audit.log")
    runtime: Path = Path("/run/bunny")
    agent_url: str = "http://127.0.0.1:8422/health"


DEFAULT_SETTINGS: dict[str, Any] = {
    "session": {
        "default_mode": "gaming",
        "autologin": True,
        "desktop_session": "bunny-desktop",
        "gaming_session": "bunny-gaming",
    },
    "performance": {
        "profile": "balanced",
        "fps_cap": 60,
        "tdp_watts": 15,
        "gpu_driver": "auto",
        "allow_overclock": False,
        "mangohud": False,
    },
    "audio": {
        "sink": "auto",
        "mic": "auto",
        "latency_ms": 40,
        "duck_media_for_voice": True,
        "bunbun_volume": 0.85,
    },
    "display": {"resolution": "auto", "refresh_hz": 60, "hdr": False, "scaling": "auto"},
    "ai": {
        "enabled": True,
        "voice_enabled": True,
        "voice": "bunny-default",
        "hint_level": "gentle",
        "commentary": True,
        "coop_opt_in": False,
        "coop_mode": "invite-only",
        "screen_vision": False,
        "memory_enabled": True,
        "kid_safe": True,
    },
    "updates": {"channel": "stable", "auto_check": True},
    "privacy": {"local_only": True, "telemetry": False},
}


# ---------------------------------------------------------------------------
# Settings schema
# ---------------------------------------------------------------------------
class Invalid(ValueError):
    pass


@dataclass(frozen=True)
class Enum:
    values: tuple[str, ...]

    def __call__(self, value: Any) -> Any:
        if value not in self.values:
            raise Invalid(f"expected one of {self.values}, got {value!r}")
        return value


@dataclass(frozen=True)
class IntRange:
    lo: int
    hi: int

    def __call__(self, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int):
            raise Invalid(f"expected integer, got {type(value).__name__}")
        if not self.lo <= value <= self.hi:
            raise Invalid(f"expected {self.lo}..{self.hi}, got {value}")
        return value


@dataclass(frozen=True)
class FloatRange:
    lo: float
    hi: float

    def __call__(self, value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Invalid(f"expected number, got {type(value).__name__}")
        if not self.lo <= float(value) <= self.hi:
            raise Invalid(f"expected {self.lo}..{self.hi}, got {value}")
        return round(float(value), 3)


@dataclass(frozen=True)
class Bool:
    def __call__(self, value: Any) -> Any:
        if not isinstance(value, bool):
            raise Invalid(f"expected boolean, got {type(value).__name__}")
        return value


@dataclass(frozen=True)
class StrSet:
    """Free-form string constrained to an allowlist of known identifiers."""

    values: tuple[str, ...]
    allow_auto: bool = True

    def __call__(self, value: Any) -> Any:
        if not isinstance(value, str):
            raise Invalid("expected string")
        if self.allow_auto and value == "auto":
            return value
        if value not in self.values:
            raise Invalid(f"unknown value {value!r}")
        return value


SPEC: dict[str, Callable[[Any], Any]] = {
    "session.default_mode": Enum(("gaming", "desktop")),
    "session.autologin": Bool(),
    "performance.profile": Enum(("quiet", "balanced", "performance", "custom")),
    "performance.fps_cap": IntRange(30, 240),
    "performance.tdp_watts": IntRange(4, 60),
    "performance.gpu_driver": StrSet(("mesa", "nvidia", "amdgpu-pro")),
    "performance.allow_overclock": Bool(),
    "performance.mangohud": Bool(),
    "audio.sink": StrSet(("hdmi", "speakers", "headphones", "usb", "bluetooth")),
    "audio.mic": StrSet(("internal", "headset", "usb", "none")),
    "audio.latency_ms": IntRange(10, 250),
    "audio.duck_media_for_voice": Bool(),
    "audio.bunbun_volume": FloatRange(0.0, 1.0),
    "display.resolution": StrSet(("1280x800", "1920x1080", "2560x1600", "3840x2160")),
    "display.refresh_hz": IntRange(30, 165),
    "display.hdr": Bool(),
    "display.scaling": Enum(("auto", "100%", "125%", "150%", "200%")),
    "ai.enabled": Bool(),
    "ai.voice_enabled": Bool(),
    "ai.voice": StrSet(("bunny-default", "bunny-soft", "bunny-bright")),
    "ai.hint_level": Enum(("off", "gentle", "helpful", "spoilery")),
    "ai.commentary": Bool(),
    "ai.coop_opt_in": Bool(),
    "ai.coop_mode": Enum(("invite-only", "friends", "off")),
    "ai.screen_vision": Bool(),
    "ai.memory_enabled": Bool(),
    "ai.kid_safe": Bool(),
    "updates.channel": Enum(("stable", "beta", "dev")),
    "updates.auto_check": Bool(),
    "privacy.local_only": Bool(),
    "privacy.telemetry": Bool(),
}

# Turning these on has social/privacy consequences: require explicit consent.
CONSENT_REQUIRED: dict[str, str] = {
    "ai.coop_opt_in": "I understand Bun Bun may join multiplayer lobbies",
    "ai.screen_vision": "screen vision is a reserved feature and does nothing in v0.1",
    "performance.allow_overclock": "I understand overclocking can damage hardware",
}


def flatten(tree: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in tree.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten(value, f"{dotted}."))
        else:
            flat[dotted] = value
    return flat


def unflatten(flat: dict[str, Any]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for dotted, value in flat.items():
        node = tree
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return tree


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class SettingsStore:
    def __init__(self, path: Path, defaults: dict[str, Any] | None = None):
        self.path = path
        self.defaults = defaults or DEFAULT_SETTINGS
        self._lock = threading.RLock()
        self._cache: dict[str, Any] | None = None

    # -- io ----------------------------------------------------------------
    def load(self) -> dict[str, Any]:
        with self._lock:
            if self._cache is not None:
                return self._cache
            merged = deep_merge(self.defaults, {})
            if self.path.is_file():
                try:
                    on_disk = json.loads(self.path.read_text("utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    LOG.warning("settings unreadable (%s); using defaults", exc)
                    on_disk = {}
                if isinstance(on_disk, dict):
                    merged = deep_merge(merged, on_disk)
            self._cache = merged
            return merged

    def save(self, tree: dict[str, Any]) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".settings.")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(tree, fh, indent=2, sort_keys=False)
                    fh.write("\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, self.path)
                os.chmod(self.path, 0o644)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            self._cache = tree

    # -- mutation ----------------------------------------------------------
    def apply(self, patch: dict[str, Any], confirm: str | None = None) -> dict[str, Any]:
        if not isinstance(patch, dict) or not patch:
            raise Invalid("patch must be a non-empty object")
        flat = flatten(patch)
        changed: dict[str, Any] = {}
        for key, raw in flat.items():
            validator = SPEC.get(key)
            if validator is None:
                raise Invalid(f"unknown setting: {key}")
            try:
                value = validator(raw)
            except Invalid as exc:
                raise Invalid(f"{key}: {exc}") from None
            warning = CONSENT_REQUIRED.get(key)
            if warning and value is True and not _consent_ok(confirm, warning):
                raise Invalid(f"{key} requires confirmation: {warning}")
            changed[key] = value

        with self._lock:
            current = flatten(self.load())
            for key, value in changed.items():
                if key not in current or current[key] != value:
                    current[key] = value
            tree = unflatten(current)
            self.save(tree)
        return tree

    def check_invariants(self) -> list[str]:
        """Fix obvious contradictions, return human-readable repairs."""
        problems: list[str] = []
        tree = self.load()
        if tree["ai"]["coop_mode"] == "off" and tree["ai"]["coop_opt_in"]:
            tree["ai"]["coop_opt_in"] = False
            problems.append("coop_opt_in disabled because coop_mode=off")
        if not tree["ai"]["enabled"] and tree["ai"]["voice_enabled"]:
            tree["ai"]["voice_enabled"] = False
            problems.append("voice_enabled disabled because ai.enabled=false")
        if tree["privacy"]["local_only"] and tree["privacy"]["telemetry"]:
            tree["privacy"]["telemetry"] = False
            problems.append("telemetry disabled because local_only=true")
        if problems:
            self.save(tree)
        return problems


def _consent_ok(confirm: Any, warning: str) -> bool:
    if not isinstance(confirm, str):
        return False
    return confirm.strip().upper() in {"I AGREE", "CONFIRM", "YES"}


# ---------------------------------------------------------------------------
# Session / mode control
# ---------------------------------------------------------------------------
VALID_MODES = ("gaming", "desktop")


class ModeController:
    def __init__(self, paths: Paths, settings: SettingsStore, dry_run: bool = False):
        self.paths = paths
        self.settings = settings
        self.dry_run = dry_run
        # switch() calls set_default() while holding the lock, so it must be
        # re-entrant.
        self._lock = threading.RLock()

    # -- helpers -----------------------------------------------------------
    def _read_session_conf(self) -> dict[str, str]:
        conf: dict[str, str] = {}
        if not self.paths.session_conf.is_file():
            return conf
        for line in self.paths.session_conf.read_text("utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            conf[key.strip()] = value.strip().strip('"')
        return conf

    def _session_name(self, mode: str) -> str:
        conf = self._read_session_conf()
        tree = self.settings.load()["session"]
        if mode == "gaming":
            return tree.get("gaming_session") or conf.get("BUNNY_GAMING_SESSION", "bunny-gaming")
        return tree.get("desktop_session") or conf.get("BUNNY_DESKTOP_SESSION", "bunny-desktop")

    def current_mode(self) -> str:
        default = self.settings.load()["session"]["default_mode"]
        try:
            data = json.loads(self.paths.state.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return default
        # state.json records the mode that was switched to during *this* boot.
        # After a reboot the display manager starts session.default_mode, so a
        # stale record from the previous boot must not win.
        if data.get("boot_id") != _boot_id():
            return default
        mode = data.get("mode")
        return mode if mode in VALID_MODES else default

    def _write_state(self, mode: str, session: str) -> None:
        payload = {
            "mode": mode,
            "session": session,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "boot_id": _boot_id(),
        }
        if self.dry_run:
            LOG.info("[dry-run] would write state %s", payload)
            return
        self.paths.state.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.paths.state.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", "utf-8")
        os.replace(tmp, self.paths.state)

    def _write_sddm_dropin(self, session: str, autologin: bool = True) -> None:
        user = self._read_session_conf().get("BUNNY_USER", "bunny") if autologin else ""
        content = (
            "# Generated by bunny-sessiond. Do not edit; use `bunnyctl set-mode`\n"
            "# or the Control Panel. An empty User= disables autologin.\n"
            f"[Autologin]\nUser={user}\nSession={session}\nRelogin=false\n"
        )
        if self.dry_run:
            LOG.info("[dry-run] would write %s with Session=%s autologin=%s",
                     self.paths.sddm_dropin, session, autologin)
            return
        self.paths.sddm_dropin.parent.mkdir(parents=True, exist_ok=True)
        self.paths.sddm_dropin.write_text(content, "utf-8")
        os.chmod(self.paths.sddm_dropin, 0o644)

    @staticmethod
    def _display_manager_active() -> bool:
        if not shutil.which("systemctl"):
            return False
        try:
            return subprocess.run(
                ["systemctl", "is-active", "--quiet", "sddm.service"],
                check=False, timeout=5,
            ).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _systemctl(self, *args: str) -> subprocess.CompletedProcess[str]:
        if self.dry_run:
            LOG.info("[dry-run] systemctl %s", " ".join(args))
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.run(["systemctl", *args], check=False, timeout=30,
                              capture_output=True, text=True)

    # -- public API --------------------------------------------------------
    def refresh_sddm(self) -> dict[str, Any]:
        """Rewrite the autologin drop-in from the persisted session settings."""
        with self._lock:
            session_settings = self.settings.load()["session"]
            mode = session_settings["default_mode"]
            session = self._session_name(mode)
            autologin = bool(session_settings["autologin"])
            self._write_sddm_dropin(session, autologin)
            return {"mode": mode, "session": session, "autologin": autologin}

    def set_default(self, mode: str) -> dict[str, Any]:
        """Persist the preferred mode and rewrite SDDM. Does not restart it.

        Deliberately does not write state.json: the running session has not
        changed, and recording it as active would make a later switch-mode a
        no-op.
        """
        if mode not in VALID_MODES:
            raise Invalid(f"mode must be one of {VALID_MODES}")
        with self._lock:
            self.settings.apply({"session": {"default_mode": mode}})
            session = self._session_name(mode)
            autologin = bool(self.settings.load()["session"]["autologin"])
            self._write_sddm_dropin(session, autologin)
            return {"mode": mode, "session": session, "autologin": autologin,
                    "applies": "next login"}

    def switch(self, mode: str) -> dict[str, Any]:
        if mode not in VALID_MODES:
            raise Invalid(f"mode must be one of {VALID_MODES}")
        with self._lock:
            if mode == self.current_mode() and not self.dry_run:
                return {"mode": mode, "changed": False, "reason": "already active"}

            result = self.set_default(mode)
            restarted = False
            if self._display_manager_active():
                self._systemctl("restart", "sddm.service")
                restarted = True
            else:
                LOG.warning("sddm not active; new mode will apply at next graphical login")
            self._write_state(mode, result["session"])

            return {**result, "changed": True, "restarted_display_manager": restarted}

    def status(self) -> dict[str, Any]:
        mode = self.current_mode()
        return {
            "version": VERSION,
            "mode": mode,
            "mode_session": self._session_name(mode),
            "default_mode": self.settings.load()["session"]["default_mode"],
            "live": Path("/run/archiso").exists(),
            "display_manager_active": self._display_manager_active(),
            "sessions": {
                "gaming": self._session_name("gaming"),
                "desktop": self._session_name("desktop"),
            },
            "settings": self.settings.load(),
            "agent": self._agent_health(),
        }

    def _agent_health(self) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(self.paths.agent_url, timeout=1.5) as resp:
                return json.loads(resp.read(8192).decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
            return {"status": "offline"}


def _boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return "unknown"


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------
def user_in_group(uid: int, group: str) -> bool:
    try:
        entry = pwd.getpwuid(uid)
        gid = grp.getgrnam(group).gr_gid
    except KeyError:
        return False
    if entry.pw_gid == gid:
        return True
    return entry.pw_name in grp.getgrgid(gid).gr_mem


def is_authorized(uid: int) -> bool:
    return uid == 0 or user_in_group(uid, "bunny") or user_in_group(uid, "wheel")


# ---------------------------------------------------------------------------
# Command layer
# ---------------------------------------------------------------------------
class BunnyService:
    READ_COMMANDS = {"ping", "status", "get-settings", "library", "help"}
    ADMIN_COMMANDS = {
        "set-settings", "set-mode", "switch-mode", "launch", "power",
        "agent", "input-agent", "installer", "update", "audit-tail",
    }
    PLATFORMS = {
        "steam": ["steam"],
        "epic": ["heroic"],
        "heroic": ["heroic"],
        "gog": ["gog"],
        "lutris": ["lutris"],
        "retroarch": ["retroarch"],
        "desktop": ["desktop"],
    }
    LIBRARY_SCANNER = "/usr/local/bin/bunny-platform-scan"
    LIBRARY_TTL = 120.0

    def __init__(self, paths: Paths, dry_run: bool = False):
        self.paths = paths
        self.dry_run = dry_run
        self.settings = SettingsStore(paths.settings)
        self.modes = ModeController(paths, self.settings, dry_run=dry_run)
        self._lock = threading.Lock()
        self._library_cache: tuple[float, dict[str, Any]] | None = None

    # -- entrypoint --------------------------------------------------------
    def dispatch(self, request: dict[str, Any], peer_uid: int) -> dict[str, Any]:
        req_id = request.get("id")
        cmd = request.get("cmd")
        args = request.get("args") or {}
        if not isinstance(cmd, str) or not isinstance(args, dict):
            raise Invalid("request needs string 'cmd' and object 'args'")
        if cmd not in self.READ_COMMANDS | self.ADMIN_COMMANDS:
            raise Invalid(f"unknown command: {cmd}")
        if cmd in self.ADMIN_COMMANDS and not is_authorized(peer_uid):
            raise PermissionError(f"uid {peer_uid} is not permitted to run {cmd}")

        handler = getattr(self, "cmd_" + cmd.replace("-", "_"))
        if cmd in self.ADMIN_COMMANDS:
            self._audit(peer_uid, cmd, args)
        result = handler(args)
        return {"id": req_id, "ok": True, "result": result}

    def _audit(self, uid: int, cmd: str, args: dict[str, Any]) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "uid": uid,
            "cmd": cmd,
            "args": args,
        }
        line = json.dumps(record, separators=(",", ":")) + "\n"
        try:
            self.paths.audit.parent.mkdir(parents=True, exist_ok=True)
            with open(self.paths.audit, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:
            LOG.warning("audit log unavailable: %s", exc)
        LOG.info("audit %s", line.strip())

    # -- read ---------------------------------------------------------------
    def cmd_ping(self, _args: dict[str, Any]) -> dict[str, Any]:
        return {"pong": True, "version": VERSION}

    def cmd_status(self, _args: dict[str, Any]) -> dict[str, Any]:
        return self.modes.status()

    def cmd_get_settings(self, _args: dict[str, Any]) -> dict[str, Any]:
        return self.settings.load()

    def cmd_library(self, args: dict[str, Any]) -> dict[str, Any]:
        """Return the cached game library, scanning on demand.

        The scan runs as the desktop user: manifests live in that user's home
        and Flatpak exports, and a root-owned cache would leak paths between
        accounts.  Results are cached for two minutes so opening the panel does
        not walk every Steam library on every key press.
        """
        force = bool(args.get("refresh", False))
        now = time.monotonic()
        with self._lock:
            cached = self._library_cache
            if cached and not force and now - cached[0] < self.LIBRARY_TTL:
                return cached[1]

        result = self._scan_library()
        with self._lock:
            self._library_cache = (time.monotonic(), result)
        return result

    def _scan_library(self) -> dict[str, Any]:
        empty: dict[str, Any] = {
            "games": [], "platforms": [], "errors": [],
            "scanned_at": None, "source": "unavailable",
        }
        if self.dry_run:
            return {**empty, "note": "dry-run: library scan disabled"}
        if not Path(self.LIBRARY_SCANNER).exists():
            return {**empty, "error": f"{self.LIBRARY_SCANNER} is not installed"}

        name, env = self._user_env()
        argv = [self.LIBRARY_SCANNER, "--json"]
        if os.geteuid() == 0 and name != "root" and shutil.which("runuser"):
            argv = ["runuser", "-u", name, "--", *argv]
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                argv, env=env, check=False, timeout=60,
                capture_output=True, text=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {**empty, "error": f"scan failed: {exc}"}
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "scanner failed").strip()
            return {**empty, "error": detail[-500:]}
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {**empty, "error": "scanner returned invalid JSON"}
        if not isinstance(parsed, dict):
            return {**empty, "error": "scanner returned an unexpected payload"}
        parsed.setdefault("games", [])
        parsed.setdefault("platforms", [])
        parsed.setdefault("errors", [])
        parsed["source"] = "live"
        parsed.setdefault("scanned_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        return parsed

    def cmd_help(self, _args: dict[str, Any]) -> dict[str, Any]:
        return {
            "read": sorted(self.READ_COMMANDS),
            "admin": sorted(self.ADMIN_COMMANDS),
            "platforms": sorted(self.PLATFORMS),
        }

    # -- admin --------------------------------------------------------------
    def cmd_set_settings(self, args: dict[str, Any]) -> dict[str, Any]:
        patch = args.get("patch")
        confirm = args.get("confirm")
        if not isinstance(patch, dict):
            raise Invalid("args.patch must be an object")
        self.settings.apply(patch, confirm=confirm if isinstance(confirm, str) else None)
        repairs = self.settings.check_invariants()
        # Reply with the post-repair tree so the panel never renders a value the
        # invariant pass has just reverted.
        tree = self.settings.load()
        session_touched = any(key.startswith("session.") for key in flatten(patch))
        if session_touched:
            # Autologin and default mode live in the SDDM drop-in, not only in
            # settings.json; keep the two in sync without restarting the DM.
            self.modes.refresh_sddm()
        return {"settings": tree, "repairs": repairs}

    def cmd_set_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.modes.set_default(str(args.get("mode", "")))

    def cmd_switch_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.modes.switch(str(args.get("mode", "")))

    def cmd_launch(self, args: dict[str, Any]) -> dict[str, Any]:
        platform = str(args.get("platform", ""))
        if platform not in self.PLATFORMS:
            raise Invalid(f"unknown platform {platform!r}")
        if not is_live_or_installed(platform):
            raise Invalid(f"{platform} is not installed on this system")
        game_id = args.get("game_id") or ""
        if game_id and (not isinstance(game_id, str)
                        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 :._-]{0,127}", game_id)):
            raise Invalid("game_id must start with a letter or digit and be at most 128 safe characters")
        argv = ["/usr/local/bin/bunny-launcher", *self.PLATFORMS[platform]]
        if game_id:
            # A launcher option, not a trailing extra: anything after `--` is
            # forwarded verbatim to the store client.
            argv += ["--game-id", game_id]
        if self.dry_run:
            LOG.info("[dry-run] launch %s", argv)
            return {"launched": False, "dry_run": True, "argv": argv}
        proc = self._as_user(argv)
        return {"launched": True, "pid": proc.pid, "platform": platform}

    def cmd_agent(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action", "status"))
        if action not in {"start", "stop", "restart", "status"}:
            raise Invalid("action must be start|stop|restart|status")
        if action == "status":
            return self.modes._agent_health()
        if self.dry_run:
            return {"dry_run": True, "action": action}
        self._user_systemctl(action, "bunny-bunbun.service")
        return {"ok": True, "action": action}

    def cmd_input_agent(self, args: dict[str, Any]) -> dict[str, Any]:
        """Enable/disable the uinput helper. Requires explicit consent."""
        enable = bool(args.get("enable", False))
        if enable and not _consent_ok(args.get("confirm"), "input"):
            raise Invalid(
                "enabling the input agent lets Bun Bun press buttons. "
                "Pass confirm='I AGREE' after the user has consented."
            )
        token = Path("/etc/bunny/allow-input-agent")
        if self.dry_run:
            return {"dry_run": True, "enable": enable}
        if enable:
            target = self._active_user()
            token.write_text(
                "Enabled by bunnyctl. Bun Bun may inject input only into allowlisted games.\n"
                f"user={target}\nat={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n",
                "utf-8",
            )
            os.chmod(token, 0o600)
            self._systemctl("unmask", "bunny-input-agent.service")
            self._systemctl("start", "bunny-input-agent.service")
        else:
            if token.exists():
                token.unlink()
            self._systemctl("stop", "bunny-input-agent.service")
            self._systemctl("mask", "bunny-input-agent.service")
        return {"ok": True, "enabled": enable}

    def cmd_installer(self, _args: dict[str, Any]) -> dict[str, Any]:
        if not Path("/run/archiso").exists():
            raise Invalid("the installer is only available in the live environment")
        terminal = shutil.which("konsole") or shutil.which("alacritty") or shutil.which("xterm")
        if not terminal:
            raise Invalid("no terminal emulator found")
        argv = [terminal, "-e", "pkexec", "/usr/local/bin/bunny-install"] \
            if shutil.which("pkexec") else [terminal, "-e", "/usr/local/bin/bunny-install"]
        if self.dry_run:
            return {"dry_run": True, "argv": argv}
        proc = self._as_user(argv)
        return {"launched": True, "pid": proc.pid}

    def cmd_power(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action", ""))
        mapping = {
            "reboot": ["reboot"],
            "poweroff": ["poweroff"],
            "logout": ["restart", "sddm.service"],
            "suspend": ["suspend"],
        }
        if action not in mapping:
            raise Invalid("action must be reboot|poweroff|logout|suspend")
        if self.dry_run:
            return {"dry_run": True, "action": action}
        self._systemctl(*mapping[action])
        return {"ok": True, "action": action}

    def cmd_audit_tail(self, args: dict[str, Any]) -> dict[str, Any]:
        limit = max(1, min(int(args.get("lines", 50) or 50), 500))
        try:
            lines = self.paths.audit.read_text("utf-8").splitlines()[-limit:]
        except OSError:
            lines = []
        return {"lines": lines}

    def cmd_update(self, args: dict[str, Any]) -> dict[str, Any]:
        action = str(args.get("action", "check"))
        if action not in {"check", "apply"}:
            raise Invalid("action must be check|apply")
        script = "/usr/local/bin/bunny-update"
        if self.dry_run:
            return {"dry_run": True, "action": action,
                    "output": "dry-run: no update performed"}
        if not Path(script).exists():
            raise Invalid("bunny-update is not installed")
        if action == "apply":
            self._systemctl("start", "bunny-update.service")
            return {
                "started": True,
                "unit": "bunny-update.service",
                "output": "update staged in the background; watch bunny-update.service",
            }
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [script, "--check"], check=False, timeout=180,
                capture_output=True, text=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Invalid(f"update check failed: {exc}") from None
        output = (proc.stdout + proc.stderr).strip()[-2000:]
        return {"ok": proc.returncode == 0, "action": "check",
                "output": output or "everything is up to date"}

    # -- helpers ------------------------------------------------------------
    def _active_user(self) -> str:
        # The daemon-owned drop-in wins; fall back to the build-time seed.
        for candidate in (self.paths.sddm_dropin,
                          Path("/etc/sddm.conf.d/10-bunny.conf")):
            try:
                for line in candidate.read_text("utf-8").splitlines():
                    if line.strip().startswith("User="):
                        value = line.split("=", 1)[1].strip()
                        if value:
                            return value
            except OSError:
                continue
        return "bunny"

    def _user_env(self) -> tuple[str, dict[str, str]]:
        name = self._active_user()
        env = dict(os.environ)
        try:
            uid = pwd.getpwnam(name).pw_uid
        except KeyError:
            uid = 1000
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
        env["HOME"] = pwd.getpwnam(name).pw_dir if _user_exists(name) else f"/home/{name}"
        return name, env

    def _as_user(self, argv: list[str]) -> subprocess.Popen[bytes]:
        name, env = self._user_env()
        if os.geteuid() == 0 and name != "root" and shutil.which("runuser"):
            full = ["runuser", "-u", name, "--", *argv]
        else:
            full = argv
        LOG.info("spawn as %s: %s", name, " ".join(full))
        return subprocess.Popen(  # noqa: S603 - argv is allowlisted
            full, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _user_systemctl(self, action: str, unit: str) -> None:
        name, env = self._user_env()
        subprocess.run(
            ["runuser", "-u", name, "--", "systemctl", "--user", action, unit],
            env=env, check=False, timeout=30, capture_output=True, text=True,
        )

    def _systemctl(self, *args: str) -> None:
        self.modes._systemctl(*args)


def _user_exists(name: str) -> bool:
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def is_live_or_installed(platform: str) -> bool:
    """Best-effort platform detection; the launcher re-checks for real."""
    markers = {
        "steam": ["/usr/bin/steam", "/usr/share/steam"],
        "epic": ["/var/lib/flatpak/exports/bin/com.heroicgameslauncher.hgl"],
        "heroic": ["/var/lib/flatpak/exports/bin/com.heroicgameslauncher.hgl"],
        "gog": ["/var/lib/flatpak/exports/bin/com.heroicgameslauncher.hgl"],
        "lutris": ["/var/lib/flatpak/exports/bin/net.lutris.Lutris", "/usr/bin/lutris"],
        "retroarch": ["/var/lib/flatpak/exports/bin/org.libretro.RetroArch", "/usr/bin/retroarch"],
        "desktop": ["/usr/bin/startplasma-wayland", "/usr/bin/startplasma-x11"],
    }
    return any(Path(p).exists() for p in markers.get(platform, []))


# ---------------------------------------------------------------------------
# Socket server
# ---------------------------------------------------------------------------
class Handler(socketserver.BaseRequestHandler):
    service: BunnyService  # injected by BunnyServer

    def handle(self) -> None:
        uid = self._peer_uid()
        self.request.settimeout(SOCKET_TIMEOUT)
        buffer = b""
        while True:
            try:
                chunk = self.request.recv(4096)
            except (socket.timeout, ConnectionResetError):
                return
            if not chunk:
                return
            buffer += chunk
            if len(buffer) > MAX_REQUEST:
                self._send({"ok": False, "error": "request too large"})
                return
            while b"\n" in buffer:
                line, _, buffer = buffer.partition(b"\n")
                if not line.strip():
                    continue
                self._send(self._dispatch(line, uid))

    def _dispatch(self, line: bytes, uid: int) -> dict[str, Any]:
        try:
            request = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"invalid json: {exc}"}
        if not isinstance(request, dict):
            return {"ok": False, "error": "request must be an object"}
        try:
            return self.service.dispatch(request, uid)
        except PermissionError as exc:
            LOG.warning("denied: %s", exc)
            return {"id": request.get("id"), "ok": False, "error": "permission denied"}
        except Invalid as exc:
            return {"id": request.get("id"), "ok": False, "error": str(exc)}
        except Exception as exc:  # never leak a traceback to a client
            LOG.exception("command failed")
            return {"id": request.get("id"), "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _send(self, payload: dict[str, Any]) -> None:
        try:
            self.request.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        except OSError:
            pass

    def _peer_uid(self) -> int:
        try:
            raw = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _pid, uid, _gid = struct.unpack("3i", raw)
            return int(uid)
        except (AttributeError, OSError):
            # Non-Linux test environments: fall back to the current euid.
            return os.geteuid()


class BunnyServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: str, service: BunnyService):
        self.service = service
        handler = type("BoundHandler", (Handler,), {"service": service})
        super().__init__(address, handler)

    def server_bind(self) -> None:
        super().server_bind()
        try:
            os.chmod(self.server_address, 0o660)
            gid = grp.getgrnam("bunny").gr_gid
            os.chown(self.server_address, 0, gid)
        except (OSError, KeyError) as exc:
            LOG.warning("could not tighten socket permissions: %s", exc)


def run_server(paths: Paths, dry_run: bool) -> None:
    service = BunnyService(paths, dry_run=dry_run)

    if not dry_run:
        try:
            paths.runtime.mkdir(parents=True, exist_ok=True)
            os.chmod(paths.runtime, 0o750)
            try:
                os.chown(paths.runtime, 0, grp.getgrnam("bunny").gr_gid)
            except KeyError:
                pass
            if paths.socket.exists() or paths.socket.is_symlink():
                paths.socket.unlink()
        except OSError as exc:
            LOG.error("cannot prepare runtime dir: %s", exc)
            raise SystemExit(1) from exc

    server = BunnyServer(str(paths.socket), service)
    LOG.info("bunny-sessiond %s listening on %s (dry_run=%s)", VERSION, paths.socket, dry_run)
    for repair in service.settings.check_invariants():
        LOG.warning("settings repair: %s", repair)
    # Re-seed the autologin drop-in so settings.json and SDDM cannot drift
    # after an upgrade, a manual edit, or an interrupted mode switch.
    try:
        service.modes.refresh_sddm()
    except OSError as exc:
        LOG.warning("could not refresh the SDDM autologin drop-in: %s", exc)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        LOG.info("shutting down")
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bunny OS session/settings daemon")
    parser.add_argument("--socket", type=Path, help="override socket path")
    parser.add_argument("--settings", type=Path, help="override settings file")
    parser.add_argument("--state", type=Path, help="override state file")
    parser.add_argument("--dry-run", action="store_true",
                        help="never touch systemd or write system files")
    parser.add_argument("--selftest", action="store_true",
                        help="exercise the command layer and exit")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    paths = Paths()
    if args.socket:
        paths.socket = args.socket
    if args.settings:
        paths.settings = args.settings
    if args.state:
        paths.state = args.state
        paths.audit = args.state.parent / "audit.log"

    if args.selftest:
        service = BunnyService(paths, dry_run=True)
        print(json.dumps(service.dispatch({"id": 1, "cmd": "status"}, os.geteuid()), indent=2))
        return 0

    if not args.dry_run and os.geteuid() != 0:
        LOG.error("bunny-sessiond must run as root (use --dry-run for a preview)")
        return 1

    run_server(paths, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
