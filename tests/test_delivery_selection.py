from __future__ import annotations

import copy
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


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
from delivery_gateway import (execute_v9_logical_delivery, execute_v9_selected_action,
                              terminate_v9_delivery)  # noqa: E402
from delivery_recovery import RecoveryRefused
from delivery_control import DeliveryControlError  # noqa: E402
from execution_contracts import ContractError, digest, validate_envelope  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from provider_selection import merge_selection_policy  # noqa: E402
from provider_availability import normalize_availability  # noqa: E402
from provider_outcomes import ObservedNotExecuted  # noqa: E402
from selection_authority import (  # noqa: E402
    seal_selection_authority,
    successor_authority_digest,
)
from selection_receipt import V9ReceiptError, receipt_from_snapshot, verify_selection_receipt  # noqa: E402
from verifier_contracts import evaluate_candidate  # noqa: E402


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


def _manager_result(assignment_id: str = "producer", task: str = "Implement the approved change.") -> dict:
    return {"manager_response": {
        "is_request_satisfied": {"answer": False},
        "is_in_loop": {"answer": True},
        "is_progress_being_made": {"answer": True},
        "next_speaker": {"answer": assignment_id, "reason": "approved work remains"},
        "instruction_or_question": {"answer": task},
    }}


def _manager_result_for_action(action: dict, task: str = "Complete the approved stage.") -> dict:
    assignment_id = "verifier" if '"verifier"' in action["task"] else "producer"
    return _manager_result(assignment_id, task)


def _envelope(*, excluded_families: list[str] | None = None,
              waiver: bool = False, allowed_candidates: list[str] | None = None,
              attempt_id: str = "attempt-v9") -> dict:
    policy = merge_selection_policy({} if allowed_candidates is None else {"allowed_candidates": allowed_candidates})
    catalog = [
        _candidate("local", "ollama", "local"),
        _candidate("claude", "claude", "anthropic"),
        _candidate("codex", "codex", "openai"),
    ]
    sealed = datetime(2026, 9, 29, 12, tzinfo=timezone.utc)
    availability = [normalize_availability({
        "candidate_id": item["candidate_id"],
        "state": "ready",
        "observed_at": (sealed - timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        "expires_at": (sealed + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
        "evidence_code": "model_present",
        "probe_version": "availability-v1",
    }, now=sealed) for item in catalog]
    common = {
        "minimum_tier": "working", "required_capabilities": ["structured_output"],
        "locality": "any", "input_bytes": 65536, "output_bytes": 16384, "context_tokens": 32768,
        "risk_class": "standard", "independence_required": False,
    }
    assignments = [
        {"assignment_id": "manager", "role": "delivery-lead", "instructions": "Coordinate logical work.",
         "depends_on": [],
         "requirements": {**common, "operation": "manage"}},
        {"assignment_id": "producer", "role": "lead-developer", "instructions": "Edit the approved scope.",
         "depends_on": [],
         "requirements": {**common, "operation": "edit", "required_capabilities": ["structured_edit"]}},
        {"assignment_id": "verifier", "role": "quality-reviewer", "instructions": "Verify independently.",
         "depends_on": ["producer"],
         "requirements": {**common, "operation": "verify",
                          "risk_class": "high" if excluded_families else "standard",
                          "independence_required": bool(excluded_families)}},
    ]
    constraints = ([{
        "assignment_id": "verifier",
        "risk_class": "high",
        "excluded_provider_families": excluded_families,
        "producer_assignment_ids": ["producer"],
        "evidence_collector_assignment_ids": [],
        "source_binding_digests": ["d" * 64],
    }] if excluded_families else [])
    successor = successor_authority_digest(
        work_id="selection-test", attempt_id=attempt_id, charter_digest="b" * 64,
        manifest_digest="c" * 64, generation=1,
        sealed_at="2026-09-29T12:00:00Z", logical_assignments=assignments,
        catalog=catalog, availability=availability, independence_constraints=constraints,
        prior_authority_digest=None,
    )
    if waiver:
        amendment = {
            "schema_version": 1,
            "decision": "approve",
            "work_id": "selection-test",
            "attempt_id": attempt_id,
            "assignment_id": "verifier",
            "risk_class": "high",
            "excluded_provider_families": excluded_families,
            "waived_provider_families": excluded_families,
            "prior_policy_digest": policy["policy_digest"],
            "successor_authority_digest": successor,
            "approval_actor": "user",
            "approval_event_digest": "a" * 64,
        }
        amendment["approval_digest"] = digest(amendment)
        policy = merge_selection_policy({}, None, None, {"independence_waiver": amendment})
    inputs = {"policy": policy, "catalog": catalog, "availability": availability}
    envelope = {
        "schema_version": 1,
        "execution_protocol_version": 9,
        "work_id": "selection-test",
        "attempt_id": attempt_id,
        "charter_digest": "b" * 64,
        "manifest_digest": "c" * 64,
        "run_protocol_revision": 2,
        "logical_assignments": assignments,
        "selection_inputs": inputs,
        "selection_input_digests": {key: digest(value) for key, value in inputs.items()},
        "limits": {"max_actions": 18},
        "checkpoint_dir": ".flow/runs/selection-test/checkpoints",
        "delivery_charter_digest": "e" * 64,
        "delivery_lead_claim_digest": "f" * 64,
        "delivery_lead_claim": {"generation": 1},
    }
    envelope["selection_authority"] = seal_selection_authority(
        work_id=envelope["work_id"], attempt_id=envelope["attempt_id"],
        charter_digest=envelope["charter_digest"], manifest_digest=envelope["manifest_digest"], generation=1,
        sealed_at="2026-09-29T12:00:00Z", logical_assignments=assignments,
        policy=policy, catalog=catalog, availability=availability,
        independence_constraints=constraints,
    )
    return envelope


from tests.v9_coordinator import coordinate, adapt
from tests.maf_env import MAF_PYTHON, requires_maf

class DeliverySelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        guard = patch("delivery_gateway.delivery_authority_guard", return_value=nullcontext())
        guard.start()
        self.addCleanup(guard.stop)

    def test_historical_v9_action_budget_is_readable_without_rewriting(self):
        envelope = _envelope()
        envelope["limits"]["max_actions"] = 64
        validate_envelope(envelope)
        self.assertEqual(envelope["limits"]["max_actions"], 64)

    def test_v9_rejects_concrete_shaper_authority(self) -> None:
        envelope = _envelope()
        envelope["logical_assignments"][0]["provider"] = "ollama"
        with self.assertRaisesRegex(ContractError, "concrete provider authority"):
            validate_envelope(envelope)

    def test_v9_rejects_delivery_and_selection_generation_mismatch(self) -> None:
        envelope = _envelope()
        envelope["delivery_lead_claim"]["generation"] = 2
        with self.assertRaisesRegex(ContractError, "generations differ"):
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

    def test_repeated_pre_send_refusals_accumulate_without_candidate_reuse(self) -> None:
        envelope = _envelope()
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        selected = []
        for expected_id in ("local", "claude", "codex"):
            self.assertEqual(action["selection_decision"]["selected_candidate_id"], expected_id)
            result = authorize_and_dispatch(
                envelope, action, lambda *_: self.fail("adapter must not be called"),
                readiness_recheck=lambda binding: {
                    **binding, "state": "unavailable", "no_send_observed": True,
                    "evidence_code": "connection_refused_before_send",
                },
            )
            selected.append(result["candidate_id"])
            action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1,
                                 decision=result["successor_decision"])
        self.assertEqual(selected, ["local", "claude", "codex"])
        self.assertEqual(action["selection_decision"]["prior_no_send_failures"],
                         ["local", "claude", "codex"])
        self.assertIsNone(action["selection_decision"]["selected_binding"])

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

    def test_gateway_v9_send_is_ledger_claimed_before_adapter_and_closed_after_result(self) -> None:
        envelope = _envelope()
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            seen = []

            def send(binding, sent_action):
                snapshot = ledger.snapshot(envelope["attempt_id"])
                seen.append((binding["candidate_id"], sent_action["action_id"], snapshot))
                self.assertEqual(snapshot["provider_selections"][0]["state"], "consumed")
                self.assertEqual(snapshot["provider_selections"][0]["provider_action_id"], action["action_id"])
                self.assertEqual(snapshot["actions"][0]["status"], "started")
                return {"output": "done"}

            result = execute_v9_selected_action(
                envelope, action, send,
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                ledger=ledger, generation=1,
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(seen[0][0], "local")
            snapshot = ledger.snapshot(envelope["attempt_id"])
            self.assertEqual(snapshot["actions"][0]["status"], "completed")
            self.assertEqual(snapshot["provider_selections"][0]["state"], "consumed")
            self.assertFalse(ledger.v9_recovery_required(envelope["attempt_id"]))

    def test_gateway_v9_uncertain_send_is_durable_and_cannot_fall_forward(self) -> None:
        envelope = _envelope()
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            with self.assertRaises(RecoveryRequired):
                execute_v9_selected_action(
                    envelope, action, lambda *_: (_ for _ in ()).throw(TimeoutError()),
                    readiness_recheck=lambda binding: {**binding, "state": "ready"},
                    ledger=ledger, generation=1,
                )
            snapshot = ledger.snapshot(envelope["attempt_id"])
            self.assertEqual(snapshot["provider_selections"][0]["state"], "consumed")
            self.assertEqual(snapshot["actions"][0]["status"], "unknown")

    def test_crash_after_dispatch_before_receipt_blocks_restart_without_duplicate(self):
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            sends = []

            def send(binding, action):
                sends.append(action["assignment_id"])
                if action["assignment_id"] == "manager":
                    return _manager_result_for_action(action)
                raise SystemExit("crash after worker dispatch, before receipt")

            with self.assertRaises(RecoveryRequired):
                execute_v9_logical_delivery(envelope, "Implement.", ledger, send,
                    readiness_recheck=lambda binding: {**binding, "state": "ready"}, supervisor=coordinate)
            self.assertEqual(ledger.snapshot(envelope["attempt_id"])["actions"][-1]["status"], "unknown")
            with self.assertRaisesRegex(ContractError, "reconciliation"):
                execute_v9_logical_delivery(envelope, "Implement.", ledger, send,
                    readiness_recheck=lambda binding: {**binding, "state": "ready"}, supervisor=coordinate)
            with self.assertRaises(RecoveryRefused):
                ledger.create_attempt(_envelope(attempt_id="new-attempt-cannot-hide-unknown"))
            self.assertEqual(sends, ["manager", "producer"])
            self.assertEqual(ledger.snapshot(envelope["attempt_id"])["status"], "started")

    def test_new_attempt_cannot_reset_sealed_authority_token_spend(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            sends = []
            for attempt_id in ("first", "second"):
                envelope = _envelope(attempt_id=attempt_id, allowed_candidates=["codex"])
                envelope["limits"].update({"max_manager_calls": 12, "max_delegations": 6,
                    "max_verifier_calls": 2, "max_paid_worker_calls": 6,
                    "max_lineage_tokens": 1, "unobserved_send_tokens": 1})
                ledger.create_attempt(envelope)
                action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
                dispatch = lambda: execute_v9_selected_action(envelope, action,
                    lambda binding, request: sends.append(request["attempt_id"]) or {"output": "observed"},
                    readiness_recheck=lambda binding: {**binding, "state": "ready"}, ledger=ledger, generation=1)
                if attempt_id == "first":
                    dispatch()
                    ledger.terminate_v9_attempt(attempt_id, "abandoned", generation=1, actor="test",
                        explanation="budget test", cause="operator_abandoned", receipt_path=Path(tmp)/"receipt.json")
                else:
                    with self.assertRaisesRegex(ContractError, "token budget exhausted"):
                        dispatch()
                    self.assertEqual(ledger.snapshot(attempt_id)["actions"], [])
            self.assertEqual(sends, ["first"])

    def test_capacity_refusal_resume_preserves_logical_identity_and_does_not_accept_refusal(self):
        for interrupt_success, max_actions in ((False, 5), (True, 18)):
            with self.subTest(interrupt_success=interrupt_success, max_actions=max_actions):
                self._resume_capacity_refusal(interrupt_success=interrupt_success, max_actions=max_actions)

    def _resume_capacity_refusal(self, *, interrupt_success, max_actions):
        envelope = _envelope(allowed_candidates=["claude", "codex"])
        envelope["limits"]["max_actions"] = max_actions
        sends = []
        refused = []
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)

            def send(binding, action):
                sends.append((action["assignment_id"], binding["candidate_id"]))
                if action["assignment_id"] == "manager":
                    return _manager_result_for_action(action)
                if action["assignment_id"] == "producer" and binding["provider"] == "claude":
                    refused.append(action)
                    raise ObservedNotExecuted(provider="claude", category="model_capacity",
                                              observation_sha256="a" * 64)
                return {"output": "observed"}

            real_selected = execute_v9_selected_action

            def stop_after_refusal(*args, **kwargs):
                result = real_selected(*args, **kwargs)
                if result["status"] == "observed_not_executed":
                    raise SystemExit("crash after durable capacity refusal")
                return result

            with patch("delivery_gateway.execute_v9_selected_action", side_effect=stop_after_refusal):
                with self.assertRaises(SystemExit):
                    execute_v9_logical_delivery(envelope, "Implement.", ledger, send,
                        readiness_recheck=lambda b: {**b, "state": "ready"}, supervisor=coordinate)
            self.assertFalse(ledger.v9_recovery_required(envelope["attempt_id"]))
            accepted_on_resume = []

            def resume(envelope, task, on_action, **kwargs):
                accepted_on_resume.extend(kwargs["completed_assignments"])
                return coordinate(envelope, task, on_action, **kwargs)

            def stop_after_success(*args, **kwargs):
                result = real_selected(*args, **kwargs)
                if args[1]["assignment_id"] == "producer" and result["status"] == "completed":
                    raise SystemExit("crash after durable successor result")
                return result

            if interrupt_success:
                with patch("delivery_gateway.execute_v9_selected_action", side_effect=stop_after_success):
                    with self.assertRaises(SystemExit):
                        execute_v9_logical_delivery(envelope, "Implement.", ledger, send,
                            readiness_recheck=lambda b: {**b, "state": "ready"}, supervisor=resume)
                self.assertEqual(accepted_on_resume, [])
            execute_v9_logical_delivery(envelope, "Implement.", ledger, send,
                readiness_recheck=lambda b: {**b, "state": "ready"}, supervisor=resume)
            self.assertEqual(accepted_on_resume, ["producer"] if interrupt_success else [])
            workers = [row for row in ledger.snapshot(envelope["attempt_id"])["actions"]
                       if row["request"]["assignment_id"] == "producer"]
            self.assertEqual([row["status"] for row in workers], ["observed_not_executed", "completed"])
            for key in ("logical_action_id", "task", "sequence", "manager_turn"):
                self.assertEqual(workers[1]["request"][key], refused[0][key])
            self.assertEqual([candidate for assignment, candidate in sends if assignment == "producer"],
                             ["claude", "codex"])

    def test_capacity_successor_uses_same_action_slot_and_new_action_is_refused_before_send(self):
        envelope = _envelope(allowed_candidates=["claude", "codex"])
        envelope["limits"]["max_actions"] = 1
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            original = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
            refused = execute_v9_selected_action(envelope, original,
                lambda *_: (_ for _ in ()).throw(ObservedNotExecuted(
                    provider="claude", category="model_capacity", observation_sha256="a" * 64)),
                readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1)
            successor = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1,
                                    decision=refused["successor_decision"])
            sends = []
            result = execute_v9_selected_action(envelope, successor,
                lambda b, a: sends.append(a["action_id"]) or {"output": "observed"},
                readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1,
                predecessor_selection_id=original["selection_id"])
            self.assertEqual(result["status"], "completed")
            new_action = make_action(envelope, "manager", "New work.", sequence=2, manager_turn=2)
            with self.assertRaisesRegex(ContractError, "action budget exhausted"):
                execute_v9_selected_action(envelope, new_action,
                    lambda b, a: sends.append(a["action_id"]) or {"output": "unexpected"},
                    readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1)
            self.assertEqual(sends, [successor["action_id"]])
            self.assertFalse(ledger.v9_recovery_required(envelope["attempt_id"]))
            self.assertEqual(len(ledger.snapshot(envelope["attempt_id"])["actions"]), 2)

    def test_budget_denials_allow_terminal_receipts_and_successors(self):
        # Fresh work is rejected before reservation. The final fence must also
        # close a reservation if another send used the last slot meanwhile.
        cases = [("max_actions", "manager", "local", "action"),
                 ("max_manager_calls", "manager", "local", "operation"),
                 ("max_delegations", "producer", "local", "operation"),
                 ("max_verifier_calls", "verifier", "local", "operation"),
                 ("max_paid_worker_calls", "producer", "codex", "operation"),
                 ("max_lineage_tokens", "producer", "codex", "token")]
        for limit, assignment, candidate, error in cases:
            for reserved in (False, True):
                for terminal in ("cancelled", "abandoned"):
                    with self.subTest(limit=limit, reserved=reserved, terminal=terminal), tempfile.TemporaryDirectory() as tmp:
                        envelope = _envelope(allowed_candidates=[candidate])
                        envelope["limits"].update(max_manager_calls=12, max_delegations=6,
                            max_verifier_calls=2, max_paid_worker_calls=6,
                            max_lineage_tokens=1000, unobserved_send_tokens=1)
                        envelope["limits"][limit] = 1
                        ledger = ExecutionLedger(Path(tmp)/"ledger.sqlite")
                        ledger.create_attempt(envelope)
                        first = make_action(envelope, assignment, "First.", sequence=1, manager_turn=1)
                        denied = make_action(envelope, assignment, "Denied.", sequence=2, manager_turn=2)
                        sends = []
                        send = lambda binding, action: sends.append(action["action_id"]) or {"output": "done"}
                        if reserved:
                            ledger.prepare_v9_selection(envelope, denied, generation=1)
                        execute_v9_selected_action(envelope, first, send,
                            readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1)
                        for _ in range(2):
                            with self.assertRaises(ContractError):
                                execute_v9_selected_action(envelope, denied, send,
                                    readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1)
                        snapshot = ledger.snapshot(envelope["attempt_id"])
                        self.assertEqual(sends, [first["action_id"]])
                        self.assertFalse(ledger.v9_recovery_required(envelope["attempt_id"]))
                        self.assertFalse(any(r["state"] in {"computed", "reserved"}
                                             for r in snapshot["provider_selections"]))
                        if reserved:
                            self.assertEqual(snapshot["actions"][-1]["status"], "pre_send_refused")
                            self.assertIn(error + " budget exhausted", snapshot["actions"][-1]["reason"])
                        else:
                            self.assertEqual(len(snapshot["actions"]), 1)
                            self.assertEqual(len(snapshot["provider_selections"]), 1)
                        path = Path(tmp)/"receipt.json"
                        ledger.terminate_v9_attempt(envelope["attempt_id"], terminal, generation=1,
                            actor="operator", explanation="budget exhausted", cause="operator_"+terminal,
                            receipt_path=path)
                        receipt = json.loads(path.read_text())
                        self.assertEqual(receipt["outcome"]["status"], terminal)
                        verify_selection_receipt(receipt)
                        ledger.create_attempt(_envelope(attempt_id="successor", allowed_candidates=[candidate]))

    def test_budget_denied_fallback_preserves_refusal_chain_and_can_close(self):
        for capacity in (False, True):
            with self.subTest(capacity=capacity), tempfile.TemporaryDirectory() as tmp:
                envelope = _envelope(allowed_candidates=["claude", "codex"] if capacity else None)
                envelope["limits"].update(max_manager_calls=12, max_delegations=1,
                    max_verifier_calls=2, max_paid_worker_calls=1 if capacity else 0,
                    max_lineage_tokens=1000, unobserved_send_tokens=1)
                ledger = ExecutionLedger(Path(tmp)/"ledger.sqlite")
                ledger.create_attempt(envelope)
                first = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
                def send(*_):
                    if capacity:
                        raise ObservedNotExecuted(provider="claude", category="model_capacity", observation_sha256="a"*64)
                    self.fail("pre-send refusal called adapter")
                result = execute_v9_selected_action(envelope, first, send,
                    readiness_recheck=lambda b: {**b, "state": "ready" if capacity else "unavailable",
                                                "no_send_observed": True, "evidence_code": "unavailable"},
                    ledger=ledger, generation=1)
                successor = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1,
                                        decision=result["successor_decision"])
                with self.assertRaisesRegex(ContractError, "operation budget exhausted"):
                    execute_v9_selected_action(envelope, successor, lambda *_: self.fail("send"),
                        readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1,
                        predecessor_selection_id=first["selection_id"])
                snapshot = ledger.snapshot(envelope["attempt_id"])
                self.assertFalse(any(r["state"] in {"computed", "reserved"} for r in snapshot["provider_selections"]))
                self.assertEqual(snapshot["actions"][-1]["status"], "pre_send_refused")
                path = Path(tmp)/"receipt.json"
                ledger.terminate_v9_attempt(envelope["attempt_id"], "abandoned", generation=1,
                    actor="operator", explanation="budget exhausted", cause="operator_abandoned", receipt_path=path)
                verify_selection_receipt(json.loads(path.read_text()))

    def test_lineage_token_denial_on_new_attempt_can_be_abandoned_without_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp)/"ledger.sqlite")
            sends = []
            for attempt_id in ("spent", "denied"):
                envelope = _envelope(attempt_id=attempt_id, allowed_candidates=["codex"])
                envelope["limits"].update(max_manager_calls=12, max_delegations=6,
                    max_verifier_calls=2, max_paid_worker_calls=6,
                    max_lineage_tokens=1, unobserved_send_tokens=1)
                ledger.create_attempt(envelope)
                action = make_action(envelope, "manager", "Plan.", sequence=1, manager_turn=1)
                if attempt_id == "spent":
                    execute_v9_selected_action(envelope, action,
                        lambda b, a: sends.append(a["action_id"]) or {"output": "done"},
                        readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1)
                else:
                    with self.assertRaisesRegex(ContractError, "token budget exhausted"):
                        execute_v9_selected_action(envelope, action,
                            lambda *_: self.fail("denied send executed"),
                            readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1)
                    self.assertEqual(ledger.snapshot(attempt_id)["provider_selections"], [])
                path = Path(tmp)/(attempt_id+".json")
                ledger.terminate_v9_attempt(attempt_id, "abandoned", generation=1,
                    actor="operator", explanation="close attempt", cause="operator_abandoned", receipt_path=path)
                verify_selection_receipt(json.loads(path.read_text()))
            self.assertEqual(len(sends), 1)

    def test_budget_closure_cannot_modify_stale_owner_or_unknown_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            envelope = _envelope()
            envelope["limits"]["max_actions"] = 1
            ledger = ExecutionLedger(Path(tmp)/"ledger.sqlite")
            ledger.create_attempt(envelope)
            action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
            with self.assertRaises(RecoveryRequired):
                execute_v9_selected_action(envelope, action,
                    lambda *_: (_ for _ in ()).throw(TimeoutError("unknown")),
                    readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1)
            denied = make_action(envelope, "manager", "Plan.", sequence=2, manager_turn=2)
            before = ledger.snapshot(envelope["attempt_id"])
            with self.assertRaisesRegex(ContractError, "ownership is stale"):
                execute_v9_selected_action(envelope, denied, lambda *_: self.fail("send"),
                    readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=2)
            self.assertEqual(ledger.snapshot(envelope["attempt_id"]), before)
            with self.assertRaisesRegex(ContractError, "action budget exhausted"):
                execute_v9_selected_action(envelope, denied, lambda *_: self.fail("send"),
                    readiness_recheck=lambda b: {**b, "state": "ready"}, ledger=ledger, generation=1)
            self.assertTrue(ledger.v9_recovery_required(envelope["attempt_id"]))
            self.assertEqual(ledger.snapshot(envelope["attempt_id"])["actions"][0]["status"], "unknown")
            with self.assertRaises(RecoveryRefused):
                ledger.create_attempt(_envelope(attempt_id="successor"))

    def test_gateway_v9_observed_capacity_refusal_is_failed_and_can_select_successor(self) -> None:
        """A bounded terminal capacity refusal is not an uncertain paid send."""
        envelope = _envelope()
        inputs = envelope["selection_inputs"]
        # The ordinary fixture ranks Ollama first.  This focused provider
        # refusal test begins with Claude and leaves Codex as the only
        # deterministic successor.
        inputs["catalog"] = [item for item in inputs["catalog"]
                             if item["candidate_id"] in {"claude", "codex"}]
        inputs["availability"] = [item for item in inputs["availability"]
                                  if item["candidate_id"] in {"claude", "codex"}]
        envelope["selection_input_digests"] = {key: digest(value) for key, value in inputs.items()}
        envelope["selection_authority"] = seal_selection_authority(
            work_id=envelope["work_id"], attempt_id=envelope["attempt_id"],
            charter_digest=envelope["charter_digest"], manifest_digest=envelope["manifest_digest"],
            generation=1, sealed_at="2026-09-29T12:00:00Z",
            logical_assignments=envelope["logical_assignments"], policy=inputs["policy"],
            catalog=inputs["catalog"], availability=inputs["availability"],
            independence_constraints=[],
        )
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        self.assertEqual(action["selection_decision"]["selected_candidate_id"], "claude")
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            result = execute_v9_selected_action(
                envelope, action,
                lambda _binding, _action: (_ for _ in ()).throw(
                    ObservedNotExecuted(provider="claude", category="model_capacity",
                                        observation_sha256="a" * 64)),
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                ledger=ledger, generation=1,
            )
            self.assertEqual(result["status"], "observed_not_executed")
            self.assertEqual(result["evidence_code"], "model_capacity")
            self.assertEqual(result["successor_decision"]["selected_candidate_id"], "codex")
            snapshot = ledger.snapshot(envelope["attempt_id"])
            self.assertEqual(snapshot["actions"][0]["status"], "observed_not_executed")
            self.assertEqual(snapshot["actions"][0]["reason"], "model_capacity")
            self.assertEqual(snapshot["provider_selections"][0]["state"], "observed_not_executed")
            self.assertFalse(ledger.v9_recovery_required(envelope["attempt_id"]))
            receipt = receipt_from_snapshot(
                snapshot, outcome={"status": "abandoned", "reason": "fixture_capacity_refusal"})
            self.assertEqual(verify_selection_receipt(receipt)["status"], "valid_pass")
            self.assertEqual(receipt["provider_refusals"][0]["diagnostic_sha256"], "a" * 64)
            tampered = copy.deepcopy(receipt)
            tampered["provider_refusals"][0]["observation_sha256"] = "b" * 64
            tampered["receipt_digest"] = digest({key: value for key, value in tampered.items()
                                                  if key != "receipt_digest"})
            with self.assertRaisesRegex(V9ReceiptError, "v9_provider_refusal_invalid|v9_observed_refusal_invalid|v9_receipt"):
                verify_selection_receipt(tampered)

    def test_v9_unknown_send_can_only_be_abandoned_with_a_terminal_receipt(self) -> None:
        envelope = _envelope()
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = ExecutionLedger(root / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            with self.assertRaises(RecoveryRequired):
                execute_v9_selected_action(
                    envelope, action, lambda *_: (_ for _ in ()).throw(TimeoutError()),
                    readiness_recheck=lambda binding: {**binding, "state": "ready"}, ledger=ledger, generation=1,
                )
            with self.assertRaisesRegex(ContractError, "recovery or selection closure"):
                ledger.seal_v9_attempt(envelope["attempt_id"], "completed", "done", root / "receipt.json", generation=1)
            terminal = ledger.terminate_v9_attempt(
                envelope["attempt_id"], "abandoned", generation=1, actor="operator",
                explanation="provider outcome remained unknown", cause="operator_abandoned",
                receipt_path=root / "receipt.json",
            )
            self.assertEqual(terminal["status"], "abandoned")
            receipt = json.loads((root / "receipt.json").read_text())
            self.assertEqual(receipt["termination"]["status"], "abandoned")
            self.assertEqual(receipt["selections"][0]["state"], "consumed")

    def test_logical_v9_route_passes_maf_proposal_through_flow_fence_to_adapter(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            seen = {}
            supervisor_timeouts = []

            def supervisor(sent_envelope, task, on_action, *, manager_decision, **_kwargs):
                self.assertEqual(sent_envelope, envelope)
                supervisor_timeouts.append(_kwargs["timeout_s"])
                outcome = on_action({"attempt_id": envelope["attempt_id"],
                                     "assignment_id": manager_decision["assignment_id"],
                                     "task": manager_decision["task"], "sequence": 1,
                                     "manager_turn": manager_decision["manager_turn"]})
                return {"status": "completed", "outcome": outcome}

            def adapter(binding, action):
                seen[action["assignment_id"]] = binding
                snapshot = ledger.snapshot(envelope["attempt_id"])
                self.assertEqual(snapshot["actions"][-1]["status"], "started")
                self.assertEqual(snapshot["provider_selections"][-1]["state"], "consumed")
                return (_manager_result_for_action(action, task="Implement the approved change.")
                        if action["assignment_id"] == "manager" else {"output": "applied"})

            outcome = execute_v9_logical_delivery(
                envelope, "Implement the approved change.", ledger, adapter,
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                supervisor=adapt(supervisor),
            )
            self.assertEqual(outcome["status"], "completed")
            manager_task = ledger.snapshot(envelope["attempt_id"])["actions"][0]["request"]["task"]
            self.assertIn('"producer"', manager_task)
            self.assertEqual({name: item["candidate_id"] for name, item in seen.items()},
                             {"manager": "local", "producer": "local", "verifier": "local"})
            self.assertEqual([item["status"] for item in ledger.snapshot(envelope["attempt_id"])["actions"]],
                             ["completed", "completed", "completed", "completed"])
            self.assertEqual(supervisor_timeouts, [900, 900])

    def test_logical_v9_manager_decision_drives_verifier_stage(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            seen = []

            def adapter(binding, action):
                seen.append(action["assignment_id"])
                if action["assignment_id"] == "manager":
                    return _manager_result_for_action(action)
                return {"output": "verified"}

            def supervisor(_envelope, _task, on_action, *, manager_decision, **_kwargs):
                self.assertIn(manager_decision["assignment_id"], {"producer", "verifier"})
                return on_action({"attempt_id": envelope["attempt_id"],
                                  "assignment_id": manager_decision["assignment_id"],
                                  "task": manager_decision["task"], "sequence": 1,
                                  "manager_turn": manager_decision["manager_turn"]})

            outcome = execute_v9_logical_delivery(
                envelope, "Complete the approved work.", ledger, adapter,
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                supervisor=adapt(supervisor),
            )
            self.assertEqual(outcome["status"], "completed")
            self.assertEqual(seen, ["manager", "producer", "manager", "verifier"])

    def test_manager_selects_one_of_multiple_dependency_valid_assignments(self) -> None:
        envelope = _envelope()
        producer_two = copy.deepcopy(next(item for item in envelope["logical_assignments"]
                                           if item["assignment_id"] == "producer"))
        producer_two["assignment_id"] = "producer-two"
        producer_two["instructions"] = "Edit the second approved scope."
        envelope["logical_assignments"].insert(2, producer_two)
        verifier = next(item for item in envelope["logical_assignments"]
                        if item["assignment_id"] == "verifier")
        verifier["depends_on"] = ["producer", "producer-two"]
        envelope["limits"]["max_actions"] = 6
        inputs = envelope["selection_inputs"]
        envelope["selection_authority"] = seal_selection_authority(
            work_id=envelope["work_id"], attempt_id=envelope["attempt_id"],
            charter_digest=envelope["charter_digest"], manifest_digest=envelope["manifest_digest"],
            generation=1, sealed_at="2026-09-29T12:00:00Z",
            logical_assignments=envelope["logical_assignments"], policy=inputs["policy"],
            catalog=inputs["catalog"], availability=inputs["availability"],
            independence_constraints=[],
        )
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            manager_turn = 0
            worker_order = []

            def adapter(_binding, action):
                nonlocal manager_turn
                if action["assignment_id"] == "manager":
                    manager_turn += 1
                    selected = ("producer-two" if manager_turn == 1 else
                                "producer" if manager_turn == 2 else "verifier")
                    return _manager_result(selected, "bounded note")
                worker_order.append(action["assignment_id"])
                return {"output": "done"}

            execute_v9_logical_delivery(
                envelope, "Complete approved work.", ledger, adapter,
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                supervisor=coordinate,
            )
            self.assertEqual(worker_order, ["producer-two", "producer", "verifier"])
            prompts = [item["request"]["task"] for item in ledger.snapshot(envelope["attempt_id"])["actions"]
                       if item["request"]["assignment_id"] == "manager"]
            self.assertIn('"producer-two"', prompts[0])
            self.assertIn('"producer"', prompts[0])
            self.assertNotIn('"verifier"', prompts[0])

    def test_logical_v9_rejects_proposal_that_differs_from_manager_decision(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)

            def adapter(_binding, action):
                if action["assignment_id"] == "manager":
                    return _manager_result_for_action(action)
                self.fail("worker adapter must not be called")

            with self.assertRaisesRegex(ContractError, "differs from the permitted Magentic decision"):
                execute_v9_logical_delivery(
                    envelope, "Complete the approved work.", ledger, adapter,
                    readiness_recheck=lambda binding: {**binding, "state": "ready"},
                    supervisor=lambda _envelope, _task, on_action, **_kwargs: on_action({
                        "attempt_id": envelope["attempt_id"], "assignment_id": "producer",
                        "task": "Implement instead.", "sequence": 1, "manager_turn": 1,
                    }),
                )

    def test_logical_v9_pre_send_refusal_falls_to_hosted_candidate_once(self) -> None:
        """Only a no-I/O local refusal may advance to the next binding."""
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            sends = []

            def supervisor(_envelope, task, on_action, *, manager_decision, **_kwargs):
                return {"status": "completed", "outcome": on_action({
                    "attempt_id": envelope["attempt_id"], "assignment_id": manager_decision["assignment_id"],
                    "task": manager_decision["task"], "sequence": 1,
                    "manager_turn": manager_decision["manager_turn"],
                })}

            def readiness(binding):
                if binding["candidate_id"] == "local":
                    return {**binding, "state": "unavailable", "no_send_observed": True,
                            "evidence_code": "model_absent"}
                return {**binding, "state": "ready"}

            outcome = execute_v9_logical_delivery(
                envelope, "Implement.", ledger,
                lambda binding, action: sends.append(binding["candidate_id"]) or (
                    _manager_result_for_action(action, task="Implement.") if action["assignment_id"] == "manager"
                    else {"output": "done"}),
                readiness_recheck=readiness, supervisor=adapt(supervisor),
            )
            self.assertEqual(outcome["outcome"]["status"], "completed")
            self.assertEqual(sends, ["claude", "claude", "claude", "claude"])
            selections = ledger.snapshot(envelope["attempt_id"])["provider_selections"]
            self.assertEqual([item["state"] for item in selections],
                             ["superseded", "consumed", "superseded", "consumed",
                              "superseded", "consumed", "superseded", "consumed"])

    def test_verifier_family_exclusions_use_final_consumed_producer_after_fallback(self) -> None:
        envelope = _envelope(excluded_families=["local"])
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            sends = []

            def readiness(binding):
                if binding["candidate_id"] == "local":
                    return {**binding, "state": "unavailable", "no_send_observed": True,
                            "evidence_code": "model_absent"}
                return {**binding, "state": "ready"}

            def adapter(binding, action):
                sends.append((action["assignment_id"], binding["candidate_id"]))
                return (_manager_result_for_action(action) if action["assignment_id"] == "manager"
                        else {"output": "done"})

            execute_v9_logical_delivery(
                envelope, "Complete.", ledger, adapter, readiness_recheck=readiness,
                supervisor=coordinate,
            )
            self.assertIn(("producer", "claude"), sends)
            self.assertIn(("verifier", "codex"), sends)
            verifier_action = next(item["request"] for item in ledger.snapshot(envelope["attempt_id"])["actions"]
                                   if item["request"]["assignment_id"] == "verifier")
            self.assertEqual(verifier_action["selection_decision"]["excluded_families"], ["anthropic"])

    def test_verifier_fallback_receipt_replays_runtime_family_exclusions(self) -> None:
        envelope = _envelope(excluded_families=["local"])
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)

            def readiness(binding):
                if binding["candidate_id"] == "claude":
                    return {**binding, "state": "unavailable", "no_send_observed": True,
                            "evidence_code": "connection_refused_before_send"}
                return {**binding, "state": "ready"}

            def adapter(_binding, action):
                if action["assignment_id"] == "manager":
                    return _manager_result_for_action(action)
                if action["assignment_id"] == "verifier":
                    return {"output": json.dumps({"schema_version": 1, "decision": "pass",
                                                   "summary": "Evidence passes.", "findings": []})}
                return {"output": "done"}

            execute_v9_logical_delivery(
                envelope, "Complete.", ledger, adapter, readiness_recheck=readiness,
                supervisor=coordinate,
            )
            snapshot = ledger.snapshot(envelope["attempt_id"])
            verifier_row = next(item for item in snapshot["actions"]
                                if item["request"]["assignment_id"] == "verifier")
            verifier_action = verifier_row["request"]
            result = verifier_row["result"]["result"]
            verifier_input = {"provider_task": verifier_action["task"], "assignment_id": "verifier"}
            evaluation = evaluate_candidate(
                action_id=verifier_action["action_id"], verifier_input_digest=digest(verifier_input),
                raw_output=result["output"], diff_digest="d" * 64,
                test_evidence_digest="e" * 64,
            )
            ledger.record_v9_verifier_evaluation(
                verifier_action["action_id"], verifier_input, result, evaluation,
                "d" * 64, "e" * 64, generation=1,
            )
            receipt = receipt_from_snapshot(
                ledger.snapshot(envelope["attempt_id"]),
                outcome={"status": "completed", "reason": "semantic_verifier_valid_pass"},
            )
            self.assertEqual(verify_selection_receipt(receipt)["status"], "valid_pass")
            verifier_selections = [item for item in receipt["selections"]
                                   if item["logical_action_id"] == verifier_action["logical_action_id"]]
            self.assertEqual([item["candidate_id"] for item in verifier_selections], ["claude", "codex"])

    def test_refusal_only_exhaustion_seals_a_normal_failed_receipt(self) -> None:
        envelope = _envelope()
        inputs = envelope["selection_inputs"]
        inputs["catalog"] = [item for item in inputs["catalog"] if item["candidate_id"] == "claude"]
        inputs["availability"] = [item for item in inputs["availability"] if item["candidate_id"] == "claude"]
        envelope["selection_input_digests"] = {key: digest(value) for key, value in inputs.items()}
        envelope["selection_authority"] = seal_selection_authority(
            work_id=envelope["work_id"], attempt_id=envelope["attempt_id"],
            charter_digest=envelope["charter_digest"], manifest_digest=envelope["manifest_digest"],
            generation=1, sealed_at="2026-09-29T12:00:00Z",
            logical_assignments=envelope["logical_assignments"], policy=inputs["policy"],
            catalog=inputs["catalog"], availability=inputs["availability"],
            independence_constraints=[],
        )
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = ExecutionLedger(root / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            result = execute_v9_selected_action(
                envelope, action,
                lambda _binding, _action: (_ for _ in ()).throw(
                    ObservedNotExecuted(provider="claude", category="model_capacity",
                                        observation_sha256="a" * 64)),
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                ledger=ledger, generation=1,
            )
            self.assertIsNone(result["successor_decision"]["selected_binding"])
            sealed = ledger.seal_v9_attempt(
                envelope["attempt_id"], "failed", "provider_candidates_exhausted",
                root / "receipt.json", generation=1)
            receipt = json.loads(Path(sealed["receipt_path"]).read_text())
            self.assertEqual(receipt["outcome"], {
                "status": "failed", "reason": "provider_candidates_exhausted"})
            self.assertEqual(verify_selection_receipt(receipt)["status"], "valid_pass")
            self.assertFalse(ledger.v9_recovery_required(envelope["attempt_id"]))

    def test_refusal_only_failure_is_rejected_while_a_successor_remains(self) -> None:
        envelope = _envelope()
        inputs = envelope["selection_inputs"]
        inputs["catalog"] = [item for item in inputs["catalog"]
                             if item["candidate_id"] in {"claude", "codex"}]
        inputs["availability"] = [item for item in inputs["availability"]
                                  if item["candidate_id"] in {"claude", "codex"}]
        envelope["selection_input_digests"] = {key: digest(value) for key, value in inputs.items()}
        envelope["selection_authority"] = seal_selection_authority(
            work_id=envelope["work_id"], attempt_id=envelope["attempt_id"],
            charter_digest=envelope["charter_digest"], manifest_digest=envelope["manifest_digest"],
            generation=1, sealed_at="2026-09-29T12:00:00Z",
            logical_assignments=envelope["logical_assignments"], policy=inputs["policy"],
            catalog=inputs["catalog"], availability=inputs["availability"],
            independence_constraints=[],
        )
        action = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            result = execute_v9_selected_action(
                envelope, action,
                lambda _binding, _action: (_ for _ in ()).throw(
                    ObservedNotExecuted(provider="claude", category="model_capacity",
                                        observation_sha256="a" * 64)),
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                ledger=ledger, generation=1,
            )
            self.assertEqual(result["successor_decision"]["selected_candidate_id"], "codex")
            with self.assertRaisesRegex(V9ReceiptError, "v9_failed_outcome_evidence_missing"):
                ledger.seal_v9_attempt(
                    envelope["attempt_id"], "failed", "provider_candidates_exhausted",
                    Path(tmp) / "receipt.json", generation=1)

    def test_capacity_fallback_dispatches_successor_at_same_logical_sequence(self) -> None:
        envelope = _envelope()
        inputs = envelope["selection_inputs"]
        inputs["catalog"] = [item for item in inputs["catalog"]
                             if item["candidate_id"] in {"claude", "codex"}]
        inputs["availability"] = [item for item in inputs["availability"]
                                  if item["candidate_id"] in {"claude", "codex"}]
        envelope["selection_input_digests"] = {key: digest(value) for key, value in inputs.items()}
        envelope["selection_authority"] = seal_selection_authority(
            work_id=envelope["work_id"], attempt_id=envelope["attempt_id"],
            charter_digest=envelope["charter_digest"], manifest_digest=envelope["manifest_digest"],
            generation=1, sealed_at="2026-09-29T12:00:00Z",
            logical_assignments=envelope["logical_assignments"], policy=inputs["policy"],
            catalog=inputs["catalog"], availability=inputs["availability"],
            independence_constraints=[],
        )
        first = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            first_result = execute_v9_selected_action(
                envelope, first,
                lambda _binding, _action: (_ for _ in ()).throw(
                    ObservedNotExecuted(provider="claude", category="model_capacity",
                                        observation_sha256="a" * 64)),
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                ledger=ledger, generation=1,
            )
            successor = make_action(
                envelope, "producer", "Implement.", sequence=1, manager_turn=1,
                decision=first_result["successor_decision"],
            )
            sent = []
            result = execute_v9_selected_action(
                envelope, successor,
                lambda binding, _action: sent.append(binding["candidate_id"]) or {"output": "done"},
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                ledger=ledger, generation=1,
                predecessor_selection_id=first["selection_id"],
            )
            self.assertEqual(sent, ["codex"])
            self.assertEqual(result["status"], "completed")
            snapshot = ledger.snapshot(envelope["attempt_id"])
            self.assertEqual([item["request"]["sequence"] for item in snapshot["actions"]], [1, 1])

    def test_independent_verifier_pre_send_fallback_survives_transient_selection_row(self) -> None:
        envelope = _envelope(excluded_families=["local"])
        producer = make_action(envelope, "producer", "Implement.", sequence=1, manager_turn=1)
        verifier = make_action(
            envelope, "verifier", "Verify.", sequence=2, manager_turn=2,
            runtime_excluded_families=["local"],
        )
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            execute_v9_selected_action(
                envelope, producer, lambda _binding, _action: {"output": "done"},
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                ledger=ledger, generation=1,
            )
            first = execute_v9_selected_action(
                envelope, verifier, lambda _binding, _action: self.fail("refused candidate sent"),
                readiness_recheck=lambda binding: {
                    **binding, "state": "unavailable", "no_send_observed": True,
                    "evidence_code": "probe_failed",
                },
                ledger=ledger, generation=1,
            )
            successor = make_action(
                envelope, "verifier", "Verify.", sequence=2, manager_turn=2,
                decision=first["successor_decision"],
            )
            sent = []
            result = execute_v9_selected_action(
                envelope, successor,
                lambda binding, _action: sent.append(binding["candidate_id"]) or {"output": "pass"},
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                ledger=ledger, generation=1,
                predecessor_selection_id=verifier["selection_id"],
            )
            self.assertEqual(result["status"], "completed")
            self.assertEqual(sent, ["codex"])

    def test_logical_v9_hosted_uncertain_send_fails_closed_without_next_fallback(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            sends = []

            def supervisor(_envelope, _task, on_action, *, manager_decision, **_kwargs):
                return on_action({"attempt_id": envelope["attempt_id"], "assignment_id": "producer",
                                  "task": manager_decision["task"], "sequence": 1, "manager_turn": 1})

            def readiness(binding):
                if binding["candidate_id"] == "local":
                    return {**binding, "state": "unavailable", "no_send_observed": True,
                            "evidence_code": "model_absent"}
                return {**binding, "state": "ready"}

            def uncertain_hosted(binding, action):
                sends.append(binding["candidate_id"])
                if action["assignment_id"] == "manager":
                    return _manager_result_for_action(action, task="Implement.")
                raise TimeoutError("hosted send outcome unknown")

            with self.assertRaises(RecoveryRequired):
                execute_v9_logical_delivery(envelope, "Implement.", ledger, uncertain_hosted,
                                            readiness_recheck=readiness, supervisor=adapt(supervisor))
            self.assertEqual(sends, ["claude", "claude"])
            selections = ledger.snapshot(envelope["attempt_id"])["provider_selections"]
            self.assertEqual([item["state"] for item in selections],
                             ["superseded", "consumed", "superseded", "consumed"])
            self.assertEqual(ledger.snapshot(envelope["attempt_id"])["actions"][-1]["status"], "unknown")

    @requires_maf
    def test_logical_v9_route_runs_stock_magentic_with_dependent_assignments(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            checkpoints = Path(tmp) / "checkpoints"
            checkpoints.mkdir()
            envelope["checkpoint_dir"] = str(checkpoints)
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            worker_order = []
            phases = []

            def adapter(binding, action):
                if action["assignment_id"] != "manager":
                    worker_order.append(action["assignment_id"])
                    return {"output": "applied"}
                match = re.search(r"Flow permitted unfinished frontier: (\[[^\n]*\])", action["task"])
                if match is None:
                    phases.append("text")
                    return {"output": "Bounded stock manager facts, plan or final answer."}
                frontier = json.loads(match.group(1))
                phases.append("progress")
                progress = _manager_result(frontier[0] if frontier else "verifier")["manager_response"]
                progress["is_request_satisfied"]["answer"] = not frontier
                return {"output": json.dumps(progress)}

            outcome = execute_v9_logical_delivery(
                envelope, "Implement the approved change.", ledger, adapter,
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                python_path=MAF_PYTHON)
            self.assertEqual(outcome["coordination"], "stock_magentic")
            self.assertEqual(worker_order, ["producer", "verifier"])
            self.assertGreaterEqual(phases.count("text"), 3)
            self.assertEqual(phases.count("progress"), 3)
            self.assertTrue(list(checkpoints.glob("*.json")))
            self.assertTrue(all(a["status"] == "completed" for a in ledger.snapshot(envelope["attempt_id"])["actions"]))

    def test_logical_v9_manager_uncertain_send_stops_inside_maf_callback(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            supervisor_calls = []
            with self.assertRaises(RecoveryRequired):
                execute_v9_logical_delivery(
                    envelope, "Implement.", ledger,
                    lambda _binding, _action: (_ for _ in ()).throw(TimeoutError("unknown")),
                    readiness_recheck=lambda binding: {**binding, "state": "ready"},
                    supervisor=coordinate,
                )
            self.assertEqual(supervisor_calls, [])
            snapshot = ledger.snapshot(envelope["attempt_id"])
            self.assertEqual(snapshot["actions"][0]["request"]["assignment_id"], "manager")
            self.assertEqual(snapshot["actions"][0]["status"], "unknown")


class V9ExternalAuthorityFenceTests(unittest.TestCase):
    def test_superseded_delivery_generation_blocks_send_and_termination(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / ".flow" / "runs" / envelope["work_id"]
            attempt_dir = run_dir / "execution" / envelope["attempt_id"]
            (attempt_dir / "checkpoints").mkdir(parents=True)
            envelope["checkpoint_dir"] = str(attempt_dir / "checkpoints")
            ledger = ExecutionLedger(run_dir / "execution" / "ledger.sqlite")
            ledger.create_attempt(envelope)
            (run_dir / "run.json").write_text(json.dumps({"delivery": {
                "owner_status": "active", "owner_generation": 2,
                "charter_digest": envelope["delivery_charter_digest"],
                "lead_claim_digest": "0" * 64,
            }}))
            sends = []
            with self.assertRaisesRegex(DeliveryControlError, "stale"):
                execute_v9_logical_delivery(
                    envelope, "Implement.", ledger,
                    lambda binding, _action: sends.append(binding["candidate_id"]),
                    readiness_recheck=lambda binding: {**binding, "state": "ready"},
                    supervisor=lambda *_args, **_kwargs: {"status": "completed"},
                )
            self.assertEqual(sends, [])
            with self.assertRaisesRegex(DeliveryControlError, "stale"):
                terminate_v9_delivery(
                    envelope["work_id"], envelope["attempt_id"], status="abandoned",
                    actor="test", explanation="stale owner", root=root,
                )
            self.assertEqual(ledger.snapshot(envelope["attempt_id"])["status"], "started")


if __name__ == "__main__":
    unittest.main()
