from __future__ import annotations

import copy
import json
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
from delivery_control import DeliveryControlError  # noqa: E402
from execution_contracts import ContractError, digest, validate_envelope  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from provider_selection import merge_selection_policy  # noqa: E402
from provider_availability import normalize_availability  # noqa: E402
from selection_authority import (  # noqa: E402
    seal_selection_authority,
    successor_authority_digest,
)


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
              waiver: bool = False) -> dict:
    policy = merge_selection_policy({})
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
        "locality": "any", "input_bytes": 100, "output_bytes": 100, "context_tokens": 100,
        "risk_class": "standard", "independence_required": False,
    }
    assignments = [
        {"assignment_id": "manager", "role": "delivery-lead", "instructions": "Coordinate logical work.",
         "requirements": {**common, "operation": "manage"}},
        {"assignment_id": "producer", "role": "lead-developer", "instructions": "Edit the approved scope.",
         "requirements": {**common, "operation": "edit", "required_capabilities": ["structured_edit"]}},
        {"assignment_id": "verifier", "role": "quality-reviewer", "instructions": "Verify independently.",
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
        work_id="selection-test", attempt_id="attempt-v9", charter_digest="b" * 64,
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
            "attempt_id": "attempt-v9",
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
        "attempt_id": "attempt-v9",
        "charter_digest": "b" * 64,
        "manifest_digest": "c" * 64,
        "run_protocol_revision": 2,
        "logical_assignments": assignments,
        "selection_inputs": inputs,
        "selection_input_digests": {key: digest(value) for key, value in inputs.items()},
        "limits": {"max_actions": 3},
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


class DeliverySelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        guard = patch("delivery_gateway.delivery_authority_guard", return_value=nullcontext())
        guard.start()
        self.addCleanup(guard.stop)

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

            def supervisor(sent_envelope, task, on_action, *, manager_decision, **_kwargs):
                self.assertEqual(sent_envelope, envelope)
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
                supervisor=supervisor,
            )
            self.assertEqual(outcome["status"], "completed")
            manager_task = ledger.snapshot(envelope["attempt_id"])["actions"][0]["request"]["task"]
            self.assertIn('"producer"', manager_task)
            self.assertEqual({name: item["candidate_id"] for name, item in seen.items()},
                             {"manager": "local", "producer": "local", "verifier": "local"})
            self.assertEqual([item["status"] for item in ledger.snapshot(envelope["attempt_id"])["actions"]],
                             ["completed", "completed", "completed", "completed"])

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
                supervisor=supervisor,
            )
            self.assertEqual(outcome["status"], "completed")
            self.assertEqual(seen, ["manager", "producer", "manager", "verifier"])

    def test_logical_v9_rejects_proposal_that_differs_from_manager_decision(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)

            def adapter(_binding, action):
                if action["assignment_id"] == "manager":
                    return _manager_result_for_action(action)
                self.fail("worker adapter must not be called")

            with self.assertRaisesRegex(ContractError, "differs from the bounded manager decision"):
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
                readiness_recheck=readiness, supervisor=supervisor,
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
                supervisor=lambda _envelope, _task, on_action, *, manager_decision, **_kwargs:
                    on_action({"attempt_id": envelope["attempt_id"],
                               "assignment_id": manager_decision["assignment_id"],
                               "task": manager_decision["task"], "sequence": 1,
                               "manager_turn": manager_decision["manager_turn"]}),
            )
            self.assertIn(("producer", "claude"), sends)
            self.assertIn(("verifier", "codex"), sends)
            verifier_action = next(item["request"] for item in ledger.snapshot(envelope["attempt_id"])["actions"]
                                   if item["request"]["assignment_id"] == "verifier")
            self.assertEqual(verifier_action["selection_decision"]["excluded_families"], ["anthropic"])

    def test_logical_v9_hosted_uncertain_send_fails_closed_without_next_fallback(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            sends = []

            def supervisor(_envelope, task, on_action, **_kwargs):
                return on_action({"attempt_id": envelope["attempt_id"], "assignment_id": "producer",
                                  "task": task, "sequence": 1, "manager_turn": 1})

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
                                            readiness_recheck=readiness, supervisor=supervisor)
            self.assertEqual(sends, ["claude", "claude"])
            selections = ledger.snapshot(envelope["attempt_id"])["provider_selections"]
            self.assertEqual([item["state"] for item in selections],
                             ["superseded", "consumed", "superseded", "consumed"])
            self.assertEqual(ledger.snapshot(envelope["attempt_id"])["actions"][-1]["status"], "unknown")

    def test_logical_v9_route_runs_the_credentialless_maf_child(self) -> None:
        envelope = _envelope()
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / "ledger.sqlite3")
            ledger.create_attempt(envelope)
            outcome = execute_v9_logical_delivery(
                envelope, "Implement the approved change.", ledger,
                lambda binding, action: (_manager_result_for_action(action, task="Implement the approved change.")
                                         if action["assignment_id"] == "manager"
                                         else {"provider": binding["provider"], "output": "applied"}),
                readiness_recheck=lambda binding: {**binding, "state": "ready"},
                python_path=sys.executable,
            )
            self.assertEqual(outcome["attempt_id"], envelope["attempt_id"])
            self.assertEqual([item["status"] for item in ledger.snapshot(envelope["attempt_id"])["actions"]],
                             ["completed", "completed", "completed", "completed"])

    def test_logical_v9_manager_uncertain_send_stops_before_maf(self) -> None:
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
                    supervisor=lambda *_args, **_kwargs: supervisor_calls.append(True),
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
