"""Expansion pauses and replays against the pinned stock Magentic runner (ADR 0017).

These drive the real ``runtime.maf_runner.delivery_lead`` child through the
gateway with scripted manager text and stub workers. They pin the replay
identity the design depends on: a paused worker proposal returns with its
original action id, and manager calls replay with identical call ids after an
answer-mode restore and after a fresh restart (spike S1-S3).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import delivery_gateway  # noqa: E402
from maf_env import MAF_PYTHON, requires_maf  # noqa: E402
from maf_supervisor import run_maf_delivery  # noqa: E402
from tests.test_expansion_gateway import ExpansionGatewayFixture  # noqa: E402


def real_runner(envelope, task, on_manager, on_action, **kwargs):
    return run_maf_delivery(envelope, task, on_manager, on_action, **{**kwargs, "python_path": MAF_PYTHON})


class MafExpansionFixture(ExpansionGatewayFixture):
    verifier_outputs = ("PASS",)

    def setUp(self):
        super().setUp()
        self.manager_sends: list[tuple[int, str, str]] = []
        self.worker_sends: list[tuple[str, str]] = []
        self.outputs = [getattr(self, name) for name in self.verifier_outputs]
        self.passed = False

    def manager(self, message, *, envelope, workspace):
        phase = message["phase"]
        self.manager_sends.append((message["sequence"], phase, message["call_id"]))
        if phase == "progress":
            done = self.passed
            speaker = "editor" if not self.worker_sends else "verifier"
            return {"output": json.dumps({
                "is_request_satisfied": {"reason": "verified" if done else "pending", "answer": done},
                "is_in_loop": {"reason": "no", "answer": False},
                "is_progress_being_made": {"reason": "yes", "answer": True},
                "next_speaker": {"reason": "bounded next step", "answer": speaker},
                "instruction_or_question": {"reason": "task", "answer": "Edit target.py" if speaker == "editor" else "Verify target.py"}})}
        return {"output": {"facts": "Fixture facts", "plan": "- Edit then verify target.py", "final": "Done"}[phase]}

    def worker(self, action, *, envelope, workspace):
        self.worker_sends.append((action["assignment_id"], action["action_id"]))
        if action["assignment_id"] == "editor":
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")
        output = self.outputs.pop(0)
        self.passed = output == self.PASS
        return self._result("ollama", "local-model", output)

    def run_live(self):
        return self.execute(real_runner, worker=self.worker, manager=self.manager)

    def decide(self, paused, *, approve):
        generation = self.ledger().snapshot(paused["attempt_id"])["owner_generation"]
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])):
            return delivery_gateway.decide_expansion("sample", paused["attempt_id"], paused["request_id"], approve=approve,
                                                     expected_generation=generation, actor="andy",
                                                     explanation="bounded extra unit", root=self.root)

    def recover(self, attempt):
        with patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            return delivery_gateway.recover_delivery("sample", attempt, root=self.root, supervisor=real_runner,
                                                     worker_adapter=self.worker, manager_adapter=self.manager)

    def assert_calls_unique(self, attempt):
        calls = self.ledger().snapshot(attempt)["manager_calls"]
        self.assertEqual([item["sequence"] for item in calls], list(range(1, len(calls) + 1)))
        sent = [call_id for _, _, call_id in self.manager_sends]
        self.assertEqual(len(sent), len(set(sent)), "no manager call is sent twice")


@requires_maf
class AutomaticExpansionMafTests(MafExpansionFixture):
    headroom = {"delegations": 1}
    verifier_outputs = ("FAIL", "PASS")

    def test_retry_within_headroom_completes_without_pausing(self):
        result = self.run_live()
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual([name for name, _ in self.worker_sends], ["editor", "verifier", "verifier"])
        [request] = self.ledger().expansion_state(result["attempt_id"])["requests"]
        self.assertEqual((request["status"], request["grant"]["authority"]), ("granted", "charter_headroom"))


@requires_maf
class WorkerEscalationMafTests(MafExpansionFixture):
    verifier_outputs = ("FAIL", "PASS")

    def test_approved_worker_escalation_replays_the_same_proposal_and_completes(self):
        paused = self.run_live()
        self.assertEqual(paused["status"], "expansion_paused", paused)
        denied = self.ledger().snapshot(paused["attempt_id"])["actions"][2]
        self.assertEqual(len(self.worker_sends), 2)
        self.decide(paused, approve=True)
        result = self.recover(paused["attempt_id"])
        self.assertEqual((result["mode"], result["status"]), ("pending", "completed"), result)
        # The runner re-emitted the paused proposal under its original identity (S1).
        self.assertEqual(self.worker_sends[2], ("verifier", denied["action_id"]))
        self.assertEqual(len(self.worker_sends), 3)
        self.assert_calls_unique(paused["attempt_id"])


@requires_maf
class ManagerEscalationMafTests(MafExpansionFixture):
    # facts, plan, progress->editor, progress->verifier, progress(satisfied), final: the final call pauses.
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 5}

    def pause(self):
        paused = self.run_live()
        self.assertEqual(paused["status"], "expansion_paused", paused)
        denied = self.ledger().snapshot(paused["attempt_id"])["manager_calls"][-1]
        self.assertEqual((denied["status"], denied["sequence"]), ("denied", 6))
        return paused, denied

    def test_approved_manager_call_resumes_from_the_worker_checkpoint_and_replays_calls(self):
        paused, denied = self.pause()
        self.decide(paused, approve=True)
        result = self.recover(paused["attempt_id"])
        self.assertEqual((result["mode"], result["status"]), ("answer", "completed"), result)
        # Calls after the checkpoint replayed under identical call ids (S2); the
        # denied call arrived again under its own id and was sent once.
        final = self.ledger().snapshot(paused["attempt_id"])["manager_calls"][-1]
        self.assertEqual((final["call_id"], final["status"]), (denied["call_id"], "completed"))
        self.assertEqual([call_id for _, _, call_id in self.manager_sends].count(denied["call_id"]), 1)
        self.assertEqual(len(self.worker_sends), 2, "completed actions are answered, not resent")
        self.assert_calls_unique(paused["attempt_id"])

    def test_denied_manager_call_seals_the_attempt_failed(self):
        paused, _ = self.pause()
        self.decide(paused, approve=False)
        sends = len(self.manager_sends)
        result = self.recover(paused["attempt_id"])
        self.assertEqual((result["mode"], result["status"]), ("seal", "failed"), result)
        self.assertEqual(result["reason"], "manager_call_cap")
        self.assertEqual(len(self.manager_sends), sends)


@requires_maf
class RestartMafTests(MafExpansionFixture):
    # The third call (the first progress) pauses before any worker checkpoint exists.
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 2}

    def test_restart_replays_planning_calls_and_the_supervisor_allows_growth_past_base(self):
        paused = self.run_live()
        self.assertEqual(paused["status"], "expansion_paused", paused)
        self.assertEqual(self.ledger().snapshot(paused["attempt_id"])["actions"], [])
        first = self.ledger().snapshot(paused["attempt_id"])["manager_calls"]
        self.decide(paused, approve=True)
        result = self.recover(paused["attempt_id"])
        self.assertEqual(result["mode"], "restart", result)
        # A fresh start reissued calls 1-2 with identical ids (S3), answered from
        # the ledger; call 3 ran under the grant, and the next call escalated
        # again. That fourth call in one process is past base + 1, which the
        # v8 supervisor guard now allows up to the runner ceiling (A1).
        self.assertEqual(result["status"], "expansion_paused", result)
        calls = self.ledger().snapshot(paused["attempt_id"])["manager_calls"]
        self.assertEqual([item["call_id"] for item in calls[:3]], [item["call_id"] for item in first])
        self.assertEqual([item["status"] for item in calls], ["completed", "completed", "completed", "denied"])
        self.assertEqual([sequence for sequence, _, _ in self.manager_sends], [1, 2, 3])
        self.assert_calls_unique(paused["attempt_id"])


if __name__ == "__main__":
    import unittest

    unittest.main()
