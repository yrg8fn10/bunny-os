#!/usr/bin/env python3
"""mam_bridge: bunhud's hookup to Bun Bun's MAM loop.

Connects to the companion service's local SSE stream
(127.0.0.1:8422/v1/stream) and turns MAM bus events into bunhud
commands: the game started, she appears; the agent stopped, she hides.
A future revision will drive hint bubbles from "bunbun.spoken".

Localhost only. bunhud never talks to the network, with or without
this bridge.
"""
from __future__ import annotations

import http.client
import json
import queue
import threading

# Provisional mapping, pinned to the topics service.py publishes today.
# Revisit when the MAM engine grows show/hide-aware topics.
TOPIC_COMMANDS = {
    "game.started": "show",
    "agent.started": "show",
    "bunbun.spoken": "show",
    "agent.stopped": "hide",
}


def event_to_command(event) -> str | None:
    """One bus event -> one bunhud command (or None to ignore)."""
    if not isinstance(event, dict):
        return None
    topic = event.get("topic") or event.get("event")
    return TOPIC_COMMANDS.get(topic)


def parse_sse_line(line: str):
    """One SSE line -> the event dict it carries, else None.

    The companion service sends data-only frames ("data: {json}") and
    comment keepalives (": keepalive"); comments are ignored.
    """
    if not line.startswith("data: "):
        return None
    try:
        return json.loads(line[6:].strip())
    except json.JSONDecodeError:
        return None


class MamBridge(threading.Thread):
    """Reads the MAM event stream and feeds a command queue.

    Runs as a daemon thread: if the companion service is not up yet,
    the bridge retries with a growing backoff and bunhud keeps drawing.
    """

    def __init__(self, commands: "queue.Queue[str]", host="127.0.0.1", port=8422):
        super().__init__(daemon=True, name="bunhud-mam")
        self.commands = commands
        self.host = host
        self.port = port
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        backoff = 2.0
        conn = None
        while not self._stop.is_set():
            try:
                conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
                conn.request(
                    "GET", "/v1/stream", headers={"Accept": "text/event-stream"}
                )
                resp = conn.getresponse()
                if resp.status != 200:
                    raise OSError(f"stream returned {resp.status}")
                backoff = 2.0  # connected once: reset the retry pace
                while not self._stop.is_set():
                    raw = resp.fp.readline()
                    if not raw:
                        break  # server closed; loop reconnects
                    event = parse_sse_line(raw.decode("utf-8", "replace"))
                    command = event_to_command(event)
                    if command:
                        try:
                            self.commands.put_nowait(command)
                        except queue.Full:
                            pass  # the newest state wins; drop the rest
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            # Service not up yet: retry gently, never hot-loop.
            self._stop.wait(backoff)
            backoff = min(backoff * 2.0, 30.0)
