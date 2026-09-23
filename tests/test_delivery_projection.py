"""Read-only v7 projection inspection tests."""

from __future__ import annotations

import unittest
import sqlite3
import tempfile
import json
import tempfile

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_projection import inspect_delivery, inspect_delivery_projection
from execution_contracts import ContractError, digest
from execution_ledger import ExecutionLedger


def envelope() -> dict:
    sources = {"requirements": {"path": ".flow/runs/work/requirements.md", "sha256": "b" * 64},
               "acceptance": {"path": ".flow/runs/work/acceptance.md", "sha256": "c" * 64}}
    base = {
        "schema_version": 1, "execution_protocol_version": 7, "work_id": "work", "attempt_id": "attempt",
        "charter_digest": digest({"requirements": sources["requirements"]["sha256"], "acceptance": sources["acceptance"]["sha256"]}),
        "charter_sources": sources,
        "run_protocol_revision": 2, "manifest_digest": "d" * 64, "checkpoint_dir": "/tmp/checkpoints",
        "source_commit": "e" * 40, "worktree": "/tmp/worktree", "allowed_paths": ["target.py"],
        "manager": {"provider": "claude", "model": "manager"},
        "roster": [{"assignment_id": "editor", "definition_digest": digest({"role": "lead-developer", "instructions": "edit"}),
                    "instance_id": "editor", "role": "lead-developer", "provider": "codex", "model": "model",
                    "instructions": "edit", "capabilities": ["read", "edit"]},
                   {"assignment_id": "verify", "definition_digest": digest({"role": "test-engineer", "instructions": "verify"}),
                    "instance_id": "verify", "role": "test-engineer", "provider": "ollama", "model": "local",
                    "instructions": "verify", "capabilities": ["read"]}],
        "job_contract": {"task": "edit", "baseline": {"kind": "clean", "diff_sha256": "f" * 64},
                         "read_paths": ["target.py"], "write_paths": ["target.py"],
                         "test": {"argv": ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_target.py"], "timeout_seconds": 10},
                         "producer_instance_ids": ["editor"], "verifier_instance_ids": ["verify"]},
        "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2,
                   "max_manager_calls": 12, "max_manager_rounds": 6, "max_paid_worker_calls": 6},
        "shaper_contract_digest": "1" * 64, "delivery_charter_digest": "2" * 64,
        "handoff_digest": "3" * 64, "delivery_lead_claim_digest": "4" * 64,
        "delivery_lead_claim": {"lead_id": "delivery-lead", "generation": 1},
    }
    return base


class DeliveryProjectionTests(unittest.TestCase):
    def test_started_current_generation_is_executable(self):
        view = inspect_delivery_projection(envelope(), {"attempt_id": "attempt", "status": "started", "owner_generation": 1, "actions": []})
        self.assertTrue(view["executable"])
        self.assertEqual(view["delivery_lead"]["id"], "delivery-lead")

    def test_stale_generation_is_visible_but_not_executable(self):
        view = inspect_delivery_projection(envelope(), {"attempt_id": "attempt", "status": "started", "owner_generation": 2, "actions": []})
        self.assertFalse(view["executable"])

    def test_different_attempt_is_rejected(self):
        with self.assertRaisesRegex(ContractError, "attempt differs"):
            inspect_delivery_projection(envelope(), {"attempt_id": "other", "status": "started", "owner_generation": 1})

    def test_legacy_duplicate_action_positions_do_not_break_ledger_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.sqlite"
            db = sqlite3.connect(path)
            db.executescript("""
                CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY, work_id TEXT NOT NULL, envelope_json TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL, receipt_path TEXT);
                CREATE TABLE actions (action_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, request_json TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL, grant_id TEXT UNIQUE, result_json TEXT);
                INSERT INTO attempts VALUES ('old', 'work', '{}', 'failed', '', NULL);
                INSERT INTO actions VALUES ('one', 'old', '{}', 'failed', '', NULL, NULL);
                INSERT INTO actions VALUES ('two', 'old', '{}', 'failed', '', NULL, NULL);
            """)
            db.commit()
            db.close()
            ExecutionLedger(path)
            db = sqlite3.connect(path)
            names = {row[1] for row in db.execute("PRAGMA index_list(actions)")}
            db.close()
            self.assertIn("actions_attempt_kind_sequence_lookup", names)

    def test_run_without_execution_attempt_reports_sealed_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / ".flow" / "runs" / "work"
            run_dir.mkdir(parents=True)
            authority = {"charter_digest": "2" * 64, "owner_generation": 1, "owner_status": "active"}
            (run_dir / "run.json").write_text(json.dumps({
                "work_id": "work", "state": "planning", "phase": "planning",
                "updated_at": "2026-09-23T00:00:00Z", "delivery": authority,
            }))

            view = inspect_delivery("work", root=root)

            self.assertEqual(view["delivery_authority"], authority)
            self.assertIsNone(view["attempt"])
