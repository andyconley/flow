from __future__ import annotations

import copy
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from delivery_selection import (  # noqa: E402
    RecoveryRequired,
    SelectionDenied,
    authorize_and_dispatch,
    bootstrap_manager,
    compute_binding,
    make_action,
)
from delivery_gateway import execute_v9_selected_action  # noqa: E402
from execution_contracts import ContractError, digest, validate_envelope  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from provider_selection import merge_selection_policy  # noqa: E402


def _candidate(candidate_id: str, provider: str, family: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "provider": provider,
        "model": f"{candidate_id}-model",
        "provider_family": family,
        "tier": "judgment",
        "locality": "local" if provider == "ollama" else "hosted",
        "operations": ["manage", "edit", "verify"],
        "capabilities": ["structured_output", "structured_edit"],
        "cost_class": 0 if provider == "ollama" else 1,
        "enabled": True,
    }


def _envelope(*, excluded_families: list[str] | None = None,
              waiver: bool = False) -> dict:
    policy = merge_selection_policy({}, None, None, ({
        "independence_waiver": {"approved": True, "approval_digest": "a" * 64}
    } if waiver else None))
    catalog = [
        _candidate("local", "ollama", "local"),
        _candidate("claude", "claude", "anthropic"),
        _candidate("codex", "codex", "openai"),
    ]
    availability = [{"candidate_id": item["candidate_id"], "state": "ready"}
                    for item in catalog]
    common = {
        "minimum_tier": "working", "required_capabilities": ["structured_output"],
        "locality": "any", "input_bytes": 100, "output_bytes": 100, "context_tokens": 100,
    }
    assignments = [
        {"assignment_id": "manager", "role": "delivery-lead", "instructions": "Coordinate logical work.",
         "requirements": {**common, "operation": "manage"}},
        {"assignment_id": "producer", "role": "lead-developer", "instructions": "Edit the approved scope.",
         "requirements": {**common, "operation": "edit", "required_capabilities": ["structured_edit"]}},
        {"assignment_id": "verifier", "role": "quality-reviewer", "instructions": "Verify independently.",
         "requirements": {**common, "operation": "verify",
                          "excluded_provider_families": excluded_families or []}},
    ]
    inputs = {"policy": policy, "catalog": catalog, "availability": availability}
    return {
        "schema_version": 1,
        "execution_protocol_version": 9,
        "work_id": "selection-test",
        "attempt_id": "attempt-v9",
        "charter_digest": "b" * 64,
        "manifest_digest": "c" * 64,
        "run_protocol_revision": 2,
        "logical_assignments": assignments,
        "selection_inputs": inputs,
        "selection_input_digests": {key: digest(value) for key, value in inputs.items()},
        "limits": {"max_actions": 3},
        "checkpoint_dir": ".flow/runs/selection-test/checkpoints",
    }


class DeliverySelectionTests(unittest.TestCase):
    def test_v9_rejects_concrete_shaper_authority(self) -> None:
        envelope = _envelope()
        envelope["logical_assignments"][0]["provider"] = "ollama"
        with self.assertRaisesRegex(ContractError, "concrete provider authority"):
            validate_envelope(envelope)

    def test_manager_bootstrap_and_child_binding_use_local_first_selector(self) -> None:
        envelope = _envelope()
        validate_envelope(envelope)
        self.assertEqual(bootstrap_manager(envelope)["selected_candidate_id"], "local")
        self.assertEqual(compute_binding(envelope, "producer")["selected_candidate_id"], "local")

    def test_flow_recomputation_denies_forged_binding_with_zero_sends(self) -> None:
        envelope = _envelope()
        decision = compute_binding(envelope, "producer")
        forged = copy.deepcopy(decision)
        forged["selected_candidate_id"] = "claude"
        forged["selected_binding"] = {
            "candidate_id": "claude", "provider": "claude", "model": "claude-model",
            "provider_family": "anthropic",
        }
        action = make_action(envelope, "producer", "Implement the change.", sequence=1,
                             manager_turn=1, decision=forged)
        sends: list[str] = []
        with self.assertRaisesRegex(SelectionDenied, "differs from Flow recomputation"):
            execute_v9_selected_action(
                envelope, action, lambda binding, _action: sends.append(binding["candidate_id"]),
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
            )
        self.assertEqual(sends, [])

    def test_positive_pre_send_refusal_falls_forward_without_send(self) -> None:
        envelope = _envelope()
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        sends: list[str] = []
        result = authorize_and_dispatch(
            envelope, action, lambda binding, _action: sends.append(binding["candidate_id"]),
            readiness_recheck=lambda binding: {
                **binding, "state": "unavailable", "no_send_observed": True,
                "evidence_code": "connection_refused_before_send",
            },
        )
        self.assertEqual(result["status"], "pre_send_refused")
        self.assertEqual(result["successor_decision"]["selected_candidate_id"], "claude")
        self.assertEqual(sends, [])

    def test_uncertain_recheck_and_started_send_require_recovery(self) -> None:
        envelope = _envelope()
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        with self.assertRaises(RecoveryRequired):
            authorize_and_dispatch(
                envelope, action, lambda *_: None,
                readiness_recheck=lambda binding: {**binding, "state": "unknown"},
            )
        with self.assertRaises(RecoveryRequired):
            authorize_and_dispatch(
                envelope, action, lambda *_: (_ for _ in ()).throw(TimeoutError()),
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
            )

    def test_high_risk_family_filter_and_sealed_waiver(self) -> None:
        envelope = _envelope(excluded_families=["local", "anthropic"])
        self.assertEqual(compute_binding(envelope, "verifier")["selected_candidate_id"], "codex")
        waived = _envelope(excluded_families=["local", "anthropic"], waiver=True)
        self.assertEqual(compute_binding(waived, "verifier")["selected_candidate_id"], "local")

    def test_ledger_fences_selection_consumption_and_positive_no_send_successor(self) -> None:
        envelope = _envelope()
        first = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite3"
            ledger = ExecutionLedger(path)
            ledger.create_attempt(envelope)
            ledger.record_v9_selection(envelope, first, generation=1)
            ledger.transition_v9_selection(first["selection_id"], "computed", "reserved", generation=1)
            ledger.transition_v9_selection(
                first["selection_id"], "reserved", "pre_send_refused", generation=1,
                reason="connection_refused_before_send",
            )
            successor_decision = compute_binding(
                envelope, "producer", prior_no_send_failures=["local"]
            )
            successor = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1,
                                    decision=successor_decision)
            ledger.record_v9_selection(
                envelope, successor, generation=1,
                predecessor_selection_id=first["selection_id"],
            )
            ledger.transition_v9_selection(successor["selection_id"], "computed", "reserved", generation=1)
            ledger.transition_v9_selection(
                successor["selection_id"], "reserved", "consumed", generation=1,
                provider_action_id=successor["action_id"],
            )
            with sqlite3.connect(path) as db:
                states = dict(db.execute("SELECT selection_id,state FROM provider_selections"))
            self.assertEqual(states[first["selection_id"]], "superseded")
            self.assertEqual(states[successor["selection_id"]], "consumed")


if __name__ == "__main__":
    unittest.main()
