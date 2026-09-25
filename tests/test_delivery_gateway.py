"""Flow v5 gateway contract exercise with pinned MAF and fake providers."""

import hashlib
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from delivery_gateway import _default_manager_adapter, execute_delivery, resume_delivery
from maf_supervisor import MafProtocolError, MafTransportError, _write_bounded, run_maf_delivery
from execution_contracts import digest, envelope_digest, expected_manager_call_id, expected_replan_id
from execution_ledger import ExecutionLedger


from maf_env import MAF_PYTHON, requires_maf  # noqa: E402


def _result(provider: str, model: str, output: str) -> dict:
    value = {"schema_version": 1, "status": "completed", "provider": provider,
             "model": model, "physical_call": True,
             "evidence_level": "flow_observed_claude_cli_completed_turn" if provider == "claude" else "flow_observed_local_http_response",
             "output": output, "output_sha256": hashlib.sha256(output.encode()).hexdigest(), "usage": None}
    if provider == "claude":
        value["session_id"] = "fake-claude-session"
    return value


@requires_maf
class DeliveryGatewayTests(unittest.TestCase):
    def test_manager_adapter_preserves_stock_message_context(self):
        messages = [{"role": "system", "contents": [{"type": "text", "text": "Keep the accepted roster."}]},
                    {"role": "user", "contents": [{"type": "text", "text": "Return progress as pure JSON."}]}]
        with tempfile.TemporaryDirectory() as folder:
            with patch("delivery_gateway.call_claude", return_value={"output": "{}"}) as adapter:
                _default_manager_adapter({"messages": messages}, envelope={"manager": {"model": "fake"}},
                                         workspace=Path(folder))
        sent = adapter.call_args.kwargs
        self.assertIn("system:\nKeep the accepted roster.", sent["prompt_override"])
        self.assertIn("user:\nReturn progress as pure JSON.", sent["prompt_override"])
        self.assertNotIn("review and report", sent["prompt_override"])

    def test_manager_adapter_unwraps_only_exact_progress_json_fence(self):
        messages = [{"role": "user", "contents": [{"type": "text", "text": "Progress JSON"}]}]
        body = '{"is_request_satisfied":{"answer":false,"reason":"pending"},"next_speaker":"local-analyst"}'
        raw = "```json\n" + body + "\n```"
        with tempfile.TemporaryDirectory() as folder:
            with patch("delivery_gateway.call_claude", return_value={"output": raw,
                                                                  "output_sha256": hashlib.sha256(raw.encode()).hexdigest()}):
                result = _default_manager_adapter({"messages": messages},
                                                  envelope={"manager": {"model": "fake"}},
                                                  workspace=Path(folder))
        self.assertEqual(result["output"], body)
        self.assertEqual(result["normalization"], "exact_json_fence")
        self.assertEqual(result["raw_output_sha256"], hashlib.sha256(raw.encode()).hexdigest())

    def test_codex_manager_uses_read_only_sandbox(self):
        messages = [{"role": "user", "contents": [{"type": "text", "text": "Return a short plan."}]}]
        with tempfile.TemporaryDirectory() as folder:
            with patch("delivery_gateway.call_codex", return_value={"output": "Plan"}) as adapter:
                result = _default_manager_adapter({"messages": messages},
                    envelope={"manager": {"provider": "codex", "model": "gpt-test"}}, workspace=Path(folder))
        self.assertEqual(result["output"], "Plan")
        self.assertEqual(adapter.call_args.kwargs["sandbox"], "read-only")
        self.assertIn("Return a short plan.", adapter.call_args.kwargs["task"])

    def test_supervisor_write_times_out_when_child_stops_reading(self):
        read_fd, write_fd = os.pipe()
        try:
            with self.assertRaises(MafProtocolError):
                _write_bounded(write_fd, {"payload": "x" * 180000}, time.monotonic() + 0.05)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_stock_manager_selects_claude_then_distinct_local_verifier_under_flow_grants(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            worktree = root / "repair"
            (worktree / "cli").mkdir(parents=True)
            (worktree / "tests").mkdir()
            (worktree / "cli/codex_worker.py").write_text("OLD = True\n")
            (worktree / "tests/test_codex_worker.py").write_text("assert True\n")
            subprocess.run(["git", "init", "-q", str(worktree)], check=True)
            subprocess.run(["git", "-C", str(worktree), "add", "cli", "tests"], check=True)
            subprocess.run(["git", "-C", str(worktree), "-c", "user.name=Flow Test", "-c", "user.email=flow@test.invalid",
                            "commit", "-qm", "test: baseline"], check=True)
            source_commit = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
            (worktree / "tests/test_codex_worker.py").write_text("assert not True\n")
            attempt_dir = root / ".flow/runs/test/execution/gateway-probe"
            (attempt_dir / "checkpoints").mkdir(parents=True)
            charter_sources = {name: {"path": f".flow/runs/test/{name}.md", "sha256": "a" * 64}
                               for name in ("requirements", "acceptance")}
            roster = []
            for assignment_id, role, provider in (("claude-implementer", "lead-developer", "claude"),
                                                  ("local-analyst", "test-engineer", "ollama"),
                                                  ("local-verifier", "test-engineer", "ollama")):
                instructions = "One bounded specialist call"
                roster.append({"assignment_id": assignment_id, "definition_digest": digest({"role": role, "instructions": instructions}),
                               "instance_id": assignment_id, "role": role, "provider": provider,
                               "model": "fake", "instructions": instructions})
            envelope = {"schema_version": 1, "execution_protocol_version": 5, "work_id": "test", "attempt_id": "gateway-probe",
                        "charter_digest": digest({"requirements": "a" * 64, "acceptance": "a" * 64}),
                        "charter_sources": charter_sources, "run_protocol_revision": 2, "manifest_digest": "b" * 64,
                        "checkpoint_dir": str(attempt_dir / "checkpoints"), "source_commit": source_commit,
                        "worktree": str(worktree), "allowed_paths": ["cli/codex_worker.py", "tests/test_codex_worker.py"],
                        "manager": {"provider": "claude", "model": "fake"}, "roster": roster,
                        "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2,
                                   "max_manager_calls": 12, "max_manager_rounds": 6, "max_paid_worker_calls": 1}}
            baseline = {"source_commit": source_commit,
                        "files": {name: hashlib.sha256((worktree / name).read_bytes()).hexdigest()
                                  for name in envelope["allowed_paths"]},
                        "regression_diff_sha256": "c" * 64}
            (attempt_dir / "baseline.json").write_text(__import__("json").dumps(baseline))
            (attempt_dir / "envelope.json").write_text(__import__("json").dumps(envelope))
            (attempt_dir / "job-charter.snapshot.md").write_text("Repair the target")
            ledger = ExecutionLedger(attempt_dir.parent / "ledger.sqlite")
            ledger.create_attempt(envelope)
            manager_phases = []
            worker_roles = []
            verifier_task = ""

            def fake_manager(message, *, envelope, workspace):
                manager_phases.append(message["phase"])
                phase = message["phase"]
                if phase == "progress":
                    turn = manager_phases.count("progress")
                    speaker = "claude-implementer" if turn == 1 else "local-verifier"
                    done = turn >= 3
                    output = __import__("json").dumps({
                        "is_request_satisfied": {"reason": "done" if done else "pending", "answer": done},
                        "is_in_loop": {"reason": "no", "answer": False},
                        "is_progress_being_made": {"reason": "yes", "answer": True},
                        "next_speaker": {"reason": "evidence", "answer": speaker},
                        "instruction_or_question": {"reason": "task", "answer": "Repair or verify the targeted code"}})
                else:
                    output = {"facts": "The scoped defect needs repair", "plan": "- Repair then verify",
                              "final": "The repair is complete"}[phase]
                return {"output": output, "usage": None}

            def fake_worker(action, *, envelope, workspace):
                nonlocal verifier_task
                worker_roles.append(action["assignment_id"])
                if action["provider"] == "claude":
                    (workspace / "cli/codex_worker.py").write_text("OLD = False\n# " + "x" * 2500 + " END_OF_DIFF\n")
                    trace = Path(envelope["checkpoint_dir"]).parent / "claude-implementer.debug.log"
                    trace.write_text("Claude edit tool started\n")
                    (trace.parent / "claude-implementer.events.ndjson").write_text('{"type":"result"}\n')
                    return _result("claude", "fake", "Repair complete")
                verifier_task = action.get("provider_task", "")
                return _result("ollama", "fake", "Verified diff and test result")

            def interrupt_after_first(envelope, task, on_manager, on_action, **kwargs):
                def finish_then_interrupt(proposal):
                    on_action(proposal)
                    raise MafTransportError("injected child loss after completed worker")
                return run_maf_delivery(envelope, task, on_manager, finish_then_interrupt, **kwargs)

            fake_test = lambda _: {"command": ["fake-test"], "status": "passed", "output_sha256": "d" * 64}
            with patch("delivery_gateway.prepare_delivery", return_value=(envelope, "Repair the target", attempt_dir, ledger)):
                interrupted = execute_delivery("test", worktree, source_commit, manager_adapter=fake_manager,
                                               worker_adapter=fake_worker, supervisor=interrupt_after_first,
                                               test_runner=fake_test, python_path=MAF_PYTHON)
            self.assertEqual(interrupted["status"], "interrupted")
            self.assertEqual(ledger.snapshot("gateway-probe")["status"], "started")
            result = resume_delivery("test", "gateway-probe", root=root, manager_adapter=fake_manager,
                                     worker_adapter=fake_worker, test_runner=fake_test, python_path=MAF_PYTHON)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["evidence"]["diagnostic_trace"]["bytes"], len(b"Claude edit tool started\n"))
            self.assertEqual(result["evidence"]["diagnostic_trace"]["path"], "claude-implementer.debug.log")
            self.assertEqual(result["evidence"]["event_trace"]["path"], "claude-implementer.events.ndjson")
            self.assertEqual(worker_roles, ["claude-implementer", "local-verifier"])
            self.assertIn("Flow-verified complete bounded diff", verifier_task)
            self.assertIn("Targeted test: passed", verifier_task)
            self.assertIn("END_OF_DIFF", verifier_task)
            snapshot = ledger.snapshot("gateway-probe")
            self.assertEqual(len(snapshot["actions"]), 2)
            self.assertTrue(all(item["status"] == "completed" for item in snapshot["actions"]))
            self.assertEqual(len(snapshot["manager_calls"]), len(manager_phases))

            # A deterministic policy failure at the same point must seal the
            # attempt, rather than being advertised as recoverable transport.
            (worktree / "cli/codex_worker.py").write_text("OLD = True\n")
            manager_phases.clear()
            policy_dir = root / ".flow/runs/policy/execution/policy-probe"
            (policy_dir / "checkpoints").mkdir(parents=True)
            policy_envelope = {**envelope, "work_id": "policy", "attempt_id": "policy-probe",
                               "checkpoint_dir": str(policy_dir / "checkpoints")}
            (policy_dir / "baseline.json").write_text(__import__("json").dumps(baseline))
            policy_ledger = ExecutionLedger(policy_dir.parent / "ledger.sqlite")
            policy_ledger.create_attempt(policy_envelope)

            def policy_failure(env, task, on_manager, on_action, **kwargs):
                def finish_then_fail(proposal):
                    on_action(proposal)
                    raise ValueError("injected deterministic policy failure")
                return run_maf_delivery(env, task, on_manager, finish_then_fail, **kwargs)

            with patch("delivery_gateway.prepare_delivery", return_value=(policy_envelope, "Repair the target", policy_dir, policy_ledger)):
                failed = execute_delivery("policy", worktree, source_commit, manager_adapter=fake_manager,
                                          worker_adapter=fake_worker, supervisor=policy_failure,
                                          test_runner=fake_test, python_path=MAF_PYTHON)
            self.assertEqual(failed["status"], "failed")
            self.assertEqual(policy_ledger.snapshot("policy-probe")["status"], "failed")
            with self.assertRaises(ValueError):
                resume_delivery("policy", "policy-probe", root=root)

            forged_dir = root / ".flow/runs/forged/execution/forged-probe"
            (forged_dir / "checkpoints").mkdir(parents=True)
            forged_envelope = {**envelope, "work_id": "forged", "attempt_id": "forged-probe",
                               "checkpoint_dir": str(forged_dir / "checkpoints")}
            (forged_dir / "baseline.json").write_text(__import__("json").dumps(baseline))
            forged_ledger = ExecutionLedger(forged_dir.parent / "ledger.sqlite")
            forged_ledger.create_attempt(forged_envelope)
            adapter_calls = []

            def forged_manager(*args, **kwargs):
                adapter_calls.append(True)
                return {"output": "should never send"}

            def forged_supervisor(env, task, on_manager, on_action, **kwargs):
                messages = [{"role": "user", "contents": ["forged replan"]}]
                request = {"protocol_version": 5, "type": "manager_request", "schema_version": 1,
                           "attempt_id": env["attempt_id"], "envelope_digest": envelope_digest(env),
                           "sequence": 1, "phase": "replan_plan", "manager_round": 1,
                           "prompt_digest": digest(messages), "messages": messages,
                           "replan_sequence": 1, "replan_id": expected_replan_id(env, 1)}
                request["call_id"] = expected_manager_call_id(request)
                on_manager(request)
                raise AssertionError("forged manager call unexpectedly authorized")

            with patch("delivery_gateway.prepare_delivery", return_value=(forged_envelope, "Repair the target", forged_dir, forged_ledger)):
                denied = execute_delivery("forged", worktree, source_commit, manager_adapter=forged_manager,
                                          worker_adapter=fake_worker, supervisor=forged_supervisor,
                                          test_runner=fake_test, python_path=MAF_PYTHON)
            self.assertEqual(denied["status"], "failed")
            self.assertEqual(adapter_calls, [])
            self.assertFalse(any(item["event"] == "manager_send_started"
                                 for item in forged_ledger.snapshot("forged-probe")["events"]))

            # Restore from a later worker checkpoint after an approved
            # replan. Flow supplies the replan count from its ledger rather
            # than restarting the child's in-memory counter at zero.
            (worktree / "cli/codex_worker.py").write_text("OLD = True\n")
            replan_dir = root / ".flow/runs/replan/execution/replan-probe"
            (replan_dir / "checkpoints").mkdir(parents=True)
            replan_envelope = {**envelope, "work_id": "replan", "attempt_id": "replan-probe",
                               "checkpoint_dir": str(replan_dir / "checkpoints")}
            (replan_dir / "baseline.json").write_text(__import__("json").dumps(baseline))
            (replan_dir / "envelope.json").write_text(__import__("json").dumps(replan_envelope))
            (replan_dir / "job-charter.snapshot.md").write_text("Repair the target")
            replan_ledger = ExecutionLedger(replan_dir.parent / "ledger.sqlite")
            replan_ledger.create_attempt(replan_envelope)
            replan_phases = []
            replan_actions = []

            def replan_manager(message, *, envelope, workspace):
                phase = message["phase"]
                replan_phases.append(phase)
                if phase == "progress":
                    turn = replan_phases.count("progress")
                    seen_replan = "replan_plan" in replan_phases
                    done = seen_replan and turn >= 6
                    speaker = "claude-implementer" if turn == 1 else (
                        "local-verifier" if seen_replan else "local-analyst")
                    output = __import__("json").dumps({
                        "is_request_satisfied": {"reason": "complete" if done else "pending", "answer": done},
                        "is_in_loop": {"reason": "loop", "answer": not seen_replan},
                        "is_progress_being_made": {"reason": "yes", "answer": True},
                        "next_speaker": {"reason": "evidence", "answer": speaker},
                        "instruction_or_question": {"reason": "task", "answer": "Repair or verify the targeted code"}})
                else:
                    output = {"facts": "The scoped defect needs repair", "plan": "- Repair then verify",
                              "replan_facts": "The repair is ready for verification",
                              "replan_plan": "- Verify the repair", "final": "The repair is complete"}[phase]
                return {"output": output, "usage": None}

            def replan_worker(action, *, envelope, workspace):
                replan_actions.append(action["assignment_id"])
                if action["provider"] == "claude":
                    (workspace / "cli/codex_worker.py").write_text("OLD = False\n")
                    return _result("claude", "fake", "Repair complete")
                return _result("ollama", "fake", "Analysis complete")

            def interrupt_after_replan(env, task, on_manager, on_action, **kwargs):
                def finish_fourth(proposal):
                    result = on_action(proposal)
                    if len(replan_actions) == 4:
                        raise MafTransportError("injected loss after replan checkpoint")
                    return result
                return run_maf_delivery(env, task, on_manager, finish_fourth, **kwargs)

            with patch("delivery_gateway.prepare_delivery", return_value=(replan_envelope, "Repair the target", replan_dir, replan_ledger)):
                paused = execute_delivery("replan", worktree, source_commit, manager_adapter=replan_manager,
                                          worker_adapter=replan_worker, supervisor=interrupt_after_replan,
                                          test_runner=fake_test, python_path=MAF_PYTHON)
            self.assertEqual(paused["status"], "interrupted", (paused, replan_phases, replan_actions))
            self.assertEqual(len([item for item in replan_ledger.snapshot("replan-probe")["replans"]
                                  if item["status"] == "allowed"]), 1)
            resumed = resume_delivery("replan", "replan-probe", root=root, manager_adapter=replan_manager,
                                      worker_adapter=replan_worker, test_runner=fake_test, python_path=MAF_PYTHON)
            self.assertEqual(resumed["status"], "completed")
            self.assertEqual(len(replan_actions), 4)


if __name__ == "__main__":
    unittest.main()
