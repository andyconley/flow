"""Flow keeps stock Magentic's choices inside a durable v5 policy boundary."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from execution_contracts import (ContractError, digest, envelope_digest,
                                 expected_magentic_action_id, expected_manager_call_id,
                                 expected_replan_id, validate_action, validate_envelope,
                                 validate_manager_call, validate_receipt, validate_result)
from claude_edit_worker import _result as claude_edit_result
from execution_ledger import ExecutionLedger
from delivery_gateway import _normalized_manager_request


def envelope() -> dict:
    sources = {key: {"path": f".flow/runs/delivery/{key}.md", "sha256": char * 64}
               for key, char in (("requirements", "a"), ("acceptance", "b"))}
    def role(name: str, provider: str, model: str) -> dict:
        instructions = f"Do {name} work."
        return {"assignment_id": name, "definition_digest": digest({"role": name, "instructions": instructions}),
                "instance_id": f"{name}-1", "role": name, "provider": provider, "model": model,
                "instructions": instructions}
    return {"schema_version": 1, "execution_protocol_version": 5, "work_id": "delivery-work", "attempt_id": "delivery-attempt",
            "charter_sources": sources, "charter_digest": digest({key: value["sha256"] for key, value in sources.items()}),
            "run_protocol_revision": 2, "manifest_digest": "c" * 64, "checkpoint_dir": "/tmp/delivery-checkpoints",
            "source_commit": "d" * 40, "worktree": "/tmp/delivery-worktree",
            "allowed_paths": ["cli/codex_worker.py", "tests/test_codex_worker.py"],
            "manager": {"provider": "ollama", "model": "local-model"},
            "roster": [role("test-engineer", "ollama", "local-model"), role("lead-developer", "claude", "sonnet")],
            "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2,
                       "max_manager_calls": 12, "max_manager_rounds": 6, "max_paid_worker_calls": 1}}


def action(env: dict, sequence: int, assignment: dict, *, task: str = "Inspect the scoped change.") -> dict:
    value = {"schema_version": 1, "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
             "sequence": sequence, "kind": "delegate", "manager_turn": min(sequence, 6),
             "task": task, "task_digest": hashlib.sha256(task.encode()).hexdigest(),
             "rationale": "Manager selected this specialist.", "checkpoint_id": f"pending-{sequence}",
             "parent_action_id": None,
             **{key: assignment[key] for key in ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model")}}
    value["action_id"] = expected_magentic_action_id(value)
    return value


def manager_call(env: dict, sequence: int, phase: str = "facts", replan_sequence: int | None = None) -> dict:
    request = {"schema_version": 1, "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
               "sequence": sequence, "phase": phase, "manager_round": 1,
               "prompt_digest": digest({"messages": [f"prompt {sequence}"]})}
    if replan_sequence is not None:
        request["replan_sequence"] = replan_sequence
        request["replan_id"] = expected_replan_id(env, replan_sequence)
    request["call_id"] = expected_manager_call_id(request)
    return request


class MagenticContractTests(unittest.TestCase):
    def test_manager_accepts_verified_progress_prompt_within_claude_limit(self) -> None:
        env = envelope()
        messages = [{"role": "user", "contents": [{"type": "text", "text": "x" * 24000}]}]
        request = manager_call(env, 1, "progress")
        request["prompt_digest"] = digest(messages)
        request["call_id"] = expected_manager_call_id(request)
        self.assertEqual(_normalized_manager_request(env, {**request, "messages": messages}), request)

    def test_claude_edit_result_matches_v5_worker_contract(self) -> None:
        env = envelope()
        selected = env["roster"][1]
        delegated = action(env, 1, selected)
        raw = {"type": "result", "subtype": "success", "is_error": False,
               "result": "Edited the scoped file.", "session_id": "session-1",
               "num_turns": 9, "usage": {"input_tokens": 5}}
        validate_result(env, claude_edit_result(json.dumps(raw).encode(), selected["model"]),
                        action=delegated)

    def test_paid_manager_call_budget_is_per_attempt(self) -> None:
        first = {**envelope(), "manager": {"provider": "claude", "model": "sonnet"}}
        second = {**first, "attempt_id": "delivery-attempt-2"}
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(first)
            for sequence in range(1, 13):
                phase = "facts" if sequence == 1 else "plan" if sequence == 2 else "progress"
                self.assertTrue(ledger.decide_manager_call(first, manager_call(first, sequence, phase), generation=1)["allowed"])
            self.assertEqual(ledger.decide_manager_call(first, manager_call(first, 13, "progress"), generation=1)["reason"],
                             "manager_call_cap")
            ledger.create_attempt(second)
            self.assertTrue(ledger.decide_manager_call(second, manager_call(second, 1), generation=1)["allowed"])

    def test_local_calls_have_no_delegation_cap_but_keep_concurrency_limit(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            local = env["roster"][0]
            for sequence in range(1, 8):
                proposal = action(env, sequence, local, task=f"Analyze bounded fact {sequence}.")
                decision = ledger.decide(env, proposal, generation=1)
                self.assertTrue(decision["allowed"], decision)
                ledger.close_pre_send_failure(proposal["action_id"], decision["grant_id"], generation=1)
            for sequence in range(8, 11):
                proposal = action(env, sequence, local, task=f"Analyze bounded fact {sequence}.")
                self.assertTrue(ledger.decide(env, proposal, generation=1)["allowed"])
            denied = action(env, 11, local, task="One more concurrent local call.")
            self.assertEqual(ledger.decide(env, denied, generation=1)["reason"], "concurrency_cap")

    def test_local_manager_has_no_paid_call_cap(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            for sequence in range(1, 15):
                phase = "facts" if sequence == 1 else "plan" if sequence == 2 else "progress"
                self.assertTrue(ledger.decide_manager_call(env, manager_call(env, sequence, phase), generation=1)["allowed"])

    def test_paid_worker_call_allowance_is_charter_configurable(self) -> None:
        env = envelope()
        env = {**env, "limits": {**env["limits"], "max_paid_worker_calls": 3}}
        validate_envelope(env)
        with self.assertRaises(ContractError):
            validate_envelope({**env, "limits": {**env["limits"], "max_paid_worker_calls": 7}})
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            for sequence in (1, 2, 3):
                proposal = action(env, sequence, env["roster"][1], task=f"Authorized paid task {sequence}.")
                self.assertTrue(ledger.decide(env, proposal, generation=1)["allowed"])
            fourth = action(env, 4, env["roster"][1], task="Unapproved fourth paid task.")
            self.assertEqual(ledger.decide(env, fourth, generation=1)["reason"], "paid_call_cap")

    def test_paid_worker_and_replan_allowances_reset_for_new_attempt(self) -> None:
        first = envelope()
        second = {**first, "attempt_id": "delivery-attempt-2"}
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(first)
            self.assertTrue(ledger.decide(first, action(first, 1, first["roster"][1]), generation=1)["allowed"])
            for sequence in (1, 2):
                replan = {"schema_version": 1, "replan_id": expected_replan_id(first, sequence),
                          "attempt_id": first["attempt_id"], "envelope_digest": envelope_digest(first),
                          "sequence": sequence, "kind": "replan", "proposal": {"reason": "new evidence"}}
                self.assertTrue(ledger.decide_replan(first, replan, generation=1)["allowed"])
            ledger.create_attempt(second)
            self.assertTrue(ledger.decide(second, action(second, 1, second["roster"][1]), generation=1)["allowed"])
            replan = {"schema_version": 1, "replan_id": expected_replan_id(second, 1),
                      "attempt_id": second["attempt_id"], "envelope_digest": envelope_digest(second),
                      "sequence": 1, "kind": "replan", "proposal": {"reason": "new evidence"}}
            self.assertTrue(ledger.decide_replan(second, replan, generation=1)["allowed"])

    def test_dynamic_choice_is_bound_to_roster_scope_and_task(self) -> None:
        env = envelope()
        validate_envelope(env)
        chosen = action(env, 1, env["roster"][1], task="Repair the scoped worker.")
        validate_action(env, chosen)
        with self.assertRaises(ContractError):
            validate_action(env, {**chosen, "provider": "codex"})
        with self.assertRaises(ContractError):
            validate_action(env, {**chosen, "task": "Change another file."})
        with self.assertRaises(ContractError):
            validate_envelope({**env, "allowed_paths": ["../other"]})

    def test_manager_grant_is_one_use_and_unknown_blocks_workers(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            request = manager_call(env, 1)
            validate_manager_call(env, request)
            grant = ledger.decide_manager_call(env, request, generation=1)
            self.assertTrue(grant["allowed"])
            self.assertEqual(ledger.decide_manager_call(env, request, generation=1)["grant_id"], grant["grant_id"])
            self.assertTrue(ledger.consume_manager_grant(request["call_id"], grant["grant_id"], generation=1))
            self.assertFalse(ledger.consume_manager_grant(request["call_id"], grant["grant_id"], generation=1))
            ledger.mark_manager_unknown(request["call_id"], "lost_response", generation=1)
            worker = action(env, 1, env["roster"][0])
            self.assertEqual(ledger.decide(env, worker, generation=1)["reason"], "reconciliation_required")
            self.assertEqual(len(ledger.snapshot(env["attempt_id"])["actions"]), 0)

    def test_paid_worker_and_third_replan_are_denied_before_send(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            paid = action(env, 1, env["roster"][1])
            self.assertTrue(ledger.decide(env, paid, generation=1)["allowed"])
            second = action(env, 2, env["roster"][1], task="Try the paid worker again.")
            self.assertEqual(ledger.decide(env, second, generation=1)["reason"], "paid_call_cap")
            for sequence in (1, 2, 3):
                replan = {"schema_version": 1, "replan_id": expected_replan_id(env, sequence),
                          "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
                          "sequence": sequence, "kind": "replan", "proposal": {"reason": "new evidence"}}
                decision = ledger.decide_replan(env, replan, generation=1)
                self.assertEqual(decision["allowed"], sequence < 3)
            self.assertEqual(ledger.snapshot(env["attempt_id"])["replans"][-1]["reason"], "replan_cap")

    def test_completed_manager_response_is_durable_and_bound_to_output(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            request = manager_call(env, 1)
            grant = ledger.decide_manager_call(env, request, generation=1)
            self.assertTrue(ledger.consume_manager_grant(request["call_id"], grant["grant_id"], generation=1))
            output = {"next_speaker": "lead-developer"}
            response = {"status": "completed", "output": output, "output_sha256": digest(output), "usage": {"input_tokens": 8}}
            with self.assertRaisesRegex(ContractError, "response is invalid"):
                ledger.observe_manager_response(request["call_id"], {**response, "output_sha256": "0" * 64}, generation=1)
            ledger.observe_manager_response(request["call_id"], response, generation=1)
            ledger.observe_manager_response(request["call_id"], response, generation=1)
            with self.assertRaisesRegex(ContractError, "conflicts"):
                other = {"another": "choice"}
                ledger.observe_manager_response(request["call_id"], {**response, "output": other, "output_sha256": digest(other)}, generation=1)
            self.assertEqual(ledger.snapshot(env["attempt_id"])["manager_calls"][0]["result"], response)

    def test_worker_checkpoint_binds_pending_maf_request_and_file_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = {**envelope(), "checkpoint_dir": str(root)}
            ledger = ExecutionLedger(root / "ledger.sqlite")
            ledger.create_attempt(env)
            worker = action(env, 1, env["roster"][0])
            self.assertTrue(ledger.decide(env, worker, generation=1)["allowed"])
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": "cp-1", "workflow_name": "flow-magentic-delivery-v5",
                                              "pending_request_info_events": {"flow-magentic-action-1": {"request": "opaque"}}}))
            high_water = ledger.snapshot(env["attempt_id"])["events"][-1]["seq"]
            bound = ledger.bind_magentic_checkpoint(env["attempt_id"], "cp-1", "worker", worker["action_id"],
                                                      high_water, str(checkpoint), generation=1)
            self.assertEqual(ledger.read_magentic_checkpoint(env["attempt_id"], "worker", worker["action_id"])["bytes"], checkpoint.read_bytes())
            self.assertEqual(bound["pending_id"], worker["action_id"])
            checkpoint.write_text(checkpoint.read_text().replace("flow-magentic-action-1", "flow-magentic-action-2"))
            with self.assertRaisesRegex(ContractError, "changed"):
                ledger.read_magentic_checkpoint(env["attempt_id"], "worker", worker["action_id"])

    def test_terminal_v5_attempt_continues_only_after_observed_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = {**envelope(), "checkpoint_dir": str(root)}
            ledger = ExecutionLedger(root / "ledger.sqlite")
            ledger.create_attempt(env)
            worker = action(env, 1, env["roster"][1])
            grant = ledger.decide(env, worker, generation=1)
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(json.dumps({"checkpoint_id": "cp-1", "workflow_name": "flow-magentic-delivery-v5",
                                              "pending_request_info_events": {"flow-magentic-action-1": {"request": "opaque"}}}))
            high_water = ledger.snapshot(env["attempt_id"])["events"][-1]["seq"]
            bound = ledger.bind_magentic_checkpoint(env["attempt_id"], "cp-1", "worker", worker["action_id"],
                                                      high_water, str(checkpoint), generation=1)
            self.assertTrue(ledger.consume_grant(worker["action_id"], grant["grant_id"], generation=1))
            ledger.observe_send(worker["action_id"], 1)
            ledger.mark_unknown(worker["action_id"], "adapter_result_invalid", generation=1)
            original = root / "receipt.json"
            original.write_text("original unknown receipt\n")
            ledger.finish_attempt(env["attempt_id"], "unknown", "reconciliation_required", str(original), generation=1)
            manager = manager_call(env, 1)
            with self.assertRaisesRegex(ContractError, "closed"):
                ledger.decide_manager_call(env, manager, generation=1)
            raw = {"type": "result", "subtype": "success", "is_error": False, "result": "Edited.",
                   "session_id": "session-1", "num_turns": 9, "usage": {"input_tokens": 5}}
            result = claude_edit_result(json.dumps(raw).encode(), worker["model"])
            generation = ledger.claim_recovery(env["attempt_id"], actor="operator")
            ledger.observe_response(worker["action_id"], result, generation)
            proof = [{"kind": "provider_result", "path": "receipt.json",
                      "sha256": hashlib.sha256(original.read_bytes()).hexdigest()}]
            resolution = ledger.resolve_unknown(env["attempt_id"], worker["action_id"], "operator",
                                                "resolved_completed", "Provider result verified", proof,
                                                generation=generation)
            epoch = ledger.begin_continuation(env["attempt_id"], worker["action_id"], resolution["resolution_id"],
                                              proof[0]["sha256"], bound["file_sha256"], actor="operator")
            epoch_generation = ledger.claim_continuation(epoch["epoch_id"], actor="operator")
            ledger.start_magentic_continuation(epoch["epoch_id"], generation=epoch_generation)
            generation = ledger.claim_recovery(env["attempt_id"], actor="operator")
            self.assertTrue(ledger.decide_manager_call(env, manager, generation=generation)["allowed"])
            verifier = action(env, 2, env["roster"][0])
            verifier_grant = ledger.decide(env, verifier, generation=generation)
            verifier_checkpoint = root / "verifier-checkpoint.json"
            verifier_checkpoint.write_text(json.dumps({"checkpoint_id": "pending-2", "workflow_name": "flow-magentic-delivery-v5",
                                                       "pending_request_info_events": {"flow-magentic-action-2": {"request": "opaque"}}}))
            high_water = ledger.snapshot(env["attempt_id"])["events"][-1]["seq"]
            verifier_bound = ledger.bind_magentic_checkpoint(env["attempt_id"], "pending-2", "worker",
                                                               verifier["action_id"], high_water,
                                                               str(verifier_checkpoint), generation=generation)
            self.assertTrue(ledger.consume_grant(verifier["action_id"], verifier_grant["grant_id"], generation=generation))
            ledger.observe_send(verifier["action_id"], generation)
            verdict = {"schema_version": 1, "status": "completed", "provider": "ollama", "model": "local-model", "physical_call": True,
                       "evidence_level": "flow_observed_local_http_response", "output": "Verified.",
                       "output_sha256": hashlib.sha256(b"Verified.").hexdigest()}
            ledger.observe_response(verifier["action_id"], verdict, generation)
            ledger.complete(verifier["action_id"], verdict, generation=generation)
            linked = root / "linked-receipt.json"
            linked.write_text("linked continuation receipt\n")
            ledger.finish_magentic_continuation(epoch["epoch_id"], "failed", "probe complete", str(linked),
                                                generation=generation)
            self.assertEqual(original.read_text(), "original unknown receipt\n")
            self.assertEqual(ledger.snapshot(env["attempt_id"])["status"], "unknown")
            self.assertEqual(ledger.continuation_snapshot(epoch["epoch_id"])["status"], "failed")
            retry = ledger.retry_failed_magentic_continuation(epoch["epoch_id"], verifier["action_id"],
                                                               verifier_bound["file_sha256"], actor="operator")
            self.assertEqual(retry["status"], "pending")
            self.assertEqual(ledger.retry_failed_magentic_continuation(epoch["epoch_id"], verifier["action_id"],
                                                                        verifier_bound["file_sha256"], actor="operator")["epoch_id"],
                             retry["epoch_id"])
            retry_generation = ledger.claim_continuation(retry["epoch_id"], actor="operator")
            ledger.start_magentic_continuation(retry["epoch_id"], generation=retry_generation)

    def test_replan_model_calls_need_matching_approval_and_ordered_pair(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            def approve(n: int) -> bool:
                request = {"schema_version": 1, "replan_id": expected_replan_id(env, n),
                           "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
                           "sequence": n, "kind": "replan", "proposal": {"reason": f"replan {n}"}}
                return ledger.decide_replan(env, request, generation=1)["allowed"]
            def observed(request: dict) -> None:
                grant = ledger.decide_manager_call(env, request, generation=1)
                self.assertTrue(grant["allowed"])
                self.assertTrue(ledger.consume_manager_grant(request["call_id"], grant["grant_id"], generation=1))
                output = "manager response"
                ledger.observe_manager_response(request["call_id"], {"status": "completed", "output": output,
                                                           "output_sha256": digest(output)}, generation=1)
            self.assertTrue(approve(1))
            observed(manager_call(env, 1, "replan_facts", 1))
            observed(manager_call(env, 2, "replan_plan", 1))
            self.assertTrue(approve(2))
            observed(manager_call(env, 3, "replan_facts", 2))
            observed(manager_call(env, 4, "replan_plan", 2))
            self.assertFalse(approve(3))
            third = ledger.decide_manager_call(env, manager_call(env, 5, "replan_facts", 3), generation=1)
            self.assertFalse(third["allowed"])
            self.assertEqual(third["reason"], "replan_not_authorized")
            self.assertFalse(ledger.consume_manager_grant(third["call_id"], "invalid", generation=1))
            snapshot = ledger.snapshot(env["attempt_id"])
            self.assertEqual(sum(item["status"] == "completed" for item in snapshot["manager_calls"]), 4)
            self.assertFalse(any(item["status"] == "started" for item in snapshot["manager_calls"]))

    def test_replan_plan_before_facts_denied_without_send(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            replan = {"schema_version": 1, "replan_id": expected_replan_id(env, 1),
                      "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
                      "sequence": 1, "kind": "replan", "proposal": {"reason": "new evidence"}}
            self.assertTrue(ledger.decide_replan(env, replan, generation=1)["allowed"])
            premature = manager_call(env, 1, "replan_plan", 1)
            denied = ledger.decide_manager_call(env, premature, generation=1)
            self.assertEqual(denied["reason"], "replan_out_of_order")
            self.assertFalse(ledger.consume_manager_grant(denied["call_id"], "invalid", generation=1))
            self.assertEqual(ledger.snapshot(env["attempt_id"])["manager_calls"][0]["status"], "denied")

    def test_one_approval_cannot_grant_two_facts_calls(self) -> None:
        env = envelope()
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            ledger.create_attempt(env)
            replan = {"schema_version": 1, "replan_id": expected_replan_id(env, 1),
                      "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
                      "sequence": 1, "kind": "replan", "proposal": {"reason": "new evidence"}}
            self.assertTrue(ledger.decide_replan(env, replan, generation=1)["allowed"])
            first = manager_call(env, 1, "replan_facts", 1)
            grant = ledger.decide_manager_call(env, first, generation=1)
            self.assertTrue(grant["allowed"])
            self.assertTrue(ledger.consume_manager_grant(first["call_id"], grant["grant_id"], generation=1))
            output = "facts"
            ledger.observe_manager_response(first["call_id"], {"status": "completed", "output": output,
                                                              "output_sha256": digest(output)}, generation=1)
            duplicate = ledger.decide_manager_call(env, manager_call(env, 2, "replan_facts", 1), generation=1)
            self.assertEqual(duplicate["reason"], "replan_out_of_order")
            self.assertFalse(ledger.consume_manager_grant(duplicate["call_id"], "invalid", generation=1))


if __name__ == "__main__":
    unittest.main()
