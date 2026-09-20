"""A mixed MAF job remains bound to two Flow-approved specialist identities."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from execution_contracts import ContractError, digest, envelope_digest, expected_action_id, validate_action, validate_envelope, validate_receipt, validate_result
from execution_ledger import ExecutionLedger


def assignment(sequence: int, role: str, provider: str, task: str) -> dict:
    instructions = f"Perform the {role} assignment."
    return {
        "sequence": sequence, "assignment_id": f"approved-{role}", "definition_digest": digest({"role": role, "instructions": instructions}),
        "instance_id": f"instance-{sequence}", "role": role, "provider": provider,
        "model": "local-model" if sequence == 1 else "codex-model", "task": task,
        "task_digest": hashlib.sha256(task.encode()).hexdigest(), "instructions": instructions,
    }


def envelope() -> dict:
    sources = {key: {"path": f".flow/runs/mixed/{key}.md", "sha256": char * 64} for key, char in (("requirements", "a"), ("acceptance", "b"))}
    return {
        "schema_version": 1, "execution_protocol_version": 3, "work_id": "mixed-work", "attempt_id": "mixed-attempt",
        "charter_sources": sources, "charter_digest": digest({key: value["sha256"] for key, value in sources.items()}),
        "run_protocol_revision": 2, "manifest_digest": "c" * 64,
        "assignments": [assignment(1, "test-engineer", "ollama", "Write a small test plan"), assignment(2, "lead-developer", "codex", "Implement fixture")],
        "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "max_codex_calls": 1},
        "checkpoint_dir": "/tmp/mixed-checkpoint",
    }


def action(env: dict, sequence: int) -> dict:
    chosen = env["assignments"][sequence - 1]
    return {
        "schema_version": 1, "action_id": expected_action_id(env, sequence), "attempt_id": env["attempt_id"],
        "envelope_digest": envelope_digest(env), "sequence": sequence, "kind": "delegate",
        **{key: chosen[key] for key in ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model", "task_digest")},
    }


def result(chosen: dict) -> dict:
    output = "bounded result"
    return {"schema_version": 1, "status": "completed", "provider": chosen["provider"], "model": chosen["model"],
            "physical_call": True, "evidence_level": "flow_observed_local_http_response" if chosen["provider"] == "ollama" else "flow_observed_codex_cli_completed_turn",
            "output": output, "output_sha256": hashlib.sha256(output.encode()).hexdigest(), "usage": None}


class MixedContractTests(unittest.TestCase):
    def test_distinct_assignments_and_results_are_bound_to_sequences(self) -> None:
        env = envelope()
        validate_envelope(env)
        first, second = action(env, 1), action(env, 2)
        validate_action(env, first)
        validate_action(env, second)
        self.assertNotEqual(first["action_id"], second["action_id"])
        validate_result(env, result(env["assignments"][1]), action=second)
        with self.assertRaises(ContractError):
            validate_result(env, result(env["assignments"][1]), action=first)
        with self.assertRaises(ContractError):
            validate_action(env, {**second, "definition_digest": first["definition_digest"]})

    def test_ledger_orders_actions_and_requires_resolution_of_unknown(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite")
            ledger.create_attempt(env)
            with self.assertRaisesRegex(ContractError, "out of order"):
                ledger.decide(env, action(env, 2), generation=1)
            first = action(env, 1)
            grant = ledger.decide(env, first, generation=1)
            self.assertTrue(grant["allowed"])
            self.assertTrue(ledger.consume_grant(first["action_id"], grant["grant_id"], generation=1))
            ledger.mark_unknown(first["action_id"], "interrupted", generation=1)
            self.assertEqual(ledger.decide(env, action(env, 2), generation=1)["reason"], "reconciliation_required")
            self.assertEqual(len(ledger.snapshot(env["attempt_id"])["actions"]), 1)

    def test_no_dollar_limit_or_extra_codex_assignment(self) -> None:
        env = envelope()
        with self.assertRaisesRegex(ContractError, "limits"):
            validate_envelope({**env, "limits": {**env["limits"], "paid_budget_usd": 0}})
        with self.assertRaisesRegex(ContractError, "two assignments"):
            validate_envelope({**env, "assignments": env["assignments"] * 2})

    def test_v3_pending_checkpoint_is_bound_and_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**envelope(), "checkpoint_dir": str(root)}
            ledger = ExecutionLedger(root / "ledger.sqlite")
            ledger.create_attempt(env)
            first = action(env, 1)
            grant = ledger.decide(env, first, generation=1)
            checkpoint_id = "mixed-checkpoint-1"
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": checkpoint_id,
                "workflow_name": "flow-maf-mixed-provider-v3",
                "pending_request_info_events": {"flow-mixed-action-1": {"request": "opaque"}}}))
            high_water = ledger.snapshot(env["attempt_id"])["events"][-1]["seq"]
            bound = ledger.bind_checkpoint_position(env["attempt_id"], "pending_delegate", 1, checkpoint_id,
                envelope_digest(env), high_water, 1, "pinned-maf", str(checkpoint), generation=1)
            self.assertEqual(bound["protocol_version"], 3)
            self.assertEqual(ledger.read_checkpoint_position(env["attempt_id"], "pending_delegate", 1)["bytes"], checkpoint.read_bytes())
            receipt = {"schema_version": 1, "work_id": env["work_id"], "attempt_id": env["attempt_id"],
                "envelope_digest": envelope_digest(env), "charter_digest": env["charter_digest"],
                "manifest_digest": env["manifest_digest"], "charter_sources": env["charter_sources"],
                "run_protocol_revision": 2, "status": "failed", "actions": [], "execution_protocol_version": 3,
                "assignments": env["assignments"], "replans": [], "checkpoints": [{"kind": "pending_delegate", "sequence": 1,
                    "file_sha256": bound["file_sha256"]}]}
            validate_receipt(env, receipt)
            ledger.close_pre_send_failure(first["action_id"], grant["grant_id"], generation=1)
            self.assertEqual(ledger.snapshot(env["attempt_id"])["actions"][0]["reason"], "pre_send_failure")
            self.assertFalse(ledger.consume_grant(first["action_id"], grant["grant_id"], generation=1))

    def test_completed_receipt_binds_both_results_and_fixture_evidence(self) -> None:
        env = envelope()
        receipt = {"schema_version": 1, "work_id": env["work_id"], "attempt_id": env["attempt_id"],
            "envelope_digest": envelope_digest(env), "charter_digest": env["charter_digest"],
            "manifest_digest": env["manifest_digest"], "charter_sources": env["charter_sources"],
            "run_protocol_revision": 2, "status": "completed", "execution_protocol_version": 3,
            "assignments": env["assignments"], "replans": [], "checkpoints": [],
            "actions": [{"action_id": action(env, sequence)["action_id"], "request": action(env, sequence),
                "status": "completed", "reason": "allowed", "result": result(env["assignments"][sequence - 1])}
                for sequence in (1, 2)],
            "fixture_diff": {"changed_files": ["greet.py"], "before_sha256": "a" * 64,
                             "after_sha256": "b" * 64, "diff_sha256": "c" * 64, "behavior_check": "passed"}}
        validate_receipt(env, receipt)
        with self.assertRaisesRegex(ContractError, "both completed"):
            validate_receipt(env, {**receipt, "actions": receipt["actions"][:1]})
        bad_action = {**receipt["actions"][1], "result": result(env["assignments"][0])}
        with self.assertRaisesRegex(ContractError, "result status, provider, or model"):
            validate_receipt(env, {**receipt, "actions": [receipt["actions"][0], bad_action]})
        with self.assertRaisesRegex(ContractError, "fixture diff"):
            validate_receipt(env, {**receipt, "fixture_diff": None})
        with self.assertRaisesRegex(ContractError, "behavior check"):
            validate_receipt(env, {**receipt, "fixture_diff": {**receipt["fixture_diff"], "behavior_check": "unverified"}})


if __name__ == "__main__":
    unittest.main()
