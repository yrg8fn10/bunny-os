"""Tiny in-process pub/sub bus used for overlay events and SSE streams."""
from __future__ import annotations

import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {"topic": self.topic, "payload": self.payload, "ts": self.ts}


class EventBus:
    def __init__(self, history: int = 100):
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue[Event]] = []
        self._history: deque[Event] = deque(maxlen=history)

    def subscribe(self, maxsize: int = 64) -> queue.Queue[Event]:
        q: queue.Queue[Event] = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue[Event]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, topic: str, payload: dict[str, Any] | None = None) -> Event:
        event = Event(topic=topic, payload=payload or {})
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                # Slow overlay: drop the oldest, keep the newest.
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (queue.Empty, queue.Full):
                    pass
        return event

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._history)[-max(1, min(limit, 200)):]
        return [e.as_dict() for e in events]

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
