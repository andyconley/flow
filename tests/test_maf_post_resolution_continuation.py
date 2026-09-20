"""The new continuation gate against an actual Flow-bound MAF checkpoint."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "tests"))

import execution_gateway as gateway  # noqa: E402
from execution_contracts import ContractError  # noqa: E402
from test_execution import ASSIGNMENT_ID, ExecutionFixture, WORK_ID, stub_result  # noqa: E402


def _continue_in_process(root: str, attempt_id: str, action_id: str, python_path: str, results) -> None:
    def adapter(envelope):
        path = Path(root) / ".flow" / "runs" / WORK_ID / "execution" / attempt_id / "continued-sends.txt"
        with path.open("a") as stream:
            stream.write("send\n")
        return stub_result(envelope)

    try:
        results.put(gateway.continue_resolved_local(WORK_ID, attempt_id, action_id, "race-operator",
                                                    root=Path(root), python_path=python_path, adapter=adapter))
    except Exception as exc:
        results.put({"error": type(exc).__name__})


class PostResolutionContinuationTests(ExecutionFixture):
    def _pinned_python(self) -> str:
        executable = Path("/private/tmp/flow-maf-runtime-spike-20260919/bin/python")
        if not executable.is_file():
            self.skipTest("optional pinned MAF environment is absent")
        return str(executable)

    def _make_attempt(self, disposition: str):
        executable = self._pinned_python()
        calls = []

        def adapter(envelope):
            calls.append(envelope["attempt_id"])
            return stub_result(envelope)

        if disposition == "resolved_completed":
            original_complete = gateway.ExecutionLedger.complete

            def interrupt_after_observation(ledger, action_id, result, *, generation=None):
                if len(calls) == 3:
                    raise RuntimeError("controlled crash after durable third response")
                return original_complete(ledger, action_id, result, generation=generation)

            with patch.object(gateway.ExecutionLedger, "complete", interrupt_after_observation):
                outcome = gateway.execute_multiturn_local(
                    WORK_ID, ASSIGNMENT_ID, f".flow/runs/{WORK_ID}/task.md",
                    root=self.root, adapter=adapter, python_path=executable,
                )
        else:
            original_consume = gateway.ExecutionLedger.consume_grant

            def interrupt_before_dispatch(ledger, action_id, grant_id, *, generation=None):
                if len(calls) == 2:
                    raise RuntimeError("controlled crash before third dispatch")
                return original_consume(ledger, action_id, grant_id, generation=generation)

            with patch.object(gateway.ExecutionLedger, "consume_grant", interrupt_before_dispatch):
                outcome = gateway.execute_multiturn_local(
                    WORK_ID, ASSIGNMENT_ID, f".flow/runs/{WORK_ID}/task.md",
                    root=self.root, adapter=adapter, python_path=executable,
                )
        attempt_id = outcome["attempt_id"]
        ledger = gateway.ExecutionLedger(self.run_dir / "execution" / "ledger.sqlite")
        snapshot = ledger.snapshot(attempt_id)
        action_id = snapshot["actions"][-1]["action_id"]
        generation = ledger.claim_recovery(attempt_id, "test-operator")
        proof = self.run_dir / "execution" / attempt_id / "positive-no-send.txt"
        proof.write_text("controlled boundary proof\n")
        kind = "positive_no_send" if disposition == "resolved_not_dispatched" else "flow_response_observation"
        evidence = [{"kind": kind, "path": str(proof.relative_to(self.root)),
                     "sha256": hashlib.sha256(proof.read_bytes()).hexdigest()}]
        ledger.resolve_unknown(attempt_id, action_id, "test-operator", disposition,
                               "controlled fixture", evidence, generation=generation)
        return attempt_id, action_id, calls, adapter

    def test_completed_result_replays_without_new_send(self):
        attempt_id, action_id, calls, adapter = self._make_attempt("resolved_completed")
        before = len(calls)
        original = self.run_dir / "execution" / attempt_id / "receipt.json"
        original_bytes = original.read_bytes()
        result = gateway.continue_resolved_local(
            WORK_ID, attempt_id, action_id, "test-operator", root=self.root,
            python_path=self._pinned_python(), adapter=adapter,
        )
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(calls), before)
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(json.loads(Path(result["receipt_path"]).read_text())["maf_acknowledgment"]["reason"], "action-3-complete")
        self.assertEqual(gateway.inspect_attempt(WORK_ID, attempt_id, root=self.root)["missing_evidence"], [])

    def test_no_dispatch_requires_ready_then_sends_once(self):
        attempt_id, action_id, calls, adapter = self._make_attempt("resolved_not_dispatched")
        before = len(calls)
        result = gateway.continue_resolved_local(
            WORK_ID, attempt_id, action_id, "test-operator", root=self.root,
            python_path=self._pinned_python(), adapter=adapter,
        )
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(calls), before + 1)
        self.assertEqual(gateway.inspect_attempt(WORK_ID, attempt_id, root=self.root)["missing_evidence"], [])
        with self.assertRaises(ContractError):
            gateway.continue_resolved_local(WORK_ID, attempt_id, action_id, "test-operator",
                                            root=self.root, python_path=self._pinned_python(), adapter=adapter)

    def test_readiness_failure_halts_without_regrant_or_send(self):
        attempt_id, action_id, calls, adapter = self._make_attempt("resolved_not_dispatched")
        before = len(calls)
        with patch.object(gateway, "run_maf_action3_continuation", side_effect=RuntimeError("controlled readiness failure")):
            result = gateway.continue_resolved_local(
                WORK_ID, attempt_id, action_id, "test-operator", root=self.root,
                python_path=self._pinned_python(), adapter=adapter,
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(calls), before)
        ledger = gateway.ExecutionLedger(self.run_dir / "execution" / "ledger.sqlite")
        epoch = ledger.continuation_snapshot(result["epoch_id"])
        self.assertIsNone(epoch["grant"])
        self.assertFalse(epoch["send_claimed"])

    def test_changed_checkpoint_blocks_before_epoch_or_send(self):
        attempt_id, action_id, calls, adapter = self._make_attempt("resolved_not_dispatched")
        ledger = gateway.ExecutionLedger(self.run_dir / "execution" / "ledger.sqlite")
        checkpoint = next(p for p in ledger.snapshot(attempt_id)["checkpoint_positions"]
                          if p["kind"] == "pending_delegate" and p["sequence"] == 3)
        Path(checkpoint["path"]).write_text("{}")
        before = len(calls)
        with self.assertRaisesRegex(ContractError, "evidence is missing"):
            gateway.continue_resolved_local(WORK_ID, attempt_id, action_id, "test-operator",
                                            root=self.root, python_path=self._pinned_python(), adapter=adapter)
        self.assertEqual(len(calls), before)
        self.assertEqual(ledger.snapshot(attempt_id)["continuations"], [])

    def test_checkpoint_mutation_after_first_check_blocks_send(self):
        attempt_id, action_id, calls, adapter = self._make_attempt("resolved_not_dispatched")
        ledger = gateway.ExecutionLedger(self.run_dir / "execution" / "ledger.sqlite")
        checkpoint = next(p for p in ledger.snapshot(attempt_id)["checkpoint_positions"]
                          if p["kind"] == "pending_delegate" and p["sequence"] == 3)

        def mutate_after_launch(_envelope, resume, on_ready, **_kwargs):
            Path(checkpoint["path"]).write_text("{}")
            on_ready({"request_id": resume["request_id"], "action_id": action_id,
                      "sequence": 3})

        before = len(calls)
        with patch.object(gateway, "run_maf_action3_continuation", side_effect=mutate_after_launch):
            result = gateway.continue_resolved_local(
                WORK_ID, attempt_id, action_id, "test-operator", root=self.root,
                python_path=self._pinned_python(), adapter=adapter,
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(calls), before)
        self.assertIsNone(ledger.continuation_snapshot(result["epoch_id"])["grant"])

    def test_restart_after_claim_seals_unknown_without_second_send(self):
        attempt_id, action_id, calls, adapter = self._make_attempt("resolved_not_dispatched")
        ledger = gateway.ExecutionLedger(self.run_dir / "execution" / "ledger.sqlite")
        inspected = gateway.inspect_attempt(WORK_ID, attempt_id, root=self.root)
        snapshot = inspected["snapshot"]
        receipt = self.run_dir / "execution" / attempt_id / "receipt.json"
        checkpoint = next(p for p in snapshot["checkpoint_positions"]
                          if p["kind"] == "pending_delegate" and p["sequence"] == 3)
        opened = ledger.begin_continuation(attempt_id, action_id, snapshot["resolutions"][0]["resolution_id"],
                                           hashlib.sha256(receipt.read_bytes()).hexdigest(),
                                           checkpoint["file_sha256"], actor="crashed-parent")
        generation = ledger.claim_continuation(opened["epoch_id"], actor="crashed-parent")
        with ledger.send_lock():
            decision = ledger.regrant_continuation(opened["epoch_id"], snapshot["envelope"],
                                                   snapshot["actions"][-1]["request"], generation=generation)
            self.assertTrue(ledger.claim_continuation_send(opened["epoch_id"], decision["grant_id"], generation=generation))
        before = len(calls)
        result = gateway.continue_resolved_local(WORK_ID, attempt_id, action_id, "recovery-operator",
                                                 root=self.root, python_path=self._pinned_python(), adapter=adapter)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(calls), before)
        self.assertTrue(Path(result["receipt_path"]).is_file())
        self.assertEqual(gateway.inspect_attempt(WORK_ID, attempt_id, root=self.root)["missing_evidence"], [])

    def test_lost_response_after_new_send_is_unknown_and_not_retried(self):
        attempt_id, action_id, calls, _adapter = self._make_attempt("resolved_not_dispatched")

        def lost_response(_envelope):
            calls.append("continued-send")
            raise RuntimeError("controlled lost response")

        result = gateway.continue_resolved_local(WORK_ID, attempt_id, action_id, "test-operator",
                                                 root=self.root, python_path=self._pinned_python(), adapter=lost_response)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(calls.count("continued-send"), 1)
        with self.assertRaises(ContractError):
            gateway.continue_resolved_local(WORK_ID, attempt_id, action_id, "test-operator",
                                            root=self.root, python_path=self._pinned_python(), adapter=lost_response)
        self.assertEqual(calls.count("continued-send"), 1)

    def test_lineage_cap_denies_new_grant(self):
        attempt_id, action_id, calls, adapter = self._make_attempt("resolved_not_dispatched")
        ledger = gateway.ExecutionLedger(self.run_dir / "execution" / "ledger.sqlite")
        with ledger._db() as db:
            for _ in range(3):
                ledger._event(db, attempt_id, action_id, "policy_allowed", "controlled_prior_grant")
        before = len(calls)
        result = gateway.continue_resolved_local(WORK_ID, attempt_id, action_id, "test-operator",
                                                 root=self.root, python_path=self._pinned_python(), adapter=adapter)
        self.assertEqual(result["status"], "failed")
        self.assertIn("delegation_cap", result["reason"])
        self.assertEqual(len(calls), before)
        self.assertIsNone(ledger.continuation_snapshot(result["epoch_id"])["grant"])

    def test_two_racing_continuations_fence_stale_owner_before_send(self):
        attempt_id, action_id, calls, adapter = self._make_attempt("resolved_not_dispatched")
        barrier = threading.Barrier(2)

        def ready(envelope, resume, on_ready, **_kwargs):
            proposal = gateway.ExecutionLedger(self.run_dir / "execution" / "ledger.sqlite").snapshot(attempt_id)["actions"][-1]["request"]
            barrier.wait(timeout=5)
            on_ready({**proposal, "request_id": resume["request_id"],
                      "checkpoint_id": resume["checkpoint_id"],
                      "runtime_version": gateway.PINNED_MAF_CORE_VERSION})
            return {"reason": "action-3-complete"}

        def run():
            try:
                return gateway.continue_resolved_local(
                    WORK_ID, attempt_id, action_id, "test-operator", root=self.root,
                    python_path=self._pinned_python(), adapter=adapter,
                )
            except Exception as exc:
                return {"error": type(exc).__name__}

        before = len(calls)
        with patch.object(gateway, "run_maf_action3_continuation", side_effect=ready), ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _i: run(), range(2)))
        self.assertEqual(sum(item.get("status") == "completed" for item in outcomes), 1, outcomes)
        self.assertEqual(len(calls), before + 1)

    def test_two_processes_cannot_send_continued_action_twice(self):
        attempt_id, action_id, _calls, _adapter = self._make_attempt("resolved_not_dispatched")
        context = multiprocessing.get_context("spawn")
        results = context.Queue()
        processes = [context.Process(target=_continue_in_process,
                                     args=(str(self.root), attempt_id, action_id, self._pinned_python(), results))
                     for _ in range(2)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(15)
            self.assertEqual(process.exitcode, 0)
        outcomes = [results.get(timeout=2) for _ in processes]
        self.assertLessEqual(sum(item.get("status") == "completed" for item in outcomes), 1, outcomes)
        sends = self.run_dir / "execution" / attempt_id / "continued-sends.txt"
        self.assertEqual(sends.read_text().count("send\n") if sends.exists() else 0, 1, outcomes)
