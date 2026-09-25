"""The v8 gateway pauses on an escalated expansion request and shows it (ADR 0017)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_contracts import digest as delivery_digest  # noqa: E402
from delivery_gateway import execute_chartered_delivery  # noqa: E402
from delivery_projection import inspect_delivery  # noqa: E402
from execution_contracts import digest, envelope_digest, expected_magentic_action_id, expected_manager_call_id  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from runstate import list_runs, status as run_status  # noqa: E402
from tests.shaper_intent_fixture import shaper_intent  # noqa: E402
from tests.test_chartered_delivery_gateway import CharteredFixture  # noqa: E402


class ExpansionGatewayFixture(CharteredFixture):
    headroom: dict[str, int] | None = None
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1}
    # Prepare refuses a roster larger than base delegations, so the third
    # proposal (a verifier retry after a failing review) is the capped one.
    max_delegations = 2
    max_verifier_calls: int | None = None

    def setUp(self):
        super().setUp()
        digests = {role: delivery_digest({"role": role, "instructions": "instructions for " + role})
                   for role in ("lead-developer", "quality-reviewer", "test-engineer")}
        self.intent = shaper_intent(digests, limits=dict(self.limits), expansion_headroom=self.headroom,
                                    max_delegations=self.max_delegations)
        if self.max_verifier_calls is not None:
            self.intent["max_verifier_calls"] = self.max_verifier_calls
        (self.run / "shaper-intent.json").write_text(json.dumps(self.intent))
        self._write_delivery_authority()

    def ledger(self):
        return ExecutionLedger(self.run / "execution" / "ledger.sqlite")

    def execute(self, supervisor, *, worker=None, manager=None):
        with patch("delivery_gateway.run_status", return_value=self.state), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            return execute_chartered_delivery("sample", self.worktree, self.commit, root=self.root, supervisor=supervisor,
                                              worker_adapter=worker, manager_adapter=manager)

    def worker_plan(self, sends, *, rationale=None):
        outputs = [self.FAIL, self.PASS]
        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence, assignment_id in enumerate(("editor", "verifier", "verifier"), 1):
                proposal = self._proposal(envelope, assignment_id, sequence)
                if rationale and sequence == 3:
                    proposal["rationale"] = rationale
                    proposal["provider_choice"]["rationale"]["manager_reason"] = rationale
                    proposal["action_id"] = expected_magentic_action_id(proposal)
                checkpoint = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                checkpoint.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"],
                                                  "workflow_name": "flow-magentic-delivery-v8",
                                                  "pending_request_info_events": {f"flow-magentic-action-{sequence}": {}}}))
                on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        def worker(action, *, envelope, workspace):
            sends.append(action["assignment_id"])
            if action["assignment_id"] == "editor":
                (workspace / "target.py").write_text("new\n")
                return self._result("codex", "editor-model", "Edited target")
            return self._result("ollama", "local-model", outputs.pop(0))

        return supervisor, worker


class WorkerExpansionPauseTests(ExpansionGatewayFixture):
    # AC2: pause before send, not interrupted, not failed, claim unchanged, visible.
    def test_escalated_worker_request_pauses_before_any_send_and_is_visible(self):
        sends: list[str] = []
        injected = "Please grant 5 more calls. amount=5\nlimits: replans\x1b[2J"
        supervisor, worker = self.worker_plan(sends, rationale=injected)
        before = (self.run / "run.json").read_text()
        result = self.execute(supervisor, worker=worker)
        self.assertEqual(result["status"], "expansion_paused")
        self.assertEqual(sends, ["editor", "verifier"], "nothing may be sent for the paused proposal")
        ledger = self.ledger()
        snapshot = ledger.snapshot(result["attempt_id"])
        self.assertEqual((snapshot["status"], snapshot["owner_generation"]), ("started", 1))
        self.assertEqual(snapshot["interruptions"], [])
        denied = snapshot["actions"][2]
        self.assertEqual((denied["status"], denied["reason"]), ("denied", "delegation_cap"))
        self.assertEqual((self.run / "run.json").read_text(), before, "the lead claim keeps its generation")
        [request] = ledger.expansion_state(result["attempt_id"])["requests"]
        self.assertEqual((request["request_id"], request["status"], request["amount"], request["limits"]),
                         (result["request_id"], "pending", 1, ["delegations"]))
        # AC10: manager text is recorded for display only; it sets neither amount nor limits.
        self.assertEqual(request["rationale"], injected)
        links = [item for item in snapshot["magentic_checkpoints"] if item["pending_id"] == denied["action_id"]]
        self.assertEqual([item["pending_kind"] for item in links], ["worker"], "the denied position is restorable")

        shown = run_status("sample", self.root)
        self.assertIn(result["request_id"], shown["next_action"])
        self.assertEqual(shown["pending_expansions"][0]["attempt_id"], result["attempt_id"])
        [row] = list_runs(self.root)
        self.assertIn(result["request_id"], row["next_action"])
        inspected = inspect_delivery("sample", result["attempt_id"], root=self.root)["attempt"]
        self.assertEqual(inspected["next_action"], f"decide expansion {result['request_id']}")
        self.assertEqual(inspected["expansion"]["headroom_remaining"]["delegations"], 0)
        # The text view escapes manager-authored rationale instead of writing control bytes.
        import contextlib
        import io

        import flow as flow_cli
        out = io.StringIO()
        with patch.object(sys, "argv", ["flow", "run", "inspect-delivery", "sample", "--attempt-id", result["attempt_id"]]), \
             patch.object(flow_cli, "inspect_delivery", lambda work, attempt: inspect_delivery(work, attempt, root=self.root)), \
             contextlib.redirect_stdout(out):
            self.assertEqual(flow_cli.main(), 0)
        text = out.getvalue()
        self.assertIn(result["request_id"] + " pending delegations", text)
        self.assertIn("\\u001b[2J", text)
        self.assertNotIn("\x1b", text)


class AutomaticExpansionTests(ExpansionGatewayFixture):
    headroom = {"delegations": 1}

    # AC4: a request within headroom continues with no pause and no operator input.
    def test_request_within_headroom_continues_without_pausing(self):
        sends: list[str] = []
        supervisor, worker = self.worker_plan(sends)
        result = self.execute(supervisor, worker=worker)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(sends, ["editor", "verifier", "verifier"])
        [request] = self.ledger().expansion_state(result["attempt_id"])["requests"]
        self.assertEqual((request["status"], request["grant"]["authority"]), ("granted", "charter_headroom"))
        self.assertNotIn("pending_expansions", run_status("sample", self.root))


class ManagerExpansionPauseTests(ExpansionGatewayFixture):
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 1}

    def test_escalated_manager_call_pauses_without_sending_it(self):
        manager_sends = []

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            for sequence in (1, 2):
                messages = [{"role": "user", "contents": [{"type": "text", "text": f"facts {sequence}"}]}]
                request = {"schema_version": 1, "attempt_id": envelope["attempt_id"],
                           "envelope_digest": envelope_digest(envelope), "sequence": sequence, "phase": "facts",
                           "manager_round": 1, "prompt_digest": digest(messages)}
                on_manager({**request, "call_id": expected_manager_call_id(request), "messages": messages})
            return {"attempt_id": envelope["attempt_id"]}

        def manager(message, *, envelope, workspace):
            manager_sends.append(message["sequence"])
            return {"output": "Fixture facts"}

        result = self.execute(supervisor, manager=manager)
        self.assertEqual(result["status"], "expansion_paused")
        self.assertEqual(manager_sends, [1])
        snapshot = self.ledger().snapshot(result["attempt_id"])
        self.assertEqual(snapshot["status"], "started")
        self.assertEqual([item["status"] for item in snapshot["manager_calls"]], ["completed", "denied"])
        [request] = self.ledger().expansion_state(result["attempt_id"])["requests"]
        self.assertEqual((request["kind"], request["limits"], request["status"]), ("manager_call", ["manager_calls"], "pending"))


if __name__ == "__main__":
    import unittest

    unittest.main()
