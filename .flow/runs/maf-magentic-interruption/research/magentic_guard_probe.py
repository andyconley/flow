"""Guard actual Magentic participant calls and exercise interrupted local work."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

from agent_framework import (
    Agent,
    Executor,
    FileCheckpointStorage,
    Message,
    WorkflowContext,
    handler,
)
from agent_framework_ollama import OllamaChatClient
from agent_framework_orchestrations import (
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
    MagenticBuilder,
    MagenticManagerBase,
    MagenticProgressLedger,
    MagenticProgressLedgerItem,
)

from flow_gate import FlowGate


FLOW_ROOT = Path(__file__).resolve().parents[4]
DEFINITION = FLOW_ROOT / "scaffolds/default/agents/test-engineer.md"
FIXTURE = Path("/private/tmp/flow-maf-live-20260919")
CHARTER = "One local specialist; max six delegations, three concurrent, two replans; no paid calls, nested delegation, or repository edits."


class DeterministicMagenticManager(MagenticManagerBase):
    """Select the one participant so this proves MAF routing without model variance."""

    def __init__(self, participant_id: str) -> None:
        super().__init__(max_round_count=2, max_reset_count=1)
        self.participant_id = participant_id
        self.progress_calls = 0

    async def plan(self, magentic_context) -> Message:
        return Message(role="assistant", contents=["Ask the named specialist once; wait for Flow review before execution."])

    async def replan(self, magentic_context) -> Message:
        raise RuntimeError("replanning disabled for bounded spike")

    async def create_progress_ledger(self, magentic_context) -> MagenticProgressLedger:
        self.progress_calls += 1
        satisfied = self.progress_calls > 1
        item = MagenticProgressLedgerItem
        return MagenticProgressLedger(
            is_request_satisfied=item(reason="one bounded turn", answer=satisfied),
            is_in_loop=item(reason="one bounded turn", answer=False),
            is_progress_being_made=item(reason="one bounded turn", answer=True),
            next_speaker=item(reason="selected specialist", answer=self.participant_id),
            instruction_or_question=item(reason="bounded task", answer="Check the one-line fixture; answer briefly."),
        )

    async def prepare_final_answer(self, magentic_context) -> Message:
        if any("manual_reconciliation_required" in message.text for message in magentic_context.chat_history):
            return Message(role="assistant", contents=["manual_reconciliation_required: do not retry provider call"])
        return Message(role="assistant", contents=["Magentic turn ended after Flow-gated specialist response."])


class GuardedSpecialist(Executor):
    def __init__(self, *, instance_id: str, role: str, run_id: str, root: Path, crash_after_stream: bool) -> None:
        super().__init__(id=instance_id)
        self.role = role
        self.run_id = run_id
        self.root = root
        self.crash_after_stream = crash_after_stream
        self.gate = FlowGate(root / "flow-policy.sqlite")

    @handler
    async def on_broadcast(self, message: GroupChatParticipantMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
        # Context broadcast is not authority to dispatch a worker.
        return

    @handler
    async def on_request(self, request: GroupChatRequestMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
        # One specialist invocation is allowed in this bounded workflow. The ID
        # stays identical when MAF replays the same pre-dispatch checkpoint.
        request_id = f"{self.run_id}:{self.id}:delegation-1"
        decision = self.gate.decide({
            "request_id": request_id,
            "kind": "delegate",
            "role": self.role,
            "provider": "ollama",
            "hard_cap_usd": 0.0,
        })
        if not decision.allowed:
            status = self.gate.request_status(request_id)
            if status == "unknown":
                self.gate.require_reconciliation(request_id)
            response_text = "manual_reconciliation_required" if status == "unknown" else "flow_denied:" + decision.reason
            await self._respond(ctx, response_text)
            return
        if not self.gate.claim_dispatch(request_id):
            await self._respond(ctx, "manual_reconciliation_required")
            return
        if self.crash_after_stream:
            agent = Agent(
                client=OllamaChatClient(model="llama3.1:8b"),
                id="flow-test-engineer-interrupted-1",
                name="test-engineer",
                instructions=DEFINITION.read_text() + "\n" + CHARTER,
            )
            fixture_line = (FIXTURE / "README.md").read_text().strip()
            stream = agent.run(f"Review this fixture line: {fixture_line}. Write a detailed explanation of how you would verify it in a test.", stream=True)
            async for update in stream:
                chunk = update.text or ""
                if chunk:
                    marker = {"request_id": request_id, "first_stream_chunk_sha256": hashlib.sha256(chunk.encode()).hexdigest(), "first_stream_chunk_chars": len(chunk)}
                    (self.root / "stream-observed.json").write_text(json.dumps(marker, sort_keys=True))
                    self.gate.mark_unknown(request_id, "stream_observed_process_exit")
                    os._exit(77)  # Intentional crash after actual provider stream data.
            raise RuntimeError("local provider returned no streamed text")
        # The denied scenario never reaches this path; replay must also fail closed.
        raise RuntimeError("unexpected second provider dispatch")

    async def _respond(self, ctx: WorkflowContext[GroupChatResponseMessage], text: str) -> None:
        await ctx.send_message(GroupChatResponseMessage(message=Message(role="assistant", contents=[text], author_name=self.id)))


def guarded_magentic_workflow(root: Path, *, role: str, run_id: str, crash_after_stream: bool):
    # This is the only builder path in the spike. Callers supply a role, never a
    # raw MAF Agent/Executor; the factory installs the Flow gate for every participant.
    instance_id = "guarded-" + role + "-1"
    specialist = GuardedSpecialist(instance_id=instance_id, role=role, run_id=run_id, root=root, crash_after_stream=crash_after_stream)
    if not isinstance(specialist, GuardedSpecialist):
        raise TypeError("unguarded participant")
    manager = DeterministicMagenticManager(instance_id)
    storage = FileCheckpointStorage(root / "checkpoints")
    workflow = MagenticBuilder(participants=[specialist], manager=manager, enable_plan_review=True,
                               checkpoint_storage=storage,
                               name="flow-guarded-magentic").build()
    return workflow, storage


async def pending_checkpoint(storage: FileCheckpointStorage, workflow_name: str, request_id: str) -> str:
    checkpoints = await storage.list_checkpoints(workflow_name=workflow_name)
    matching = [cp for cp in checkpoints if request_id in cp.pending_request_info_events]
    if len(matching) != 1:
        raise RuntimeError(f"expected one plan-review checkpoint; found {len(matching)}")
    return matching[0].checkpoint_id


async def prepare(root: Path, *, role: str, run_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    work, storage = guarded_magentic_workflow(root, role=role, run_id=run_id, crash_after_stream=True)
    pending = await work.run("Ask the named specialist to check a one-line fixture; require plan review first.")
    requests = pending.get_request_info_events()
    assert len(requests) == 1
    checkpoint_id = await pending_checkpoint(storage, work.name, requests[0].request_id)
    handoff = {"role": role, "run_id": run_id, "plan_request_id": requests[0].request_id, "checkpoint_id": checkpoint_id,
               "definition_sha256": hashlib.sha256(DEFINITION.read_bytes()).hexdigest(), "charter_sha256": hashlib.sha256(CHARTER.encode()).hexdigest()}
    (root / "handoff.json").write_text(json.dumps(handoff, sort_keys=True))
    print(json.dumps({"mode": "prepare", "role": role, "plan_review_pending": True, "provider_dispatch_count": 0}))


async def continue_from_plan(root: Path, *, crash_after_stream: bool) -> None:
    handoff = json.loads((root / "handoff.json").read_text())
    work, _ = guarded_magentic_workflow(root, role=handoff["role"], run_id=handoff["run_id"], crash_after_stream=crash_after_stream)
    # The plan was already reviewed for this bounded test. Specialist dispatch
    # still requires a separate FlowGate decision in GuardedSpecialist.
    from agent_framework_orchestrations import MagenticPlanReviewResponse
    result = await work.run(checkpoint_id=handoff["checkpoint_id"], responses={handoff["plan_request_id"]: MagenticPlanReviewResponse.approve()})
    snapshot = FlowGate(root / "flow-policy.sqlite").snapshot()
    terminal_reconciliation_required = any("manual_reconciliation_required" in str(getattr(output, "text", output)) for output in result.get_outputs())
    if handoff["role"] == "test-engineer" and not crash_after_stream:
        assert terminal_reconciliation_required
    print(json.dumps({"mode": "continue", "role": handoff["role"], "run_id": handoff["run_id"], "checkpoint_id": handoff["checkpoint_id"],
                      "work_request_id": f"{handoff['run_id']}:guarded-{handoff['role']}-1:delegation-1",
                      "provider_dispatch_count": len(snapshot["dispatches"]),
                      "request_statuses": [row[5] for row in snapshot["requests"]], "terminal_outputs": len(result.get_outputs()),
                      "terminal_reconciliation_required": terminal_reconciliation_required,
                      "event_types": [event.type for event in result],
                      "final_state": str(result.get_final_state())[:80]}))


async def main() -> None:
    mode, root_arg = sys.argv[1:]
    root = Path(root_arg)
    if mode == "denied-prepare":
        await prepare(root, role="security-reviewer", run_id="denied-magentic")
    elif mode == "allowed-prepare":
        await prepare(root, role="test-engineer", run_id="interrupted-magentic")
    elif mode == "execute":
        await continue_from_plan(root, crash_after_stream=True)
    elif mode == "recover":
        gate = FlowGate(root / "flow-policy.sqlite")
        for request_id, _kind, _role, _provider, _cap, status, _reason in gate.snapshot()["requests"]:
            if status == "allowed" and any(row[0] == request_id and row[2] == "started" for row in gate.snapshot()["dispatches"]):
                gate.mark_unknown(request_id, "process_died_without_completion")
        await continue_from_plan(root, crash_after_stream=False)
    else:
        raise ValueError(mode)


if __name__ == "__main__":
    asyncio.run(main())
