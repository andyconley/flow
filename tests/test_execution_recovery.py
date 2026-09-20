"""Recovery-boundary tests for Flow's durable execution ledger.

These tests use the existing disposable execution fixture and never import MAF
or contact a model.  Their oracle is the persisted ledger state after a fresh
``ExecutionLedger`` instance reopens the SQLite file.
"""

from __future__ import annotations

import sqlite3
import multiprocessing
import os
import json
import sys
import unittest
import hashlib
import tempfile
import uuid
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "tests"))

from execution_contracts import ContractError, digest, envelope_digest, expected_action_id  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402


EVIDENCE_DIGEST = "a" * 64


def evidence(kind: str = "positive_no_send") -> list[dict[str, str]]:
    return [{"kind": kind, "path": ".flow/runs/proof.json", "sha256": EVIDENCE_DIGEST}]


def _claim_in_process(path: str, attempt_id: str, started, finished, generations=None) -> None:
    ledger = ExecutionLedger(Path(path))
    started.set()
    generation = ledger.claim_recovery(attempt_id)
    if generations is not None:
        generations.put(generation)
    finished.set()


def _abrupt_boundary(path: str, envelope: dict, action: dict, result: dict, stage: str, calls_file: str) -> None:
    """Exit without Python cleanup at a durable barrier, like a killed parent."""
    ledger = ExecutionLedger(Path(path))
    ledger.create_attempt(envelope)
    if stage == "intent":
        os._exit(77)
    grant = ledger.decide(envelope, action)
    if stage == "grant":
        os._exit(77)
    ledger.consume_grant(action["action_id"], grant["grant_id"], generation=1)
    if stage == "dispatch":
        os._exit(77)
    ledger.observe_send(action["action_id"], 1)
    with open(calls_file, "a", encoding="utf-8") as stream:
        stream.write("send\n")
        stream.flush()
        os.fsync(stream.fileno())
    if stage == "send":
        os._exit(77)
    ledger.observe_response(action["action_id"], result, 1)
    if stage == "response_observation":
        os._exit(77)
    ledger.complete(action["action_id"], result, generation=1)
    if stage == "result_commit":
        os._exit(77)
    checkpoint = Path(path).parent / "checkpoints" / f"{uuid.uuid4()}.json"
    checkpoint.parent.mkdir(exist_ok=True)
    checkpoint.write_text("{}")
    high_water = ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"]
    ledger.bind_checkpoint(envelope["attempt_id"], checkpoint.stem, envelope_digest(envelope), high_water, 1, "maf-test", str(checkpoint), generation=1)
    if stage == "checkpoint":
        os._exit(77)
    (Path(path).parent / "receipt.json").write_text(json.dumps({"attempt_id": envelope["attempt_id"], "status": "completed"}))
    os._exit(77)


class LedgerRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def _envelope(self) -> dict:
        sources = {
            "requirements": {"path": ".flow/runs/recovery/requirements.md", "sha256": "a" * 64},
            "acceptance": {"path": ".flow/runs/recovery/acceptance.md", "sha256": "b" * 64},
        }
        task = "Return a deterministic recovery test result."
        return {
            "schema_version": 1, "work_id": "recovery", "attempt_id": uuid.uuid4().hex,
            "charter_digest": digest({"requirements": sources["requirements"]["sha256"], "acceptance": sources["acceptance"]["sha256"]}),
            "charter_sources": sources, "run_protocol_revision": 2, "manifest_digest": "c" * 64,
            "assignment_id": "test-engineer", "definition_digest": "d" * 64,
            "instance_id": "test-engineer-1", "role": "test-engineer", "provider": "local-stub",
            "model": "deterministic-stub", "task_digest": hashlib.sha256(task.encode()).hexdigest(),
            "task": task, "instructions": "test", "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "paid_budget_usd": 0},
            "checkpoint_dir": str(self.root / "checkpoints"),
        }

    @staticmethod
    def _action(envelope: dict) -> dict:
        return {"schema_version": 1, "action_id": expected_action_id(envelope, 1), "attempt_id": envelope["attempt_id"],
                "envelope_digest": envelope_digest(envelope), "role": envelope["role"], "instance_id": envelope["instance_id"],
                "provider": envelope["provider"], "model": envelope["model"], "task_digest": envelope["task_digest"],
                "sequence": 1, "kind": "delegate"}

    @staticmethod
    def _result(envelope: dict, output: str = "durable response") -> dict:
        return {"schema_version": 1, "status": "completed", "provider": envelope["provider"], "model": envelope["model"],
                "physical_call": False, "evidence_level": "local_stub", "output": output,
                "output_sha256": hashlib.sha256(output.encode()).hexdigest(), "usage": None}

    def _started_action(self):
        envelope = self._envelope()
        ledger = ExecutionLedger(self.root / "ledger.sqlite")
        ledger.create_attempt(envelope)
        action = self._action(envelope)
        decision = ledger.decide(envelope, action)
        self.assertTrue(ledger.consume_grant(action["action_id"], decision["grant_id"]))
        return envelope, ledger, action

    def test_recovery_claim_waits_for_process_shared_send_boundary(self) -> None:
        envelope = self._envelope()
        ledger = ExecutionLedger(self.root / "ledger.sqlite")
        ledger.create_attempt(envelope)
        ctx = multiprocessing.get_context("spawn")
        started, finished = ctx.Event(), ctx.Event()
        contender = ctx.Process(target=_claim_in_process, args=(str(ledger.path), envelope["attempt_id"], started, finished))
        with ledger.send_lock():
            contender.start()
            self.assertTrue(started.wait(5))
            self.assertFalse(finished.wait(0.2))
            self.assertEqual(ledger.snapshot(envelope["attempt_id"])["owner_generation"], 1)
        self.assertTrue(finished.wait(5))
        contender.join(5)
        self.assertEqual(contender.exitcode, 0)
        self.assertEqual(ledger.snapshot(envelope["attempt_id"])["owner_generation"], 2)

    def test_two_racing_recovery_claims_leave_only_latest_owner_authorized(self) -> None:
        envelope, ledger, action = self._started_action()
        ctx = multiprocessing.get_context("spawn")
        started_a, started_b = ctx.Event(), ctx.Event()
        finished_a, finished_b = ctx.Event(), ctx.Event()
        generations = ctx.Queue()
        first = ctx.Process(target=_claim_in_process, args=(str(ledger.path), envelope["attempt_id"], started_a, finished_a, generations))
        second = ctx.Process(target=_claim_in_process, args=(str(ledger.path), envelope["attempt_id"], started_b, finished_b, generations))
        first.start()
        second.start()
        self.assertTrue(finished_a.wait(5))
        self.assertTrue(finished_b.wait(5))
        first.join(5)
        second.join(5)
        self.assertEqual({generations.get(timeout=2), generations.get(timeout=2)}, {2, 3})
        current = ledger.snapshot(envelope["attempt_id"])["owner_generation"]
        self.assertEqual(current, 3)
        with self.assertRaisesRegex(ContractError, "ownership is stale"):
            ledger.assert_owner(envelope["attempt_id"], 2)
        self.assertEqual(ledger.snapshot(envelope["attempt_id"])["actions"][0]["status"], "unknown")

    def test_each_durable_crash_barrier_reopens_with_exact_safe_state(self) -> None:
        """A fresh ledger sees the state produced at every crash barrier.

        The oracle is intentionally Flow-side: a restart can replay a committed
        result, while every boundary after dispatch remains unknown and has no
        second send observation.
        """
        expected = {
            "intent": (None, 0, 0, False),
            "grant": ("allowed", 0, 0, False),
            "dispatch": ("unknown", 0, 0, False),
            "response_observation": ("unknown", 1, 0, False),
            "result_commit": ("completed", 1, 1, False),
            "checkpoint": ("completed", 1, 1, True),
            "receipt": ("completed", 1, 1, False),
        }
        for barrier, (status, responses, completions, has_checkpoint) in expected.items():
            with self.subTest(barrier=barrier):
                barrier_root = self.root / barrier
                barrier_root.mkdir()
                original_root = self.root
                self.root = barrier_root
                try:
                    envelope = self._envelope()
                    ledger = ExecutionLedger(self.root / "ledger.sqlite")
                    ledger.create_attempt(envelope)
                    action = self._action(envelope)
                    if barrier != "intent":
                        decision = ledger.decide(envelope, action)
                    if barrier not in {"intent", "grant"}:
                        self.assertTrue(ledger.consume_grant(action["action_id"], decision["grant_id"]))
                    result = self._result(envelope, barrier)
                    if barrier in {"response_observation", "result_commit", "checkpoint", "receipt"}:
                        ledger.observe_send(action["action_id"], 1)
                        ledger.observe_response(action["action_id"], result, 1)
                    if barrier in {"result_commit", "checkpoint", "receipt"}:
                        ledger.complete(action["action_id"], result, generation=1)
                    if barrier == "checkpoint":
                        checkpoint = self.root / "checkpoints" / "checkpoint.json"
                        checkpoint.parent.mkdir()
                        checkpoint.write_text("{}")
                        high_water = ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"]
                        ledger.bind_checkpoint(envelope["attempt_id"], "checkpoint", envelope_digest(envelope), high_water, 1, "maf-test", str(checkpoint), generation=1)
                    if barrier == "receipt":
                        ledger.finish_attempt(envelope["attempt_id"], "completed", "", str(self.root / "receipt.json"), generation=1)
                    if barrier != "receipt":
                        ledger.claim_recovery(envelope["attempt_id"], f"restart-{barrier}")
                    reopened = ExecutionLedger(ledger.path).snapshot(envelope["attempt_id"])
                    action_state = reopened["actions"][0]["status"] if reopened["actions"] else None
                    self.assertEqual(action_state, status)
                    self.assertEqual(len(reopened["response_observations"]), responses)
                    self.assertEqual(sum(event["event"] == "worker_completed" for event in reopened["events"]), completions)
                    self.assertEqual(reopened["checkpoint"] is not None, has_checkpoint)
                    self.assertEqual(sum(event["event"] == "adapter_send_started" for event in reopened["events"]), 1 if barrier in {"response_observation", "result_commit", "checkpoint", "receipt"} else 0)
                finally:
                    self.root = original_root

    def test_abrupt_process_exit_at_each_boundary_preserves_send_count(self) -> None:
        ctx = multiprocessing.get_context("spawn")
        expected = {
            "intent": (None, 0), "grant": ("allowed", 0),
            "dispatch": ("unknown", 0), "send": ("unknown", 1),
            "response_observation": ("unknown", 1),
            "result_commit": ("completed", 1),
            "checkpoint": ("completed", 1), "receipt": ("completed", 1),
        }
        for stage, (status, calls) in expected.items():
            with self.subTest(stage=stage):
                stage_root = self.root / stage
                stage_root.mkdir()
                old_root = self.root
                self.root = stage_root
                try:
                    envelope = self._envelope()
                    action = self._action(envelope)
                    result = self._result(envelope)
                    path = stage_root / "ledger.sqlite"
                    calls_file = stage_root / "calls.txt"
                    child = ctx.Process(target=_abrupt_boundary, args=(str(path), envelope, action, result, stage, str(calls_file)))
                    child.start()
                    child.join(10)
                    self.assertEqual(child.exitcode, 77)
                    reopened = ExecutionLedger(path)
                    reopened.claim_recovery(envelope["attempt_id"])
                    snapshot = reopened.snapshot(envelope["attempt_id"])
                    actual = snapshot["actions"][0]["status"] if snapshot["actions"] else None
                    self.assertEqual(actual, status)
                    self.assertEqual(calls_file.read_text().count("send\n") if calls_file.exists() else 0, calls)
                    self.assertEqual(sum(e["event"] == "adapter_send_started" for e in snapshot["events"]), calls)
                finally:
                    self.root = old_root

    def test_recovery_fences_a_started_action_and_preserves_blocked_unknown(self) -> None:
        envelope, ledger, action = self._started_action()
        first_owner = ledger.claim_recovery(envelope["attempt_id"], "replacement-parent")
        reopened = ExecutionLedger(ledger.path).snapshot(envelope["attempt_id"])

        self.assertEqual(first_owner, 2)
        self.assertEqual(reopened["actions"][0]["status"], "unknown")
        self.assertEqual([event["event"] for event in reopened["events"]][-2:], ["worker_unknown", "recovery_claimed"])
        duplicate = ExecutionLedger(ledger.path).decide(envelope, action, generation=first_owner)
        self.assertEqual(duplicate["reason"], "duplicate_request")
        self.assertFalse(duplicate["allowed"])

    def test_new_owner_rejects_stale_parent_at_send_boundary(self) -> None:
        envelope, ledger, action = self._started_action()
        old_owner = ledger.claim_recovery(envelope["attempt_id"], "first-replacement")
        new_owner = ledger.claim_recovery(envelope["attempt_id"], "second-replacement")

        self.assertGreater(new_owner, old_owner)
        with self.assertRaisesRegex(ContractError, "ownership is stale"):
            ledger.observe_send(action["action_id"], old_owner)
        with self.assertRaisesRegex(ContractError, "not ready for send"):
            ledger.observe_send(action["action_id"], new_owner)

    def test_observed_response_reopens_and_replays_exact_result_without_new_send(self) -> None:
        envelope, ledger, action = self._started_action()
        result = self._result(envelope, "durable response")

        observed = ledger.observe_response(action["action_id"], result, 1)
        ledger.complete(action["action_id"], result, generation=1)
        generation = ledger.claim_recovery(envelope["attempt_id"])
        replayed = ExecutionLedger(ledger.path).observe_response(action["action_id"], result, generation)
        snapshot = ExecutionLedger(ledger.path).snapshot(envelope["attempt_id"])

        self.assertEqual(observed, result)
        self.assertEqual(replayed, result)
        self.assertEqual(snapshot["actions"][0]["result"], result)
        self.assertEqual(snapshot["actions"][0]["status"], "completed")
        self.assertEqual(sum(event["event"] == "adapter_send_started" for event in snapshot["events"]), 0)
        self.assertEqual(snapshot["response_observations"][0]["result"], result)
        self.assertEqual(sum(event["event"] == "response_observed" for event in snapshot["events"]), 1)

    def test_tampered_action_and_response_are_rejected_before_recovery_replay(self) -> None:
        envelope, ledger, action = self._started_action()
        altered_action = dict(action)
        altered_action["model"] = "changed-model"
        with self.assertRaisesRegex(ContractError, "model differs"):
            ledger.decide(envelope, altered_action, generation=1)

        good = self._result(envelope, "good response")
        ledger.observe_response(action["action_id"], good, 1)
        altered = self._result(envelope, "changed response")
        with self.assertRaisesRegex(ContractError, "conflicts with durable response"):
            ledger.observe_response(action["action_id"], altered, 1)
        self.assertEqual(ledger.snapshot(envelope["attempt_id"])["response_observations"][0]["result"], good)

    def test_resolution_requires_threshold_evidence_and_is_append_only_idempotent(self) -> None:
        envelope = self._envelope()
        ledger = ExecutionLedger(self.root / "ledger.sqlite")
        ledger.create_attempt(envelope)
        action = self._action(envelope)
        decision = ledger.decide(envelope, action)
        self.assertTrue(decision["allowed"])
        generation = ledger.claim_recovery(envelope["attempt_id"])
        with self.assertRaisesRegex(ContractError, "positive no-send"):
            ledger.resolve_unknown(envelope["attempt_id"], action["action_id"], "operator", "resolved_not_dispatched", "claim", evidence("narrative"), generation=generation)
        with self.assertRaisesRegex(ContractError, "durable validated response"):
            ledger.resolve_unknown(envelope["attempt_id"], action["action_id"], "operator", "resolved_completed", "claim", evidence("response"), generation=generation)

        first = ledger.resolve_unknown(envelope["attempt_id"], action["action_id"], "operator", "resolved_not_dispatched", "no send boundary was reached", evidence(), generation=generation)
        replay = ExecutionLedger(ledger.path).resolve_unknown(envelope["attempt_id"], action["action_id"], "operator", "resolved_not_dispatched", "no send boundary was reached", evidence(), generation=generation)
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        with self.assertRaisesRegex(ContractError, "conflicting recovery resolution"):
            ledger.resolve_unknown(envelope["attempt_id"], action["action_id"], "operator", "still_unknown", "contradiction", evidence(), generation=generation)
        self.assertEqual(ledger.snapshot(envelope["attempt_id"])["actions"][0]["status"], "not_dispatched")

    def test_checkpoint_requires_current_high_water_envelope_and_owner(self) -> None:
        envelope, ledger, _ = self._started_action()
        generation = ledger.claim_recovery(envelope["attempt_id"])
        high_water = ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"]
        checkpoint = self.root / "checkpoints" / "checkpoint.json"
        checkpoint.parent.mkdir()
        checkpoint.write_text("{}")
        checkpoint_path = str(checkpoint)

        with self.assertRaisesRegex(ContractError, "ledger barrier"):
            ledger.bind_checkpoint(envelope["attempt_id"], "checkpoint", envelope_digest(envelope), high_water - 1, 1, "maf-test", checkpoint_path, generation=generation)
        with self.assertRaisesRegex(ContractError, "envelope digest"):
            ledger.bind_checkpoint(envelope["attempt_id"], "checkpoint", "0" * 64, high_water, 1, "maf-test", checkpoint_path, generation=generation)
        bound = ledger.bind_checkpoint(envelope["attempt_id"], "checkpoint", envelope_digest(envelope), high_water, 1, "maf-test", checkpoint_path, generation=generation)
        self.assertFalse(bound["replayed"])
        self.assertTrue(ledger.bind_checkpoint(envelope["attempt_id"], "checkpoint", envelope_digest(envelope), high_water, 1, "maf-test", checkpoint_path, generation=generation)["replayed"])

    def test_v1_database_is_readable_but_cannot_be_claimed_for_recovery(self) -> None:
        path = self.root / "legacy.sqlite"
        with sqlite3.connect(path) as db:
            db.executescript("""
                CREATE TABLE attempts (attempt_id TEXT PRIMARY KEY, work_id TEXT NOT NULL, envelope_json TEXT NOT NULL,
                  status TEXT NOT NULL, reason TEXT NOT NULL, receipt_path TEXT);
                CREATE TABLE actions (action_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL, request_json TEXT NOT NULL,
                  status TEXT NOT NULL, reason TEXT NOT NULL, grant_id TEXT UNIQUE, result_json TEXT);
                CREATE TABLE events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, attempt_id TEXT NOT NULL,
                  action_id TEXT, event TEXT NOT NULL, detail TEXT NOT NULL);
            """)
            db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?)", ("legacy", "work", "{}", "unknown", "", None))
        legacy = ExecutionLedger(path)
        self.assertEqual(legacy.snapshot("legacy")["attempt_id"], "legacy")
        with self.assertRaisesRegex(ContractError, "historical attempt is read-only"):
            legacy.claim_recovery("legacy")

    def test_terminal_continuation_regrant_is_single_use_and_preserves_original(self) -> None:
        envelope = {**self._envelope(), "execution_protocol_version": 2}
        ledger = ExecutionLedger(self.root / "continuation.sqlite")
        ledger.create_attempt(envelope)
        actions = []
        for sequence in (1, 2, 3):
            action = {**self._action(envelope), "action_id": expected_action_id(envelope, sequence), "sequence": sequence}
            actions.append(action)
            decision = ledger.decide(envelope, action, generation=1)
            self.assertTrue(decision["allowed"])
            if sequence < 3:
                self.assertTrue(ledger.consume_grant(action["action_id"], decision["grant_id"], generation=1))
                ledger.observe_send(action["action_id"], 1)
                result = self._result(envelope, f"result-{sequence}")
                ledger.observe_response(action["action_id"], result, 1)
                ledger.complete(action["action_id"], result, generation=1)
        checkpoint_sha = "f" * 64
        with ledger._db() as db:
            db.execute("INSERT INTO checkpoint_position_links VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (envelope["attempt_id"], "pending_delegate", 3, "cp", envelope_digest(envelope),
                        ledger.snapshot(envelope["attempt_id"])["events"][-1]["seq"], 2, "maf-test", 2,
                        str(self.root / "checkpoint.json"), checkpoint_sha, 20, "2026-01-01", 1))
        receipt = self.root / "original-receipt.json"
        receipt.write_text('{"status":"failed"}')
        ledger.finish_attempt(envelope["attempt_id"], "failed", "unsent", str(receipt), generation=1)
        resolution = ledger.resolve_unknown(envelope["attempt_id"], actions[2]["action_id"], "operator",
                                            "resolved_not_dispatched", "positive no-send proof", evidence(), generation=1)
        opened = ledger.begin_continuation(envelope["attempt_id"], actions[2]["action_id"], resolution["resolution_id"],
                                           hashlib.sha256(receipt.read_bytes()).hexdigest(), checkpoint_sha, actor="local")
        self.assertEqual(opened["status"], "pending")
        epoch = opened["epoch_id"]
        generation = ledger.claim_continuation(epoch, actor="local")
        grant = ledger.regrant_continuation(epoch, envelope, actions[2], generation=generation)
        self.assertTrue(grant["allowed"])
        self.assertTrue(ledger.regrant_continuation(epoch, envelope, actions[2], generation=generation)["replayed"])
        with ledger.send_lock():
            self.assertTrue(ledger.claim_continuation_send(epoch, grant["grant_id"], generation=generation))
            self.assertFalse(ledger.claim_continuation_send(epoch, grant["grant_id"], generation=generation))
        result = self._result(envelope, "continued")
        ledger.observe_continuation_response(epoch, result, generation=generation)
        ledger.finish_continuation(epoch, "completed", "maf_acknowledged", str(self.root / "continuation.json"), generation=generation)
        snapshot = ledger.snapshot(envelope["attempt_id"])
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["receipt_path"], str(receipt))
        self.assertEqual(snapshot["actions"][2]["status"], "not_dispatched")
        self.assertEqual(snapshot["continuations"][0]["status"], "completed")
        self.assertTrue(snapshot["continuations"][0]["send_claimed"])
        with self.assertRaisesRegex(ContractError, "terminal"):
            ledger.claim_continuation(epoch, actor="other")


if __name__ == "__main__":
    unittest.main()
