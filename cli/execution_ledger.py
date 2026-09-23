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
    validate_manager_call,
)
from verifier_contracts import VerifierContractError, validate_evaluation, validate_structured_verifier_result


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
            CREATE TABLE IF NOT EXISTS manager_calls (
                call_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                sequence INTEGER NOT NULL, request_json TEXT NOT NULL, status TEXT NOT NULL,
                reason TEXT NOT NULL, grant_id TEXT UNIQUE, result_json TEXT,
                observed_at TEXT, UNIQUE(attempt_id,sequence)
            );
            CREATE TABLE IF NOT EXISTS magentic_checkpoint_links (
                attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                pending_kind TEXT NOT NULL, pending_id TEXT NOT NULL,
                checkpoint_id TEXT NOT NULL, ledger_seq INTEGER NOT NULL,
                path TEXT NOT NULL, file_sha256 TEXT NOT NULL, file_size INTEGER NOT NULL,
                bound_at TEXT NOT NULL, owner_generation INTEGER NOT NULL,
                PRIMARY KEY(attempt_id,pending_kind,pending_id)
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
            CREATE TABLE IF NOT EXISTS continuation_epochs (
                epoch_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                action_id TEXT NOT NULL REFERENCES actions(action_id),
                resolution_id TEXT NOT NULL REFERENCES recovery_resolutions(resolution_id),
                receipt_sha256 TEXT NOT NULL, checkpoint_sha256 TEXT NOT NULL,
                status TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', receipt_path TEXT,
                owner_generation INTEGER NOT NULL DEFAULT 1, owner_actor TEXT NOT NULL,
                created_at TEXT NOT NULL, sealed_receipt_sha256 TEXT, policy_before_json TEXT,
                UNIQUE(attempt_id,action_id)
            );
            CREATE TABLE IF NOT EXISTS continuation_grants (
                grant_id TEXT PRIMARY KEY, epoch_id TEXT NOT NULL REFERENCES continuation_epochs(epoch_id),
                issued_at TEXT NOT NULL, status TEXT NOT NULL,
                claimed_at TEXT, UNIQUE(epoch_id)
            );
            CREATE TABLE IF NOT EXISTS continuation_responses (
                epoch_id TEXT PRIMARY KEY REFERENCES continuation_epochs(epoch_id),
                result_json TEXT NOT NULL, result_digest TEXT NOT NULL, observed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verifier_inputs (
                action_id TEXT PRIMARY KEY REFERENCES actions(action_id), recorded_at TEXT NOT NULL,
                input_json TEXT NOT NULL, input_digest TEXT NOT NULL, diff_digest TEXT NOT NULL,
                test_digest TEXT NOT NULL, send_claimed_at TEXT, owner_generation INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS verifier_evaluations (
                action_id TEXT PRIMARY KEY REFERENCES actions(action_id), evaluated_at TEXT NOT NULL,
                evaluation_json TEXT NOT NULL, evaluation_digest TEXT NOT NULL, outcome TEXT NOT NULL,
                reason TEXT NOT NULL, owner_generation INTEGER NOT NULL
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
            # Older databases may already contain duplicate historical action
            # positions.  Do not make those receipts unreadable merely to add
            # a new lookup constraint. New writes are fenced by ``decide``'s
            # transactional slot check; retain a non-unique lookup index when
            # a legacy unique-index migration cannot be applied.
            try:
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS actions_attempt_kind_sequence ON actions(attempt_id, kind, sequence)")
            except sqlite3.IntegrityError:
                db.execute("CREATE INDEX IF NOT EXISTS actions_attempt_kind_sequence_lookup ON actions(attempt_id, kind, sequence)")
            continuation_columns = {row[1] for row in db.execute("PRAGMA table_info(continuation_epochs)")}
            if "sealed_receipt_sha256" not in continuation_columns:
                db.execute("ALTER TABLE continuation_epochs ADD COLUMN sealed_receipt_sha256 TEXT")
            if "policy_before_json" not in continuation_columns:
                db.execute("ALTER TABLE continuation_epochs ADD COLUMN policy_before_json TEXT")

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

    @staticmethod
    def _magentic_continuation_open(db: sqlite3.Connection, attempt_id: str) -> bool:
        return db.execute(
            "SELECT 1 FROM continuation_epochs JOIN recovery_resolutions USING(resolution_id) "
            "WHERE continuation_epochs.attempt_id=? AND continuation_epochs.status='running' "
            "AND recovery_resolutions.disposition='resolved_completed'",
            (attempt_id,),
        ).fetchone() is not None

    def create_attempt(self, envelope: dict[str, Any]) -> None:
        validate_envelope(envelope)
        protocol_version = execution_protocol_version(envelope)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            claim = envelope.get("delivery_lead_claim") if protocol_version in {7, 8} else None
            owner_generation = claim["generation"] if isinstance(claim, dict) else 1
            owner_actor = claim["lead_id"] if isinstance(claim, dict) else "initial"
            db.execute("INSERT INTO attempts(attempt_id,work_id,envelope_json,status,reason,receipt_path,recovery_version,owner_generation,owner_actor,execution_protocol_version) VALUES(?,?,?,?,?,?,?,?,?,?)", (envelope["attempt_id"], envelope["work_id"], canonical(envelope), "started", "", None, 2, owner_generation, owner_actor, protocol_version))
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
            manager_unknown = db.execute("SELECT call_id FROM manager_calls WHERE attempt_id=? AND status='started'", (attempt_id,)).fetchall()
            for (call_id,) in manager_unknown:
                db.execute("UPDATE manager_calls SET status='unknown',reason='recovery_after_dispatch' WHERE call_id=?", (call_id,))
                self._event(db, attempt_id, call_id, "manager_unknown", "recovery_after_dispatch")
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
        if row:
            return row[0]
        manager = db.execute("SELECT call_id FROM manager_calls WHERE attempt_id=? AND status IN ('started','unknown') ORDER BY rowid LIMIT 1", (attempt_id,)).fetchone()
        return manager[0] if manager else None

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
            if (stored is None or stored[0] != canonical(envelope) or stored[2] != protocol_version
                    or not (stored[1] == "started" or protocol_version == 5 and stored[1] == "unknown"
                            and self._magentic_continuation_open(db, attempt))):
                raise ContractError("attempt is absent, changed, or closed")
            request_json = canonical(action)
            existing = db.execute("SELECT request_json,status,reason,grant_id,result_json FROM actions WHERE action_id=?", (aid,)).fetchone()
            if existing:
                if existing[0] != request_json:
                    raise ContractError("action ID reused with changed payload")
                self._event(db, attempt, aid, "duplicate_request", existing[1])
                if protocol_version in {2, 3, 4, 5, 6, 7, 8}:
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
            if protocol_version in {2, 3, 4, 5, 6, 7, 8}:
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
            if protocol_version in {5, 6, 7, 8}:
                completed_producer = False
                if protocol_version in {6, 7, 8} and action["instance_id"] in envelope["job_contract"]["producer_instance_ids"]:
                    prior_completed = db.execute(
                        "SELECT request_json FROM actions WHERE attempt_id=? AND status='completed'",
                        (attempt,),
                    ).fetchall()
                    completed_producer = any(
                        json.loads(row[0]).get("instance_id") in envelope["job_contract"]["producer_instance_ids"]
                        for row in prior_completed
                    )
                paid_count = db.execute(
                    "SELECT count(*) FROM actions WHERE attempt_id=? "
                    "AND json_extract(request_json,'$.provider') IN ('codex','claude') "
                    "AND actions.status IN ('allowed','started','completed','unknown','failed','not_dispatched')",
                    (attempt,),
                ).fetchone()[0]
                paid_delegations = db.execute(
                    "SELECT count(*) FROM actions WHERE attempt_id=? "
                    "AND json_extract(request_json,'$.provider') IN ('codex','claude') "
                    "AND status IN ('allowed','started','completed','unknown')",
                    (attempt,),
                ).fetchone()[0]
                chartered_delegations = db.execute(
                    "SELECT count(*) FROM actions WHERE attempt_id=? "
                    "AND status IN ('allowed','started','completed','unknown','failed')",
                    (attempt,),
                ).fetchone()[0] if protocol_version in {6, 7, 8} else 0
                concurrent_count = db.execute(
                    "SELECT count(*) FROM actions WHERE attempt_id=? "
                    "AND status IN ('allowed','started','unknown')",
                    (attempt,),
                ).fetchone()[0]
                verifier_reserved = 0
                is_verifier = protocol_version == 8 and action["instance_id"] in envelope["job_contract"]["verifier_instance_ids"]
                if protocol_version == 8:
                    verifier_ids = set(envelope["job_contract"]["verifier_instance_ids"])
                    verifier_reserved = sum(
                        1 for request_json, status in db.execute(
                            "SELECT request_json,status FROM actions WHERE attempt_id=? "
                            "AND status IN ('allowed','started','completed','failed','unknown')", (attempt,)
                        )
                        if json.loads(request_json).get("instance_id") in verifier_ids
                    )
                    latest_verifier_outcome = db.execute(
                        "SELECT verifier_evaluations.outcome FROM verifier_evaluations "
                        "JOIN actions USING(action_id) WHERE actions.attempt_id=? "
                        "ORDER BY verifier_evaluations.evaluated_at DESC, verifier_evaluations.rowid DESC LIMIT 1",
                        (attempt,),
                    ).fetchone()
                if completed_producer:
                    reason = "producer_already_completed"
                elif is_verifier and verifier_reserved >= envelope["limits"]["max_verifier_calls"]:
                    reason = "verifier_call_cap"
                elif is_verifier and verifier_reserved > 0 and (
                        latest_verifier_outcome is None
                        or latest_verifier_outcome[0] not in {"valid_fail", "unusable"}):
                    reason = "verifier_retry_denied"
                elif action["provider"] in {"codex", "claude"} and paid_count >= envelope["limits"]["max_paid_worker_calls"]:
                    reason = "paid_call_cap"
                elif (chartered_delegations if protocol_version in {6, 7, 8} else paid_delegations) >= envelope["limits"]["max_delegations"]:
                    reason = "delegation_cap"
                elif concurrent_count >= envelope["limits"]["max_concurrent"]:
                    reason = "concurrency_cap"
                else:
                    reason = "allowed"
            elif protocol_version in {3, 4}:
                paid_provider = "codex" if protocol_version == 3 else "claude"
                paid_count = db.execute(
                    "SELECT count(*) FROM actions JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND json_extract(actions.request_json,'$.provider')=? AND actions.status IN ('allowed','started','completed','unknown','failed','not_dispatched')",
                    (work_id, paid_provider),
                ).fetchone()[0]
                if action["provider"] == paid_provider and paid_count >= envelope["limits"][f"max_{paid_provider}_calls"]:
                    reason = f"{paid_provider}_call_cap"
                elif allowed_count >= envelope["limits"]["max_delegations"]:
                    reason = "delegation_cap"
                elif concurrent_count >= envelope["limits"]["max_concurrent"]:
                    reason = "concurrency_cap"
                else:
                    reason = "allowed"
            elif action["role"] != "test-engineer":
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
            if (stored is None or stored[0] != canonical(envelope) or stored[2] not in {2, 5, 6}
                    or not (stored[1] == "started" or stored[2] == 5 and stored[1] == "unknown"
                            and self._magentic_continuation_open(db, attempt))):
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
            if stored[2] in {5, 6, 7, 8}:
                prior_attempt_replans = db.execute(
                    "SELECT COUNT(*) FROM replan_decisions WHERE attempt_id=? AND status='allowed'",
                    (attempt,),
                ).fetchone()[0]
                allowed = prior_attempt_replans < envelope["limits"]["max_replans"]
            else:
                allowed = replan["sequence"] <= envelope["limits"]["max_replans"]
            reason = "allowed" if allowed else "replan_cap"
            db.execute("INSERT INTO replan_decisions(replan_id,attempt_id,sequence,request_json,proposal_digest,status,reason) VALUES(?,?,?,?,?,?,?)", (replan_id, attempt, replan["sequence"], request_json, hashlib.sha256(request_json.encode()).hexdigest(), "allowed" if allowed else "denied", reason))
            self._event(db, attempt, replan_id, "replan_allowed" if allowed else "replan_denied", reason)
            return {"allowed": allowed, "reason": reason, "replan_id": replan_id}

    def decide_manager_call(self, envelope: dict[str, Any], request: dict[str, Any], *, generation: int | None = None) -> dict[str, Any]:
        """Authorize one stock-manager model call, without choosing its response."""
        validate_manager_call(envelope, request)
        attempt, call_id = envelope["attempt_id"], request["call_id"]
        encoded = canonical(request)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_owner(db, attempt, generation)
            stored = db.execute("SELECT envelope_json,status,execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt,)).fetchone()
            if (stored is None or stored[0] != canonical(envelope) or stored[2] not in {5, 6, 7, 8}
                    or not (stored[1] == "started" or stored[1] == "unknown"
                            and self._magentic_continuation_open(db, attempt))):
                raise ContractError("attempt is absent, changed, or closed")
            existing = db.execute("SELECT request_json,status,reason,grant_id,result_json FROM manager_calls WHERE call_id=?", (call_id,)).fetchone()
            if existing:
                if existing[0] != encoded:
                    raise ContractError("manager call ID reused with changed payload")
                self._event(db, attempt, call_id, "duplicate_manager_request", existing[1])
                return {"allowed": existing[1] == "allowed", "reason": existing[2], "call_id": call_id,
                        "grant_id": existing[3] if existing[1] == "allowed" else None,
                        "result": json.loads(existing[4]) if existing[4] else None, "replayed": True}
            occupied = db.execute("SELECT call_id FROM manager_calls WHERE attempt_id=? AND sequence=?", (attempt, request["sequence"])).fetchone()
            if occupied:
                raise ContractError("manager call sequence already occupied")
            if self._unresolved_action(db, attempt):
                return {"allowed": False, "reason": "reconciliation_required", "call_id": call_id}
            previous = db.execute("SELECT COALESCE(MAX(sequence),0) FROM manager_calls WHERE attempt_id=?", (attempt,)).fetchone()[0]
            if request["sequence"] != previous + 1:
                raise ContractError("manager call sequence is skipped or out of order")
            reason = "allowed"
            if request["phase"] in {"replan_facts", "replan_plan"}:
                replan_sequence = request["replan_sequence"]
                linked = db.execute("SELECT status FROM replan_decisions WHERE attempt_id=? AND sequence=? AND replan_id=?",
                                    (attempt, replan_sequence, request["replan_id"])).fetchone()
                if linked != ("allowed",):
                    reason = "replan_not_authorized"
                else:
                    facts = db.execute("SELECT status FROM manager_calls WHERE attempt_id=? AND json_extract(request_json,'$.phase')='replan_facts' AND json_extract(request_json,'$.replan_sequence')=?", (attempt, replan_sequence)).fetchall()
                    plans = db.execute("SELECT status FROM manager_calls WHERE attempt_id=? AND json_extract(request_json,'$.phase')='replan_plan' AND json_extract(request_json,'$.replan_sequence')=?", (attempt, replan_sequence)).fetchall()
                    if request["phase"] == "replan_facts":
                        previous = db.execute("SELECT status FROM manager_calls WHERE attempt_id=? AND json_extract(request_json,'$.phase')='replan_plan' AND json_extract(request_json,'$.replan_sequence')=?", (attempt, replan_sequence - 1)).fetchall()
                        if facts or (replan_sequence > 1 and previous != [("completed",)]):
                            reason = "replan_out_of_order"
                    elif facts != [("completed",)] or plans:
                        reason = "replan_out_of_order"
            attempt_calls = db.execute(
                "SELECT COUNT(*) FROM manager_calls WHERE attempt_id=? "
                "AND status IN ('allowed','started','completed','unknown')",
                (attempt,),
            ).fetchone()[0]
            if envelope["manager"]["provider"] in {"codex", "claude"} and attempt_calls >= envelope["limits"]["max_manager_calls"]:
                reason = "manager_call_cap"
            elif request["manager_round"] > envelope["limits"]["max_manager_rounds"]:
                reason = "manager_round_cap"
            grant = uuid.uuid4().hex if reason == "allowed" else None
            db.execute("INSERT INTO manager_calls(call_id,attempt_id,sequence,request_json,status,reason,grant_id) VALUES(?,?,?,?,?,?,?)",
                       (call_id, attempt, request["sequence"], encoded, "allowed" if grant else "denied", reason, grant))
            self._event(db, attempt, call_id, "manager_policy_allowed" if grant else "manager_policy_denied", reason)
            return {"allowed": bool(grant), "reason": reason, "call_id": call_id, "grant_id": grant}

    def consume_manager_grant(self, call_id: str, grant_id: str, *, generation: int) -> bool:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status,grant_id FROM manager_calls WHERE call_id=?", (call_id,)).fetchone()
            if row is None:
                raise ContractError("manager call missing")
            self._assert_owner(db, row[0], generation)
            if row[1] != "allowed" or row[2] != grant_id:
                return False
            issued = db.execute("SELECT at FROM events WHERE action_id=? AND event='manager_policy_allowed' ORDER BY seq DESC LIMIT 1", (call_id,)).fetchone()
            if not issued or datetime.now(timezone.utc) > datetime.fromisoformat(issued[0]) + timedelta(seconds=60):
                db.execute("UPDATE manager_calls SET status='denied',reason='grant_expired' WHERE call_id=?", (call_id,))
                self._event(db, row[0], call_id, "manager_policy_denied", "grant_expired")
                return False
            db.execute("UPDATE manager_calls SET status='started' WHERE call_id=?", (call_id,))
            self._event(db, row[0], call_id, "manager_send_started", "grant_consumed")
            return True

    def observe_manager_response(self, call_id: str, response: dict[str, Any], *, generation: int) -> None:
        encoded = canonical(response)
        output = response.get("output") if isinstance(response, dict) else None
        usage = response.get("usage") if isinstance(response, dict) else None
        if (not isinstance(response, dict) or response.get("status") != "completed" or output is None
                or response.get("output_sha256") != hashlib.sha256(canonical(output).encode()).hexdigest()
                or len(encoded.encode()) > 65536 or
                (usage is not None and (not isinstance(usage, dict) or any(type(v) is not int or v < 0 for v in usage.values())))):
            raise ContractError("manager response is invalid")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status,result_json FROM manager_calls WHERE call_id=?", (call_id,)).fetchone()
            if row is None:
                raise ContractError("manager call missing")
            self._assert_owner(db, row[0], generation)
            if row[2] is not None:
                if row[2] != encoded:
                    raise ContractError("manager response conflicts with durable observation")
                return
            if row[1] not in {"started", "unknown"}:
                raise ContractError("manager call was not sent")
            db.execute("UPDATE manager_calls SET status='completed',result_json=?,observed_at=? WHERE call_id=?", (encoded, utc_now(), call_id))
            self._event(db, row[0], call_id, "manager_response_observed", response["output_sha256"])

    def mark_manager_unknown(self, call_id: str, reason: str, *, generation: int) -> None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status FROM manager_calls WHERE call_id=?", (call_id,)).fetchone()
            if row is None:
                raise ContractError("manager call missing")
            self._assert_owner(db, row[0], generation)
            if row[1] == "started":
                db.execute("UPDATE manager_calls SET status='unknown',reason=? WHERE call_id=?", (reason, call_id))
                self._event(db, row[0], call_id, "manager_unknown", reason)

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

    def prepare_verifier_send(self, action_id: str, grant_id: str, verifier_input: dict[str, Any],
                              diff_digest: str, test_digest: str, *, generation: int) -> dict[str, Any]:
        """Atomically bind v8 verifier input, consume its grant, and claim send."""
        if not isinstance(verifier_input, dict):
            raise ContractError("verifier input must be an object")
        if not all(isinstance(value, str) and len(value) == 64
                   and all(char in "0123456789abcdef" for char in value)
                   for value in (diff_digest, test_digest)):
            raise ContractError("verifier evidence digest is invalid")
        encoded = canonical(verifier_input)
        input_digest = hashlib.sha256(encoded.encode()).hexdigest()
        expired = False
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt, _, _ = self._v8_verifier_action(db, action_id)
            self._assert_owner(db, attempt, generation)
            row = db.execute("SELECT status,grant_id FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if row != ("allowed", grant_id):
                raise ContractError("verifier grant is absent or already consumed")
            issued = db.execute("SELECT at FROM events WHERE action_id=? AND event='policy_allowed' ORDER BY seq DESC LIMIT 1", (action_id,)).fetchone()
            if not issued or datetime.now(timezone.utc) > datetime.fromisoformat(issued[0]) + timedelta(seconds=60):
                # Commit the denial before refusing; raising inside the
                # transaction would roll it back and leave the grant reserved.
                db.execute("UPDATE actions SET status='denied',reason='grant_expired' WHERE action_id=?", (action_id,))
                self._event(db, attempt, action_id, "policy_denied", "grant_expired")
                expired = True
            elif db.execute("SELECT 1 FROM verifier_inputs WHERE action_id=?", (action_id,)).fetchone():
                raise ContractError("verifier input was already prepared")
            else:
                now = utc_now()
                db.execute("INSERT INTO verifier_inputs VALUES(?,?,?,?,?,?,?,?)",
                           (action_id, now, encoded, input_digest, diff_digest, test_digest, now, generation))
                db.execute("UPDATE actions SET status='started' WHERE action_id=?", (action_id,))
                self._event(db, attempt, action_id, "verifier_input_recorded", input_digest)
                self._event(db, attempt, action_id, "worker_dispatched", "grant_consumed")
                self._event(db, attempt, action_id, "adapter_send_started", "flow_observed_boundary")
                self._event(db, attempt, action_id, "verifier_send_claimed", "flow_observed_boundary")
        if expired:
            raise ContractError("verifier grant expired")
        return {"action_id": action_id, "input": verifier_input, "input_digest": input_digest,
                "diff_digest": diff_digest, "test_digest": test_digest,
                "recorded_at": now, "owner_generation": generation, "replayed": False}

    def close_pre_send_failure(self, action_id: str, grant_id: str, *, generation: int) -> None:
        """Close a guarded grant when the gateway failed before crossing dispatch.

        This is only valid for the exact still-allowed grant. A consumed grant
        or recorded adapter send can never be relabeled as safely unsent.
        """
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT actions.attempt_id,actions.status,actions.grant_id,attempts.execution_protocol_version "
                "FROM actions JOIN attempts USING(attempt_id) WHERE actions.action_id=?", (action_id,),
            ).fetchone()
            if row is None:
                raise ContractError("action missing")
            self._assert_owner(db, row[0], generation)
            if row[3] not in {3, 4, 5, 6, 8} or row[1] != "allowed" or row[2] != grant_id:
                raise ContractError("action is not an unconsumed mixed grant")
            crossed = db.execute(
                "SELECT 1 FROM events WHERE action_id=? AND event IN ('worker_dispatched','adapter_send_started')", (action_id,),
            ).fetchone()
            if crossed:
                raise ContractError("pre-send failure conflicts with dispatch evidence")
            db.execute("UPDATE actions SET status='not_dispatched',reason='pre_send_failure',grant_id=NULL WHERE action_id=?", (action_id,))
            self._event(db, row[0], action_id, "pre_send_failure", "checkpoint_or_grant_failed_before_dispatch")

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

    @staticmethod
    def _v8_verifier_action(db: sqlite3.Connection, action_id: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """Return the sealed v8 action and envelope or refuse a foreign caller."""
        row = db.execute(
            "SELECT actions.attempt_id,actions.request_json,attempts.envelope_json,attempts.execution_protocol_version "
            "FROM actions JOIN attempts USING(attempt_id) WHERE actions.action_id=?", (action_id,),
        ).fetchone()
        if row is None or row[3] != 8:
            raise ContractError("structured verifier action is absent or incompatible")
        action, envelope = json.loads(row[1]), json.loads(row[2])
        if action.get("instance_id") not in envelope.get("job_contract", {}).get("verifier_instance_ids", []):
            raise ContractError("action is not an approved structured verifier")
        return row[0], action, envelope

    def bind_verifier_input(self, action_id: str, verifier_input: dict[str, Any],
                            diff_digest: str, test_digest: str, *, generation: int) -> dict[str, Any]:
        """Persist the exact Flow-supplied verifier input before the send boundary."""
        if not isinstance(verifier_input, dict):
            raise ContractError("verifier input must be an object")
        if not all(isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)
                   for value in (diff_digest, test_digest)):
            raise ContractError("verifier evidence digest is invalid")
        encoded = canonical(verifier_input)
        input_digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt, _, _ = self._v8_verifier_action(db, action_id)
            self._assert_owner(db, attempt, generation)
            status = db.execute("SELECT status FROM actions WHERE action_id=?", (action_id,)).fetchone()[0]
            if status not in {"allowed", "started"}:
                raise ContractError("verifier input requires an active grant before send")
            prior = db.execute(
                "SELECT input_json,input_digest,diff_digest,test_digest,recorded_at,owner_generation "
                "FROM verifier_inputs WHERE action_id=?", (action_id,),
            ).fetchone()
            record = {"action_id": action_id, "input": verifier_input, "input_digest": input_digest,
                      "diff_digest": diff_digest, "test_digest": test_digest}
            if prior:
                if prior[:4] != (encoded, input_digest, diff_digest, test_digest):
                    raise ContractError("verifier input conflicts with durable binding")
                return {**record, "recorded_at": prior[4], "owner_generation": prior[5], "replayed": True}
            recorded_at = utc_now()
            db.execute("INSERT INTO verifier_inputs(action_id,recorded_at,input_json,input_digest,diff_digest,test_digest,send_claimed_at,owner_generation) VALUES(?,?,?,?,?,?,NULL,?)",
                       (action_id, recorded_at, encoded, input_digest, diff_digest, test_digest, generation))
            self._event(db, attempt, action_id, "verifier_input_recorded", input_digest)
            return {**record, "recorded_at": recorded_at, "owner_generation": generation, "replayed": False}

    def claim_verifier_send(self, action_id: str, *, generation: int) -> None:
        """Record that a v8 verifier input crossed Flow's provider-send boundary."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt, _, _ = self._v8_verifier_action(db, action_id)
            self._assert_owner(db, attempt, generation)
            row = db.execute("SELECT actions.status,verifier_inputs.send_claimed_at FROM actions JOIN verifier_inputs USING(action_id) WHERE actions.action_id=?", (action_id,)).fetchone()
            if row is None:
                raise ContractError("verifier send requires a durable input binding")
            if row[1] is not None:
                raise ContractError("verifier send was already claimed")
            if row[0] != "started":
                raise ContractError("verifier send requires a consumed grant")
            claimed_at = utc_now()
            db.execute("UPDATE verifier_inputs SET send_claimed_at=? WHERE action_id=?", (claimed_at, action_id))
            self._event(db, attempt, action_id, "verifier_send_claimed", "flow_observed_boundary")

    def record_verifier_evaluation(self, action_id: str, evaluation: dict[str, Any], *, generation: int) -> dict[str, Any]:
        """Persist one idempotent Flow evaluation after response observation and completion."""
        validate_evaluation(evaluation)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt, _, _ = self._v8_verifier_action(db, action_id)
            self._assert_owner(db, attempt, generation)
            if evaluation["action_id"] != action_id:
                raise ContractError("verifier evaluation action binding is invalid")
            input_row = db.execute("SELECT input_digest,diff_digest,test_digest,send_claimed_at FROM verifier_inputs WHERE action_id=?", (action_id,)).fetchone()
            response = db.execute("SELECT result_json FROM response_observations WHERE action_id=?", (action_id,)).fetchone()
            action_row = db.execute("SELECT status FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if input_row is None or input_row[3] is None:
                raise ContractError("verifier evaluation requires a claimed input")
            if response is None or action_row is None or action_row[0] not in {"completed", "failed"}:
                raise ContractError("verifier evaluation requires observed completed response")
            result = json.loads(response[0])
            if (evaluation["verifier_input_digest"], evaluation["diff_digest"], evaluation["test_evidence_digest"], evaluation["raw_output_digest"]) != (
                    input_row[0], input_row[1], input_row[2], result.get("output_sha256")):
                raise ContractError("verifier evaluation evidence binding conflicts")
            encoded = canonical(evaluation)
            prior = db.execute("SELECT evaluation_json,evaluation_digest,outcome,reason,evaluated_at,owner_generation FROM verifier_evaluations WHERE action_id=?", (action_id,)).fetchone()
            if prior:
                if prior[0] != encoded:
                    raise ContractError("verifier evaluation conflicts with durable evaluation")
                return {"evaluation": json.loads(prior[0]), "evaluated_at": prior[4], "owner_generation": prior[5], "replayed": True}
            evaluated_at = utc_now()
            db.execute("INSERT INTO verifier_evaluations VALUES(?,?,?,?,?,?,?)", (action_id, evaluated_at, encoded,
                       evaluation["evaluation_digest"], evaluation["disposition"], evaluation["reason"], generation))
            self._event(db, attempt, action_id, "verifier_evaluated", evaluation["disposition"])
            return {"evaluation": evaluation, "evaluated_at": evaluated_at, "owner_generation": generation, "replayed": False}

    @staticmethod
    def _verifier_usage(db: sqlite3.Connection, attempt_id: str, envelope: dict[str, Any]) -> dict[str, Any]:
        verifier_ids = set(envelope["job_contract"]["verifier_instance_ids"])
        rows = db.execute("SELECT action_id,request_json,status,reason FROM actions WHERE attempt_id=?", (attempt_id,)).fetchall()
        verifier_rows = [row for row in rows if json.loads(row[1]).get("instance_id") in verifier_ids]
        reserved = sum(row[2] in {"allowed", "started", "completed", "failed", "unknown"} for row in verifier_rows)
        consumed = 0
        for action_id, _, status, _ in verifier_rows:
            claimed = db.execute("SELECT send_claimed_at FROM verifier_inputs WHERE action_id=?", (action_id,)).fetchone()
            consumed += bool((claimed and claimed[0] is not None) or status in {"completed", "failed", "unknown"})
        denied = sum(row[2] == "denied" and row[3] in {"verifier_call_cap", "verifier_retry_denied"} for row in verifier_rows)
        evaluations = db.execute("SELECT outcome FROM verifier_evaluations WHERE action_id IN (SELECT action_id FROM actions WHERE attempt_id=?) ORDER BY evaluated_at, rowid", (attempt_id,)).fetchall()
        latest = evaluations[-1][0] if evaluations else None
        maximum = envelope["limits"]["max_verifier_calls"]
        return {"maximum": maximum, "reserved": reserved, "consumed": consumed, "denied": denied,
                "retry_eligible": latest in {"valid_fail", "unusable"} and reserved < maximum}

    def verifier_usage(self, attempt_id: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT envelope_json,execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row[1] != 8:
                raise ContractError("structured verifier usage is unavailable")
            return self._verifier_usage(db, attempt_id, json.loads(row[0]))

    def observe_response(self, action_id: str, result: dict[str, Any], generation: int) -> dict[str, Any]:
        """Durably retain a validated normalized response before replaying it."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,status,request_json FROM actions WHERE action_id=?", (action_id,)).fetchone()
            if not row:
                raise ContractError("action missing")
            self._assert_owner(db, row[0], generation)
            envelope_row = db.execute("SELECT envelope_json FROM attempts WHERE attempt_id=?", (row[0],)).fetchone()
            envelope = json.loads(envelope_row[0])
            action = json.loads(row[2])
            is_v8_verifier = (execution_protocol_version(envelope) == 8
                              and action.get("instance_id") in envelope.get("job_contract", {}).get("verifier_instance_ids", []))
            if is_v8_verifier:
                try:
                    validate_structured_verifier_result(result)
                except VerifierContractError as exc:
                    raise ContractError(str(exc)) from exc
            else:
                validate_result(envelope, result, action=action)
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
                request = json.loads(db.execute("SELECT request_json FROM actions WHERE action_id=?", (action_id,)).fetchone()[0])
                if (execution_protocol_version(envelope) == 8
                        and request.get("instance_id") in envelope.get("job_contract", {}).get("verifier_instance_ids", [])):
                    # Same shape rule as observe_response; Flow judges content later.
                    try:
                        validate_structured_verifier_result(json.loads(observed[0]))
                    except VerifierContractError as exc:
                        raise ContractError(str(exc)) from exc
                else:
                    validate_result(envelope, json.loads(observed[0]), action=request)
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
    def _validate_maf_checkpoint(raw: bytes, checkpoint_id: str, kind: str, sequence: int,
                                 protocol_version: int = 2) -> None:
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
        expected_workflow = ("flow-maf-claude-review-v4" if protocol_version == 4 else
                             "flow-maf-mixed-provider-v3" if protocol_version == 3 else
                             "flow-maf-v2-action3" if kind == "pending_delegate" and sequence == 3 else
                             "flow-maf-v2-initial")
        if value.get("workflow_name") != expected_workflow:
            raise ContractError("checkpoint workflow does not match position")
        pending = value.get("pending_request_info_events")
        request_id = (f"flow-mixed-action-{sequence}" if protocol_version in {3, 4} else
                      f"flow-action-{sequence}" if kind == "pending_delegate" else f"flow-replan-{sequence}")
        if not isinstance(pending, dict) or set(pending) != {request_id} or not isinstance(pending[request_id], dict):
            raise ContractError("checkpoint request does not match position")

    def bind_checkpoint_position(self, attempt_id: str, kind: str, sequence: int, checkpoint_id: str,
                                 checkpoint_envelope_digest: str, ledger_seq: int, format_version: int,
                                 runtime_version: str, path: str, *, generation: int,
                                 max_bytes: int = 65536) -> dict[str, Any]:
        """Bind a versioned checkpoint to one completed Flow decision position.

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
            if row is None or row[1] not in {2, 3, 4}:
                raise ContractError("checkpoint positions require execution protocol v2 or v3")
            protocol_version = row[1]
            if protocol_version in {3, 4} and (kind != "pending_delegate" or sequence not in {1, 2}):
                raise ContractError("mixed checkpoint position is invalid")
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
                self._validate_maf_checkpoint(raw, checkpoint_id, kind, sequence, protocol_version)
            record = {"attempt_id": attempt_id, "kind": kind, "sequence": sequence, "checkpoint_id": checkpoint_id,
                      "envelope_digest": checkpoint_envelope_digest, "ledger_seq": ledger_seq,
                      "format_version": format_version, "runtime_version": runtime_version,
                      "protocol_version": protocol_version, "path": str(checkpoint_path), "file_sha256": file_sha256,
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
            db.execute("INSERT INTO checkpoint_position_links(attempt_id,kind,sequence,checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,protocol_version,path,file_sha256,file_size,bound_at,owner_generation) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (attempt_id, kind, sequence, checkpoint_id, checkpoint_envelope_digest, ledger_seq, format_version, runtime_version, protocol_version, str(checkpoint_path), file_sha256, file_size, bound_at, generation))
            self._event(db, attempt_id, None, "checkpoint_position_bound", canonical({"kind": kind, "sequence": sequence, "checkpoint_id": checkpoint_id, "ledger_seq": ledger_seq}))
            return {**record, "bound_at": bound_at, "replayed": False}

    def bind_magentic_checkpoint(self, attempt_id: str, checkpoint_id: str, pending_kind: str,
                                 pending_id: str, ledger_seq: int, path: str, *, generation: int,
                                 max_bytes: int = 65536) -> dict[str, Any]:
        """Link a v5 or v6 MAF snapshot to a Flow proposal, without granting restore authority."""
        if pending_kind not in {"manager", "worker"} or not isinstance(pending_id, str) or not pending_id or not isinstance(checkpoint_id, str) or not checkpoint_id or type(ledger_seq) is not int or ledger_seq < 0:
            raise ContractError("Magentic checkpoint identity is invalid")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._assert_owner(db, attempt_id, generation)
            attempt = db.execute("SELECT envelope_json,execution_protocol_version,status FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if (attempt is None or attempt[1] not in {5, 6, 7, 8} or not (attempt[2] == "started"
                    or attempt[2] == "unknown" and self._magentic_continuation_open(db, attempt_id))):
                raise ContractError("Magentic attempt is absent or closed")
            table, key = ("manager_calls", "call_id") if pending_kind == "manager" else ("actions", "action_id")
            proposal = db.execute(f"SELECT status,request_json FROM {table} WHERE attempt_id=? AND {key}=?", (attempt_id, pending_id)).fetchone()
            if proposal is None or proposal[0] not in {"allowed", "started", "completed"}:
                raise ContractError("Magentic checkpoint has no authorized proposal")
            high_water = db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
            if ledger_seq != high_water:
                raise ContractError("Magentic checkpoint ledger barrier mismatch")
            envelope = json.loads(attempt[0])
            checkpoint_path, file_sha256, file_size, raw = self._checkpoint_file(envelope, path, max_bytes=max_bytes)
            try:
                value = json.loads(raw)
            except ValueError as exc:
                raise ContractError("Magentic checkpoint is not JSON") from exc
            if not isinstance(value, dict) or value.get("checkpoint_id") != checkpoint_id or value.get("workflow_name") != f"flow-magentic-delivery-v{attempt[1]}":
                raise ContractError("Magentic checkpoint identity or workflow mismatch")
            if pending_kind == "worker":
                sequence = json.loads(proposal[1])["sequence"]
                pending = value.get("pending_request_info_events")
                request_key = f"flow-magentic-action-{sequence}"
                if not isinstance(pending, dict) or set(pending) != {request_key} or not isinstance(pending[request_key], dict):
                    raise ContractError("Magentic worker checkpoint request mismatch")
            record = {"attempt_id": attempt_id, "pending_kind": pending_kind, "pending_id": pending_id,
                      "checkpoint_id": checkpoint_id, "ledger_seq": ledger_seq, "path": str(checkpoint_path),
                      "file_sha256": file_sha256, "file_size": file_size, "owner_generation": generation}
            old = db.execute("SELECT checkpoint_id,ledger_seq,path,file_sha256,file_size,bound_at,owner_generation FROM magentic_checkpoint_links WHERE attempt_id=? AND pending_kind=? AND pending_id=?", (attempt_id, pending_kind, pending_id)).fetchone()
            if old:
                if old[:5] != (checkpoint_id, ledger_seq, str(checkpoint_path), file_sha256, file_size):
                    raise ContractError("Magentic checkpoint conflicts with durable link")
                return {**record, "bound_at": old[5], "replayed": True}
            bound_at = utc_now()
            db.execute("INSERT INTO magentic_checkpoint_links VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (attempt_id, pending_kind, pending_id, checkpoint_id, ledger_seq, str(checkpoint_path), file_sha256, file_size, bound_at, generation))
            self._event(db, attempt_id, pending_id, "magentic_checkpoint_bound", canonical({"checkpoint_id": checkpoint_id, "ledger_seq": ledger_seq, "file_sha256": file_sha256}))
            return {**record, "bound_at": bound_at, "replayed": False}

    def read_magentic_checkpoint(self, attempt_id: str, pending_kind: str, pending_id: str,
                                 *, max_bytes: int = 65536) -> dict[str, Any]:
        with self._db() as db:
            attempt = db.execute("SELECT envelope_json,execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            row = db.execute("SELECT checkpoint_id,ledger_seq,path,file_sha256,file_size,bound_at,owner_generation FROM magentic_checkpoint_links WHERE attempt_id=? AND pending_kind=? AND pending_id=?", (attempt_id, pending_kind, pending_id)).fetchone()
            if attempt is None or attempt[1] not in {5, 6, 7, 8} or row is None:
                raise ContractError("Magentic checkpoint link is absent")
            high_water = db.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
            if high_water < row[1]:
                raise ContractError("Magentic checkpoint ledger barrier is unavailable")
        envelope = json.loads(attempt[0])
        _, file_sha256, file_size, raw = self._checkpoint_file(envelope, row[2], max_bytes=max_bytes)
        if file_sha256 != row[3] or file_size != row[4]:
            raise ContractError("Magentic checkpoint file changed")
        value = json.loads(raw)
        if value.get("checkpoint_id") != row[0] or value.get("workflow_name") != f"flow-magentic-delivery-v{attempt[1]}":
            raise ContractError("Magentic checkpoint identity changed")
        if pending_kind == "worker":
            with self._db() as db:
                proposal = db.execute("SELECT request_json FROM actions WHERE attempt_id=? AND action_id=?", (attempt_id, pending_id)).fetchone()
            if proposal is None:
                raise ContractError("Magentic checkpoint action missing")
            request_key = f"flow-magentic-action-{json.loads(proposal[0])['sequence']}"
            pending = value.get("pending_request_info_events")
            if not isinstance(pending, dict) or set(pending) != {request_key}:
                raise ContractError("Magentic checkpoint pending request changed")
        return {"metadata": {"attempt_id": attempt_id, "pending_kind": pending_kind, "pending_id": pending_id,
                             "checkpoint_id": row[0], "ledger_seq": row[1], "path": row[2],
                             "file_sha256": row[3], "file_size": row[4], "bound_at": row[5],
                             "owner_generation": row[6]}, "bytes": raw}

    def read_checkpoint_position(self, attempt_id: str, kind: str, sequence: int, *, max_bytes: int = 65536) -> dict[str, Any]:
        """Return a bounded checkpoint only after all Flow-owned link checks pass."""
        if kind not in {"delegate", "pending_delegate", "replan"} or not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
            raise ContractError("checkpoint position is invalid")
        with self._db() as db:
            row = db.execute("SELECT envelope_json,execution_protocol_version,owner_generation FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            link = db.execute("SELECT checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,protocol_version,path,file_sha256,file_size,bound_at,owner_generation FROM checkpoint_position_links WHERE attempt_id=? AND kind=? AND sequence=?", (attempt_id, kind, sequence)).fetchone()
            if row is None or link is None or row[1] not in {2, 3, 4} or link[5] != row[1] or link[3] != 1:
                raise ContractError("checkpoint position is absent or incompatible")
            if row[1] in {3, 4} and (kind != "pending_delegate" or sequence not in {1, 2}):
                raise ContractError("mixed checkpoint position is invalid")
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
            self._validate_maf_checkpoint(raw, link[0], kind, sequence, link[5])
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
            row = db.execute("SELECT status,execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None or row[0] != "started":
                raise ContractError("attempt not active")
            if row[1] in {5, 6, 7, 8}:
                uncertain = db.execute("SELECT COUNT(*) FROM actions WHERE attempt_id=? AND status IN ('started','unknown')", (attempt_id,)).fetchone()[0]
                uncertain += db.execute("SELECT COUNT(*) FROM manager_calls WHERE attempt_id=? AND status IN ('started','unknown')", (attempt_id,)).fetchone()[0]
                if (uncertain > 0) != (status == "unknown"):
                    raise ContractError("Magentic terminal status contradicts uncertain sends")
            db.execute("UPDATE attempts SET status=?,reason=?,receipt_path=? WHERE attempt_id=?", (status, reason, receipt_path, attempt_id))
            self._event(db, attempt_id, None, "attempt_" + status, reason)

    def finish_magentic_continuation(self, epoch_id: str, status: str, reason: str,
                                     receipt_path: str, *, generation: int) -> None:
        """Seal a linked v5 receipt while preserving the original terminal attempt."""
        if status not in {"completed", "failed", "unknown"}:
            raise ContractError("Magentic continuation status is invalid")
        path = Path(receipt_path)
        if path.is_symlink() or not path.is_file():
            raise ContractError("Magentic continuation receipt is absent or unsafe")
        receipt_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT attempt_id,action_id,status,receipt_path FROM continuation_epochs WHERE epoch_id=?", (epoch_id,)).fetchone()
            if not row or row[2] != "running" or row[3] is not None:
                raise ContractError("Magentic continuation is not running")
            self._assert_owner(db, row[0], generation)
            attempt = db.execute("SELECT status,receipt_path,execution_protocol_version FROM attempts WHERE attempt_id=?", (row[0],)).fetchone()
            if not attempt or attempt[0] != "unknown" or attempt[2] != 5 or attempt[1] == receipt_path:
                raise ContractError("original Magentic receipt must remain terminal and separate")
            unresolved = db.execute("SELECT COUNT(*) FROM actions WHERE attempt_id=? AND status IN ('started','unknown')", (row[0],)).fetchone()[0]
            unresolved += db.execute("SELECT COUNT(*) FROM manager_calls WHERE attempt_id=? AND status IN ('started','unknown')", (row[0],)).fetchone()[0]
            if (unresolved > 0) != (status == "unknown"):
                raise ContractError("Magentic continuation status contradicts uncertain sends")
            db.execute("UPDATE continuation_epochs SET status=?,reason=?,receipt_path=?,sealed_receipt_sha256=? WHERE epoch_id=?",
                       (status, reason, receipt_path, receipt_sha, epoch_id))
            self._event(db, row[0], row[1], "magentic_continuation_" + status, epoch_id)

    @staticmethod
    def _continuation_owner(db: sqlite3.Connection, epoch_id: str, generation: int) -> tuple[str, str, str]:
        row = db.execute("SELECT attempt_id,action_id,status,owner_generation FROM continuation_epochs WHERE epoch_id=?", (epoch_id,)).fetchone()
        if row is None or row[3] != generation:
            raise ContractError("continuation ownership is stale or absent")
        return row[0], row[1], row[2]

    @staticmethod
    def _policy_counts(db: sqlite3.Connection, work_id: str, *, terminal_epoch: str | None = None,
                       terminal_status: str | None = None) -> dict[str, int]:
        grants = db.execute("SELECT count(*) FROM events JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND event IN ('policy_allowed','policy_reallowed')", (work_id,)).fetchone()[0]
        continuation_grants = db.execute("SELECT count(*) FROM continuation_grants JOIN continuation_epochs USING(epoch_id) JOIN attempts USING(attempt_id) WHERE attempts.work_id=?", (work_id,)).fetchone()[0]
        replans = db.execute("SELECT count(*) FROM replan_decisions JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND replan_decisions.status='allowed'", (work_id,)).fetchone()[0]
        active = db.execute("SELECT count(*) FROM actions JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND actions.status IN ('allowed','started','unknown')", (work_id,)).fetchone()[0]
        active_epochs = db.execute("SELECT continuation_epochs.epoch_id,continuation_epochs.status FROM continuation_grants JOIN continuation_epochs USING(epoch_id) JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND continuation_grants.status IN ('issued','claimed')", (work_id,)).fetchall()
        active += sum((terminal_status if epoch_id == terminal_epoch else status) not in {"completed", "failed"}
                      for epoch_id, status in active_epochs)
        return {"delegations": grants + continuation_grants, "concurrent": active,
                "replans": replans, "paid_budget_usd": 0}

    def continuation_policy_counters(self, epoch_id: str, *, terminal_status: str) -> dict[str, Any]:
        with self._db() as db:
            row = db.execute("SELECT attempts.work_id,continuation_epochs.policy_before_json FROM continuation_epochs JOIN attempts USING(attempt_id) WHERE epoch_id=?", (epoch_id,)).fetchone()
            if not row or not row[1]:
                raise ContractError("continuation policy baseline is absent")
            return {"before": json.loads(row[1]),
                    "after": self._policy_counts(db, row[0], terminal_epoch=epoch_id, terminal_status=terminal_status)}

    def begin_continuation(self, attempt_id: str, action_id: str, resolution_id: str,
                           receipt_sha256: str, checkpoint_sha256: str, *, actor: str) -> dict[str, Any]:
        """Bind one terminal attempt to one separately fenced continuation epoch.

        The caller verifies receipt/checkpoint bytes and the MAF barrier. This
        transaction checks their durable ledger links and never edits the old
        attempt, action, or receipt.
        """
        if not isinstance(actor, str) or not actor.strip() or len(actor.encode()) > 256:
            raise ContractError("continuation actor is invalid")
        for digest in (receipt_sha256, checkpoint_sha256):
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ContractError("continuation digest is invalid")
        with self.send_lock():
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                attempt = db.execute("SELECT status,receipt_path,recovery_version FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
                action = db.execute("SELECT attempt_id,status,request_json FROM actions WHERE action_id=?", (action_id,)).fetchone()
                resolution = db.execute("SELECT attempt_id,action_id,disposition FROM recovery_resolutions WHERE resolution_id=?", (resolution_id,)).fetchone()
                protocol = db.execute("SELECT execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
                if protocol == (5,):
                    checkpoint = db.execute("SELECT file_sha256 FROM magentic_checkpoint_links WHERE attempt_id=? AND pending_kind='worker' AND pending_id=?", (attempt_id, action_id)).fetchone()
                else:
                    checkpoint = db.execute("SELECT file_sha256 FROM checkpoint_position_links WHERE attempt_id=? AND kind='pending_delegate' AND sequence=3", (attempt_id,)).fetchone()
                if not attempt or attempt[0] not in {"unknown", "failed"} or attempt[2] != 2 or not attempt[1]:
                    raise ContractError("attempt is not terminal and continuation-capable")
                if not action or action[0] != attempt_id or not resolution or resolution[:2] != (attempt_id, action_id):
                    raise ContractError("continuation lineage is invalid")
                expected_status = "completed" if resolution[2] == "resolved_completed" else "not_dispatched"
                if resolution[2] not in {"resolved_completed", "resolved_not_dispatched"} or action[1] != expected_status:
                    raise ContractError("continuation action is not resolved")
                if not checkpoint or checkpoint[0] != checkpoint_sha256:
                    raise ContractError("continuation checkpoint link mismatch")
                try:
                    actual_receipt_sha256 = hashlib.sha256(Path(attempt[1]).read_bytes()).hexdigest()
                except OSError as exc:
                    raise ContractError("original receipt is absent") from exc
                if actual_receipt_sha256 != receipt_sha256:
                    raise ContractError("original receipt digest mismatch")
                prior = db.execute("SELECT epoch_id,resolution_id,receipt_sha256,checkpoint_sha256,status,owner_generation FROM continuation_epochs WHERE attempt_id=? AND action_id=?", (attempt_id, action_id)).fetchone()
                if prior:
                    if prior[1:4] != (resolution_id, receipt_sha256, checkpoint_sha256):
                        raise ContractError("continuation epoch conflicts with durable lineage")
                    return {"epoch_id": prior[0], "status": prior[4], "generation": prior[5], "replayed": True}
                epoch_id = uuid.uuid4().hex
                work_id = db.execute("SELECT work_id FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
                before = canonical(self._policy_counts(db, work_id))
                db.execute("INSERT INTO continuation_epochs(epoch_id,attempt_id,action_id,resolution_id,receipt_sha256,checkpoint_sha256,status,owner_actor,created_at,policy_before_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (epoch_id, attempt_id, action_id, resolution_id, receipt_sha256, checkpoint_sha256, "pending", actor, utc_now(), before))
                command = "flow run recover-delivery-lead" if protocol == (5,) else "flow run continue-resolved-execution"
                self._event(db, attempt_id, action_id, "continuation_opened", canonical({"epoch_id": epoch_id, "resolution_id": resolution_id, "command": command, "actor": actor}))
                return {"epoch_id": epoch_id, "status": "pending", "generation": 1, "replayed": False}

    def retry_failed_magentic_continuation(self, prior_epoch_id: str, action_id: str,
                                           checkpoint_sha256: str, *, actor: str) -> dict[str, Any]:
        """Append a new epoch after a failed v5 continuation with no uncertain sends."""
        with self.send_lock():
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                prior = db.execute("SELECT attempt_id,status,receipt_path,receipt_sha256,resolution_id "
                                   "FROM continuation_epochs WHERE epoch_id=?", (prior_epoch_id,)).fetchone()
                if not prior or prior[1] != "failed" or not prior[2]:
                    raise ContractError("prior Magentic continuation is not sealed failed")
                attempt_id = prior[0]
                attempt = db.execute("SELECT status,execution_protocol_version FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
                action = db.execute("SELECT attempt_id,status FROM actions WHERE action_id=?", (action_id,)).fetchone()
                checkpoint = db.execute("SELECT file_sha256 FROM magentic_checkpoint_links WHERE attempt_id=? AND pending_kind='worker' AND pending_id=?", (attempt_id, action_id)).fetchone()
                uncertain = db.execute("SELECT COUNT(*) FROM actions WHERE attempt_id=? AND status IN ('started','unknown')", (attempt_id,)).fetchone()[0]
                uncertain += db.execute("SELECT COUNT(*) FROM manager_calls WHERE attempt_id=? AND status IN ('started','unknown')", (attempt_id,)).fetchone()[0]
                if attempt != ("unknown", 5) or action != (attempt_id, "completed") or checkpoint != (checkpoint_sha256,) or uncertain:
                    raise ContractError("Magentic retry lacks a completed action and safe checkpoint")
                if hashlib.sha256(Path(prior[2]).read_bytes()).hexdigest() != db.execute(
                        "SELECT sealed_receipt_sha256 FROM continuation_epochs WHERE epoch_id=?", (prior_epoch_id,)).fetchone()[0]:
                    raise ContractError("prior Magentic continuation receipt changed")
                existing = db.execute("SELECT epoch_id,status FROM continuation_epochs WHERE attempt_id=? AND action_id=?", (attempt_id, action_id)).fetchone()
                if existing:
                    return {"epoch_id": existing[0], "status": existing[1], "replayed": True}
                epoch_id = uuid.uuid4().hex
                work_id = db.execute("SELECT work_id FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
                before = canonical(self._policy_counts(db, work_id))
                db.execute("INSERT INTO continuation_epochs(epoch_id,attempt_id,action_id,resolution_id,receipt_sha256,checkpoint_sha256,status,owner_actor,created_at,policy_before_json,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (epoch_id, attempt_id, action_id, prior[4], prior[3], checkpoint_sha256,
                            "pending", actor, utc_now(), before, "follows failed epoch " + prior_epoch_id))
                self._event(db, attempt_id, action_id, "magentic_continuation_retry_opened",
                            canonical({"epoch_id": epoch_id, "prior_epoch_id": prior_epoch_id, "actor": actor}))
                return {"epoch_id": epoch_id, "status": "pending", "replayed": False}

    def claim_continuation(self, epoch_id: str, *, actor: str) -> int:
        """Fence a prior process; a claimed send becomes unknown on restart."""
        if not isinstance(actor, str) or not actor.strip() or len(actor.encode()) > 256:
            raise ContractError("continuation actor is invalid")
        with self.send_lock():
            with self._db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT attempt_id,action_id,status,owner_generation FROM continuation_epochs WHERE epoch_id=?", (epoch_id,)).fetchone()
                if not row or row[2] in {"completed", "failed", "unknown"}:
                    raise ContractError("continuation is absent or terminal")
                claimed = db.execute("SELECT 1 FROM continuation_grants WHERE epoch_id=? AND status='claimed'", (epoch_id,)).fetchone()
                status = "unknown" if claimed else row[2]
                generation = row[3] + 1
                reason = "previous continuation send outcome uncertain" if claimed else ""
                db.execute("UPDATE continuation_epochs SET owner_generation=?,owner_actor=?,status=?,reason=? WHERE epoch_id=?", (generation, actor, status, reason, epoch_id))
                self._event(db, row[0], row[1], "continuation_claimed", canonical({"epoch_id": epoch_id, "generation": generation, "status": status}))
                return generation

    def start_magentic_continuation(self, epoch_id: str, *, generation: int) -> None:
        """Open v5 policy decisions only after the linked epoch is fenced."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT continuation_epochs.attempt_id,continuation_epochs.action_id,"
                             "continuation_epochs.status,continuation_epochs.owner_generation,"
                             "attempts.status,attempts.execution_protocol_version "
                             "FROM continuation_epochs JOIN attempts USING(attempt_id) WHERE epoch_id=?",
                             (epoch_id,)).fetchone()
            if (not row or row[2] != "pending" or row[3] != generation
                    or row[4:] != ("unknown", 5)):
                raise ContractError("Magentic continuation is not ready to run")
            resolution = db.execute("SELECT disposition FROM recovery_resolutions WHERE resolution_id="
                                    "(SELECT resolution_id FROM continuation_epochs WHERE epoch_id=?)",
                                    (epoch_id,)).fetchone()
            if resolution != ("resolved_completed",):
                raise ContractError("Magentic continuation lacks completed resolution")
            db.execute("UPDATE continuation_epochs SET status='running' WHERE epoch_id=?", (epoch_id,))
            self._event(db, row[0], row[1], "magentic_continuation_running", epoch_id)

    def regrant_continuation(self, epoch_id: str, envelope: dict[str, Any], action: dict[str, Any], *, generation: int) -> dict[str, Any]:
        """Reserve one fresh delegation unit for a proven unsent action."""
        validate_action(envelope, action)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt_id, action_id, status = self._continuation_owner(db, epoch_id, generation)
            row = db.execute("SELECT envelope_json,work_id FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            original = db.execute("SELECT request_json,status FROM actions WHERE action_id=?", (action_id,)).fetchone()
            resolution = db.execute("SELECT disposition FROM recovery_resolutions WHERE resolution_id=(SELECT resolution_id FROM continuation_epochs WHERE epoch_id=?)", (epoch_id,)).fetchone()
            if status not in {"pending", "running"} or not row or row[0] != canonical(envelope) or action_id != action["action_id"] or original != (canonical(action), "not_dispatched") or resolution != ("resolved_not_dispatched",):
                raise ContractError("continuation is not eligible for regrant")
            prior = db.execute("SELECT grant_id,status FROM continuation_grants WHERE epoch_id=?", (epoch_id,)).fetchone()
            if prior:
                return {"allowed": prior[1] == "issued", "reason": "existing_continuation_grant", "action_id": action_id, "grant_id": prior[0], "replayed": True}
            historical = db.execute("SELECT count(*) FROM events JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND event IN ('policy_allowed','policy_reallowed')", (row[1],)).fetchone()[0]
            extra = db.execute("SELECT count(*) FROM continuation_grants JOIN continuation_epochs USING(epoch_id) JOIN attempts USING(attempt_id) WHERE attempts.work_id=?", (row[1],)).fetchone()[0]
            active = db.execute("SELECT count(*) FROM actions JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND actions.status IN ('allowed','started','unknown')", (row[1],)).fetchone()[0]
            active_extra = db.execute("SELECT count(*) FROM continuation_grants JOIN continuation_epochs USING(epoch_id) JOIN attempts USING(attempt_id) WHERE attempts.work_id=? AND continuation_grants.status IN ('issued','claimed') AND continuation_epochs.status NOT IN ('completed','failed')", (row[1],)).fetchone()[0]
            limits = envelope["limits"]
            if action["role"] != envelope["role"] or action["role"] != "test-engineer":
                reason = "specialist_denied"
            elif action["provider"] != envelope["provider"] or action["provider"] not in {"ollama", "local-stub"}:
                reason = "provider_denied"
            elif historical + extra >= limits["max_delegations"]:
                reason = "delegation_cap"
            elif active + active_extra >= limits["max_concurrent"]:
                reason = "concurrency_cap"
            else:
                reason = "allowed"
            if reason != "allowed":
                self._event(db, attempt_id, action_id, "continuation_policy_denied", canonical({"epoch_id": epoch_id, "reason": reason}))
                return {"allowed": False, "reason": reason, "action_id": action_id, "grant_id": None}
            grant_id = uuid.uuid4().hex
            db.execute("INSERT INTO continuation_grants(grant_id,epoch_id,issued_at,status) VALUES(?,?,?,'issued')", (grant_id, epoch_id, utc_now()))
            db.execute("UPDATE continuation_epochs SET status='running' WHERE epoch_id=?", (epoch_id,))
            self._event(db, attempt_id, action_id, "continuation_granted", canonical({"epoch_id": epoch_id, "grant_id": grant_id}))
            return {"allowed": True, "reason": "allowed", "action_id": action_id, "grant_id": grant_id, "replayed": False}

    def claim_continuation_send(self, epoch_id: str, grant_id: str, *, generation: int) -> bool:
        """Single-use durable claim; caller holds send_lock across physical I/O."""
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt_id, action_id, status = self._continuation_owner(db, epoch_id, generation)
            grant = db.execute("SELECT status,issued_at FROM continuation_grants WHERE epoch_id=? AND grant_id=?", (epoch_id, grant_id)).fetchone()
            if status != "running" or not grant or grant[0] != "issued":
                return False
            if datetime.now(timezone.utc) > datetime.fromisoformat(grant[1]) + timedelta(seconds=60):
                db.execute("UPDATE continuation_grants SET status='expired' WHERE grant_id=?", (grant_id,))
                self._event(db, attempt_id, action_id, "continuation_grant_expired", epoch_id)
                return False
            db.execute("UPDATE continuation_grants SET status='claimed',claimed_at=? WHERE grant_id=?", (utc_now(), grant_id))
            self._event(db, attempt_id, action_id, "continuation_send_claimed", canonical({"epoch_id": epoch_id, "grant_id": grant_id}))
            return True

    def observe_continuation_response(self, epoch_id: str, result: dict[str, Any], *, generation: int) -> None:
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt_id, action_id, status = self._continuation_owner(db, epoch_id, generation)
            disposition = db.execute("SELECT disposition,result_json FROM recovery_resolutions WHERE resolution_id=(SELECT resolution_id FROM continuation_epochs WHERE epoch_id=?)", (epoch_id,)).fetchone()
            envelope = json.loads(db.execute("SELECT envelope_json FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()[0])
            validate_result(envelope, result)
            encoded = canonical(result)
            if status not in {"pending", "running"}:
                raise ContractError("continuation cannot observe response")
            if disposition[0] == "resolved_completed" and encoded != disposition[1]:
                raise ContractError("continuation replay differs from resolved response")
            if disposition[0] == "resolved_not_dispatched" and not db.execute("SELECT 1 FROM continuation_grants WHERE epoch_id=? AND status='claimed'", (epoch_id,)).fetchone():
                raise ContractError("continuation response lacks send claim")
            prior = db.execute("SELECT result_json FROM continuation_responses WHERE epoch_id=?", (epoch_id,)).fetchone()
            if prior:
                if prior[0] != encoded:
                    raise ContractError("continuation response conflicts with durable observation")
                return
            db.execute("INSERT INTO continuation_responses VALUES(?,?,?,?)", (epoch_id, encoded, hashlib.sha256(encoded.encode()).hexdigest(), utc_now()))
            self._event(db, attempt_id, action_id, "continuation_response_observed", canonical({"epoch_id": epoch_id, "result_digest": hashlib.sha256(encoded.encode()).hexdigest()}))

    def finish_continuation(self, epoch_id: str, status: str, reason: str, receipt_path: str, *, generation: int) -> None:
        if status not in {"completed", "failed", "unknown"} or not isinstance(receipt_path, str) or not receipt_path:
            raise ContractError("invalid continuation terminal state")
        receipt_sha256 = hashlib.sha256(Path(receipt_path).read_bytes()).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt_id, action_id, old_status = self._continuation_owner(db, epoch_id, generation)
            if old_status in {"completed", "failed", "unknown"}:
                raise ContractError("continuation is already terminal")
            if status == "completed" and not db.execute("SELECT 1 FROM continuation_responses WHERE epoch_id=?", (epoch_id,)).fetchone():
                raise ContractError("continuation success lacks durable response")
            db.execute("UPDATE continuation_epochs SET status=?,reason=?,receipt_path=?,sealed_receipt_sha256=? WHERE epoch_id=?", (status, reason, receipt_path, receipt_sha256, epoch_id))
            self._event(db, attempt_id, action_id, "continuation_" + status, canonical({"epoch_id": epoch_id, "reason": reason}))

    def seal_unknown_continuation(self, epoch_id: str, receipt_path: str, *, generation: int) -> None:
        """Attach a linked receipt after a restart detects an earlier send claim."""
        if not isinstance(receipt_path, str) or not Path(receipt_path).is_file():
            raise ContractError("unknown continuation receipt is absent")
        receipt_sha256 = hashlib.sha256(Path(receipt_path).read_bytes()).hexdigest()
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt_id, action_id, status = self._continuation_owner(db, epoch_id, generation)
            row = db.execute("SELECT receipt_path,reason FROM continuation_epochs WHERE epoch_id=?", (epoch_id,)).fetchone()
            if status != "unknown" or row[0] is not None or row[1] != "previous continuation send outcome uncertain":
                raise ContractError("continuation is not an unsealed send-claim unknown")
            db.execute("UPDATE continuation_epochs SET receipt_path=?,sealed_receipt_sha256=? WHERE epoch_id=?", (receipt_path, receipt_sha256, epoch_id))
            self._event(db, attempt_id, action_id, "continuation_unknown_sealed", epoch_id)

    def continuation_snapshot(self, epoch_id: str) -> dict[str, Any]:
        with self._db() as db:
            columns = {item[1] for item in db.execute("PRAGMA table_info(continuation_epochs)")}
            sealed = "sealed_receipt_sha256" if "sealed_receipt_sha256" in columns else "NULL"
            before = "policy_before_json" if "policy_before_json" in columns else "NULL"
            row = db.execute(f"SELECT epoch_id,attempt_id,action_id,resolution_id,receipt_sha256,checkpoint_sha256,status,reason,receipt_path,owner_generation,owner_actor,created_at,{sealed},{before} FROM continuation_epochs WHERE epoch_id=?", (epoch_id,)).fetchone()
            if not row:
                raise ContractError("continuation epoch missing")
            grant = db.execute("SELECT grant_id,issued_at,status,claimed_at FROM continuation_grants WHERE epoch_id=?", (epoch_id,)).fetchone()
            response = db.execute("SELECT result_json,result_digest,observed_at FROM continuation_responses WHERE epoch_id=?", (epoch_id,)).fetchone()
            return {**dict(zip(("epoch_id", "attempt_id", "action_id", "resolution_id", "receipt_sha256", "checkpoint_sha256", "status", "reason", "receipt_path", "owner_generation", "owner_actor", "created_at", "sealed_receipt_sha256", "policy_before_json"), row)),
                    "grant": dict(zip(("grant_id", "issued_at", "status", "claimed_at"), grant)) if grant else None,
                    "response": {"result": json.loads(response[0]), "result_digest": response[1], "observed_at": response[2]} if response else None,
                    "send_claimed": bool(grant and grant[2] == "claimed")}

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
            verifier_inputs = db.execute("SELECT action_id,recorded_at,input_json,input_digest,diff_digest,test_digest,send_claimed_at,owner_generation FROM verifier_inputs WHERE action_id IN (SELECT action_id FROM actions WHERE attempt_id=?) ORDER BY recorded_at", (attempt_id,)).fetchall() if "verifier_inputs" in tables else []
            verifier_evaluations = db.execute("SELECT action_id,evaluated_at,evaluation_json,evaluation_digest,outcome,reason,owner_generation FROM verifier_evaluations WHERE action_id IN (SELECT action_id FROM actions WHERE attempt_id=?) ORDER BY evaluated_at, rowid", (attempt_id,)).fetchall() if "verifier_evaluations" in tables else []
            resolutions = db.execute("SELECT resolution_id,action_id,actor,disposition,explanation,evidence_json,result_json,resolution_digest,created_at,owner_generation FROM recovery_resolutions WHERE attempt_id=? ORDER BY created_at", (attempt_id,)).fetchall() if "recovery_resolutions" in tables else []
            replans = db.execute("SELECT replan_id,sequence,request_json,proposal_digest,status,reason FROM replan_decisions WHERE attempt_id=? ORDER BY sequence", (attempt_id,)).fetchall() if "replan_decisions" in tables else []
            manager_calls = db.execute("SELECT call_id,sequence,request_json,status,reason,grant_id,result_json,observed_at FROM manager_calls WHERE attempt_id=? ORDER BY sequence", (attempt_id,)).fetchall() if "manager_calls" in tables else []
            magentic_checkpoints = db.execute("SELECT pending_kind,pending_id,checkpoint_id,ledger_seq,path,file_sha256,file_size,bound_at,owner_generation FROM magentic_checkpoint_links WHERE attempt_id=? ORDER BY rowid", (attempt_id,)).fetchall() if "magentic_checkpoint_links" in tables else []
            checkpoint_positions = db.execute("SELECT kind,sequence,checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,protocol_version,path,file_sha256,file_size,bound_at,owner_generation FROM checkpoint_position_links WHERE attempt_id=? ORDER BY kind,sequence", (attempt_id,)).fetchall() if "checkpoint_position_links" in tables else []
            checkpoint_columns = {row[1] for row in db.execute("PRAGMA table_info(checkpoint_links)")} if "checkpoint_links" in tables else set()
            checkpoint_query = "SELECT checkpoint_id,envelope_digest,ledger_seq,format_version,runtime_version,path,bound_at,owner_generation" + (",file_sha256" if "file_sha256" in checkpoint_columns else "") + " FROM checkpoint_links WHERE attempt_id=?"
            checkpoint = db.execute(checkpoint_query, (attempt_id,)).fetchone() if "checkpoint_links" in tables else None
            continuation_rows = db.execute("SELECT epoch_id FROM continuation_epochs WHERE attempt_id=? ORDER BY created_at, rowid", (attempt_id,)).fetchall() if "continuation_epochs" in tables else []
            attempt_protocol = a[9 if recovery_columns else 6] if protocol_column else 1
            structured_usage = self._verifier_usage(db, attempt_id, json.loads(a[2])) if attempt_protocol == 8 else None
        continuations = [self.continuation_snapshot(epoch_id) for (epoch_id,) in continuation_rows]
        envelope = json.loads(a[2])
        snapshot = {"attempt_id": a[0], "work_id": a[1], "envelope": envelope, "status": a[3], "reason": a[4], "receipt_path": a[5],
                "recovery_version": a[6] if recovery_columns else 1, "owner_generation": a[7] if recovery_columns else 0, "owner_actor": a[8] if recovery_columns else None,
                "execution_protocol_version": a[9 if recovery_columns else 6] if protocol_column else 1,
                "actions": [{"action_id": r[0], "request": json.loads(r[1]), "status": r[2], "reason": r[3], "grant_id": r[4], "result": json.loads(r[5]) if r[5] else None} for r in actions],
                "replans": [{"replan_id": r[0], "sequence": r[1], "request": json.loads(r[2]), "proposal_digest": r[3], "status": r[4], "reason": r[5]} for r in replans],
                "manager_calls": [{"call_id": r[0], "sequence": r[1], "request": json.loads(r[2]), "status": r[3], "reason": r[4], "grant_id": r[5], "result": json.loads(r[6]) if r[6] else None, "observed_at": r[7]} for r in manager_calls],
                "magentic_checkpoints": [{"pending_kind": r[0], "pending_id": r[1], "checkpoint_id": r[2], "ledger_seq": r[3], "path": r[4], "file_sha256": r[5], "file_size": r[6], "bound_at": r[7], "owner_generation": r[8]} for r in magentic_checkpoints],
                "checkpoint_positions": [{"kind": r[0], "sequence": r[1], "checkpoint_id": r[2], "envelope_digest": r[3], "ledger_seq": r[4], "format_version": r[5], "runtime_version": r[6], "protocol_version": r[7], "path": r[8], "file_sha256": r[9], "file_size": r[10], "bound_at": r[11], "owner_generation": r[12]} for r in checkpoint_positions],
                "events": [{"seq": r[0], "at": r[1], "action_id": r[2], "event": r[3], "detail": r[4]} for r in events],
                "response_observations": [{"action_id": r[0], "observed_at": r[1], "result": json.loads(r[2]), "result_digest": r[3], "owner_generation": r[4]} for r in observations],
                "verifier_inputs": [{"action_id": r[0], "recorded_at": r[1], "input": json.loads(r[2]), "input_digest": r[3], "diff_digest": r[4], "test_digest": r[5], "send_claimed_at": r[6], "owner_generation": r[7]} for r in verifier_inputs],
                "verifier_evaluations": [{"action_id": r[0], "evaluated_at": r[1], "evaluation": json.loads(r[2]), "evaluation_digest": r[3], "outcome": r[4], "reason": r[5], "owner_generation": r[6]} for r in verifier_evaluations],
                "resolutions": [{"resolution_id": r[0], "action_id": r[1], "actor": r[2], "disposition": r[3], "explanation": r[4], "evidence": json.loads(r[5]), "result": json.loads(r[6]) if r[6] else None, "resolution_digest": r[7], "created_at": r[8], "owner_generation": r[9]} for r in resolutions],
                "checkpoint": ({"checkpoint_id": checkpoint[0], "envelope_digest": checkpoint[1], "ledger_seq": checkpoint[2], "format_version": checkpoint[3], "runtime_version": checkpoint[4], "path": checkpoint[5], "bound_at": checkpoint[6], "owner_generation": checkpoint[7], "file_sha256": checkpoint[8] if len(checkpoint) > 8 else None} if checkpoint else None),
                "continuations": continuations}
        if structured_usage is not None:
            snapshot["verifier_usage"] = structured_usage
        return snapshot
