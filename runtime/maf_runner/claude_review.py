"""Two guarded MAF participants for Flow's Claude review execution protocol.

The child has no provider credentials or ledger access. It asks the parent for
both results and can only continue after Flow returns each normalized result.
"""

import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any, Never

from cli.execution_contracts import envelope_digest, expected_action_id
from runtime.maf_runner.multiturn import _checkpoint_id

PROTOCOL_VERSION = 4
MAX_LINE_BYTES = 256 * 1024


def _write(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _read() -> dict[str, Any]:
    line = sys.stdin.buffer.readline(MAX_LINE_BYTES + 1)
    if not line or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
        raise RuntimeError("invalid or missing parent protocol line")
    value = json.loads(line)
    if not isinstance(value, dict) or value.get("protocol_version") != PROTOCOL_VERSION:
        raise RuntimeError("unsupported mixed parent protocol message")
    return value


def _build_workflow():
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler, response_handler

    class LocalPlan(Executor):
        @handler
        async def start(self, message: str, ctx: WorkflowContext[str]) -> None:
            if message != "start":
                raise RuntimeError("unexpected mixed-job start")
            await ctx.request_info({"kind": "delegate", "sequence": 1}, dict, request_id="flow-mixed-action-1")

        @response_handler(request=dict, response=dict, output=str)
        async def accepted(self, request: dict[str, Any], response: dict[str, Any], ctx: WorkflowContext[str]) -> None:
            if request != {"kind": "delegate", "sequence": 1} or response.get("status") != "completed":
                raise RuntimeError("local specialist did not complete")
            summary = response.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                raise RuntimeError("local result lacks a summary")
            await ctx.send_message(summary)

    class ClaudeReview(Executor):
        @handler
        async def plan_received(self, message: str, ctx: WorkflowContext[Never, dict[str, str]]) -> None:
            if not isinstance(message, str) or not message.strip():
                raise RuntimeError("MAF did not receive the local test plan")
            await ctx.request_info({"kind": "delegate", "sequence": 2}, dict, request_id="flow-mixed-action-2")

        @response_handler(request=dict, response=dict, workflow_output=dict)
        async def accepted(self, request: dict[str, Any], response: dict[str, Any], ctx: WorkflowContext[Never, dict[str, str]]) -> None:
            if request != {"kind": "delegate", "sequence": 2} or response.get("status") != "completed":
                raise RuntimeError("Claude specialist did not complete")
            await ctx.yield_output({"reason": "mixed-job-complete"})

    local, claude = LocalPlan(id="flow-local-test-engineer"), ClaudeReview(id="flow-claude-quality-reviewer")
    return WorkflowBuilder(start_executor=local, name="flow-maf-claude-review-v4").add_chain([local, claude]).build()


def _proposal(envelope: dict[str, Any], sequence: int) -> dict[str, Any]:
    assignment = envelope["assignments"][sequence - 1]
    return {
        "schema_version": 1,
        "kind": "delegate",
        "sequence": sequence,
        "attempt_id": envelope["attempt_id"],
        "action_id": expected_action_id(envelope, sequence),
        "envelope_digest": envelope_digest(envelope),
        "assignment_id": assignment["assignment_id"],
        "definition_digest": assignment["definition_digest"],
        "role": assignment["role"],
        "instance_id": assignment["instance_id"],
        "provider": assignment["provider"],
        "model": assignment["model"],
        "task_digest": assignment["task_digest"],
    }


async def _run(start: dict[str, Any]) -> None:
    from agent_framework import FileCheckpointStorage

    envelope = start.get("envelope")
    if not isinstance(envelope, dict) or envelope.get("execution_protocol_version") != 4:
        raise RuntimeError("Claude review child requires a v4 Flow envelope")
    checkpoint_dir = envelope.get("checkpoint_dir")
    if not isinstance(checkpoint_dir, str) or not Path(checkpoint_dir).is_absolute():
        raise RuntimeError("mixed child requires an absolute checkpoint directory")
    storage = FileCheckpointStorage(Path(checkpoint_dir))
    workflow = _build_workflow()
    result = await workflow.run("start", checkpoint_storage=storage)
    resumed_from: str | None = None
    for sequence in (1, 2):
        requests = result.get_request_info_events()
        request_id = f"flow-mixed-action-{sequence}"
        if len(requests) != 1 or requests[0].request_id != request_id or requests[0].data != {"kind": "delegate", "sequence": sequence}:
            raise RuntimeError("MAF did not pause at the expected mixed action")
        checkpoint_id = await _checkpoint_id(storage, workflow.name, request_id, resumed_from=resumed_from)
        proposal = _proposal(envelope, sequence)
        _write({"protocol_version": PROTOCOL_VERSION, "type": "propose_action", "request_id": request_id,
                "checkpoint_id": checkpoint_id, "runtime_version": version("agent-framework-core"), **proposal})
        reply = _read()
        if (reply.get("type") != "action_result" or reply.get("action_id") != proposal["action_id"]
                or reply.get("request_id") != request_id or not isinstance(reply.get("result"), dict)):
            raise RuntimeError("parent returned an invalid mixed action result")
        result = await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage,
                                    responses={request_id: reply["result"]})
        resumed_from = checkpoint_id
    if result.get_request_info_events():
        raise RuntimeError("mixed workflow requested an extra action")
    outputs = result.get_outputs()
    if len(outputs) != 1 or outputs[0] != {"reason": "mixed-job-complete"}:
        raise RuntimeError("mixed workflow did not complete both guarded actions")
    _write({"protocol_version": PROTOCOL_VERSION, "type": "workflow_finished", "attempt_id": envelope["attempt_id"],
            "reason": "mixed-job-complete", "runtime_version": version("agent-framework-core")})


def main() -> int:
    try:
        start = _read()
        if start.get("type") != "start":
            raise RuntimeError("mixed child requires start")
        asyncio.run(_run(start))
        return 0
    except Exception as exc:
        _write({"protocol_version": PROTOCOL_VERSION, "type": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
