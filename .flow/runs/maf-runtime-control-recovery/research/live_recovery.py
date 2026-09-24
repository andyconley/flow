"""Flow-gated MAF request, live local worker, and two-process recovery."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Never

from agent_framework import Agent, Executor, FileCheckpointStorage, WorkflowBuilder, WorkflowContext, handler, response_handler
from agent_framework_ollama import OllamaChatClient

from flow_gate import FlowGate, request_json


FLOW_ROOT = Path(__file__).resolve().parents[4]
DEFINITION = FLOW_ROOT / "scaffolds/default/agents/test-engineer.md"
FIXTURE = Path("/private/tmp/flow-maf-live-20260919")
CHARTER = "Read-only Flow recovery spike. One local test-engineer worker, no nested delegation, no repository edits, no paid provider."


class DelegationGate(Executor):
    @handler
    async def start(self, scenario: str, ctx: WorkflowContext[Never, str]) -> None:
        role = "security-reviewer" if scenario == "denied" else "test-engineer"
        await ctx.request_info(request_json(f"{scenario}-request-1", role=role), str)

    @response_handler
    async def after_decision(self, original_request: str, response: str, ctx: WorkflowContext[str, dict]) -> None:
        request = json.loads(original_request)
        if response != "allowed":
            await ctx.yield_output({"request_id": request["request_id"], "decision": response, "worker_dispatched": False})
            return
        await ctx.send_message(original_request)


class LocalWorker(Executor):
    def __init__(self, gate: FlowGate) -> None:
        super().__init__(id="local-worker")
        self.gate = gate

    @handler
    async def work(self, order_json: str, ctx: WorkflowContext[dict]) -> None:
        order = json.loads(order_json)
        request_id = order["request_id"]
        if not self.gate.claim_dispatch(request_id):
            raise RuntimeError("Flow denied or already recorded dispatch")
        fixture_line = (FIXTURE / "README.md").read_text().strip()
        agent = Agent(
            client=OllamaChatClient(model="llama3.1:8b"),
            id="flow-test-engineer-live-1",
            name="test-engineer",
            instructions=DEFINITION.read_text() + "\n" + CHARTER,
        )
        result = await asyncio.wait_for(agent.run(f"Check this fixture line: {fixture_line} Reply with one brief sentence confirming it is a one-line fixture."), timeout=90)
        if not result.text.strip():
            raise RuntimeError("local worker returned empty text")
        digest = self.gate.complete(request_id, result.text)
        await ctx.send_message({"request_id": request_id, "reported_result_sha256": digest})


class FinalReview(Executor):
    @handler
    async def after_worker(self, worker_result: dict, ctx: WorkflowContext[Never, dict]) -> None:
        await ctx.request_info("finalize:" + worker_result["request_id"] + ":" + worker_result["reported_result_sha256"], str)

    @response_handler
    async def finish(self, original_request: str, response: str, ctx: WorkflowContext[Never, dict]) -> None:
        _, request_id, digest = original_request.split(":", 2)
        await ctx.yield_output({"request_id": request_id, "reported_result_sha256": digest, "final_review": response})


def workflow(root: Path, gate: FlowGate):
    first = DelegationGate(id="delegation-gate")
    worker = LocalWorker(gate)
    final = FinalReview(id="final-review")
    storage = FileCheckpointStorage(root / "checkpoints")
    built = (WorkflowBuilder(start_executor=first, checkpoint_storage=storage, name="flow-live-recovery")
             .add_edge(first, worker).add_edge(worker, final).build())
    return built, storage


async def checkpoint_for(storage: FileCheckpointStorage, name: str, request_id: str) -> str:
    checkpoints = await storage.list_checkpoints(workflow_name=name)
    matching = [cp for cp in checkpoints if request_id in cp.pending_request_info_events]
    if len(matching) != 1:
        raise RuntimeError(f"expected one checkpoint for request {request_id}; found {len(matching)}")
    return matching[0].checkpoint_id


async def start(root: Path, scenario: str) -> None:
    gate = FlowGate(root / "flow-policy.sqlite")
    work, storage = workflow(root, gate)
    pending = await work.run(scenario)
    requests = pending.get_request_info_events()
    assert len(requests) == 1
    decision = gate.decide(json.loads(requests[0].data))
    first_checkpoint = await checkpoint_for(storage, work.name, requests[0].request_id)
    resumed_work, _ = workflow(root, gate)
    after_policy = await resumed_work.run(checkpoint_id=first_checkpoint, responses={requests[0].request_id: "allowed" if decision.allowed else decision.reason})
    if scenario == "denied":
        assert not decision.allowed
        assert after_policy.get_outputs() == [{"request_id": "denied-request-1", "decision": "specialist_denied", "worker_dispatched": False}]
        assert len(gate.snapshot()["dispatches"]) == 0
        print(json.dumps({"scenario": scenario, "policy": decision.reason, "provider_dispatch_count": 0}))
        return
    assert decision.allowed
    final_requests = after_policy.get_request_info_events()
    assert len(final_requests) == 1
    final_checkpoint = await checkpoint_for(storage, work.name, final_requests[0].request_id)
    snapshot = gate.snapshot()
    assert len(snapshot["dispatches"]) == 1 and snapshot["dispatches"][0][2] == "completed"
    handoff = {"checkpoint_id": final_checkpoint, "final_request_id": final_requests[0].request_id, "work_request_id": decision.request_id,
               "charter_sha256": hashlib.sha256(CHARTER.encode()).hexdigest(), "definition_sha256": hashlib.sha256(DEFINITION.read_bytes()).hexdigest()}
    (root / "handoff.json").write_text(json.dumps(handoff, sort_keys=True))
    print(json.dumps({"scenario": scenario, "policy": decision.reason, "provider_dispatch_count": 1, "checkpoint_written": True,
                      "reported_result_sha256": snapshot["dispatches"][0][1]}))


async def resume(root: Path) -> None:
    gate = FlowGate(root / "flow-policy.sqlite")
    handoff = json.loads((root / "handoff.json").read_text())
    before = len(gate.snapshot()["dispatches"])
    work, _ = workflow(root, gate)
    result = await work.run(checkpoint_id=handoff["checkpoint_id"], responses={handoff["final_request_id"]: "approved_by_flow"})
    outputs = result.get_outputs()
    assert len(outputs) == 1 and outputs[0]["final_review"] == "approved_by_flow"
    assert len(gate.snapshot()["dispatches"]) == before == 1
    replay = gate.decide(json.loads(request_json(handoff["work_request_id"])))
    assert not replay.allowed and replay.reason == "duplicate_request"
    assert not gate.claim_dispatch(handoff["work_request_id"])
    assert len(gate.snapshot()["dispatches"]) == 1
    print(json.dumps({"scenario": "resume", "terminal_output": True, "provider_dispatch_count_before": before,
                      "provider_dispatch_count_after": len(gate.snapshot()["dispatches"]), "replay_decision": replay.reason,
                      "reported_result_sha256": outputs[0]["reported_result_sha256"]}))


async def main() -> None:
    mode, root_arg = sys.argv[1:]
    root = Path(root_arg)
    root.mkdir(parents=True, exist_ok=True)
    if mode in {"denied", "allowed"}:
        await start(root, mode)
    elif mode == "resume":
        await resume(root)
    else:
        raise ValueError(mode)


if __name__ == "__main__":
    asyncio.run(main())
