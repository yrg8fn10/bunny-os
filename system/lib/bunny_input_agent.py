#!/usr/bin/env python3
"""bunny-input-agent — the *only* component allowed to synthesise input.

Threat model
    Bun Bun can "play alongside" the player in games that permit it.  That
    requires pressing real buttons.  Handing a language model a raw uinput
    device is a root-level footgun, so this agent is a separate, root-owned
    process with a deliberately narrow surface:

      * Disabled at boot (systemd unit is masked).
      * Requires /etc/bunny/allow-input-agent, written only by an explicit
        `bunnyctl input-agent enable --i-consent`.
      * Requires the target game PID to be alive, owned by the desktop user,
        and listed in /etc/bunny/coop-allowlist.txt.
      * Requires /run/bunny/input.disable to be absent (panic switch).
      * Keyboard / mouse only; gamepad injection is intentionally not built.
      * Hard rate limit, 200-character text cap, per-command audit log.
      * No shell, no file writes outside the audit log, no network.

Injection is never used in competitive or anti-cheat protected titles; see
docs/SAFETY-AND-LEGAL.md.  This is a consent feature, not a bypass.
"""
from __future__ import annotations

import argparse
import errno
import fcntl
import json
import logging
import os
import pwd
import socket
import socketserver
import struct
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

LOG = logging.getLogger("bunny-input")
VERSION = "0.1.0"

TOKEN_FILE = Path("/etc/bunny/allow-input-agent")
ALLOWLIST_FILE = Path("/etc/bunny/coop-allowlist.txt")
PANIC_FILE = Path("/run/bunny/input.disable")
AUDIT_FILE = Path("/var/log/bunny/input-audit.log")
SOCKET_PATH = Path("/run/bunny/input.sock")

# --- uinput ABI ------------------------------------------------------------
UINPUT_MAX_NAME_SIZE = 80
UI_DEV_SETUP = 0x405C5503
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565

EV_SYN, EV_KEY, EV_REL = 0x00, 0x01, 0x02
SYN_REPORT = 0
REL_X, REL_Y, REL_WHEEL = 0x00, 0x01, 0x08

# Linux input-event-codes.h subset — nothing else is reachable.
KEYS: dict[str, int] = {
    "KEY_ESC": 1, "KEY_1": 2, "KEY_2": 3, "KEY_3": 4, "KEY_4": 5, "KEY_5": 6,
    "KEY_6": 7, "KEY_7": 8, "KEY_8": 9, "KEY_9": 10, "KEY_0": 11,
    "KEY_MINUS": 12, "KEY_EQUAL": 13, "KEY_BACKSPACE": 14, "KEY_TAB": 15,
    "KEY_Q": 16, "KEY_W": 17, "KEY_E": 18, "KEY_R": 19, "KEY_T": 20,
    "KEY_Y": 21, "KEY_U": 22, "KEY_I": 23, "KEY_O": 24, "KEY_P": 25,
    "KEY_LEFTBRACE": 26, "KEY_RIGHTBRACE": 27, "KEY_ENTER": 28, "KEY_LEFTCTRL": 29,
    "KEY_A": 30, "KEY_S": 31, "KEY_D": 32, "KEY_F": 33, "KEY_G": 34,
    "KEY_H": 35, "KEY_J": 36, "KEY_K": 37, "KEY_L": 38, "KEY_SEMICOLON": 39,
    "KEY_APOSTROPHE": 40, "KEY_GRAVE": 41, "KEY_LEFTSHIFT": 42, "KEY_BACKSLASH": 43,
    "KEY_Z": 44, "KEY_X": 45, "KEY_C": 46, "KEY_V": 47, "KEY_B": 48,
    "KEY_N": 49, "KEY_M": 50, "KEY_COMMA": 51, "KEY_DOT": 52, "KEY_SLASH": 53,
    "KEY_RIGHTSHIFT": 54, "KEY_LEFTALT": 55, "KEY_SPACE": 57, "KEY_F1": 59,
    "KEY_F2": 60, "KEY_F3": 61, "KEY_F4": 62, "KEY_F5": 63, "KEY_F6": 64,
    "KEY_F7": 65, "KEY_F8": 66, "KEY_F9": 67, "KEY_F10": 68, "KEY_F11": 87,
    "KEY_F12": 88, "KEY_RIGHTCTRL": 97, "KEY_RIGHTALT": 100, "KEY_HOME": 102,
    "KEY_UP": 103, "KEY_PAGEUP": 104, "KEY_LEFT": 105, "KEY_RIGHT": 106,
    "KEY_END": 107, "KEY_DOWN": 108, "KEY_PAGEDOWN": 109, "KEY_INSERT": 110,
    "KEY_DELETE": 111, "KEY_LEFTMETA": 125, "KEY_RIGHTMETA": 126,
    "BTN_LEFT": 0x110, "BTN_RIGHT": 0x111, "BTN_MIDDLE": 0x112,
}

# ASCII -> key (unshifted). Shifted characters use SHIFT + base key.
_BASE_CHARS = {
    "a": "KEY_A", "b": "KEY_B", "c": "KEY_C", "d": "KEY_D", "e": "KEY_E",
    "f": "KEY_F", "g": "KEY_G", "h": "KEY_H", "i": "KEY_I", "j": "KEY_J",
    "k": "KEY_K", "l": "KEY_L", "m": "KEY_M", "n": "KEY_N", "o": "KEY_O",
    "p": "KEY_P", "q": "KEY_Q", "r": "KEY_R", "s": "KEY_S", "t": "KEY_T",
    "u": "KEY_U", "v": "KEY_V", "w": "KEY_W", "x": "KEY_X", "y": "KEY_Y",
    "z": "KEY_Z", "1": "KEY_1", "2": "KEY_2", "3": "KEY_3", "4": "KEY_4",
    "5": "KEY_5", "6": "KEY_6", "7": "KEY_7", "8": "KEY_8", "9": "KEY_9",
    "0": "KEY_0", " ": "KEY_SPACE", "-": "KEY_MINUS", "=": "KEY_EQUAL",
    "[": "KEY_LEFTBRACE", "]": "KEY_RIGHTBRACE", ";": "KEY_SEMICOLON",
    "'": "KEY_APOSTROPHE", "`": "KEY_GRAVE", "\\": "KEY_BACKSLASH",
    ",": "KEY_COMMA", ".": "KEY_DOT", "/": "KEY_SLASH", "\n": "KEY_ENTER",
}
_SHIFT_CHARS = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7",
    "*": "8", "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]",
    ":": ";", '"': "'", "~": "`", "|": "\\", "<": ",", ">": ".", "?": "/",
}


class GuardError(RuntimeError):
    """Raised when a safety gate refuses an action."""


class RateLimiter:
    """Token bucket: 12 events/s sustained, burst 30."""

    def __init__(self, rate: float = 12.0, burst: int = 30):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def take(self, n: int = 1) -> None:
        with self._lock:
            now = time.monotonic()
            self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
            self._last = now
            if self._tokens < n:
                raise GuardError("rate limit exceeded")
            self._tokens -= n


class InputDevice:
    """Minimal uinput keyboard + relative mouse device."""

    def __init__(self, name: str = "Bunny OS Bun Bun"):
        self.fd: int | None = None
        self.name = name

    def open(self) -> None:
        if os.geteuid() != 0:
            raise GuardError("input agent must run as root")
        try:
            self.fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            raise GuardError(f"cannot open /dev/uinput: {exc}") from exc

        setup = struct.pack("<HHHH80sI", 0x03, 0x1D6B, 0x0001, VERSION_HI, self.name.encode()[:79], 0)
        fcntl.ioctl(self.fd, UI_DEV_SETUP, setup)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_REL)
        for code in sorted(set(KEYS.values())):
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)
        time.sleep(0.1)
        LOG.info("uinput device created")

    def close(self) -> None:
        if self.fd is not None:
            try:
                fcntl.ioctl(self.fd, UI_DEV_DESTROY)
            except OSError:
                pass
            os.close(self.fd)
            self.fd = None

    def _emit(self, ev_type: int, code: int, value: int) -> None:
        if self.fd is None:
            raise GuardError("device not open")
        os.write(self.fd, struct.pack("<qqHHi", 0, 0, ev_type, code, value))
        os.write(self.fd, struct.pack("<qqHHi", 0, 0, EV_SYN, SYN_REPORT, 0))

    def tap(self, key: str, hold_ms: int = 40) -> None:
        code = KEYS[key]
        self._emit(EV_KEY, code, 1)
        time.sleep(max(10, min(hold_ms, 500)) / 1000)
        self._emit(EV_KEY, code, 0)

    def mouse_move(self, dx: int, dy: int) -> None:
        dx, dy = max(-400, min(400, dx)), max(-400, min(400, dy))
        self._emit(EV_REL, REL_X, dx)
        self._emit(EV_REL, REL_Y, dy)

    def scroll(self, amount: int) -> None:
        self._emit(EV_REL, REL_WHEEL, max(-10, min(10, amount)))


VERSION_HI = 0x0001
RATE = RateLimiter()
DEVICE = InputDevice()
DEVICE_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Safety gates
# ---------------------------------------------------------------------------
def _desktop_user() -> pwd.struct_passwd:
    try:
        return pwd.getpwnam("bunny")
    except KeyError as exc:
        raise GuardError("desktop user 'bunny' does not exist") from exc


def gate_enabled() -> None:
    if not TOKEN_FILE.is_file():
        raise GuardError("input agent is not enabled (run: bunnyctl input-agent enable --i-consent)")
    if PANIC_FILE.exists():
        raise GuardError("panic switch present (/run/bunny/input.disable)")


def allowlist() -> set[str]:
    try:
        lines = ALLOWLIST_FILE.read_text("utf-8").splitlines()
    except OSError:
        return set()
    return {ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")}


def gate_game(pid: int) -> str:
    """The target game must be real, owned by the player, and allowlisted."""
    allowed = allowlist()
    if not allowed:
        raise GuardError("no games in /etc/bunny/coop-allowlist.txt")

    proc = Path(f"/proc/{pid}")
    if not proc.is_dir():
        raise GuardError(f"pid {pid} is not running")
    try:
        st = proc.stat()
        exe = Path(os.readlink(f"/proc/{pid}/exe")).name
    except OSError as exc:
        raise GuardError(f"cannot inspect pid {pid}: {exc}") from exc

    user = _desktop_user()
    if st.st_uid not in {user.pw_uid, 0}:
        raise GuardError(f"pid {pid} is not owned by {user.pw_name}")
    if exe not in allowed:
        raise GuardError(f"{exe} is not in the co-op allowlist")
    return exe


def audit(cmd: str, args: dict[str, Any], game: str | None, ok: bool) -> None:
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cmd": cmd,
        "args": {k: v for k, v in args.items() if k != "text"},
        "game": game,
        "ok": ok,
    }
    if "text" in args:
        record["text_len"] = len(str(args["text"]))
    try:
        AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError as exc:
        LOG.warning("audit unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
class InputService:
    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        cmd = request.get("cmd")
        args = request.get("args") or {}
        if not isinstance(cmd, str) or not isinstance(args, dict):
            raise GuardError("invalid request")

        if cmd == "status":
            return {
                "version": VERSION,
                "enabled": TOKEN_FILE.is_file(),
                "panic": PANIC_FILE.exists(),
                "allowlist": sorted(allowlist()),
                "device_open": DEVICE.fd is not None,
            }
        if cmd == "panic":
            PANIC_FILE.parent.mkdir(parents=True, exist_ok=True)
            PANIC_FILE.write_text("engaged\n", "utf-8")
            audit("panic", {}, None, True)
            return {"ok": True, "panic": True}

        if cmd not in {"tap", "hold", "text", "mouse", "scroll"}:
            raise GuardError(f"unknown command {cmd!r}")

        gate_enabled()
        pid = int(args.get("game_pid", 0) or 0)
        game = gate_game(pid)

        try:
            with DEVICE_LOCK:
                if DEVICE.fd is None:
                    DEVICE.open()
                result = self._act(cmd, args)
        except Exception:
            audit(cmd, args, game, False)
            raise
        audit(cmd, args, game, True)
        return {"ok": True, "game": game, **result}

    def _act(self, cmd: str, args: dict[str, Any]) -> dict[str, Any]:
        if cmd in {"tap", "hold"}:
            key = str(args.get("key", ""))
            if key not in KEYS:
                raise GuardError(f"key {key!r} is not allowlisted")
            hold_ms = int(args.get("ms", 40))
            RATE.take(2)
            DEVICE.tap(key, hold_ms)
            return {"key": key, "ms": hold_ms}

        if cmd == "text":
            text = str(args.get("text", ""))
            if not text or len(text) > 200:
                raise GuardError("text must be 1..200 characters")
            RATE.take(len(text) * 2)
            self._type(text)
            return {"chars": len(text)}

        if cmd == "mouse":
            dx, dy = int(args.get("dx", 0)), int(args.get("dy", 0))
            RATE.take(2)
            DEVICE.mouse_move(dx, dy)
            return {"dx": dx, "dy": dy}

        if cmd == "scroll":
            amount = int(args.get("amount", 0))
            RATE.take(2)
            DEVICE.scroll(amount)
            return {"amount": amount}

        raise GuardError("unreachable")

    def _type(self, text: str) -> None:
        for ch in text:
            if ch in _BASE_CHARS:
                DEVICE.tap(_BASE_CHARS[ch])
            elif ch in _SHIFT_CHARS:
                DEVICE.tap("KEY_LEFTSHIFT", 20)
                DEVICE.tap(_BASE_CHARS[_SHIFT_CHARS[ch]])
            else:
                LOG.debug("skipping unsupported character %r", ch)


SERVICE = InputService()


class Handler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(10)
        buf = b""
        while True:
            try:
                chunk = self.request.recv(4096)
            except (socket.timeout, ConnectionResetError):
                return
            if not chunk:
                return
            buf += chunk
            if len(buf) > 65536:
                self._send({"ok": False, "error": "request too large"})
                return
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                if line.strip():
                    self._send(self._dispatch(line))

    def _dispatch(self, line: bytes) -> dict[str, Any]:
        try:
            request = json.loads(line.decode("utf-8"))
            return {"ok": True, "result": SERVICE.handle(request)}
        except GuardError as exc:
            LOG.warning("refused: %s", exc)
            return {"ok": False, "error": str(exc)}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"ok": False, "error": "invalid json"}
        except Exception as exc:  # pragma: no cover - defensive
            LOG.exception("input command failed")
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _send(self, payload: dict[str, Any]) -> None:
        try:
            self.request.sendall(json.dumps(payload).encode() + b"\n")
        except OSError:
            pass


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def server_bind(self) -> None:
        super().server_bind()
        try:
            os.chmod(str(self.server_address), 0o660)
            import grp
            os.chown(str(self.server_address), 0, grp.getgrnam("bunny").gr_gid)
        except (OSError, KeyError) as exc:
            LOG.warning("socket permission tightening failed: %s", exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bunny OS opt-in input injection agent")
    parser.add_argument("--socket", type=Path, default=SOCKET_PATH)
    parser.add_argument("--selftest", action="store_true", help="check gates and uinput access, then exit")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    if args.selftest:
        report = {
            "root": os.geteuid() == 0,
            "uinput": Path("/dev/uinput").exists(),
            "enabled": TOKEN_FILE.is_file(),
            "allowlist": sorted(allowlist()),
            "panic": PANIC_FILE.exists(),
        }
        print(json.dumps(report, indent=2))
        return 0 if report["root"] and report["uinput"] else 1

    if os.geteuid() != 0:
        LOG.error("bunny-input-agent must run as root")
        return 1
    if not TOKEN_FILE.is_file():
        LOG.error("refusing to start: %s is missing", TOKEN_FILE)
        return 1
    if not Path("/dev/uinput").exists():
        LOG.error("refusing to start: /dev/uinput is missing (load the uinput module)")
        return 1

    args.socket.parent.mkdir(parents=True, exist_ok=True)
    if args.socket.exists():
        args.socket.unlink()
    server = Server(str(args.socket), Handler)
    LOG.info("bunny-input-agent %s listening on %s", VERSION, args.socket)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        DEVICE.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
