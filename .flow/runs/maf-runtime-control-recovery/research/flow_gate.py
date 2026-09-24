"""Flow-owned, durable dispatch policy for the bounded MAF recovery probe."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path


ALLOWED_ROLES = frozenset({"lead-developer", "test-engineer", "quality-reviewer"})
MAX_DELEGATIONS = 6
MAX_CONCURRENT = 3
MAX_REPLANS = 2
PAID_BUDGET_USD = 10.0

# A caller's claim that an adapter enforces a cap is not sufficient. Only
# registered adapters whose limiting behavior was reviewed can be admitted.
PROVIDERS = {
    "ollama": {"paid": False, "hard_cap": 0.0, "dispatchable": True},
    "metered-test": {"paid": True, "hard_cap": 10.0, "dispatchable": False},
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    request_id: str


class FlowGate:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    role TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    hard_cap_usd REAL NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dispatches (
                    request_id TEXT PRIMARY KEY REFERENCES requests(request_id),
                    result_sha256 TEXT,
                    state TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    detail TEXT NOT NULL
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _count(db: sqlite3.Connection, query: str) -> int:
        return int(db.execute(query).fetchone()[0])

    def decide(self, request: dict[str, object]) -> Decision:
        request_id = str(request["request_id"])
        kind = str(request["kind"])
        role = str(request["role"])
        provider = str(request["provider"])
        cap = request.get("hard_cap_usd")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM requests WHERE request_id=?", (request_id,)).fetchone():
                db.execute("INSERT INTO events(request_id,event,detail) VALUES(?,?,?)", (request_id, "policy_denied", "duplicate_request"))
                return Decision(False, "duplicate_request", request_id)
            reason = "allowed"
            provider_info = PROVIDERS.get(provider)
            if kind not in {"delegate", "replan"}:
                reason = "unknown_kind"
            elif role not in ALLOWED_ROLES:
                reason = "specialist_denied"
            elif provider_info is None:
                reason = "provider_without_enforceable_cap"
            elif kind == "delegate" and self._count(db, "SELECT count(*) FROM requests WHERE kind='delegate' AND status IN ('allowed','completed')") >= MAX_DELEGATIONS:
                reason = "delegation_cap"
            elif kind == "delegate" and self._count(db, "SELECT count(*) FROM requests WHERE kind='delegate' AND status='allowed'") >= MAX_CONCURRENT:
                reason = "concurrency_cap"
            elif kind == "replan" and self._count(db, "SELECT count(*) FROM requests WHERE kind='replan' AND status IN ('allowed','completed')") >= MAX_REPLANS:
                reason = "replan_cap"
            elif not isinstance(cap, (int, float)) or isinstance(cap, bool) or not math.isfinite(cap) or cap < 0 or cap > float(provider_info["hard_cap"]):
                reason = "invalid_hard_cap"
            elif provider_info["paid"] and (cap == 0 or not request.get("cap_enforced_by_adapter")):
                reason = "paid_cap_unverified"
            elif not provider_info["paid"] and cap != 0:
                reason = "local_cost_mismatch"
            elif provider_info["paid"] and float(db.execute("SELECT coalesce(sum(hard_cap_usd),0) FROM requests WHERE status IN ('allowed','completed')").fetchone()[0]) + float(cap) > PAID_BUDGET_USD:
                reason = "paid_budget_cap"
            allowed = reason == "allowed"
            db.execute(
                "INSERT INTO requests VALUES(?,?,?,?,?,?,?)",
                (request_id, kind, role, provider, float(cap) if isinstance(cap, (int, float)) and not isinstance(cap, bool) and math.isfinite(cap) else -1.0, "allowed" if allowed else "denied", reason),
            )
            db.execute("INSERT INTO events(request_id,event,detail) VALUES(?,?,?)", (request_id, "policy_allowed" if allowed else "policy_denied", reason))
            return Decision(allowed, reason, request_id)

    def claim_dispatch(self, request_id: str) -> bool:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT kind,provider,status FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None or row[0] != "delegate" or row[2] != "allowed" or not PROVIDERS[row[1]]["dispatchable"]:
                db.execute("INSERT INTO events(request_id,event,detail) VALUES(?,?,?)", (request_id, "dispatch_denied", "not_authorized_or_dispatchable"))
                return False
            if db.execute("SELECT 1 FROM dispatches WHERE request_id=?", (request_id,)).fetchone():
                db.execute("INSERT INTO events(request_id,event,detail) VALUES(?,?,?)", (request_id, "dispatch_denied", "duplicate_dispatch"))
                return False
            db.execute("INSERT INTO dispatches VALUES(?,?,?)", (request_id, None, "started"))
            db.execute("INSERT INTO events(request_id,event,detail) VALUES(?,?,?)", (request_id, "worker_dispatched", row[1]))
            return True

    def complete_replan(self, request_id: str) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT kind,status FROM requests WHERE request_id=?", (request_id,)).fetchone()
            if row != ("replan", "allowed"):
                raise ValueError("replan not active")
            db.execute("UPDATE requests SET status='completed' WHERE request_id=?", (request_id,))
            db.execute("INSERT INTO events(request_id,event,detail) VALUES(?,?,?)", (request_id, "replan_completed", "completed"))

    def complete(self, request_id: str, reported_result: str) -> str:
        digest = hashlib.sha256(reported_result.encode()).hexdigest()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM dispatches WHERE request_id=?", (request_id,)).fetchone()
            if row != ("started",):
                raise ValueError("dispatch not active")
            db.execute("UPDATE dispatches SET state='completed',result_sha256=? WHERE request_id=?", (digest, request_id))
            db.execute("UPDATE requests SET status='completed' WHERE request_id=?", (request_id,))
            db.execute("INSERT INTO events(request_id,event,detail) VALUES(?,?,?)", (request_id, "worker_completed", digest))
        return digest

    def snapshot(self) -> dict[str, object]:
        with self._connect() as db:
            requests = db.execute("SELECT request_id,kind,role,provider,hard_cap_usd,status,reason FROM requests ORDER BY rowid").fetchall()
            dispatches = db.execute("SELECT request_id,result_sha256,state FROM dispatches ORDER BY rowid").fetchall()
            events = db.execute("SELECT seq,request_id,event,detail FROM events ORDER BY seq").fetchall()
        return {"requests": requests, "dispatches": dispatches, "events": events}


def request_json(request_id: str, *, role: str = "test-engineer", provider: str = "ollama", cap: float | None = 0.0, kind: str = "delegate") -> str:
    return json.dumps({"request_id": request_id, "kind": kind, "role": role, "provider": provider, "hard_cap_usd": cap}, sort_keys=True)
