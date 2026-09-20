"""Versioned Claude review identity and policy remain Flow-owned."""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from execution_contracts import ContractError, digest, envelope_digest, expected_action_id, validate_action, validate_envelope, validate_result
from execution_ledger import ExecutionLedger


def assignment(sequence, role, provider):
    instructions = f"Perform the {role} task."
    task = f"Task for {role}."
    return {"sequence": sequence, "assignment_id": f"approved-{role}",
            "definition_digest": digest({"role": role, "instructions": instructions}),
            "instance_id": f"{role}-1", "role": role, "provider": provider,
            "model": "local-model" if sequence == 1 else "opus", "task": task,
            "task_digest": hashlib.sha256(task.encode()).hexdigest(), "instructions": instructions}


def envelope(attempt_id="claude-attempt"):
    sources = {key: {"path": f".flow/runs/claude-work/{key}.md", "sha256": char * 64}
               for key, char in (("requirements", "a"), ("acceptance", "b"))}
    return {"schema_version": 1, "execution_protocol_version": 4,
            "work_id": "claude-work", "attempt_id": attempt_id,
            "charter_sources": sources, "charter_digest": digest({key: item["sha256"] for key, item in sources.items()}),
            "run_protocol_revision": 2, "manifest_digest": "c" * 64,
            "assignments": [assignment(1, "test-engineer", "ollama"), assignment(2, "quality-reviewer", "claude")],
            "source_commit": "d" * 40,
            "source_files": [{"path": "cli/codex_worker.py", "sha256": "e" * 64},
                             {"path": "tests/test_codex_worker.py", "sha256": "f" * 64}],
            "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "max_claude_calls": 1},
            "checkpoint_dir": "/tmp/claude-checkpoints"}


def action(env, sequence):
    chosen = env["assignments"][sequence - 1]
    return {"schema_version": 1, "action_id": expected_action_id(env, sequence),
            "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
            "sequence": sequence, "kind": "delegate",
            **{key: chosen[key] for key in ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model", "task_digest")}}


class ClaudeContractTests(unittest.TestCase):
    def test_version_four_binds_role_provider_and_source(self):
        env = envelope()
        validate_envelope(env)
        validate_action(env, action(env, 1))
        validate_action(env, action(env, 2))
        with self.assertRaises(ContractError):
            validate_action(env, {**action(env, 2), "provider": "codex"})
        with self.assertRaises(ContractError):
            validate_envelope({**env, "source_files": env["source_files"][:1]})
        with self.assertRaises(ContractError):
            validate_envelope({**env, "assignments": env["assignments"][::-1]})

    def test_claude_result_requires_session_and_observed_usage_shape(self):
        env = envelope()
        output = "No finding."
        result = {"schema_version": 1, "status": "completed", "provider": "claude", "model": "opus",
                  "physical_call": True, "evidence_level": "flow_observed_claude_cli_completed_turn",
                  "output": output, "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
                  "usage": {"input_tokens": 10}, "session_id": "session-1"}
        validate_result(env, result, action=action(env, 2))
        with self.assertRaises(ContractError):
            validate_result(env, {**result, "session_id": ""}, action=action(env, 2))
        with self.assertRaises(ContractError):
            validate_result(env, {**result, "usage": {"service_tier": "standard"}}, action=action(env, 2))

    def test_one_claude_call_cap_spans_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            first = envelope("first")
            ledger.create_attempt(first)
            first_action = action(first, 1)
            grant = ledger.decide(first, first_action, generation=1)
            self.assertTrue(ledger.consume_grant(first_action["action_id"], grant["grant_id"], generation=1))
            ledger.observe_send(first_action["action_id"], 1)
            local_output = "test plan"
            local_result = {"schema_version": 1, "status": "completed", "provider": "ollama", "model": "local-model",
                            "physical_call": True, "evidence_level": "flow_observed_local_http_response",
                            "output": local_output, "output_sha256": hashlib.sha256(local_output.encode()).hexdigest(), "usage": None}
            ledger.observe_response(first_action["action_id"], local_result, 1)
            ledger.complete(first_action["action_id"], local_result, generation=1)
            paid = action(first, 2)
            paid_grant = ledger.decide(first, paid, generation=1)
            self.assertTrue(paid_grant["allowed"])
            # A granted call reserves the budget even before a response.
            second = envelope("second")
            ledger.create_attempt(second)
            second_local = action(second, 1)
            second_grant = ledger.decide(second, second_local, generation=1)
            self.assertTrue(second_grant["allowed"])
            self.assertTrue(ledger.consume_grant(second_local["action_id"], second_grant["grant_id"], generation=1))
            ledger.observe_send(second_local["action_id"], 1)
            ledger.observe_response(second_local["action_id"], local_result, 1)
            ledger.complete(second_local["action_id"], local_result, generation=1)
            denied = ledger.decide(second, action(second, 2), generation=1)
            self.assertFalse(denied["allowed"])
            self.assertEqual(denied["reason"], "claude_call_cap")


if __name__ == "__main__":
    unittest.main()
