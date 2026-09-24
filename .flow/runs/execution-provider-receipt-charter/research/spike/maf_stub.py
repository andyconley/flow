"""Exercise one deterministic MAF request/checkpoint path with no model."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import tempfile
from pathlib import Path
from typing import Never

from agent_framework import (
    Executor,
    FileCheckpointStorage,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)


CHARTER = {"allowed_actions": ("read_report",), "revision": "spike-revision"}


def flow_policy(action: str, charter: dict[str, object]) -> str:
    """Simulated Flow-owned authority check; MAF receives only its result."""
    return "allowed" if action in charter["allowed_actions"] else "denied"


class StubExecutor(Executor):
    @handler
    async def start(self, message: str, ctx: WorkflowContext[str]) -> None:
        assert message == "start"
        await ctx.request_info("approve_out_of_envelope_action", str)

    @response_handler
    async def finish(
        self,
        original_request: str,
        response: str,
        ctx: WorkflowContext[Never, str],
    ) -> None:
        await ctx.yield_output({"request": original_request, "policy_decision": response})


def build_workflow(storage: FileCheckpointStorage):
    return WorkflowBuilder(
        start_executor=StubExecutor(id="stub"),
        checkpoint_storage=storage,
        name="flow-reuse-spike",
    ).build()


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="flow-maf-spike-") as directory:
        storage = FileCheckpointStorage(Path(directory))
        first = build_workflow(storage)
        pending = await first.run("start")
        requests = pending.get_request_info_events()
        assert len(requests) == 1
        checkpoints = await storage.list_checkpoints(workflow_name=first.name)
        assert checkpoints
        pending_checkpoints = [
            checkpoint
            for checkpoint in checkpoints
            if checkpoint.pending_request_info_events
        ]
        assert len(pending_checkpoints) == 1
        checkpoint_id = pending_checkpoints[0].checkpoint_id

        policy_decision = flow_policy("write_source", CHARTER)
        assert policy_decision == "denied"
        resumed = build_workflow(storage)
        finished = await resumed.run(
            checkpoint_id=checkpoint_id,
            responses={requests[0].request_id: policy_decision},
        )
        outputs = finished.get_outputs()
        assert outputs == [
            {
                "request": "approve_out_of_envelope_action",
                "policy_decision": "denied",
            }
        ]
        assert not finished.get_request_info_events()
        print(
            json.dumps(
                {
                    "maf_version": importlib.metadata.version("agent-framework-core"),
                    "model_calls": 0,
                    "codex_client_constructed": False,
                    "states": [
                        "started",
                        "pending_request",
                        "checkpointed",
                        "resumed_new_workflow_instance",
                        "terminal_output",
                    ],
                    "pending_request_count": len(requests),
                    "checkpoint_count": len(checkpoints),
                    "checkpoint_restored": True,
                    "flow_policy_decision": policy_decision,
                    "outputs": outputs,
                    "checkpoint_storage": "temporary_file_store",
                    "process_restart_tested": False,
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
