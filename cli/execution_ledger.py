"""Transactional Flow execution authority, separate from C-Lite lifecycle state."""

from __future__ import annotations

import hashlib
import json
import fcntl
import os
import sqlite3
import stat
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from contextlib import contextmanager
from typing import Any

from execution_contracts import (
    ContractError,
    canonical,
    validate_action,
    validate_envelope,
    execution_protocol_version,
    envelope_digest,
    validate_replan,
    validate_recovery_resolution,
    validate_result,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ExecutionLedger:
    def __init__(self, path: Path, *, read_only: bool = False):
        self.path = Path(path)
        self.read_only = read_only
        if read_only:
            if not self.path.is_file():
                raise ContractError("execution ledger is absent")
            return
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
                status TEXT NOT NULL, reason TEXT NOT NULL, receipt_path TEXT,
                recovery_version INTEGER NOT NULL DEFAULT 1,
                owner_generation INTEGER NOT NULL DEFAULT 0,
                owner_actor TEXT,
                execution_protocol_version INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                request_json TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
                grant_id TEXT UNIQUE, result_json TEXT,
                kind TEXT NOT NULL DEFAULT 'delegate', sequence INTEGER NOT NULL DEFAULT 1,
                proposal_digest TEXT
            );
            CREATE TABLE IF NOT EXISTS replan_decisions (
                replan_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                sequence INTEGER NOT NULL, request_json TEXT NOT NULL, proposal_digest TEXT NOT NULL,
                status TEXT NOT NULL, reason TEXT NOT NULL,
                UNIQUE(attempt_id, sequence)
            );
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, attempt_id TEXT NOT NULL,
                action_id TEXT, event TEXT NOT NULL, detail TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS response_observations (
                action_id TEXT PRIMARY KEY REFERENCES actions(action_id), observed_at TEXT NOT NULL,
                result_json TEXT NOT NULL, result_digest TEXT NOT NULL, owner_generation INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recovery_resolutions (
                resolution_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                action_id TEXT NOT NULL REFERENCES actions(action_id), actor TEXT NOT NULL,
                disposition TEXT NOT NULL, explanation TEXT NOT NULL, evidence_json TEXT NOT NULL,
                result_json TEXT, resolution_digest TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL,
                owner_generation INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS checkpoint_links (
                attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id), checkpoint_id TEXT NOT NULL,
                envelope_digest TEXT NOT NULL, ledger_seq INTEGER NOT NULL, format_version INTEGER NOT NULL,
                runtime_version TEXT NOT NULL, path TEXT NOT NULL, bound_at TEXT NOT NULL,
                owner_generation INTEGER NOT NULL, file_sha256 TEXT
            );
            CREATE TABLE IF NOT EXISTS checkpoint_position_links (
                attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                kind TEXT NOT NULL, sequence INTEGER NOT NULL, checkpoint_id TEXT NOT NULL,
                envelope_digest TEXT NOT NULL, ledger_seq INTEGER NOT NULL,
                format_version INTEGER NOT NULL, runtime_version TEXT NOT NULL,
                protocol_version INTEGER NOT NULL, path TEXT NOT NULL,
                file_sha256 TEXT NOT NULL, file_size INTEGER NOT NULL,
                bound_at TEXT NOT NULL, owner_generation INTEGER NOT NULL,
                PRIMARY KEY(attempt_id, kind, sequence)
            );
            """)
            # SQLite's CREATE TABLE IF NOT EXISTS cannot evolve first-slice
            # databases. These columns make existing records explicitly v1 and
            # therefore inspectable but never silently resumable.
            columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
            for name, definition in (
                ("recovery_version", "INTEGER NOT NULL DEFAULT 1"),
                ("owner_generation", "INTEGER NOT NULL DEFAULT 0"),
                ("owner_actor", "TEXT"),
                ("execution_protocol_version", "INTEGER NOT NULL DEFAULT 1"),
            ):
                if name not in columns:
                    db.execute(f"ALTER TABLE attempts ADD COLUMN {name} {definition}")
            checkpoint_columns = {row[1] for row in db.execute("PRAGMA table_info(checkpoint_links)")}
            if "file_sha256" not in checkpoint_columns:
                db.execute("ALTER TABLE checkpoint_links ADD COLUMN file_sha256 TEXT")
            action_columns = {row[1] for row in db.execute("PRAGMA table_info(actions)")}
            for name, definition in (
                ("kind", "TEXT NOT NULL DEFAULT 'delegate'"),
                ("sequence", "INTEGER NOT NULL DEFAULT 1"),
                ("proposal_digest", "TEXT"),
            ):
                if name not in action_columns:
                    db.execute(f"ALTER TABLE actions ADD COLUMN {name} {definition}")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS actions_attempt_kind_sequence ON actions(attempt_id, kind, sequence)")

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=10) if self.read_only else sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @contextmanager
    def send_lock(self):
        """Serialize recovery claims with the physical adapter boundary."""
        path = self.path.with_suffix(".send.lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @staticmethod
    def _event(db: sqlite3.Connection, attempt_id: str, action_id: str | None, event: str, detail: str) -> None:
        db.execute("INSERT INTO events(at,attempt_id,action_id,event,detail) VALUES(?,?,?,?,?)", (utc_now(), attempt_id, action_id, event, detail))

    @staticmethod
    def _assert_owner(db: sqlite3.Connection, attempt_id: str, generation: int | None) -> None:
        row = db.execute("SELECT recovery_version,owner_generation,owner_actor FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        if row is None:
            raise ContractError("attempt missing")
        # The first-slice public calls lacked a fence parameter. Preserve that
        # narrow initial-owner compatibility only; once recovery has claimed an
        # attempt, every mutation needs the current generation.
        if generation is None and row[0] == 1:
            return
        if generation is None and row[0] == 2 and row[1] == 1 and row[2] == "initial":
            return
        if row[0] != 2 or row[1] != generation:
            raise ContractError("attempt ownership is stale or not recovery-capable")

    def create_attempt(self, envelope: dict[str, Any]) -> None:
        validate_envelope(envelope)
        protocol_version = execution_protocol_version(envelope)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO attempts(attempt_id,work_id,envelope_json,status,reason,receipt_path,recovery_version,owner_generation,owner_actor,execution_protocol_version) VALUES(?,?,?,?,?,?,?,?,?,?)", (envelope["attempt_id"], envelope["work_id"], canonical(envelope), "started", "", None, 2, 1, "initial", protocol_version))
            self._event(db, envelope["attempt_id"], None, "attempt_started", "")

    def claim_recovery(self, attempt_id: str, actor: str = "flow-recovery") -> int:
        with self.send_lock():
            return self._claim_recovery_locked(attempt_id, actor)

    def _claim_recovery_locked(self, attempt_id: str, actor: str) -> int:
        """Fence every former parent before a same-attempt recovery decision.

        A started action is uncertain across a process restart. This transition
        intentionally preserves its dispatch event and reserves capacity.
        """
        if not isinstance(actor, str) or not actor.strip() or len(actor) > 256:
            raise ContractError("recovery actor is invalid")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT recovery_version,owner_generation FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None:
                raise ContractError("attempt missing")
            if row[0] != 2:
                raise ContractError("historical attempt is read-only and cannot resume")
            generation = row[1] + 1
            db.execute("UPDATE attempts SET owner_generation=?,owner_actor=? WHERE attempt_id=?", (generation, actor, attempt_id))
            unknown = db.execute("SELECT action_id FROM actions WHERE attempt_id=? AND status='started'", (attempt_id,)).fetchall()
            for (action_id,) in unknown:
                db.execute("UPDATE actions SET status='unknown',reason='recovery_after_dispatch' WHERE action_id=?", (action_id,))
                self._event(db, attempt_id, action_id, "worker_unknown", "recovery_after_dispatch")
            self._event(db, attempt_id, None, "recovery_claimed", canonical({"actor": actor, "generation": generation}))
            return generation

    def assert_owner(self, attempt_id: str, generation: int) -> None:
        with self._db() as db:
            self._assert_owner(db, attempt_id, generation)

    @staticmethod
    def _unresolved_action(db: sqlite3.Connection, attempt_id: str) -> str | None:
        row = db.execute(
            "SELECT action_id FROM actions WHERE attempt_id=? AND status IN ('started','unknown') ORDER BY rowid LIMIT 1",
            (attempt_id,),
        ).fetchone()
        return row[0] if row else None

    @staticmethod
    def _decision_from_action(row: tuple[Any, ...]) -> dict[str, Any]:
        action_id, status, reason, grant_id, result_json = row
        return {
            "allowed": status == "allowed",
            "reason": reason,
            "action_id": action_id,
            "grant_id": grant_id if status == "allowed" else None,
            "result": json.loads(result_json) if result_json else None,
            "replayed": True,
        }

    @staticmethod
    def _decision_from_replan(row: tuple[Any, ...]) -> dict[str, Any]:
        replan_id, status, reason = row
        return {"allowed": status == "allowed", "reason": reason, "replan_id": replan_id, "replayed": True}

    def decide(self, envelope: dict[str, Any], action: dict[str, Any], *, generation: int | None = None) -> dict[str, Any]:
        validate_action(envelope, action)
        aid, attempt = action["action_id"], envelope["attempt_id"]
        protocol_version = execution_protocol_version(envelope)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_owner(db, attempt, generation)
            stored = db.execute("SELECT envelope_json,status,execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt,)).fetchone()
            if stored is None or stored[0] != canonical(envelope) or stored[1] != "started" or stored[2] != protocol_version:
                raise ContractError("attempt is absent, changed, or closed")
            request_json = canonical(action)
            existing = db.execute("SELECT request_json,status,reason,grant_id,result_json FROM actions WHERE action_id=?", (aid,)).fetchone()
            if existing:
                if existing[0] != request_json:
                    raise ContractError("action ID reused with changed payload")
                self._event(db, attempt, aid, "duplicate_request", existing[1])
                if protocol_version == 2:
                    return self._decision_from_action((aid, *existing[1:]))
                return {"allowed": False, "reason": "duplicate_request", "action_id": aid}
            slot = db.execute("SELECT action_id,request_json,status,reason,grant_id,result_json FROM actions WHERE attempt_id=? AND kind='delegate' AND sequence=?", (attempt, action["sequence"])).fetchone()
            if slot:
                if slot[1] == request_json:
                    self._event(db, attempt, slot[0], "duplicate_request", slot[2])
                    return self._decision_from_action((slot[0], *slot[2:]))
                raise ContractError("logical action slot already occupied")
            unresolved = self._unresolved_action(db, attempt)
            if unresolved:
                return {"allowed": False, "reason": "reconciliation_required", "action_id": aid}
            if protocol_version == 2:
                previous = db.execute("SELECT COALESCE(MAX(sequence),0) FROM actions WHERE attempt_id=? AND kind='delegate'", (attempt,)).fetchone()[0]
                if action["sequence"] != previous + 1:
                    raise ContractError("action sequence is skipped or out of order")
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
            db.execute("INSERT INTO actions(action_id,attempt_id,request_json,status,reason,grant_id,result_json,kind,sequence,proposal_digest) VALUES(?,?,?,?,?,?,?,?,?,?)", (aid, attempt, request_json, "allowed" if grant else "denied", reason, grant, None, "delegate", action["sequence"], hashlib.sha256(request_json.encode()).hexdigest()))
            self._event(db, attempt, aid, "policy_allowed" if grant else "policy_denied", reason)
            return {"allowed": bool(grant), "reason": reason, "action_id": aid, "grant_id": grant}

    def decide_replan(self, envelope: dict[str, Any], replan: dict[str, Any], *, generation: int | None = None) -> dict[str, Any]:
        """Persist a Flow policy decision for an ordered replan request.

        Replans have no grant and cannot cause an action or adapter send. The
        v2 table records the cap denial as evidence that the child was stopped.
        """
        validate_replan(envelope, replan)
        attempt, replan_id = envelope["attempt_id"], replan["replan_id"]
        request_json = canonical(replan)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_owner(db, attempt, generation)
            stored = db.execute("SELECT envelope_json,status,execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt,)).fetchone()
            if stored is None or stored[0] != canonical(envelope) or stored[1] != "started" or stored[2] != 2:
                raise ContractError("attempt is absent, changed, or closed")
            existing = db.execute("SELECT request_json,status,reason FROM replan_decisions WHERE replan_id=?", (replan_id,)).fetchone()
            if existing:
                if existing[0] != request_json:
                    raise ContractError("replan ID reused with changed payload")
                self._event(db, attempt, replan_id, "duplicate_replan", existing[1])
                return self._decision_from_replan((replan_id, existing[1], existing[2]))
            slot = db.execute("SELECT replan_id,request_json,status,reason FROM replan_decisions WHERE attempt_id=? AND sequence=?", (attempt, replan["sequence"])).fetchone()
            if slot:
                if slot[1] == request_json:
                    self._event(db, attempt, slot[0], "duplicate_replan", slot[2])
                    return self._decision_from_replan((slot[0], slot[2], slot[3]))
                raise ContractError("logical replan slot already occupied")
            unresolved = self._unresolved_action(db, attempt)
            if unresolved:
                return {"allowed": False, "reason": "reconciliation_required", "replan_id": replan_id}
            previous = db.execute("SELECT COALESCE(MAX(sequence),0) FROM replan_decisions WHERE attempt_id=?", (attempt,)).fetchone()[0]
            if replan["sequence"] != previous + 1:
                raise ContractError("replan sequence is skipped or out of order")
            allowed = replan["sequence"] <= envelope["limits"]["max_replans"]
            reason = "allowed" if allowed else "replan_cap"
            db.execute("INSERT INTO replan_decisions(replan_id,attempt_id,sequence,request_json,proposal_digest,status,reason) VALUES(?,?,?,?,?,?,?)", (replan_id, attempt, replan["sequence"], request_json, hashlib.sha256(request_json.encode()).hexdigest(), "allowed" if allowed else "denied", reason))
            self._event(db, attempt, replan_id, "replan_allowed" if allowed else "replan_denied", reason)
            return {"allowed": allowed, "reason": reason, "replan_id": replan_id}

    def consume_grant(self, action_id: str, grant_id: str, *, generation: int | None = None) -> bool:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status,grant_id FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if row:
                self._assert_owner(db, row[0], generation)
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

    def observe_send(self, action_id: str, generation: int) -> None:
        """Record the gateway-side adapter boundary after a fenced grant use."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if not row:
                raise ContractError("action missing")
            self._assert_owner(db, row[0], generation)
            if row[1] != "started":
                raise ContractError("action is not ready for send observation")
            existing = db.execute("SELECT 1 FROM events WHERE action_id=? AND event='adapter_send_started'", (action_id,)).fetchone()
            if existing:
                raise ContractError("adapter send was already observed")
            self._event(db, row[0], action_id, "adapter_send_started", "flow_observed_boundary")

    def observe_response(self, action_id: str, result: dict[str, Any], generation: int) -> dict[str, Any]:
        """Durably retain a validated normalized response before replaying it."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if not row:
                raise ContractError("action missing")
            self._assert_owner(db, row[0], generation)
            envelope_row = db.execute("SELECT envelope_json FROM attempts WHERE attempt_id=?", (row[0],)).fetchone()
            envelope = json.loads(envelope_row[0])
            validate_result(envelope, result)
            encoded = canonical(result)
            stored = db.execute("SELECT result_json,result_digest FROM response_observations WHERE action_id=?", (action_id,)).fetchone()
            if stored:
                if stored[0] != encoded:
                    raise ContractError("response observation conflicts with durable response")
                return json.loads(stored[0])
            if row[1] not in {"started", "unknown"}:
                raise ContractError("action cannot accept a response observation")
            db.execute("INSERT INTO response_observations VALUES(?,?,?,?,?)", (action_id, utc_now(), encoded, hashlib.sha256(encoded.encode()).hexdigest(), generation))
            self._event(db, row[0], action_id, "response_observed", result.get("output_sha256", ""))
            return result

    def complete(self, action_id: str, result: dict[str, Any], *, generation: int | None = None) -> None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if row:
                self._assert_owner(db, row[0], generation)
            if not row or (row[1] != "started" and not (generation is not None and row[1] == "unknown")):
                raise ContractError("action is not physically started")
            status = result.get("status")
            if status not in {"completed", "failed"}:
                raise ContractError("invalid worker result status")
            if generation is not None and status == "completed":
                observed = db.execute("SELECT result_json FROM response_observations WHERE action_id=?", (action_id,)).fetchone()
                if observed is None or observed[0] != canonical(result):
                    raise ContractError("completed result lacks matching durable response observation")
            db.execute("UPDATE actions SET status=?,result_json=? WHERE action_id=?", (status, canonical(result), action_id))
            self._event(db, row[0], action_id, "worker_" + status, result.get("output_sha256", ""))

    def mark_unknown(self, action_id: str, reason: str, *, generation: int | None = None) -> None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if row:
                self._assert_owner(db, row[0], generation)
            if row and row[1] == "started":
                db.execute("UPDATE actions SET status='unknown',reason=? WHERE action_id=?", (reason, action_id))
                self._event(db, row[0], action_id, "worker_unknown", reason)

    def resolve_unknown(self, attempt_id: str, action_id: str, actor: str, disposition: str,
                        explanation: str, evidence: list[dict[str, Any]], *, generation: int | None = None) -> dict[str, Any]:
        """Append an evidence-backed operator resolution without rewriting history."""
        validate_recovery_resolution(disposition, explanation, evidence)
        if not isinstance(actor, str) or not actor.strip() or len(actor.encode()) > 256:
            raise ContractError("recovery actor is invalid")
        if disposition == "resolved_not_dispatched" and not any(item["kind"] == "positive_no_send" for item in evidence):
            raise ContractError("no-dispatch resolution requires positive no-send evidence")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status,attempt_id FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if row is None or row[1] != attempt_id:
                raise ContractError("resolution action does not belong to attempt")
            self._assert_owner(db, attempt_id, generation)
            resolved = {"attempt_id": attempt_id, "action_id": action_id, "actor": actor,
                        "disposition": disposition, "explanation": explanation, "evidence": evidence}
            record_digest = hashlib.sha256(canonical(resolved).encode()).hexdigest()
            prior = db.execute("SELECT resolution_id,actor,disposition,explanation,evidence_json,result_json,created_at,owner_generation,resolution_digest FROM recovery_resolutions WHERE action_id=?", (action_id,)).fetchone()
            if prior:
                if prior[-1] != record_digest:
                    raise ContractError("conflicting recovery resolution")
                return {"resolution_id": prior[0], "attempt_id": attempt_id, "action_id": action_id,
                        "actor": prior[1], "disposition": prior[2], "explanation": prior[3],
                        "evidence": json.loads(prior[4]), "result": json.loads(prior[5]) if prior[5] else None,
                        "created_at": prior[6], "owner_generation": prior[7], "replayed": True}
            if row[0] not in {"unknown", "allowed"}:
                raise ContractError("only unresolved actions can be reconciled")
            if disposition == "resolved_completed":
                observed = db.execute("SELECT result_json,result_digest FROM response_observations WHERE action_id=?", (action_id,)).fetchone()
                if observed is None:
                    raise ContractError("completed resolution requires a durable validated response observation")
                if hashlib.sha256(observed[0].encode()).hexdigest() != observed[1]:
                    raise ContractError("durable response observation digest mismatch")
                envelope = json.loads(db.execute("SELECT envelope_json FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()[0])
                validate_result(envelope, json.loads(observed[0]))
            if disposition == "resolved_not_dispatched":
                if row[0] != "allowed":
                    raise ContractError("no-dispatch resolution requires an unconsumed grant")
                crossed = db.execute("SELECT 1 FROM events WHERE action_id=? AND event IN ('worker_dispatched','adapter_send_started')", (action_id,)).fetchone()
                if crossed:
                    raise ContractError("no-dispatch resolution conflicts with dispatch evidence")
            result_json = None
            if disposition == "resolved_completed":
                result_json = db.execute("SELECT result_json FROM response_observations WHERE action_id=?", (action_id,)).fetchone()[0]
                db.execute("UPDATE actions SET status='completed',result_json=?,reason='operator_resolved_completed' WHERE action_id=?", (result_json, action_id))
            elif disposition == "resolved_not_dispatched":
                db.execute("UPDATE actions SET status='not_dispatched',reason='operator_resolved_not_dispatched',grant_id=NULL WHERE action_id=?", (action_id,))
            resolution_id = uuid.uuid4().hex
            db.execute("INSERT INTO recovery_resolutions VALUES(?,?,?,?,?,?,?,?,?,?,?)", (resolution_id, attempt_id, action_id, actor, disposition, explanation, canonical(evidence), result_json, record_digest, utc_now(), generation or 0))
            self._event(db, attempt_id, action_id, "operator_resolution", canonical({"resolution_id": resolution_id, "disposition": disposition, "evidence_digest": hashlib.sha256(canonical(evidence).encode()).hexdigest()}))
            return {"resolution_id": resolution_id, **resolved, "result": json.loads(result_json) if result_json else None, "replayed": False}

    def regrant_not_dispatched(self, envelope: dict[str, Any], action: dict[str, Any], *, generation: int) -> dict[str, Any]:
        """Re-evaluate one proven-unsent logical action under the same identity."""
        validate_action(envelope, action)
        attempt_id, action_id = envelope["attempt_id"], action["action_id"]
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_owner(db, attempt_id, generation)
            stored = db.execute("SELECT envelope_json FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            row = db.execute("SELECT status,request_json FROM actions WHERE action_id=?", (action_id,)).fetchone()
            resolution = db.execute("SELECT disposition FROM recovery_resolutions WHERE action_id=?", (action_id,)).fetchone()
            if not stored or stored[0] != canonical(envelope) or not row or row[0] != "not_dispatched" or row[1] != canonical(action) or resolution != ("resolved_not_dispatched",):
                raise ContractError("action is not eligible for no-dispatch regrant")
            allowed_count = db.execute("SELECT count(*) FROM actions JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND actions.status IN ('allowed','started','completed','unknown')", (envelope["work_id"],)).fetchone()[0]
            concurrent_count = db.execute("SELECT count(*) FROM actions JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND actions.status IN ('allowed','started','unknown')", (envelope["work_id"],)).fetchone()[0]
            if allowed_count >= 6 or concurrent_count >= 3:
                reason = "delegation_cap" if allowed_count >= 6 else "concurrency_cap"
                self._event(db, attempt_id, action_id, "policy_denied", reason)
                return {"allowed": False, "reason": reason, "action_id": action_id}
            grant = uuid.uuid4().hex
            db.execute("UPDATE actions SET status='allowed',reason='regranted_after_no_dispatch',grant_id=? WHERE action_id=?", (grant, action_id))
            self._event(db, attempt_id, action_id, "policy_reallowed", "resolved_not_dispatched")
            return {"allowed": True, "reason": "regranted_after_no_dispatch", "action_id": action_id, "grant_id": grant}

    @staticmethod
    def _checkpoint_file(envelope: dict[str, Any], path: str, *, max_bytes: int) -> tuple[Path, str, int, bytes]:
        if not isinstance(path, str) or not path or not isinstance(max_bytes, int) or max_bytes < 1:
            raise ContractError("checkpoint path or size limit is invalid")
        root = Path(envelope["checkpoint_dir"])
        raw = Path(path)
        try:
            root_resolved = root.resolve(strict=True)
            resolved = raw.resolve(strict=True)
        except OSError as exc:
            raise ContractError("checkpoint file is absent") from exc
        if raw.is_symlink() or root.is_symlink() or resolved.parent != root_resolved:
            raise ContractError("checkpoint file is absent, linked, or outside attempt")
        root_fd = os.open(root_resolved, os.O_RDONLY | os.O_DIRECTORY)
        try:
            file_fd = os.open(resolved.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                before = os.fstat(file_fd)
                if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= max_bytes:
                    raise ContractError("checkpoint file exceeds size limit or is not regular")
                raw_bytes = os.read(file_fd, max_bytes + 1)
                after = os.fstat(file_fd)
                if (len(raw_bytes) != before.st_size or before.st_size != after.st_size
                        or before.st_mtime_ns != after.st_mtime_ns):
                    raise ContractError("checkpoint file changed while reading")
            finally:
                os.close(file_fd)
        finally:
            os.close(root_fd)
        return resolved, hashlib.sha256(raw_bytes).hexdigest(), len(raw_bytes), raw_bytes

    @staticmethod
    def _validate_maf_checkpoint(raw: bytes, checkpoint_id: str, kind: str, sequence: int) -> None:
        """Validate the safe JSON envelope around MAF's opaque saved state.

        Flow deliberately does not unpickle MAF internals. The storage JSON
        still supplies enough stable metadata to prove the linked position is
        the expected pending MAF request, rather than an arbitrary checkpoint
        with a borrowed filename.
        """
        try:
            value = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise ContractError("pending checkpoint is not MAF JSON") from exc
        if not isinstance(value, dict) or value.get("checkpoint_id") != checkpoint_id:
            raise ContractError("pending checkpoint ID does not match link")
        expected_workflow = "flow-maf-v2-action3" if kind == "pending_delegate" and sequence == 3 else "flow-maf-v2-initial"
        if value.get("workflow_name") != expected_workflow:
            raise ContractError("checkpoint workflow does not match position")
        pending = value.get("pending_request_info_events")
        request_id = f"flow-action-{sequence}" if kind == "pending_delegate" else f"flow-replan-{sequence}"
        if not isinstance(pending, dict) or set(pending) != {request_id} or not isinstance(pending[request_id], dict):
            raise ContractError("checkpoint request does not match position")

    def bind_checkpoint_position(self, attempt_id: str, kind: str, sequence: int, checkpoint_id: str,
                                 checkpoint_envelope_digest: str, ledger_seq: int, format_version: int,
                                 runtime_version: str, path: str, *, generation: int,
                                 max_bytes: int = 65536) -> dict[str, Any]:
        """Bind a v2 checkpoint to one completed Flow decision position.

        The persisted barrier is descriptive recovery evidence only. It never
        authorizes a grant, a replan, or a provider send.
        """
        if kind not in {"delegate", "pending_delegate", "replan"} or not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ContractError("checkpoint position is invalid")
        if not isinstance(checkpoint_id, str) or not checkpoint_id or not isinstance(ledger_seq, int) or ledger_seq < 0:
            raise ContractError("checkpoint link is invalid")
        if format_version != 1 or not isinstance(runtime_version, str) or not runtime_version:
            raise ContractError("checkpoint version is invalid")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_owner(db, attempt_id, generation)
            row = db.execute("SELECT envelope_json,execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row[1] != 2:
                raise ContractError("checkpoint positions require execution protocol v2")
            envelope = json.loads(row[0])
            if checkpoint_envelope_digest != envelope_digest(envelope):
                raise ContractError("checkpoint envelope digest mismatch")
            if kind in {"delegate", "pending_delegate"}:
                position = db.execute("SELECT status FROM actions WHERE attempt_id=? AND kind='delegate' AND sequence=?", (attempt_id, sequence)).fetchone()
                expected_status = "allowed" if kind == "pending_delegate" else "completed"
                if position is None or position[0] != expected_status:
                    raise ContractError("checkpoint action position is not completed")
            else:
                position = db.execute("SELECT status FROM replan_decisions WHERE attempt_id=? AND sequence=?", (attempt_id, sequence)).fetchone()
                if position is None:
                    raise ContractError("checkpoint replan position is absent")
            high_water = db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
            prior = db.execute("SELECT checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,protocol_version,path,file_sha256,file_size,bound_at,owner_generation FROM checkpoint_position_links WHERE attempt_id=? AND kind=? AND sequence=?", (attempt_id, kind, sequence)).fetchone()
            if ledger_seq != high_water and prior is None:
                raise ContractError("checkpoint ledger barrier mismatch")
            checkpoint_path, file_sha256, file_size, raw = self._checkpoint_file(envelope, path, max_bytes=max_bytes)
            if kind == "pending_delegate" or (kind == "delegate" and sequence in {1, 2}):
                self._validate_maf_checkpoint(raw, checkpoint_id, kind, sequence)
            record = {"attempt_id": attempt_id, "kind": kind, "sequence": sequence, "checkpoint_id": checkpoint_id,
                      "envelope_digest": checkpoint_envelope_digest, "ledger_seq": ledger_seq,
                      "format_version": format_version, "runtime_version": runtime_version,
                      "protocol_version": 2, "path": str(checkpoint_path), "file_sha256": file_sha256,
                      "file_size": file_size, "owner_generation": generation}
            if prior:
                old = {"attempt_id": attempt_id, "kind": kind, "sequence": sequence, "checkpoint_id": prior[0],
                       "envelope_digest": prior[1], "ledger_seq": prior[2], "format_version": prior[3],
                       "runtime_version": prior[4], "protocol_version": prior[5], "path": prior[6],
                       "file_sha256": prior[7], "file_size": prior[8], "owner_generation": prior[10]}
                if old != record:
                    raise ContractError("checkpoint position conflicts with durable checkpoint")
                return {**record, "bound_at": prior[9], "replayed": True}
            bound_at = utc_now()
            db.execute("INSERT INTO checkpoint_position_links(attempt_id,kind,sequence,checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,protocol_version,path,file_sha256,file_size,bound_at,owner_generation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (attempt_id, kind, sequence, checkpoint_id, checkpoint_envelope_digest, ledger_seq, format_version, runtime_version, 2, str(checkpoint_path), file_sha256, file_size, bound_at, generation))
            self._event(db, attempt_id, None, "checkpoint_position_bound", canonical({"kind": kind, "sequence": sequence, "checkpoint_id": checkpoint_id, "ledger_seq": ledger_seq}))
            return {**record, "bound_at": bound_at, "replayed": False}

    def read_checkpoint_position(self, attempt_id: str, kind: str, sequence: int, *, max_bytes: int = 65536) -> dict[str, Any]:
        """Return a bounded checkpoint only after all Flow-owned link checks pass."""
        if kind not in {"delegate", "pending_delegate", "replan"} or not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ContractError("checkpoint position is invalid")
        with self._db() as db:
            row = db.execute("SELECT envelope_json,execution_protocol_version,owner_generation FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            link = db.execute("SELECT checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,protocol_version,path,file_sha256,file_size,bound_at,owner_generation FROM checkpoint_position_links WHERE attempt_id=? AND kind=? AND sequence=?", (attempt_id, kind, sequence)).fetchone()
            if row is None or link is None or row[1] != 2 or link[5] != 2 or link[3] != 1:
                raise ContractError("checkpoint position is absent or incompatible")
            envelope = json.loads(row[0])
            if link[1] != envelope_digest(envelope) or link[10] > row[2]:
                raise ContractError("checkpoint position is stale or foreign")
            high_water = db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
            if high_water < link[2]:
                raise ContractError("checkpoint ledger barrier is unavailable")
        checkpoint_path, file_sha256, file_size, raw = self._checkpoint_file(envelope, link[6], max_bytes=max_bytes)
        if file_sha256 != link[7] or file_size != link[8]:
            raise ContractError("checkpoint file digest or size changed")
        if kind == "pending_delegate" or (kind == "delegate" and sequence in {1, 2}):
            self._validate_maf_checkpoint(raw, link[0], kind, sequence)
        metadata = {"attempt_id": attempt_id, "kind": kind, "sequence": sequence, "checkpoint_id": link[0],
                    "envelope_digest": link[1], "ledger_seq": link[2], "format_version": link[3],
                    "runtime_version": link[4], "protocol_version": link[5], "path": str(checkpoint_path),
                    "file_sha256": link[7], "file_size": link[8], "bound_at": link[9], "owner_generation": link[10]}
        return {"metadata": metadata, "bytes": raw}

    def bind_checkpoint(self, attempt_id: str, checkpoint_id: str, checkpoint_envelope_digest: str,
                        ledger_seq: int, format_version: int, runtime_version: str, path: str,
                        *, generation: int) -> dict[str, Any]:
        """Bind MAF state to a Flow-owned recovery barrier; never grant from it."""
        if not isinstance(checkpoint_id, str) or not checkpoint_id or not isinstance(ledger_seq, int) or ledger_seq < 0:
            raise ContractError("checkpoint link is invalid")
        if format_version != 1 or not isinstance(runtime_version, str) or not runtime_version or not isinstance(path, str) or not path:
            raise ContractError("checkpoint version or path is invalid")
        checkpoint_path = Path(path)
        if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
            raise ContractError("checkpoint file is absent or linked")
        file_sha256 = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_owner(db, attempt_id, generation)
            envelope = json.loads(db.execute("SELECT envelope_json FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()[0])
            if checkpoint_envelope_digest != envelope_digest(envelope):
                raise ContractError("checkpoint envelope digest mismatch")
            record = {"attempt_id": attempt_id, "checkpoint_id": checkpoint_id, "envelope_digest": checkpoint_envelope_digest,
                      "ledger_seq": ledger_seq, "format_version": format_version, "runtime_version": runtime_version, "path": path,
                      "owner_generation": generation, "file_sha256": file_sha256}
            prior = db.execute("SELECT checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,path,owner_generation,bound_at,file_sha256 FROM checkpoint_links WHERE attempt_id=?", (attempt_id,)).fetchone()
            if prior:
                old = {"attempt_id": attempt_id, "checkpoint_id": prior[0], "envelope_digest": prior[1], "ledger_seq": prior[2], "format_version": prior[3], "runtime_version": prior[4], "path": prior[5], "owner_generation": prior[6], "file_sha256": prior[8]}
                if old != record:
                    raise ContractError("checkpoint link conflicts with durable checkpoint")
                return {**record, "bound_at": prior[7], "replayed": True}
            high_water = db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
            if ledger_seq != high_water:
                raise ContractError("checkpoint ledger barrier mismatch")
            bound_at = utc_now()
            db.execute("INSERT INTO checkpoint_links(attempt_id,checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,path,bound_at,owner_generation,file_sha256) VALUES(?,?,?,?,?,?,?,?,?,?)", (attempt_id, checkpoint_id, checkpoint_envelope_digest, ledger_seq, format_version, runtime_version, path, bound_at, generation, file_sha256))
            self._event(db, attempt_id, None, "checkpoint_bound", canonical({"checkpoint_id": checkpoint_id, "ledger_seq": ledger_seq, "format_version": format_version}))
            return {**record, "bound_at": bound_at, "replayed": False}

    def finish_attempt(self, attempt_id: str, status: str, reason: str, receipt_path: str, *, generation: int | None = None) -> None:
        if status not in {"completed", "failed", "denied", "unknown"}:
            raise ContractError("invalid attempt terminal status")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_owner(db, attempt_id, generation)
            row = db.execute("SELECT status FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row != ("started",):
                raise ContractError("attempt not active")
            db.execute("UPDATE attempts SET status=?,reason=?,receipt_path=? WHERE attempt_id=?", (status, reason, receipt_path, attempt_id))
            self._event(db, attempt_id, None, "attempt_" + status, reason)

    def snapshot(self, attempt_id: str) -> dict[str, Any]:
        with self._db() as db:
            attempt_columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
            recovery_columns = {"recovery_version", "owner_generation", "owner_actor"}.issubset(attempt_columns)
            protocol_column = "execution_protocol_version" in attempt_columns
            attempt_select = "attempt_id,work_id,envelope_json,status,reason,receipt_path" + (",recovery_version,owner_generation,owner_actor" if recovery_columns else "") + (",execution_protocol_version" if protocol_column else "")
            a = db.execute(f"SELECT {attempt_select} FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if not a:
                raise ContractError("attempt missing")
            actions = db.execute("SELECT action_id,request_json,status,reason,grant_id,result_json FROM actions WHERE attempt_id=? ORDER BY rowid", (attempt_id,)).fetchall()
            events = db.execute("SELECT seq,at,action_id,event,detail FROM events WHERE attempt_id=? ORDER BY seq", (attempt_id,)).fetchall()
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            observations = db.execute("SELECT action_id,observed_at,result_json,result_digest,owner_generation FROM response_observations WHERE action_id IN (SELECT action_id FROM actions WHERE attempt_id=?) ORDER BY observed_at", (attempt_id,)).fetchall() if "response_observations" in tables else []
            resolutions = db.execute("SELECT resolution_id,action_id,actor,disposition,explanation,evidence_json,result_json,resolution_digest,created_at,owner_generation FROM recovery_resolutions WHERE attempt_id=? ORDER BY created_at", (attempt_id,)).fetchall() if "recovery_resolutions" in tables else []
            replans = db.execute("SELECT replan_id,sequence,request_json,proposal_digest,status,reason FROM replan_decisions WHERE attempt_id=? ORDER BY sequence", (attempt_id,)).fetchall() if "replan_decisions" in tables else []
            checkpoint_positions = db.execute("SELECT kind,sequence,checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,protocol_version,path,file_sha256,file_size,bound_at,owner_generation FROM checkpoint_position_links WHERE attempt_id=? ORDER BY kind,sequence", (attempt_id,)).fetchall() if "checkpoint_position_links" in tables else []
            checkpoint_columns = {row[1] for row in db.execute("PRAGMA table_info(checkpoint_links)")} if "checkpoint_links" in tables else set()
            checkpoint_query = "SELECT checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,path,bound_at,owner_generation" + (",file_sha256" if "file_sha256" in checkpoint_columns else "") + " FROM checkpoint_links WHERE attempt_id=?"
            checkpoint = db.execute(checkpoint_query, (attempt_id,)).fetchone() if "checkpoint_links" in tables else None
        return {"attempt_id": a[0], "work_id": a[1], "envelope": json.loads(a[2]), "status": a[3], "reason": a[4], "receipt_path": a[5],
                "recovery_version": a[6] if recovery_columns else 1, "owner_generation": a[7] if recovery_columns else 0, "owner_actor": a[8] if recovery_columns else None,
                "execution_protocol_version": a[9 if recovery_columns else 6] if protocol_column else 1,
                "actions": [{"action_id": r[0], "request": json.loads(r[1]), "status": r[2], "reason": r[3], "grant_id": r[4], "result": json.loads(r[5]) if r[5] else None} for r in actions],
                "replans": [{"replan_id": r[0], "sequence": r[1], "request": json.loads(r[2]), "proposal_digest": r[3], "status": r[4], "reason": r[5]} for r in replans],
                "checkpoint_positions": [{"kind": r[0], "sequence": r[1], "checkpoint_id": r[2], "envelope_digest": r[3], "ledger_seq": r[4], "format_version": r[5], "runtime_version": r[6], "protocol_version": r[7], "path": r[8], "file_sha256": r[9], "file_size": r[10], "bound_at": r[11], "owner_generation": r[12]} for r in checkpoint_positions],
                "events": [{"seq": r[0], "at": r[1], "action_id": r[2], "event": r[3], "detail": r[4]} for r in events],
                "response_observations": [{"action_id": r[0], "observed_at": r[1], "result": json.loads(r[2]), "result_digest": r[3], "owner_generation": r[4]} for r in observations],
                "resolutions": [{"resolution_id": r[0], "action_id": r[1], "actor": r[2], "disposition": r[3], "explanation": r[4], "evidence": json.loads(r[5]), "result": json.loads(r[6]) if r[6] else None, "resolution_digest": r[7], "created_at": r[8], "owner_generation": r[9]} for r in resolutions],
                "checkpoint": ({"checkpoint_id": checkpoint[0], "envelope_digest": checkpoint[1], "ledger_seq": checkpoint[2], "format_version": checkpoint[3], "runtime_version": checkpoint[4], "path": checkpoint[5], "bound_at": checkpoint[6], "owner_generation": checkpoint[7], "file_sha256": checkpoint[8] if len(checkpoint) > 8 else None} if checkpoint else None)}
