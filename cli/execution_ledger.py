"""Transactional Flow execution authority, separate from C-Lite lifecycle state."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from execution_contracts import ContractError, canonical, validate_action, validate_envelope


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        os.chmod(self.path, 0o600)
        with self._db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id TEXT PRIMARY KEY, work_id TEXT NOT NULL, envelope_json TEXT NOT NULL,
                status TEXT NOT NULL, reason TEXT NOT NULL, receipt_path TEXT
            );
            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                request_json TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
                grant_id TEXT UNIQUE, result_json TEXT
            );
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, attempt_id TEXT NOT NULL,
                action_id TEXT, event TEXT NOT NULL, detail TEXT NOT NULL
            );
            """)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _event(db: sqlite3.Connection, attempt_id: str, action_id: str | None, event: str, detail: str) -> None:
        db.execute("INSERT INTO events(at,attempt_id,action_id,event,detail) VALUES(?,?,?,?,?)", (utc_now(), attempt_id, action_id, event, detail))

    def create_attempt(self, envelope: dict[str, Any]) -> None:
        validate_envelope(envelope)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?)", (envelope["attempt_id"], envelope["work_id"], canonical(envelope), "started", "", None))
            self._event(db, envelope["attempt_id"], None, "attempt_started", "")

    def decide(self, envelope: dict[str, Any], action: dict[str, Any]) -> dict[str, Any]:
        validate_action(envelope, action)
        aid, attempt = action["action_id"], envelope["attempt_id"]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            stored = db.execute("SELECT envelope_json,status FROM attempts WHERE attempt_id=?", (attempt,)).fetchone()
            if stored is None or stored[0] != canonical(envelope) or stored[1] != "started":
                raise ContractError("attempt is absent, changed, or closed")
            existing = db.execute("SELECT request_json,status,reason,grant_id FROM actions WHERE action_id=?", (aid,)).fetchone()
            if existing:
                if existing[0] != canonical(action):
                    raise ContractError("action ID reused with changed payload")
                self._event(db, attempt, aid, "duplicate_request", existing[1])
                return {"allowed": False, "reason": "duplicate_request", "action_id": aid}
            work_id = envelope["work_id"]
            allowed_count = db.execute(
                "SELECT count(*) FROM actions JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND actions.status IN ('allowed','started','completed','unknown')",
                (work_id,),
            ).fetchone()[0]
            concurrent_count = db.execute(
                "SELECT count(*) FROM actions JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND actions.status IN ('allowed','started','unknown')",
                (work_id,),
            ).fetchone()[0]
            if action["role"] != "test-engineer":
                reason = "specialist_denied"
            elif action["provider"] not in {"ollama", "local-stub"}:
                reason = "provider_denied"
            elif allowed_count >= 6:
                reason = "delegation_cap"
            elif concurrent_count >= 3:
                reason = "concurrency_cap"
            else:
                reason = "allowed"
            grant = uuid.uuid4().hex if reason == "allowed" else None
            db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?)", (aid, attempt, canonical(action), "allowed" if grant else "denied", reason, grant, None))
            self._event(db, attempt, aid, "policy_allowed" if grant else "policy_denied", reason)
            return {"allowed": bool(grant), "reason": reason, "action_id": aid, "grant_id": grant}

    def consume_grant(self, action_id: str, grant_id: str) -> bool:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status,grant_id FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if not row or row[1] != "allowed" or row[2] != grant_id:
                return False
            issued = db.execute("SELECT at FROM events WHERE action_id=? AND event='policy_allowed' ORDER BY seq DESC LIMIT 1", (action_id,)).fetchone()
            if not issued or datetime.now(timezone.utc) > datetime.fromisoformat(issued[0]) + timedelta(seconds=60):
                db.execute("UPDATE actions SET status='denied',reason='grant_expired' WHERE action_id=?", (action_id,))
                self._event(db, row[0], action_id, "policy_denied", "grant_expired")
                return False
            db.execute("UPDATE actions SET status='started' WHERE action_id=?", (action_id,))
            self._event(db, row[0], action_id, "worker_dispatched", "grant_consumed")
            return True

    def complete(self, action_id: str, result: dict[str, Any]) -> None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if not row or row[1] != "started":
                raise ContractError("action is not physically started")
            status = result.get("status")
            if status not in {"completed", "failed"}:
                raise ContractError("invalid worker result status")
            db.execute("UPDATE actions SET status=?,result_json=? WHERE action_id=?", (status, canonical(result), action_id))
            self._event(db, row[0], action_id, "worker_" + status, result.get("output_sha256", ""))

    def mark_unknown(self, action_id: str, reason: str) -> None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if row and row[1] == "started":
                db.execute("UPDATE actions SET status='unknown',reason=? WHERE action_id=?", (reason, action_id))
                self._event(db, row[0], action_id, "worker_unknown", reason)

    def finish_attempt(self, attempt_id: str, status: str, reason: str, receipt_path: str) -> None:
        if status not in {"completed", "failed", "denied", "unknown"}:
            raise ContractError("invalid attempt terminal status")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row != ("started",):
                raise ContractError("attempt not active")
            db.execute("UPDATE attempts SET status=?,reason=?,receipt_path=? WHERE attempt_id=?", (status, reason, receipt_path, attempt_id))
            self._event(db, attempt_id, None, "attempt_" + status, reason)

    def snapshot(self, attempt_id: str) -> dict[str, Any]:
        with self._db() as db:
            a = db.execute("SELECT attempt_id,work_id,envelope_json,status,reason,receipt_path FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if not a:
                raise ContractError("attempt missing")
            actions = db.execute("SELECT action_id,request_json,status,reason,grant_id,result_json FROM actions WHERE attempt_id=? ORDER BY rowid", (attempt_id,)).fetchall()
            events = db.execute("SELECT seq,at,action_id,event,detail FROM events WHERE attempt_id=? ORDER BY seq", (attempt_id,)).fetchall()
        return {"attempt_id": a[0], "work_id": a[1], "envelope": json.loads(a[2]), "status": a[3], "reason": a[4], "receipt_path": a[5],
                "actions": [{"action_id": r[0], "request": json.loads(r[1]), "status": r[2], "reason": r[3], "grant_id": r[4], "result": json.loads(r[5]) if r[5] else None} for r in actions],
                "events": [{"seq": r[0], "at": r[1], "action_id": r[2], "event": r[3], "detail": r[4]} for r in events]}
