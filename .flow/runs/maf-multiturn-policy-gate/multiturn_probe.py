"""Run-local Magentic control probe; deliberately uses no paid provider."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from agent_framework import Agent, Executor, FileCheckpointStorage, Message, WorkflowContext, handler
from agent_framework_orchestrations import (
    GroupChatParticipantMessage, GroupChatRequestMessage, GroupChatResponseMessage,
    MagenticBuilder, MagenticManagerBase, MagenticProgressLedger,
    MagenticProgressLedgerItem,
)
from flow_gate import FlowGate

CHARTER = "Local-only Flow policy probe; no paid workers or repository edits."
CHARTER_SHA = hashlib.sha256(CHARTER.encode()).hexdigest()

@dataclass(frozen=True)
class SpecialistSpec:
    role: str
    instance_id: str
    provider: str = "local-stub"

class GuardedSpecialist(Executor):
    def __init__(self, spec: SpecialistSpec, run_id: str, root: Path):
        super().__init__(id=spec.instance_id)
        self.spec, self.run_id, self.root = spec, run_id, root
        self.gate = FlowGate(root / "flow-policy.sqlite")

    @handler
    async def on_broadcast(self, message: GroupChatParticipantMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
        return

    @handler
    async def on_request(self, request: GroupChatRequestMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
        key = f"flow-sequence:{self.id}"
        sequence = int(ctx.get_state(key, 0)) + 1
        ctx.set_state(key, sequence)
        request_id = hashlib.sha256(f"{self.run_id}|{CHARTER_SHA}|{self.id}|{sequence}".encode()).hexdigest()
        decision = self.gate.decide({"request_id": request_id, "kind": "delegate", "role": self.spec.role,
                                     "provider": self.spec.provider, "hard_cap_usd": 0.0})
        if decision.allowed and self.gate.claim_dispatch(request_id):
            response = f"local deterministic specialist response {sequence}"
            self.gate.complete(request_id, response)
        else:
            # A replayed request must halt the workflow. A bounded response alone
            # lets a fresh manager continue and propose new work after the denial.
            if decision.reason == "duplicate_request":
                raise RuntimeError("flow_replay_requires_reconciliation:" + request_id)
            response = "flow_denied:" + decision.reason
        await ctx.send_message(GroupChatResponseMessage(message=Message(role="assistant", contents=[response], author_name=self.id)))

class TwoTurnManager(MagenticManagerBase):
    def __init__(self, participant_id: str):
        super().__init__(max_round_count=5, max_reset_count=1)
        self.participant_id = participant_id
        self.progress_calls = 0

    async def plan(self, context):
        return Message(role="assistant", contents=["Ask the specialist twice."])

    async def replan(self, context):
        raise RuntimeError("unexpected replan in two-turn case")

    async def create_progress_ledger(self, context):
        self.progress_calls += 1
        item = MagenticProgressLedgerItem
        return MagenticProgressLedger(
            is_request_satisfied=item(reason="two calls", answer=self.progress_calls > 2),
            is_in_loop=item(reason="two calls", answer=False),
            is_progress_being_made=item(reason="two calls", answer=True),
            next_speaker=item(reason="specialist", answer=self.participant_id),
            instruction_or_question=item(reason="bounded", answer="Return a one-line local response."),
        )

    async def prepare_final_answer(self, context):
        return Message(role="assistant", contents=["Two calls complete."])

class ReplanManager(TwoTurnManager):
    def __init__(self, participant_id: str, gate: FlowGate, run_id: str):
        super().__init__(participant_id)
        self.max_round_count = 10
        self.max_reset_count = 5
        self.max_stall_count = 0
        self.gate, self.run_id = gate, run_id
        self.replan_count = 0

    async def create_progress_ledger(self, context):
        item = MagenticProgressLedgerItem
        return MagenticProgressLedger(
            is_request_satisfied=item(reason="force stall", answer=False),
            is_in_loop=item(reason="force stall", answer=True),
            is_progress_being_made=item(reason="force stall", answer=False),
            next_speaker=item(reason="specialist", answer=self.participant_id),
            instruction_or_question=item(reason="force replan", answer="Do not dispatch."),
        )

    async def replan(self, context):
        self.replan_count += 1
        request_id = f"{self.run_id}:{CHARTER_SHA}:replan:{self.replan_count}"
        decision = self.gate.decide({"request_id": request_id, "kind": "replan", "role": "lead-developer",
                                     "provider": "local-stub", "hard_cap_usd": 0.0})
        if not decision.allowed:
            raise RuntimeError("flow_denied:" + decision.reason)
        self.gate.complete_replan(request_id)
        return Message(role="assistant", contents=[f"Flow-approved replan {self.replan_count}"])

def guarded_workflow(root: Path, run_id: str, specs: tuple[SpecialistSpec, ...], *, replan: bool = False):
    if not specs or any(type(spec) is not SpecialistSpec for spec in specs):
        raise TypeError("raw MAF participant injection is forbidden")
    if len({spec.instance_id for spec in specs}) != len(specs):
        raise ValueError("duplicate specialist instance")
    participants = [GuardedSpecialist(spec, run_id, root) for spec in specs]
    gate = FlowGate(root / "flow-policy.sqlite")
    manager = ReplanManager(participants[0].id, gate, run_id) if replan else TwoTurnManager(participants[0].id)
    storage = FileCheckpointStorage(root / "checkpoints", allowed_checkpoint_types=[
        "agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatRequestMessage",
        "agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatResponseMessage",
    ])
    workflow = MagenticBuilder(participants=participants, manager=manager, checkpoint_storage=storage,
                               name="flow-guarded-multiturn").build()
    return workflow, storage

async def main(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    spec = SpecialistSpec("test-engineer", "guarded-test-engineer-1")
    try:
        guarded_workflow(root, "multi", (Agent.__new__(Agent),))
    except TypeError:
        raw_rejected = True
    else:
        raw_rejected = False
    workflow, storage = guarded_workflow(root / "multi", "multi", (spec,))
    result = await workflow.run("Make two local specialist calls.")
    gate = FlowGate(root / "multi" / "flow-policy.sqlite")
    before = gate.snapshot()
    checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
    replay_candidates = [cp for cp in checkpoints if cp.iteration_count == 3 and cp.state.get(f"flow-sequence:{spec.instance_id}") == 1]
    assert len(replay_candidates) == 1
    replay_id = replay_candidates[0].checkpoint_id
    replay_workflow, _ = guarded_workflow(root / "multi", "multi", (spec,))
    try:
        replay_result = await replay_workflow.run(checkpoint_id=replay_id)
        replay_error = None
    except Exception as exc:
        replay_error = f"{type(exc).__name__}:{exc}"
    after = gate.snapshot()
    replan_workflow, _ = guarded_workflow(root / "replan", "replan", (spec,), replan=True)
    try:
        await replan_workflow.run("Exercise the Flow replan cap.")
        replan_error = None
    except Exception as exc:
        replan_error = f"{type(exc).__name__}:{exc}"
    replan_snapshot = FlowGate(root / "replan" / "flow-policy.sqlite").snapshot()
    assert raw_rejected
    assert len(before["requests"]) == len(before["dispatches"]) == 2
    assert before["requests"][0][0] != before["requests"][1][0]
    assert replay_error and "flow_replay_requires_reconciliation:" + before["requests"][1][0] in replay_error
    assert len(after["requests"]) == len(after["dispatches"]) == 2
    assert replan_error and "flow_denied:replan_cap" in replan_error
    assert [row[5] for row in replan_snapshot["requests"]] == ["completed", "completed", "denied"]
    assert replan_snapshot["dispatches"] == []
    report = {"raw_rejected": raw_rejected, "requests": before["requests"], "dispatches": before["dispatches"],
              "replay_checkpoint_id": replay_id, "replay_error": replay_error,
              "replay_request_count": len(after["requests"]), "replay_dispatch_count": len(after["dispatches"]),
              "replay_events": after["events"][len(before["events"]):],
              "replan_error": replan_error, "replan_requests": replan_snapshot["requests"],
              "replan_dispatches": replan_snapshot["dispatches"],
              "checkpoints": [{"id": cp.checkpoint_id, "iteration": cp.iteration_count,
                               "sequence": cp.state.get(f"flow-sequence:{spec.instance_id}"),
                               "messages": {k: [type(m.data).__name__ for m in v] for k, v in cp.messages.items()}}
                              for cp in checkpoints]}
    print(json.dumps(report, default=str))

if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
