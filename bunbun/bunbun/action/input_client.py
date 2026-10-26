"""Client for the opt-in input agent.

The agent re-validates everything; this client is only a thin, explicit wrapper
so the MAM engine cannot accidentally construct a raw device.
"""
from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any

DEFAULT_SOCKET = Path(os.environ.get("BUNNY_INPUT_SOCKET", "/run/bunny/input.sock"))
TOKEN = Path("/etc/bunny/allow-input-agent")


class InputUnavailable(RuntimeError):
    pass


class InputClient:
    def __init__(self, socket_path: Path = DEFAULT_SOCKET, token: Path = TOKEN,
                 timeout: float = 5.0):
        self.socket_path = socket_path
        self.token = token
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return self.token.is_file() and self.socket_path.exists()

    def _call(self, cmd: str, args: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise InputUnavailable("input agent is not enabled")
        payload = json.dumps({"cmd": cmd, "args": args}) + "\n"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect(str(self.socket_path))
            sock.sendall(payload.encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    raise InputUnavailable("agent closed the connection")
                buf += chunk
        reply = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
        if not reply.get("ok"):
            raise InputUnavailable(reply.get("error", "agent refused the action"))
        return reply.get("result", {})

    # -- narrow surface ----------------------------------------------------
    def tap(self, key: str, game_pid: int, hold_ms: int = 40) -> dict[str, Any]:
        return self._call("tap", {"key": key, "ms": hold_ms, "game_pid": game_pid})

    def text(self, text: str, game_pid: int) -> dict[str, Any]:
        return self._call("text", {"text": text, "game_pid": game_pid})

    def panic(self) -> dict[str, Any]:
        return self._call("panic", {})

    def status(self) -> dict[str, Any]:
        return self._call("status", {})
