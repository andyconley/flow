"""The ADR 0020 fixture lineage: one v8 work id that exercises every verify-receipt check.

Attempt A: a paid manager call, then a paid editor send whose outcome is
lost (``unknown``); A is abandoned. Attempt B, its successor: manager calls
and a completed editor and verifier, then one automatic token tranche, then
a second hit that pauses for ``decide-expansion``; the engineer approves and
``recover-delivery-lead`` resumes in answer mode, replaying the calls after
the verifier checkpoint (including the automatically granted one) from the
ledger and sending the paused call once. B completes.

Charged tokens (M 10,000, T 5,000, U 2,000; one tranche of headroom):
A = 1,000 + U = 3,000. B: m1 4,000 (7,000); editor 1,500 (8,500); m2 1,000
(9,500); m3 allowed at 9,500, 1,000 (10,500); m4 hits the cap, one tranche
is granted, 3,000 (13,500 of 15,000); m5 2,000 (15,500); m6 hits again with
no headroom left and pauses; after approval it sends 500.

Stubs spawn real, short-lived child processes and register them with the
parent's control scope under the row they serve, and the stub editor writes
a diagnostic trace, so the group and trace checks have evidence to compare.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import process_identity
from delivery_termination import abandon_delivery
from execution_ledger import ExecutionLedger
from tests.manager_stub import manager_reply
import tests.test_expansion_recovery as expansion_recovery

M, T, U = 10_000, 5_000, 2_000
PREDECESSOR_MANAGER_USAGE = 1_000
MANAGER_USAGE = {1: 4_000, 2: 1_000, 3: 1_000, 4: 3_000, 5: 2_000, 6: 500}
EDITOR_USAGE = 1_500


def _child(row_id: str) -> None:
    """A real process group registered under ``row_id``, then ended (abandon reaps only live groups)."""
    process = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        process_identity.register_group(process.pid, "provider", row_id)
    finally:
        process.kill()
        process.wait()


class HandbackLineageFixture(expansion_recovery.ExpansionRecoveryFixture):
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 2, "max_manager_calls": 12,
              "max_lineage_tokens": M, "token_tranche": T, "unobserved_send_tokens": U}
    headroom = {"tokens": 1}
    max_delegations = 3

    # ---------------------------------------------------------------- stubs

    def manager_message(self, envelope, sequence):
        return expansion_recovery.ManagerExpansionRecoveryTests.manager_message(self, envelope, sequence)

    def manager(self, message, *, envelope, workspace):
        self.manager_sends.append((envelope["attempt_id"], message["sequence"]))
        _child(message["call_id"])
        usage = PREDECESSOR_MANAGER_USAGE if self.building_predecessor else MANAGER_USAGE[message["sequence"]]
        return manager_reply(message, f"Fixture facts {message['sequence']}",
                             usage={"input_tokens": usage, "output_tokens": 0})

    def lost_editor(self, action, *, envelope, workspace):
        _child(action["action_id"])
        raise OSError("simulated connection reset during the paid send")

    def worker(self, action, *, envelope, workspace):
        _child(action["action_id"])
        self.worker_sends.append(action["assignment_id"])
        if action["assignment_id"] == "editor":
            (workspace / "target.py").write_text("new\n")
            trace = Path(envelope["checkpoint_dir"]).parent / "claude-implementer.debug.log"
            trace.write_text("stub editor trace\n")
            return {**self._result("codex", "editor-model", "Edited target"),
                    "usage": {"input_tokens": EDITOR_USAGE, "output_tokens": 0}}
        return self._result("ollama", "local-model", self.PASS)

    def write_checkpoint(self, envelope, proposal, previous=None):
        path = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
        path.write_text(json.dumps({"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
                                    "previous_checkpoint_id": previous,
                                    "pending_request_info_events": {f"flow-magentic-action-{proposal['sequence']}": {}}}))

    # ---------------------------------------------------------------- build

    def build_lineage(self):
        """Run A and B through the real gateway and ledger; returns (A, B) attempt ids."""
        self.manager_sends, self.worker_sends = [], []
        self.building_predecessor = True

        def first(envelope, task, on_manager, on_action, **kwargs):
            on_manager(self.manager_message(envelope, 1))
            proposal = self._proposal(envelope, "editor", 1)
            self.write_checkpoint(envelope, proposal)
            on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}

        a = self.execute(first, worker=self.lost_editor, manager=self.manager)
        assert (a["status"], a["reason"]) == ("interrupted", "reconciliation_required"), a
        generation = self.ledger().snapshot(a["attempt_id"])["owner_generation"]
        abandon_delivery("sample", a["attempt_id"], actor="andy", explanation="the paid send was lost",
                         expected_generation=generation, root=self.root)
        self.building_predecessor = False

        def second(envelope, task, on_manager, on_action, **kwargs):
            on_manager(self.manager_message(envelope, 1))
            editor = self._proposal(envelope, "editor", 1)
            self.write_checkpoint(envelope, editor)
            on_action(editor)
            on_manager(self.manager_message(envelope, 2))
            verifier = self._proposal(envelope, "verifier", 2)
            self.write_checkpoint(envelope, verifier, previous=editor["checkpoint_id"])
            on_action(verifier)
            for sequence in (3, 4, 5, 6):
                on_manager(self.manager_message(envelope, sequence))
            return {"attempt_id": envelope["attempt_id"]}

        paused = self.execute(second, worker=self.worker, manager=self.manager)
        assert paused["status"] == "expansion_paused", paused
        denied = ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True).snapshot(
            paused["attempt_id"])["manager_calls"][-1]
        assert (denied["sequence"], denied["reason"]) == (6, "token_cap"), denied
        self.paused = paused
        self.decide(paused["attempt_id"], paused["request_id"], approve=True)

        def resumed(envelope, task, on_manager, on_action, **kwargs):
            self.resume = kwargs.get("resume")
            for sequence in (3, 4, 5, 6):  # after the verifier checkpoint: 3-5 replay from the ledger
                on_manager(self.manager_message(envelope, sequence))
            return {"attempt_id": envelope["attempt_id"]}

        b = self.recover(paused["attempt_id"], resumed, worker=self.worker, manager=self.manager)
        assert (b["mode"], b["status"]) == ("answer", "completed"), b
        self.attempts = (a["attempt_id"], b["attempt_id"])
        return self.attempts

    def read_ledger(self):
        return ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)
