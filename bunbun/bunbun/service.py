#!/usr/bin/env python3
"""Bun Bun service — local HTTP API + SSE overlay stream.

Runs as the desktop user.  Binds loopback only.  Standard library only.

Endpoints
    GET  /health              liveness + voice backend
    GET  /v1/status           engine, memory, co-op and policy summary
    GET  /v1/events           recent bus events (?limit=)
    GET  /v1/stream           Server-Sent Events for the overlay
    GET  /v1/policy           the exact safety rules, human readable
    POST /v1/state            game state observation
    POST /v1/tick             run one MAM cycle
    POST /v1/say              speak a line
    POST /v1/hint             request a hint
    POST /v1/coop/join        evaluate / perform a join
    POST /v1/coop/leave
    POST /v1/consent          record a consent decision
    POST /v1/memory/purge
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import __version__
from .action import CoopAgent, InputClient, JoinInvite
from .bus import EventBus
from .config import PACKAGE_DATA, AgentConfig, USER_SETTINGS, load_config
from .hints import HintLibrary
from .mam import GameState, Kind, MAMEngine, PolicyEngine
from .memory import Memory
from .perception import GameWatcher
from .persona import Persona
from .tts import TTSPipeline

LOG = logging.getLogger("bunbun")
MAX_BODY = 128 * 1024


# ---------------------------------------------------------------------------
def load_settings_file(path: Path | str = "/etc/bunny/settings.json") -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


class AgentService:
    def __init__(self, config: AgentConfig):
        self.config = config
        config.data_dir.expanduser().mkdir(parents=True, exist_ok=True)

        self.bus = EventBus()
        self.memory = Memory(config.db_path, enabled=config.memory_enabled)
        self.persona = Persona.load(max_chars=config.max_utterance_chars)
        self.hints = HintLibrary.from_directory(PACKAGE_DATA / "hints")
        self.input_client = InputClient()
        self.started_at = time.time()

        self.tts = TTSPipeline(
            config,
            on_spoken=lambda text: self.bus.publish("bunbun.spoken", {"text": text}),
        )

        self.engine = MAMEngine(
            persona=self.persona,
            hints=self.hints,
            settings_provider=self.settings,
            memory=self.memory,
            bus=self.bus,
            policy=PolicyEngine(kill_switch=self._kill_switch),
            speaker=self.tts.say,
            input_enabled=lambda: self.input_client.enabled,
        )

        self.watcher = GameWatcher(self.bus)
        self.coop = CoopAgent(self.bus)

        self._stop = threading.Event()
        self._events: queue.Queue = self.bus.subscribe(maxsize=256)
        self._threads = [
            threading.Thread(target=self._event_loop, name="bunbun-events", daemon=True),
            threading.Thread(target=self._tick_loop, name="bunbun-tick", daemon=True),
        ]

    # -- settings ----------------------------------------------------------
    def settings(self) -> dict[str, Any]:
        system_path = Path(os.environ.get("BUNBUN_SETTINGS", "/etc/bunny/settings.json"))
        system = load_settings_file(system_path)
        user = load_settings_file(USER_SETTINGS)
        ai = dict(system.get("ai", {}))
        # User overrides win, but only for keys the schema knows about.
        for key, value in user.items():
            if key in {"voice", "hint_level", "commentary", "coop_opt_in", "coop_mode",
                       "screen_vision", "kid_safe", "memory_enabled", "voice_enabled",
                       "enabled"}:
                ai[key] = value
        return {"ai": ai, "performance": system.get("performance", {})}

    def _kill_switch(self) -> bool:
        return Path("/run/bunny/agent.lock").exists() or bool(
            os.environ.get("BUNBUN_DISABLE"))

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self.config.voice_enabled:
            self.tts.start()
        self.watcher.start()
        for thread in self._threads:
            thread.start()
        self.bus.publish("agent.started", {"version": __version__,
                                          "voice": self.config.voice})
        LOG.info("Bun Bun %s online (voice=%s)", __version__, self.config.voice)

    def stop(self) -> None:
        self._stop.set()
        self.watcher.stop()
        self.tts.close()
        self.engine.close()
        self.bus.publish("agent.stopped", {})

    # -- background --------------------------------------------------------
    def _event_loop(self) -> None:
        while not self._stop.is_set():
            try:
                event = self._events.get(timeout=0.5)
            except queue.Empty:
                continue
            if event.topic == "game.detected":
                payload = dict(event.payload)
                payload.setdefault("allowlisted", False)
                self.engine.observe(payload)
            elif event.topic == "game.exited":
                self.engine.observe({})

    def _tick_loop(self) -> None:
        while not self._stop.wait(self.config.tick_seconds):
            try:
                if self.engine.state.game_id:
                    self.engine.tick()
            except Exception:
                LOG.exception("tick failed")

    # -- operations --------------------------------------------------------
    def observe(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        return [o.to_dict() for o in self.engine.observe(payload)]

    def tick(self, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return [o.to_dict() for o in self.engine.tick(payload)]

    def hint(self, secret: bool = False) -> dict[str, Any] | None:
        outcome = self.engine.request_hint(allow_secret=secret)
        return outcome.to_dict() if outcome else None

    def say(self, text: str) -> dict[str, Any]:
        if not text.strip():
            raise ValueError("text is required")
        return {"spoken": self.engine.say(text), "text": self.persona.sanitize(text)}

    def join(self, payload: dict[str, Any]) -> dict[str, Any]:
        invite = JoinInvite.from_dict(payload.get("invite") or payload)
        return self.coop.join(
            invite,
            self.settings(),
            player_confirmed=bool(payload.get("confirmed", False)),
            dry_run=bool(payload.get("dry_run", False)),
        )

    def status(self) -> dict[str, Any]:
        snap = self.watcher.snapshot
        return {
            "agent": {
                "version": __version__,
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "voice_backend": self.tts.backend.name,
                "voice_available": self.tts.available,
                "tts": self.tts.stats,
                "input_enabled": self.input_client.enabled,
                "local_only": True,
            },
            "engine": self.engine.status(),
            "watcher": snap.as_dict(),
            "coop": self.coop.status(),
            "events": self.bus.recent(10),
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "voice_backend": self.tts.backend.name,
            "voice_available": self.tts.available,
            "memory": self.memory.stats(),
            "kill_switch": self._kill_switch(),
        }


# ---------------------------------------------------------------------------
class ApiHandler(BaseHTTPRequestHandler):
    service: AgentService
    server_version = f"bunbun/{__version__}"
    sys_version = ""

    # -- plumbing ----------------------------------------------------------
    def _local_only(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        return host in {"127.0.0.1", "localhost", "[::1]"}

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        LOG.debug("%s %s", self.address_string(), fmt % args)

    # -- routes ------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if not self._local_only():
            self._json(403, {"ok": False, "error": "loopback only"})
            return
        url = urlparse(self.path)
        route = url.path
        query = parse_qs(url.query)
        svc = self.service

        if route in {"/health", "/v1/health"}:
            self._json(200, svc.health())
        elif route == "/v1/status":
            self._json(200, svc.status())
        elif route == "/v1/events":
            limit = int((query.get("limit") or ["20"])[0])
            self._json(200, {"events": svc.bus.recent(limit)})
        elif route == "/v1/policy":
            self._json(200, {"rules": PolicyEngine.rules()})
        elif route == "/v1/stream":
            self._stream()
        elif route == "/v1/state":
            self._json(200, svc.engine.state.to_dict())
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._local_only():
            self._json(403, {"ok": False, "error": "loopback only"})
            return
        route = urlparse(self.path).path
        try:
            body = self._read_json()
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return

        svc = self.service
        try:
            if route == "/v1/state":
                self._json(200, {"outcomes": svc.observe(body)})
            elif route == "/v1/tick":
                self._json(200, {"outcomes": svc.tick(body or None)})
            elif route == "/v1/say":
                self._json(200, svc.say(str(body.get("text", ""))))
            elif route == "/v1/hint":
                result = svc.hint(secret=bool(body.get("secret", False)))
                self._json(200, {"hint": result})
            elif route == "/v1/coop/join":
                self._json(200, svc.join(body))
            elif route == "/v1/coop/leave":
                self._json(200, svc.coop.leave(str(body.get("reason", "player request"))))
            elif route == "/v1/consent":
                action = Kind(str(body.get("action", "join")))
                granted = bool(body.get("granted", False))
                self._json(200, svc.engine.consent(action, granted,
                                                   str(body.get("note", ""))))
            elif route == "/v1/memory/purge":
                self._json(200, svc.memory.purge())
            elif route == "/v1/settings/reload":
                self._json(200, {"settings": svc.settings()})
            else:
                self._json(404, {"ok": False, "error": "not found"})
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            LOG.exception("request failed: %s", route)
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    # -- helpers -----------------------------------------------------------
    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("bad content length") from None
        if length > MAX_BODY:
            raise ValueError("body too large")
        if length == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("invalid json body") from None
        if not isinstance(data, dict):
            raise ValueError("body must be an object")
        return data

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()

        q = self.service.bus.subscribe(maxsize=64)
        self.close_connection = True
        try:
            self.wfile.write(b": bunny overlay stream\n\n")
            self.wfile.flush()
            last_beat = time.monotonic()
            while True:
                try:
                    event = q.get(timeout=1.0)
                    payload = json.dumps(event.as_dict())
                    # Data-only frames so the browser's EventSource.onmessage
                    # receives every topic without registering listeners.
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                except queue.Empty:
                    if time.monotonic() - last_beat > 15:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        last_beat = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.service.bus.unsubscribe(q)


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], service: AgentService):
        self.service = service
        handler = type("BoundApiHandler", (ApiHandler,), {"service": service})
        super().__init__(address, handler)


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bun Bun local agent service")
    parser.add_argument("--host", default=None, help="default 127.0.0.1 (loopback only)")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--settings", type=Path, default=None)
    parser.add_argument("--no-voice", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    config = load_config(args.settings)
    overrides: dict[str, Any] = {}
    if args.host:
        overrides["host"] = args.host
    if args.port:
        overrides["port"] = args.port
    if args.data_dir:
        overrides["data_dir"] = args.data_dir
    if args.no_voice:
        overrides["voice_enabled"] = False
    if overrides:
        from dataclasses import replace
        config = replace(config, **overrides)

    if config.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("refusing to bind a non-loopback address (local-only agent)")

    service = AgentService(config)
    server = ApiServer((config.host, config.port), service)
    service.start()

    def shutdown(*_args: object) -> None:
        LOG.info("shutting down")
        service.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    LOG.info("listening on http://%s:%s", config.host, config.port)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        service.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
