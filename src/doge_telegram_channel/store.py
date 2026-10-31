"""SQLite Volume store — outbox + seen-event idempotency (same Volume).

Logical outbox states: pending → sending → sent | failed.
Seen-event key: Telegram ``update_id`` + kind (message|callback).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Logical status values (not invented AC vocabulary beyond pending/sent/failed; sending = in-flight).
STATUS_PENDING = "pending"
STATUS_SENDING = "sending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OutboxJob:
    id: int
    status: str
    chat_id: str
    payload: dict[str, Any]
    last_error: str | None


class SqliteStore:
    """Open Volume SQLite path; create outbox table if absent."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                last_error TEXT,
                updated_at REAL NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_events (
                update_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                seen_at REAL NOT NULL,
                PRIMARY KEY (update_id, kind)
            )
            """
        )
        self._conn.commit()
        logger.info("ops_sqlite_opened path=%s", self.path)
        self.reclaim_stale_sending()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("sqlite_not_open")
        return self._conn

    def enqueue(self, *, chat_id: str, payload: dict[str, Any]) -> int:
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO outbox (status, chat_id, payload, last_error, updated_at) VALUES (?, ?, ?, NULL, ?)",
            (STATUS_PENDING, chat_id, json.dumps(payload), now),
        )
        self.conn.commit()
        job_id = int(cur.lastrowid)
        logger.info("ops_outbox_enqueued id=%s chat_id=%s", job_id, chat_id)
        return job_id

    def reclaim_stale_sending(self) -> int:
        """Move orphan ``sending`` rows → ``pending`` (crash mid-claim/deliver).

        ``claim_retryable`` marks jobs ``sending`` before Bot API; if the process
        dies, those rows would otherwise never match pending|failed again.
        """
        now = time.time()
        cur = self.conn.execute(
            "UPDATE outbox SET status = ?, last_error = COALESCE(last_error, ?), updated_at = ? WHERE status = ?",
            (STATUS_PENDING, "reclaimed_stale_sending", now, STATUS_SENDING),
        )
        self.conn.commit()
        n = int(cur.rowcount or 0)
        if n:
            logger.warning("ops_outbox_reclaimed_stale_sending count=%s", n)
        return n

    def claim_retryable(self, *, limit: int = 50) -> list[OutboxJob]:
        """Claim pending or failed jobs → sending for drain/retry."""
        self.reclaim_stale_sending()
        rows = self.conn.execute(
            """
            SELECT id, status, chat_id, payload, last_error FROM outbox
            WHERE status IN (?, ?)
            ORDER BY id ASC
            LIMIT ?
            """,
            (STATUS_PENDING, STATUS_FAILED, limit),
        ).fetchall()
        jobs: list[OutboxJob] = []
        now = time.time()
        for row in rows:
            self.conn.execute(
                "UPDATE outbox SET status = ?, updated_at = ? WHERE id = ?",
                (STATUS_SENDING, now, row["id"]),
            )
            payload = json.loads(row["payload"])
            if not isinstance(payload, dict):
                payload = {}
            jobs.append(
                OutboxJob(
                    id=int(row["id"]),
                    status=STATUS_SENDING,
                    chat_id=str(row["chat_id"]),
                    payload=payload,
                    last_error=row["last_error"],
                )
            )
        self.conn.commit()
        return jobs

    def mark_sent(self, job_id: int) -> None:
        self.conn.execute(
            "UPDATE outbox SET status = ?, last_error = NULL, updated_at = ? WHERE id = ?",
            (STATUS_SENT, time.time(), job_id),
        )
        self.conn.commit()
        logger.info("ops_outbox_sent id=%s", job_id)

    def mark_failed(self, job_id: int, error: str) -> None:
        self.conn.execute(
            "UPDATE outbox SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (STATUS_FAILED, error[:500], time.time(), job_id),
        )
        self.conn.commit()
        logger.error("ops_outbox_failed id=%s error=%s", job_id, error[:200])

    def has_seen(self, *, update_id: int, kind: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen_events WHERE update_id = ? AND kind = ?",
            (update_id, kind),
        ).fetchone()
        return row is not None

    def mark_seen(self, *, update_id: int, kind: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO seen_events (update_id, kind, seen_at)
            VALUES (?, ?, ?)
            """,
            (update_id, kind, time.time()),
        )
        self.conn.commit()
        logger.info("ops_seen_event update_id=%s kind=%s", update_id, kind)

    def get_job(self, job_id: int) -> OutboxJob | None:
        row = self.conn.execute(
            "SELECT id, status, chat_id, payload, last_error FROM outbox WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        payload = json.loads(row["payload"])
        if not isinstance(payload, dict):
            payload = {}
        return OutboxJob(
            id=int(row["id"]),
            status=str(row["status"]),
            chat_id=str(row["chat_id"]),
            payload=payload,
            last_error=row["last_error"],
        )
