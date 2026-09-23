"""Ledger tests for protocol-v8 verifier reservations and durable evaluation."""

from __future__ import annotations

import hashlib
import sqlite3
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
from verifier_contracts import evaluate_candidate  # noqa: E402
from tests.test_chartered_execution_contract import structured_verifier  # noqa: E402


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
        changed = {**evaluation, "reason": "accepted_fail"}
        with self.assertRaisesRegex(Exception, "contradicts|conflicts|digest mismatch"):
            self.ledger.record_verifier_evaluation(proposal["action_id"], changed, generation=1)

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
        self.ledger.create_attempt(retry_env)
        first = _action(retry_env, 1, retry_env["roster"][0], "Prepare verifier without send.")
        first_grant = self.ledger.decide(retry_env, first, generation=1)
        self.ledger.bind_verifier_input(first["action_id"], {"task": "verify"}, "d" * 64, "e" * 64, generation=1)
        self.ledger.close_pre_send_failure(first["action_id"], first_grant["grant_id"], generation=1)
        self.assertEqual(self.ledger.verifier_usage(retry_env["attempt_id"])["reserved"], 0)
        second = _action(retry_env, 2, retry_env["roster"][0], "Use released verifier allowance.")
        self.assertTrue(self.ledger.decide(retry_env, second, generation=1)["allowed"])

    def test_event_order_requires_input_response_completion_then_evaluation(self):
        env = self.envelope()
        self.ledger.create_attempt(env)
        proposal = _action(env, 1, env["roster"][0], "Verify ordered evidence.")
        self._complete_and_evaluate(env, proposal, '{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}')
        events = [item["event"] for item in self.ledger.snapshot(env["attempt_id"])["events"]]
        positions = [events.index(name) for name in ("verifier_input_recorded", "verifier_send_claimed", "response_observed", "worker_completed", "verifier_evaluated")]
        self.assertEqual(positions, sorted(positions))

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
