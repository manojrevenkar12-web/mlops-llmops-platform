"""The release record: an append-only event log. Every decision the platform makes is an event with a reason.

Each release step has an idempotency key, so a pipeline that crashes and restarts resumes instead of running a
step twice (a canary step that already moved traffic must not move it again). Events are hash-chained, so an
edited history is detectable. Adoption and delivery metrics are computed from this log and nothing else.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


def _plain(o):
    """numpy scalars and arrays as plain JSON values."""
    if hasattr(o, "tolist"):
        return o.tolist()
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(type(o).__name__)


@dataclass(frozen=True)
class Event:
    seq: int
    release_id: str
    step: str
    kind: str
    payload: dict
    at: float
    hash: str


class EventLog:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, release_id TEXT NOT NULL,"
            " step TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, at REAL NOT NULL, prev TEXT NOT NULL,"
            " hash TEXT NOT NULL, UNIQUE(release_id, step))"
        )
        self.db.commit()

    def _last_hash(self) -> str:
        row = self.db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        return row[0] if row else "genesis"

    def append(self, release_id: str, step: str, kind: str, payload: dict, at: float | None = None) -> Event:
        """Record a step once. Appending the same (release, step) again returns the stored event unchanged."""
        existing = self.get(release_id, step)
        if existing is not None:
            return existing
        at = time.time() if at is None else at
        payload = json.loads(json.dumps(payload, default=_plain))
        prev = self._last_hash()
        body = json.dumps({"r": release_id, "s": step, "k": kind, "p": payload, "t": at, "prev": prev}, sort_keys=True)
        h = hashlib.sha256(body.encode()).hexdigest()
        self.db.execute(
            "INSERT INTO events (release_id, step, kind, payload, at, prev, hash) VALUES (?,?,?,?,?,?,?)",
            (release_id, step, kind, json.dumps(payload, sort_keys=True), at, prev, h),
        )
        self.db.commit()
        return self.get(release_id, step)  # type: ignore[return-value]

    def get(self, release_id: str, step: str) -> Event | None:
        row = self.db.execute(
            "SELECT seq, release_id, step, kind, payload, at, hash FROM events WHERE release_id=? AND step=?",
            (release_id, step),
        ).fetchone()
        return None if row is None else Event(row[0], row[1], row[2], row[3], json.loads(row[4]), row[5], row[6])

    def events(self, release_id: str | None = None) -> list[Event]:
        q = "SELECT seq, release_id, step, kind, payload, at, hash FROM events"
        args: tuple = ()
        if release_id is not None:
            q += " WHERE release_id=?"
            args = (release_id,)
        rows = self.db.execute(q + " ORDER BY seq", args).fetchall()
        return [Event(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5], r[6]) for r in rows]

    def verify(self) -> bool:
        prev = "genesis"
        rows = self.db.execute("SELECT release_id, step, kind, payload, at, prev, hash FROM events ORDER BY seq")
        for r in rows.fetchall():
            if r[5] != prev:
                return False
            body = json.dumps(
                {"r": r[0], "s": r[1], "k": r[2], "p": json.loads(r[3]), "t": r[4], "prev": prev}, sort_keys=True
            )
            if hashlib.sha256(body.encode()).hexdigest() != r[6]:
                return False
            prev = r[6]
        return True
