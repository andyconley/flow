"""Ledger tests for protocol-v8 verifier reservations and durable evaluation."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
from execution_contracts import (  # noqa: E402
    ContractError,
    digest,
    envelope_digest,
    expected_magentic_action_id,
)
from execution_ledger import ExecutionLedger  # noqa: E402
from delivery_recovery import RecoveryRefused  # noqa: E402
from verifier_contracts import evaluate_candidate  # noqa: E402
from tests.test_chartered_execution_contract import chartered, structured_verifier  # noqa: E402


def _action(envelope: dict, sequence: int, assignment: dict, task: str) -> dict:
    group = (envelope["job_contract"]["producer_instance_ids"]
             if assignment["instance_id"] in envelope["job_contract"]["producer_instance_ids"]
             else envelope["job_contract"]["verifier_instance_ids"])
    bindings = {item["instance_id"]: item for item in envelope["roster"]}
    candidates = [{key: bindings[item][key] for key in
                   ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model")}
                  for item in group]
    rejected = {item["instance_id"]: {"reason": "not selected", "facts": ["bounded roster"]}
                for item in candidates if item["instance_id"] != assignment["instance_id"]}
    action = {"schema_version": 1, "attempt_id": envelope["attempt_id"],
              "envelope_digest": envelope_digest(envelope), "sequence": sequence,
              "kind": "delegate", "manager_turn": min(sequence, 6), "task": task,
              "task_digest": hashlib.sha256(task.encode()).hexdigest(),
              "rationale": "Manager selected this specialist.", "checkpoint_id": f"pending-{sequence}",
              "parent_action_id": None,
              "provider_choice": {"eligible_candidates": candidates,
                                  "selected_candidate": assignment["instance_id"],
                                  "rationale": {"manager_reason": "bounded task", "facts": ["charter allows it"]},
                                  "rejection_reasons": rejected},
              **{key: assignment[key] for key in ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model")}}
    action["action_id"] = expected_magentic_action_id(action)
    return action


def _result(action: dict, output: str) -> dict:
    return {"schema_version": 1, "status": "completed", "provider": action["provider"], "model": action["model"],
            "physical_call": action["provider"] != "local-stub",
            "evidence_level": "flow_observed_local_http_response" if action["provider"] == "ollama" else "local_stub",
            "output": output, "output_sha256": hashlib.sha256(output.encode()).hexdigest()}


class StructuredVerifierLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ledger = ExecutionLedger(Path(self.temporary.name) / "ledger.sqlite")

    def envelope(self, *, maximum: int = 2, two_verifiers: bool = False) -> dict:
        env = structured_verifier()
        env["attempt_id"] = "attempt-" + str(maximum) + ("-two" if two_verifiers else "")
        env["limits"]["max_verifier_calls"] = maximum
        if two_verifiers:
            first = env["roster"][0]
            clone = {**first, "assignment_id": "second-verifier", "instance_id": "second-verifier-1",
                     "instructions": "Independently verify bounded evidence."}
            clone["definition_digest"] = digest({"role": clone["role"], "instructions": clone["instructions"]})
            env["roster"].append(clone)
            env["job_contract"]["verifier_instance_ids"].append(clone["instance_id"])
        return env

    def _complete_and_evaluate(self, env: dict, proposal: dict, candidate: str) -> dict:
        grant = self.ledger.decide(env, proposal, generation=1)
        self.assertTrue(grant["allowed"], grant)
        diff, tests = "d" * 64, "e" * 64
        binding = self.ledger.bind_verifier_input(proposal["action_id"], {"task": "verify", "candidate": candidate}, diff, tests, generation=1)
        self.assertTrue(self.ledger.consume_grant(proposal["action_id"], grant["grant_id"], generation=1))
        self.ledger.claim_verifier_send(proposal["action_id"], generation=1)
        result = _result(proposal, candidate)
        self.ledger.observe_response(proposal["action_id"], result, generation=1)
        self.ledger.complete(proposal["action_id"], result, generation=1)
        evaluation = evaluate_candidate(action_id=proposal["action_id"], verifier_input_digest=binding["input_digest"],
                                        raw_output=candidate, diff_digest=diff, test_evidence_digest=tests)
        return self.ledger.record_verifier_evaluation(proposal["action_id"], evaluation, generation=1)

    def test_two_calls_are_shared_across_verifier_identities_and_third_is_denied(self):
        env = self.envelope(two_verifiers=True)
        self.ledger.create_attempt(env)
        first = _action(env, 1, env["roster"][0], "Verify first evidence.")
        self._complete_and_evaluate(env, first, '{"schema_version":1,"decision":"fail","summary":"repair","findings":[{"severity":"blocking","summary":"bad","evidence":"test"}]}')
        second = _action(env, 2, env["roster"][2], "Verify second evidence.")
        self._complete_and_evaluate(env, second, '{"schema_version":1,"decision":"fail","summary":"repair","findings":[{"severity":"blocking","summary":"bad","evidence":"test"}]}')
        third = _action(env, 3, env["roster"][0], "Try a third verifier call.")
        self.assertEqual(self.ledger.decide(env, third, generation=1)["reason"], "verifier_call_cap")
        self.assertEqual(self.ledger.verifier_usage(env["attempt_id"]),
                         {"maximum": 2, "reserved": 2, "consumed": 2, "denied": 1, "retry_eligible": False})

    def test_cap_one_denies_retry_and_first_nonpass_is_not_retry_eligible(self):
        env = self.envelope(maximum=1)
        self.ledger.create_attempt(env)
        first = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        self._complete_and_evaluate(env, first, '{"schema_version":1,"decision":"fail","summary":"repair","findings":[{"severity":"blocking","summary":"bad","evidence":"test"}]}')
        second = _action(env, 2, env["roster"][0], "Retry bounded evidence.")
        self.assertEqual(self.ledger.decide(env, second, generation=1)["reason"], "verifier_call_cap")
        self.assertFalse(self.ledger.verifier_usage(env["attempt_id"])["retry_eligible"])

    def test_pass_denies_an_unneeded_second_verifier_before_send(self):
        env = self.envelope()
        self.ledger.create_attempt(env)
        first = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        self._complete_and_evaluate(env, first, '{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}')
        second = _action(env, 2, env["roster"][0], "Unneeded retry.")
        decision = self.ledger.decide(env, second, generation=1)
        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "verifier_retry_denied")
        self.assertEqual(self.ledger.verifier_usage(env["attempt_id"])["denied"], 1)

    def test_concurrent_identical_proposals_reserve_one_atomic_grant(self):
        env = self.envelope(maximum=1)
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify concurrently.")
        barrier = threading.Barrier(2)

        def decide():
            barrier.wait()
            return self.ledger.decide(env, proposal, generation=1)

        with ThreadPoolExecutor(max_workers=2) as pool:
            decisions = [future.result() for future in (pool.submit(decide), pool.submit(decide))]
        self.assertTrue(all(item["allowed"] for item in decisions))
        self.assertEqual(len({item["grant_id"] for item in decisions}), 1)
        self.assertEqual(len(self.ledger.snapshot(env["attempt_id"])["actions"]), 1)
        self.assertEqual(self.ledger.verifier_usage(env["attempt_id"])["reserved"], 1)

    def test_exact_bindings_and_evaluations_replay_but_conflicts_refuse(self):
        env = self.envelope()
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        grant = self.ledger.decide(env, proposal, generation=1)
        binding = self.ledger.bind_verifier_input(proposal["action_id"], {"task": "verify"}, "d" * 64, "e" * 64, generation=1)
        self.assertTrue(self.ledger.bind_verifier_input(proposal["action_id"], {"task": "verify"}, "d" * 64, "e" * 64, generation=1)["replayed"])
        with self.assertRaisesRegex(ContractError, "conflicts"):
            self.ledger.bind_verifier_input(proposal["action_id"], {"task": "changed"}, "d" * 64, "e" * 64, generation=1)
        self.ledger.consume_grant(proposal["action_id"], grant["grant_id"], generation=1)
        self.ledger.claim_verifier_send(proposal["action_id"], generation=1)
        raw = '{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}'
        result = _result(proposal, raw)
        self.ledger.observe_response(proposal["action_id"], result, generation=1)
        self.ledger.complete(proposal["action_id"], result, generation=1)
        evaluation = evaluate_candidate(action_id=proposal["action_id"], verifier_input_digest=binding["input_digest"], raw_output=raw, diff_digest="d" * 64, test_evidence_digest="e" * 64)
        self.assertFalse(self.ledger.record_verifier_evaluation(proposal["action_id"], evaluation, generation=1)["replayed"])
        self.assertTrue(self.ledger.record_verifier_evaluation(proposal["action_id"], evaluation, generation=1)["replayed"])
        # A validly sealed but different judgment over the same bindings.
        changed = evaluate_candidate(action_id=proposal["action_id"], verifier_input_digest=binding["input_digest"],
                                     raw_output=raw, diff_digest="d" * 64, test_evidence_digest="e" * 64,
                                     forced_unusable_reason="provider_binding_mismatch")
        with self.assertRaisesRegex(Exception, "conflicts with durable evaluation"):
            self.ledger.record_verifier_evaluation(proposal["action_id"], changed, generation=1)
        with self.assertRaisesRegex(Exception, "reason is invalid"):
            self.ledger.record_verifier_evaluation(proposal["action_id"], {**evaluation, "reason": "accepted_fail"}, generation=1)

    def test_unknown_consumes_and_proven_not_dispatched_releases_allowance(self):
        env = self.envelope(maximum=1)
        self.ledger.create_attempt(env)
        unknown = _action(env, 1, env["roster"][0], "Verify then lose transport.")
        grant = self.ledger.decide(env, unknown, generation=1)
        self.ledger.bind_verifier_input(unknown["action_id"], {"task": "verify"}, "d" * 64, "e" * 64, generation=1)
        self.ledger.consume_grant(unknown["action_id"], grant["grant_id"], generation=1)
        self.ledger.mark_unknown(unknown["action_id"], "transport_lost", generation=1)
        self.assertEqual(self.ledger.verifier_usage(env["attempt_id"])["consumed"], 1)

        retry_env = self.envelope(maximum=1)
        retry_env["attempt_id"] = "attempt-not-dispatched"
        # A separate delivery: a same-work successor would share the lineage caps.
        retry_env["work_id"] = "work-not-dispatched"
        self.ledger.create_attempt(retry_env)
        first = _action(retry_env, 1, retry_env["roster"][0], "Prepare verifier without send.")
        first_grant = self.ledger.decide(retry_env, first, generation=1)
        self.ledger.bind_verifier_input(first["action_id"], {"task": "verify"}, "d" * 64, "e" * 64, generation=1)
        self.ledger.close_pre_send_failure(first["action_id"], first_grant["grant_id"], generation=1)
        self.assertEqual(self.ledger.verifier_usage(retry_env["attempt_id"])["reserved"], 0)
        second = _action(retry_env, 2, retry_env["roster"][0], "Use released verifier allowance.")
        self.assertTrue(self.ledger.decide(retry_env, second, generation=1)["allowed"])

    def test_pre_send_failure_releases_an_unconsumed_grant_on_every_chartered_protocol(self):
        for version in (6, 7, 8):
            with self.subTest(protocol=version):
                env = chartered() if version == 6 else self.envelope()
                env["attempt_id"] = f"attempt-pre-send-v{version}"
                if version == 7:
                    env["execution_protocol_version"] = 7
                    env["limits"].pop("max_verifier_calls")
                self.ledger.create_attempt(env)
                proposal = _action(env, 1, env["roster"][1], "Edit, then fail before dispatch.")
                grant = self.ledger.decide(env, proposal, generation=1)
                self.assertTrue(grant["allowed"], grant)
                self.ledger.close_pre_send_failure(proposal["action_id"], grant["grant_id"], generation=1)
                action = self.ledger.snapshot(env["attempt_id"])["actions"][0]
                self.assertEqual((action["status"], action["reason"]), ("not_dispatched", "pre_send_failure"))
                self.assertFalse(self.ledger.consume_grant(proposal["action_id"], grant["grant_id"], generation=1))

    def test_event_order_requires_input_response_completion_then_evaluation(self):
        env = self.envelope()
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify ordered evidence.")
        self._complete_and_evaluate(env, proposal, '{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}')
        events = [item["event"] for item in self.ledger.snapshot(env["attempt_id"])["events"]]
        positions = [events.index(name) for name in ("verifier_input_recorded", "verifier_send_claimed", "response_observed", "worker_completed", "verifier_evaluated")]
        self.assertEqual(positions, sorted(positions))

    def test_received_oversized_candidate_is_completed_and_unusable_not_unknown(self):
        env = self.envelope()
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify oversized response handling.")
        recorded = self._complete_and_evaluate(env, proposal, "x" * (16 * 1024 + 1))
        snapshot = self.ledger.snapshot(env["attempt_id"])
        self.assertEqual(snapshot["actions"][0]["status"], "completed")
        self.assertEqual(recorded["evaluation"]["disposition"], "unusable")
        self.assertEqual(recorded["evaluation"]["reason"], "raw_output_invalid")

    def test_pre_v8_database_migrates_additively_without_rewriting_legacy_row(self):
        path = Path(self.temporary.name) / "legacy.sqlite"
        envelope_json = '{"legacy":true}'
        with sqlite3.connect(path) as db:
            db.executescript("""
                CREATE TABLE attempts (
                    attempt_id TEXT PRIMARY KEY, work_id TEXT NOT NULL,
                    envelope_json TEXT NOT NULL, status TEXT NOT NULL,
                    reason TEXT NOT NULL, receipt_path TEXT
                );
                CREATE TABLE actions (
                    action_id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                    request_json TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL,
                    grant_id TEXT UNIQUE, result_json TEXT
                );
                CREATE TABLE checkpoint_links (
                    attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id), checkpoint_id TEXT NOT NULL,
                    envelope_digest TEXT NOT NULL, ledger_seq INTEGER NOT NULL, format_version INTEGER NOT NULL,
                    runtime_version TEXT NOT NULL, path TEXT NOT NULL, bound_at TEXT NOT NULL,
                    owner_generation INTEGER NOT NULL
                );
            """)
            db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?)", ("legacy", "work", envelope_json, "completed", "", "receipt.json"))
        ExecutionLedger(path)
        with sqlite3.connect(path) as db:
            self.assertEqual(db.execute("SELECT attempt_id,work_id,envelope_json,status,reason,receipt_path FROM attempts WHERE attempt_id='legacy'").fetchone(),
                             ("legacy", "work", envelope_json, "completed", "", "receipt.json"))
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({"verifier_inputs", "verifier_evaluations"}.issubset(tables))

    def test_pre_recovery_v8_database_gains_empty_recovery_tables_and_legacy_snapshots_are_unchanged(self):
        env = self.envelope()
        self.ledger.create_attempt(env)
        legacy = chartered()
        legacy["attempt_id"] = "legacy-v6"
        self.ledger.create_attempt(legacy)
        before_legacy = self.ledger.snapshot("legacy-v6")
        with sqlite3.connect(self.ledger.path) as db:
            db.execute("DROP TABLE attempt_interruptions")
            db.execute("DROP TABLE attempt_recoveries")
            db.execute("ALTER TABLE attempts DROP COLUMN sealed_receipt_sha256")
        old = ExecutionLedger(self.ledger.path, read_only=True).snapshot(env["attempt_id"])
        self.assertEqual((old["interruptions"], old["recoveries"], old["sealed_receipt_sha256"]), ([], [], None))
        ExecutionLedger(self.ledger.path)
        with sqlite3.connect(self.ledger.path) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
        self.assertTrue({"attempt_interruptions", "attempt_recoveries"}.issubset(tables))
        self.assertIn("sealed_receipt_sha256", columns)
        migrated = self.ledger.snapshot(env["attempt_id"])
        self.assertEqual((migrated["interruptions"], migrated["recoveries"], migrated["sealed_receipt_sha256"]), ([], [], None))
        after_legacy = self.ledger.snapshot("legacy-v6")
        self.assertEqual(after_legacy, before_legacy)
        self.assertFalse({"interruptions", "recoveries", "sealed_receipt_sha256"} & set(after_legacy))

    def _claim(self, env, *, expected=1, mode="pending", seq=None):
        high_water = self.ledger.snapshot(env["attempt_id"])["events"][-1]["seq"] if seq is None else seq
        return self.ledger.claim_chartered_recovery(env["attempt_id"], expected_generation=expected,
                                                    expected_event_seq=high_water, lead_generation=1,
                                                    actor="flow-chartered-resume", mode=mode, checkpoint=None, quarantined=[])

    def test_recovery_claim_refuses_moved_facts_and_uncertain_sends_without_mutation(self):
        env = self.envelope(maximum=1)
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        grant = self.ledger.decide(env, proposal, generation=1)
        stale = self.ledger.snapshot(env["attempt_id"])["events"][-1]["seq"] - 1
        before = self.ledger.snapshot(env["attempt_id"])
        with self.assertRaises(RecoveryRefused) as moved:
            self._claim(env, seq=stale)
        self.assertEqual(moved.exception.reason, "recovery_in_progress")
        self.ledger.prepare_verifier_send(proposal["action_id"], grant["grant_id"], {**proposal, "provider_task": "verify"},
                                          "d" * 64, "e" * 64, generation=1)
        before = self.ledger.snapshot(env["attempt_id"])
        with self.assertRaises(RecoveryRefused) as uncertain:
            self._claim(env)
        self.assertEqual(uncertain.exception.reason, "reconciliation_required")
        self.assertEqual(self.ledger.snapshot(env["attempt_id"]), before)

    def test_recovery_claim_is_a_compare_and_swap_that_releases_unconsumed_grants(self):
        env = self.envelope(maximum=1)
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        self.assertTrue(self.ledger.decide(env, proposal, generation=1)["allowed"])
        claim = self._claim(env)
        self.assertEqual((claim["generation"], claim["released_action_ids"]), (2, [proposal["action_id"]]))
        snapshot = self.ledger.snapshot(env["attempt_id"])
        action = snapshot["actions"][0]
        self.assertEqual((action["status"], action["reason"], action["grant_id"]),
                         ("not_dispatched", "recovery_unconsumed_grant", None))
        self.assertEqual([item["cause"] for item in snapshot["interruptions"]], ["unmarked_process_exit"])
        self.assertEqual(snapshot["recoveries"][0]["interruption_ids"], [snapshot["interruptions"][0]["interruption_id"]])
        with self.assertRaises(RecoveryRefused) as stale:
            self._claim(env, expected=1)
        self.assertEqual(stale.exception.reason, "recovery_in_progress")
        self.assertEqual(len(self.ledger.snapshot(env["attempt_id"])["recoveries"]), 1)

    def test_regrant_counts_the_released_proposal_once_and_restarts_the_grant_clock(self):
        env = self.envelope(maximum=1)
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        self.ledger.decide(env, proposal, generation=1)
        with sqlite3.connect(self.ledger.path) as db:
            db.execute("UPDATE events SET at='2000-01-01T00:00:00+00:00' WHERE event='policy_allowed'")
        generation = self._claim(env)["generation"]
        replay = self.ledger.decide(env, proposal, generation=generation)
        self.assertEqual((replay["replayed"], replay["allowed"], replay["reason"]), (True, False, "recovery_unconsumed_grant"))
        with self.assertRaises(ContractError):
            self.ledger.regrant_recovered_action(env, proposal, generation=1)
        grant = self.ledger.regrant_recovered_action(env, proposal, generation=generation)
        self.assertEqual((grant["allowed"], grant["reason"]), (True, "recovery_regranted"))
        binding = self.ledger.prepare_verifier_send(proposal["action_id"], grant["grant_id"],
                                                    {**proposal, "provider_task": "verify"}, "d" * 64, "e" * 64,
                                                    generation=generation)
        self.assertEqual(binding["owner_generation"], generation)
        self.assertEqual(self.ledger.verifier_usage(env["attempt_id"])["reserved"], 1)
        with self.assertRaises(ContractError):
            self.ledger.regrant_recovered_action(env, proposal, generation=generation)

    def test_regrant_applies_the_verifier_retry_rule_before_any_grant(self):
        env = self.envelope(maximum=2)
        self.ledger.create_attempt(env)
        first = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        self._complete_and_evaluate(env, first, '{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}')
        second = _action(env, 2, env["roster"][0], "Verify bounded evidence again.")
        with sqlite3.connect(self.ledger.path) as db:
            # A pass leaves no retry allowance, so decide would deny; force the
            # released shape that only a recovery can produce.
            db.execute("INSERT INTO actions(action_id,attempt_id,request_json,status,reason,grant_id,kind,sequence) VALUES(?,?,?,?,?,?,?,?)",
                       (second["action_id"], env["attempt_id"], __import__("execution_contracts").canonical(second),
                        "allowed", "allowed", "g" * 32, "delegate", 2))
        generation = self._claim(env)["generation"]
        denied = self.ledger.regrant_recovered_action(env, second, generation=generation)
        self.assertEqual((denied["allowed"], denied["reason"]), (False, "verifier_retry_denied"))

    def test_manager_grant_is_reissued_in_place_only_under_an_active_recovery(self):
        env = self.envelope()
        self.ledger.create_attempt(env)
        request = {"schema_version": 1, "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
                   "sequence": 1, "phase": "facts", "manager_round": 1, "prompt_digest": "a" * 64}
        request["call_id"] = __import__("execution_contracts").expected_manager_call_id(request)
        first = self.ledger.decide_manager_call(env, request, generation=1)
        with self.assertRaises(ContractError):
            self.ledger.reissue_recovered_manager_grant(request["call_id"], generation=1)
        generation = self._claim(env, mode="answer")["generation"]
        reissued = self.ledger.reissue_recovered_manager_grant(request["call_id"], generation=generation)
        self.assertNotEqual(reissued["grant_id"], first["grant_id"])
        self.assertTrue(self.ledger.consume_manager_grant(request["call_id"], reissued["grant_id"], generation=generation))

    def test_recovery_lock_names_a_live_run_and_a_concurrent_recovery(self):
        for holder, reason in (("live", "attempt_running"), ("recovery", "recovery_in_progress")):
            with self.subTest(holder=holder):
                with self.ledger.recovery_lock("attempt", holder=holder):
                    with self.assertRaises(RecoveryRefused) as raised:
                        with self.ledger.recovery_lock("attempt", holder="recovery"):
                            pass
                self.assertEqual(raised.exception.reason, reason)
        with self.ledger.recovery_lock("attempt", holder="recovery"):
            pass

    def test_send_lock_refuses_a_symlinked_lock_path(self):
        target = Path(self.temporary.name) / "elsewhere"
        target.write_text("untouched")
        self.ledger.path.with_suffix(".send.lock").symlink_to(target)
        with self.assertRaises(OSError):
            with self.ledger.send_lock():
                self.fail("a symlinked send lock must not be taken")
        self.assertEqual((target.read_text(), target.stat().st_mode & 0o777 != 0o600), ("untouched", True))

    def test_expired_verifier_grant_is_committed_denied_not_left_reserved(self):
        env = self.envelope(maximum=1)
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        grant = self.ledger.decide(env, proposal, generation=1)
        self.assertTrue(grant["allowed"], grant)
        with sqlite3.connect(self.ledger.path) as db:
            db.execute("UPDATE events SET at='2000-01-01T00:00:00+00:00' WHERE action_id=? AND event='policy_allowed'",
                       (proposal["action_id"],))
        with self.assertRaisesRegex(ContractError, "grant expired"):
            self.ledger.prepare_verifier_send(proposal["action_id"], grant["grant_id"], {**proposal, "provider_task": "verify"},
                                              "d" * 64, "e" * 64, generation=1)
        action = next(item for item in self.ledger.snapshot(env["attempt_id"])["actions"]
                      if item["action_id"] == proposal["action_id"])
        self.assertEqual((action["status"], action["reason"]), ("denied", "grant_expired"))
        self.assertEqual(self.ledger.verifier_usage(env["attempt_id"])["reserved"], 0)
        self.assertEqual(self.ledger.snapshot(env["attempt_id"])["verifier_inputs"], [])

    def test_operator_can_resolve_unknown_verifier_with_empty_observed_output(self):
        env = self.envelope(maximum=1)
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify bounded evidence.")
        grant = self.ledger.decide(env, proposal, generation=1)
        self.ledger.prepare_verifier_send(proposal["action_id"], grant["grant_id"], {**proposal, "provider_task": "verify"},
                                          "d" * 64, "e" * 64, generation=1)
        self.ledger.observe_response(proposal["action_id"], _result(proposal, ""), generation=1)
        self.ledger.mark_unknown(proposal["action_id"], "specialist_send_outcome_uncertain", generation=1)
        resolved = self.ledger.resolve_unknown(env["attempt_id"], proposal["action_id"], "operator", "resolved_completed",
                                               "observed response was durably retained",
                                               [{"kind": "response", "path": ".flow/runs/proof.json", "sha256": "a" * 64}],
                                               generation=1)
        self.assertEqual(resolved["disposition"], "resolved_completed")
