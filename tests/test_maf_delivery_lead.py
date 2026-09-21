"""Pinned stock Magentic manager bridge tests with counted parent responses."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from cli.execution_contracts import expected_magentic_action_id, expected_manager_call_id


MAF_PYTHON = os.environ.get("FLOW_MAF_PYTHON", "/private/tmp/flow-maf-runtime-spike-20260919/bin/python")


@unittest.skipUnless(Path(MAF_PYTHON).exists(), "pinned MAF interpreter unavailable")
class StockDeliveryLeadTest(unittest.TestCase):
    def _exercise(self, speaker: str, protocol_version: int = 5) -> tuple[list[str], list[str], dict]:
        roster = [
            {"assignment_id": "test", "definition_digest": "test-definition", "instance_id": "test-engineer-1",
             "role": "test-engineer", "provider": "local-stub", "model": "fake"},
            {"assignment_id": "review", "definition_digest": "review-definition", "instance_id": "reviewer-1",
             "role": "quality-reviewer", "provider": "local-stub", "model": "fake"},
        ]
        with tempfile.TemporaryDirectory() as checkpoints:
            envelope = {"execution_protocol_version": protocol_version, "attempt_id": "stock-probe", "checkpoint_dir": checkpoints,
                        "roster": roster}
            child = subprocess.Popen([MAF_PYTHON, "-m", "runtime.maf_runner.delivery_lead"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, cwd=Path(__file__).resolve().parents[1])
            assert child.stdin and child.stdout
            child.stdin.write(json.dumps({"protocol_version": protocol_version, "type": "start", "envelope": envelope,
                                          "task": "Analyze the fixture"}) + "\n")
            child.stdin.flush()
            phases: list[str] = []
            selected: list[str] = []
            replan_requests: list[dict] = []
            terminal = {}
            for _ in range(24):
                line = child.stdout.readline()
                self.assertTrue(line, "child exited before terminal message")
                event = json.loads(line)
                kind = event["type"]
                if kind == "manager_request":
                    self.assertEqual(event["call_id"], expected_manager_call_id(event))
                    phases.append(event["phase"])
                    phase = event["phase"]
                    if phase.startswith("replan_"):
                        replan_requests.append(event)
                    if phase == "progress":
                        done = event["manager_round"] > 1 and speaker != "<replan>"
                        if speaker == "<replan>" and replan_requests:
                            done = True
                        answer = json.dumps({
                            "is_request_satisfied": {"reason": "complete" if done else "pending", "answer": done},
                            "is_in_loop": {"reason": "loop" if speaker == "<replan>" else "no", "answer": speaker == "<replan>"},
                            "is_progress_being_made": {"reason": "yes", "answer": True},
                            "next_speaker": {"reason": "evidence-based selection", "answer": "test-engineer-1" if speaker == "<replan>" else speaker},
                            "instruction_or_question": {"reason": "bounded", "answer": "Analyze the fixture"},
                        })
                        if speaker == "<malformed>":
                            answer = "not JSON"
                    else:
                        answer = {"facts": "Fixture facts", "plan": "- Select a specialist",
                                  "replan_facts": "Updated fixture facts", "replan_plan": "- Revised plan",
                                  "final": "Fixture analysis finished"}[phase]
                    child.stdin.write(json.dumps({"protocol_version": protocol_version, "type": "manager_response",
                                                  "call_id": event["call_id"], "text": answer}) + "\n")
                    child.stdin.flush()
                elif kind == "propose_action":
                    self.assertEqual(event["action_id"], expected_magentic_action_id(event))
                    self.assertTrue(event["checkpoint_id"])
                    selected.append(event["instance_id"])
                    child.stdin.write(json.dumps({"protocol_version": protocol_version, "type": "action_result",
                                                  "action_id": event["action_id"],
                                                  "result": {"summary": "Fixture analyzed"}}) + "\n")
                    child.stdin.flush()
                else:
                    terminal = event
                    break
            child.wait(timeout=10)
            child.stdin.close()
            child.stdout.close()
            assert child.stderr
            child.stderr.close()
            self.last_replan_requests = replan_requests
            return phases, selected, terminal

    def test_stock_manager_routes_to_selected_worker(self):
        first_phases, first_actions, first_terminal = self._exercise("test-engineer-1")
        second_phases, second_actions, second_terminal = self._exercise("reviewer-1")
        self.assertEqual(first_phases, ["facts", "plan", "progress", "progress", "final"])
        self.assertEqual(second_phases, first_phases)
        self.assertEqual(first_actions, ["test-engineer-1"])
        self.assertEqual(second_actions, ["reviewer-1"])
        self.assertEqual(first_terminal["type"], "workflow_finished")
        self.assertEqual(second_terminal["type"], "workflow_finished")

    def test_stock_manager_routes_with_chartered_protocol(self):
        phases, actions, terminal = self._exercise("test-engineer-1", protocol_version=6)
        self.assertEqual(phases, ["facts", "plan", "progress", "progress", "final"])
        self.assertEqual(actions, ["test-engineer-1"])
        self.assertEqual(terminal["type"], "workflow_finished")
        self.assertEqual(terminal["protocol_version"], 6)

    def test_unknown_speaker_does_not_fall_back_to_first_worker(self):
        phases, actions, terminal = self._exercise("unlisted-worker")
        self.assertEqual(phases, ["facts", "plan", "progress"])
        self.assertEqual(actions, [])
        self.assertEqual(terminal["type"], "error")
        self.assertIn("unlisted specialist", terminal["message"])

    def test_malformed_progress_aborts_without_retry_or_worker(self):
        phases, actions, terminal = self._exercise("<malformed>")
        self.assertEqual(phases, ["facts", "plan", "progress"])
        self.assertEqual(actions, [])
        self.assertEqual(terminal["type"], "error")

    def test_replan_facts_and_plan_share_flow_identity(self):
        phases, actions, terminal = self._exercise("<replan>")
        self.assertEqual(phases[:3], ["facts", "plan", "progress"])
        self.assertGreaterEqual(len(actions), 3)
        self.assertEqual([item["phase"] for item in self.last_replan_requests], ["replan_facts", "replan_plan"])
        facts, plan = self.last_replan_requests
        self.assertEqual(facts["replan_sequence"], 1)
        self.assertEqual(plan["replan_sequence"], 1)
        self.assertEqual(facts["replan_id"], plan["replan_id"])
        self.assertEqual(terminal["type"], "workflow_finished")

    def test_completed_action_restores_from_pending_checkpoint(self):
        roster = [{"assignment_id": "test", "definition_digest": "test-definition", "instance_id": "test-engineer-1",
                   "role": "test-engineer", "provider": "local-stub", "model": "fake"}]
        with tempfile.TemporaryDirectory() as checkpoints:
            envelope = {"execution_protocol_version": 5, "attempt_id": "restore-probe",
                        "checkpoint_dir": checkpoints, "roster": roster}

            def launch(payload):
                process = subprocess.Popen([MAF_PYTHON, "-m", "runtime.maf_runner.delivery_lead"],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           text=True, cwd=Path(__file__).resolve().parents[1])
                assert process.stdin
                process.stdin.write(json.dumps(payload) + "\n")
                process.stdin.flush()
                return process

            def answer_manager(process, event):
                assert process.stdin
                phase = event["phase"]
                response = {"facts": "Fixture facts", "plan": "- Ask specialist", "final": "Done"}.get(phase)
                if phase == "progress":
                    finished = event["manager_round"] > 1
                    response = json.dumps({"is_request_satisfied": {"reason": "done" if finished else "pending", "answer": finished},
                                           "is_in_loop": {"reason": "no", "answer": False},
                                           "is_progress_being_made": {"reason": "yes", "answer": True},
                                           "next_speaker": {"reason": "best", "answer": "test-engineer-1"},
                                           "instruction_or_question": {"reason": "task", "answer": "Analyze fixture"}})
                process.stdin.write(json.dumps({"protocol_version": 5, "type": "manager_response",
                                                "call_id": event["call_id"], "text": response}) + "\n")
                process.stdin.flush()

            initial = launch({"protocol_version": 5, "type": "start", "envelope": envelope,
                              "task": "Analyze fixture"})
            assert initial.stdout
            for _ in range(4):
                event = json.loads(initial.stdout.readline())
                if event["type"] == "manager_request":
                    answer_manager(initial, event)
                else:
                    self.assertEqual(event["type"], "propose_action")
                    proposal = event
                    break
            initial.kill()
            initial.wait(timeout=10)
            for pipe in (initial.stdin, initial.stdout, initial.stderr):
                if pipe:
                    pipe.close()

            restored = launch({"protocol_version": 5, "type": "resume", "envelope": envelope,
                               "task": "Analyze fixture", "resume": {"checkpoint_id": proposal["checkpoint_id"],
                               "request_id": "flow-magentic-action-1", "action_id": proposal["action_id"],
                               "manager_calls_committed": 3, "replans_committed": 0,
                               "result": {"summary": "Fixture analyzed"}}})
            assert restored.stdout
            seen = []
            for _ in range(4):
                event = json.loads(restored.stdout.readline())
                seen.append(event["type"])
                if event["type"] == "manager_request":
                    answer_manager(restored, event)
                else:
                    self.assertEqual(event["type"], "workflow_finished", event)
                    break
            restored.wait(timeout=10)
            self.assertEqual(restored.returncode, 0)
            self.assertEqual(seen, ["manager_request", "manager_request", "workflow_finished"])
            for pipe in (restored.stdin, restored.stdout, restored.stderr):
                if pipe:
                    pipe.close()

    def test_checkpoint_after_replan_requires_matching_ledger_count(self):
        roster = [{"assignment_id": "test", "definition_digest": "test-definition", "instance_id": "test-engineer-1",
                   "role": "test-engineer", "provider": "local-stub", "model": "fake"}]
        with tempfile.TemporaryDirectory() as checkpoints:
            envelope = {"execution_protocol_version": 5, "attempt_id": "replan-restore",
                        "checkpoint_dir": checkpoints, "roster": roster}

            def launch(payload):
                process = subprocess.Popen([MAF_PYTHON, "-m", "runtime.maf_runner.delivery_lead"],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           text=True, cwd=Path(__file__).resolve().parents[1])
                assert process.stdin
                process.stdin.write(json.dumps(payload) + "\n")
                process.stdin.flush()
                return process

            def close(process, *, kill=False):
                if kill:
                    process.kill()
                process.wait(timeout=10)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe:
                        pipe.close()

            initial = launch({"protocol_version": 5, "type": "start", "envelope": envelope,
                              "task": "Analyze fixture"})
            assert initial.stdout and initial.stdin
            manager_calls = 0
            replan_requests = []
            for _ in range(20):
                event = json.loads(initial.stdout.readline())
                if event["type"] == "manager_request":
                    manager_calls += 1
                    if event["phase"].startswith("replan_"):
                        replan_requests.append(event)
                    if event["phase"] == "progress":
                        response = json.dumps({"is_request_satisfied": {"reason": "pending", "answer": False},
                                               "is_in_loop": {"reason": "loop", "answer": True},
                                               "is_progress_being_made": {"reason": "stalled", "answer": False},
                                               "next_speaker": {"reason": "best", "answer": "test-engineer-1"},
                                               "instruction_or_question": {"reason": "task", "answer": "Analyze fixture"}})
                    else:
                        response = {"facts": "facts", "plan": "plan", "replan_facts": "revised facts",
                                    "replan_plan": "revised plan"}[event["phase"]]
                    initial.stdin.write(json.dumps({"protocol_version": 5, "type": "manager_response",
                                                    "call_id": event["call_id"], "text": response}) + "\n")
                    initial.stdin.flush()
                elif event["type"] == "propose_action":
                    if replan_requests:
                        proposal = event
                        break
                    initial.stdin.write(json.dumps({"protocol_version": 5, "type": "action_result",
                                                    "action_id": event["action_id"],
                                                    "result": {"summary": "Fixture analyzed"}}) + "\n")
                    initial.stdin.flush()
                else:
                    self.fail(f"unexpected event before post-replan checkpoint: {event}")
            close(initial, kill=True)
            self.assertEqual(manager_calls, 9)
            self.assertEqual([item["replan_sequence"] for item in replan_requests], [1, 1])

            resume = {"checkpoint_id": proposal["checkpoint_id"], "request_id": "flow-magentic-action-4",
                      "action_id": proposal["action_id"], "manager_calls_committed": manager_calls,
                      "result": {"summary": "Fixture analyzed"}}
            wrong = launch({"protocol_version": 5, "type": "resume", "envelope": envelope,
                            "task": "Analyze fixture", "resume": {**resume, "replans_committed": 0}})
            assert wrong.stdout
            denied = json.loads(wrong.stdout.readline())
            close(wrong)
            self.assertEqual(denied["type"], "error")
            self.assertIn("replan position differs", denied["message"])

            restored = launch({"protocol_version": 5, "type": "resume", "envelope": envelope,
                               "task": "Analyze fixture", "resume": {**resume, "replans_committed": 1}})
            assert restored.stdout and restored.stdin
            progress = json.loads(restored.stdout.readline())
            self.assertEqual((progress["type"], progress["phase"], progress["sequence"]),
                             ("manager_request", "progress", 10))
            complete = json.dumps({"is_request_satisfied": {"reason": "done", "answer": True},
                                   "is_in_loop": {"reason": "no", "answer": False},
                                   "is_progress_being_made": {"reason": "yes", "answer": True},
                                   "next_speaker": {"reason": "best", "answer": "test-engineer-1"},
                                   "instruction_or_question": {"reason": "task", "answer": "Analyze fixture"}})
            restored.stdin.write(json.dumps({"protocol_version": 5, "type": "manager_response",
                                             "call_id": progress["call_id"], "text": complete}) + "\n")
            restored.stdin.flush()
            final = json.loads(restored.stdout.readline())
            self.assertEqual((final["type"], final["phase"]), ("manager_request", "final"))
            restored.stdin.write(json.dumps({"protocol_version": 5, "type": "manager_response",
                                             "call_id": final["call_id"], "text": "Done"}) + "\n")
            restored.stdin.flush()
            finished = json.loads(restored.stdout.readline())
            close(restored)
            self.assertEqual(finished["type"], "workflow_finished")


if __name__ == "__main__":
    unittest.main()
