"""Model-free, two-process MAF checkpoint/restart probe."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Never

from agent_framework import Executor, FileCheckpointStorage, WorkflowBuilder, WorkflowContext, handler, response_handler


class ApprovalGate(Executor):
    @handler
    async def start(self, message: str, ctx: WorkflowContext[str]) -> None:
        assert message == "start"
        await ctx.request_info("delegate_outside_charter", str)

    @response_handler
    async def finish(self, request: str, response: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output({"request": request, "decision": response})


async def main() -> None:
    mode, directory = sys.argv[1:]
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    storage = FileCheckpointStorage(root / "checkpoints")
    workflow = WorkflowBuilder(start_executor=ApprovalGate(id="approval-gate"), checkpoint_storage=storage, name="flow-maf-restart").build()
    if mode == "start":
        result = await workflow.run("start")
        requests = result.get_request_info_events()
        checkpoints = await storage.list_checkpoints(workflow_name=workflow.name)
        pending = [checkpoint for checkpoint in checkpoints if checkpoint.pending_request_info_events]
        assert len(requests) == len(pending) == 1
        (root / "handoff.json").write_text(json.dumps({"request_id": requests[0].request_id, "checkpoint_id": pending[0].checkpoint_id}))
        print(json.dumps({"mode": mode, "pending": 1, "checkpointed": 1}))
    elif mode == "resume":
        handoff = json.loads((root / "handoff.json").read_text())
        result = await workflow.run(checkpoint_id=handoff["checkpoint_id"], responses={handoff["request_id"]: "denied_by_flow"})
        assert result.get_outputs() == [{"request": "delegate_outside_charter", "decision": "denied_by_flow"}]
        assert not result.get_request_info_events()
        print(json.dumps({"mode": mode, "resumed": 1, "decision": "denied_by_flow", "outputs": len(result.get_outputs())}))
    else:
        raise ValueError(mode)


if __name__ == "__main__":
    asyncio.run(main())
