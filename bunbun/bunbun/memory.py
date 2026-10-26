"""Local, inspectable memory for Bun Bun.

Everything stays in one SQLite file under the user's data directory.  There is
no sync, no upload, and `purge()` really deletes every row.  The panel exposes
both facts in Settings -> Privacy.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    kind      TEXT NOT NULL,
    game_id   TEXT,
    payload   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC);

CREATE TABLE IF NOT EXISTS hints (
    hint_id   TEXT NOT NULL,
    game_id   TEXT NOT NULL,
    shown_at  REAL NOT NULL,
    PRIMARY KEY (hint_id, game_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id   TEXT NOT NULL,
    started   REAL NOT NULL,
    ended     REAL,
    minutes   REAL
);

CREATE TABLE IF NOT EXISTS consent (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    subject   TEXT NOT NULL,
    granted   INTEGER NOT NULL,
    note      TEXT
);
"""


class Memory:
    def __init__(self, path: Path, enabled: bool = True):
        self.path = Path(path)
        self.enabled = enabled
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        if enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- events ------------------------------------------------------------
    def record(self, kind: str, payload: dict[str, Any], game_id: str | None = None) -> None:
        if not self._conn:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (ts, kind, game_id, payload) VALUES (?, ?, ?, ?)",
                (time.time(), kind, game_id, json.dumps(payload, separators=(",", ":"))),
            )
            self._conn.commit()

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self._conn:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT ts, kind, game_id, payload FROM events ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [
            {"ts": r["ts"], "kind": r["kind"], "game_id": r["game_id"],
             "payload": json.loads(r["payload"])}
            for r in rows
        ]

    # -- hints -------------------------------------------------------------
    def hint_seen(self, hint_id: str, game_id: str) -> bool:
        if not self._conn:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM hints WHERE hint_id = ? AND game_id = ?",
                (hint_id, game_id),
            ).fetchone()
        return row is not None

    def mark_hint(self, hint_id: str, game_id: str) -> None:
        if not self._conn:
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO hints (hint_id, game_id, shown_at) VALUES (?, ?, ?)",
                (hint_id, game_id, time.time()),
            )
            self._conn.commit()

    def hint_count(self, game_id: str | None = None) -> int:
        if not self._conn:
            return 0
        with self._lock:
            if game_id:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM hints WHERE game_id = ?", (game_id,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) AS n FROM hints").fetchone()
        return int(row["n"]) if row else 0

    # -- sessions ----------------------------------------------------------
    def start_session(self, game_id: str) -> int | None:
        if not self._conn:
            return None
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sessions (game_id, started) VALUES (?, ?)",
                (game_id, time.time()),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def end_session(self, session_id: int | None) -> None:
        if not self._conn or session_id is None:
            return
        with self._lock:
            row = self._conn.execute(
                "SELECT started FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if not row:
                return
            minutes = round((time.time() - float(row["started"])) / 60, 1)
            self._conn.execute(
                "UPDATE sessions SET ended = ?, minutes = ? WHERE id = ?",
                (time.time(), minutes, session_id),
            )
            self._conn.commit()

    # -- consent -----------------------------------------------------------
    def record_consent(self, subject: str, granted: bool, note: str = "") -> None:
        if not self._conn:
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO consent (ts, subject, granted, note) VALUES (?, ?, ?, ?)",
                (time.time(), subject, 1 if granted else 0, note),
            )
            self._conn.commit()

    # -- privacy -----------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        if not self._conn:
            return {"enabled": False}
        with self._lock:
            events = self._conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
            sessions = self._conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
            consent = self._conn.execute("SELECT COUNT(*) AS n FROM consent").fetchone()["n"]
        return {
            "enabled": True,
            "path": str(self.path),
            "events": events,
            "sessions": sessions,
            "consent_records": consent,
        }

    def purge(self) -> dict[str, Any]:
        if not self._conn:
            return {"purged": False}
        with self._lock:
            for table in ("events", "hints", "sessions", "consent"):
                self._conn.execute(f"DELETE FROM {table}")  # noqa: S608 - constant names
            self._conn.commit()
            self._conn.execute("VACUUM")
        return {"purged": True}
