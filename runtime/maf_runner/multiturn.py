"""Bounded MAF v2 child for Flow-owned multi-turn authority.

The parent owns every policy decision and every provider send.  This child uses
MAF checkpoints only to preserve the ordered request-info workflow.  A denied
third replan is terminal; a later action three requires a separate child phase
and therefore a separate Flow authorization.
"""

import asyncio
import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any, Never


PROTOCOL_VERSION = 2
MAX_LINE_BYTES = 256 * 1024
RUNTIME_VERSION = "agent-framework-core"


def _write(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _read() -> dict[str, Any]:
    line = sys.stdin.buffer.readline(MAX_LINE_BYTES + 1)
    if not line or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
        raise RuntimeError("invalid or missing parent protocol line")
    value = json.loads(line)
    if not isinstance(value, dict) or value.get("protocol_version") != PROTOCOL_VERSION:
        raise RuntimeError("unsupported parent protocol message")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _required(envelope: dict[str, Any], key: str) -> str:
    value = envelope.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"envelope missing {key}")
    return value


def _proposal(envelope: dict[str, Any], kind: str, sequence: int) -> dict[str, Any]:
    attempt_id = _required(envelope, "attempt_id")
    envelope_digest = _digest(envelope)
    identity = {
        "attempt_id": attempt_id,
        "charter_digest": _required(envelope, "charter_digest"),
        "definition_digest": _required(envelope, "definition_digest"),
        "instance_id": _required(envelope, "instance_id"),
        "execution_protocol_version": 2,
        "kind": kind,
        "sequence": sequence,
    }
    proposal_id = _digest(identity)
    proposal = {
        "schema_version": 1,
        "attempt_id": attempt_id,
        "kind": kind,
        "sequence": sequence,
        "role": _required(envelope, "role"),
        "instance_id": _required(envelope, "instance_id"),
        "provider": _required(envelope, "provider"),
        "model": _required(envelope, "model"),
        "task_digest": _required(envelope, "task_digest"),
        "envelope_digest": envelope_digest,
        "proposal_id": proposal_id,
    }
    proposal["action_id" if kind == "delegate" else "replan_id"] = proposal_id
    if kind == "replan":
        proposal["proposal"] = {"reason": f"bounded replan {sequence}", "sequence": sequence}
    return proposal


def _result_allows(result: dict[str, Any]) -> bool:
    return result.get("status") not in {"denied", "reconciliation_required", "unknown", "failed"}


def _validate_resume(envelope: dict[str, Any], resume: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Bind a fresh-process response to the exact checkpointed proposal."""
    checkpoint_id, request_id = resume.get("checkpoint_id"), resume.get("request_id")
    result_type, result = resume.get("type"), resume.get("result")
    if not isinstance(checkpoint_id, str) or not isinstance(request_id, str) or not isinstance(result, dict):
        raise RuntimeError("invalid resume identity")
    if request_id.startswith("flow-action-"):
        kind, expected_type, id_field = "delegate", "action_result", "action_id"
    elif request_id.startswith("flow-replan-"):
        kind, expected_type, id_field = "replan", "replan_result", "replan_id"
    else:
        raise RuntimeError("resume request ID is not a bounded Flow proposal")
    try:
        sequence = int(request_id.rsplit("-", 1)[1])
    except ValueError as exc:
        raise RuntimeError("resume request ID has no valid sequence") from exc
    expected = _proposal(envelope, kind, sequence)
    if result_type != expected_type or resume.get(id_field) != expected[id_field]:
        raise RuntimeError("resume response is not bound to the checkpointed proposal")
    return checkpoint_id, request_id, result


def _build_initial():
    """Build action1 -> replan1 -> action2 -> replan2 -> replan3(stop)."""
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler, response_handler

    class ActionOne(Executor):
        @handler
        async def start(self, message: str, ctx: WorkflowContext[str]) -> None:
            if message != "start":
                raise RuntimeError("unexpected initial message")
            await ctx.request_info({"kind": "delegate", "sequence": 1}, dict, request_id="flow-action-1")

        @response_handler(request=dict, response=dict, output=str)
        async def accepted(self, request: dict[str, Any], response: dict[str, Any], ctx: WorkflowContext[str]) -> None:
            if request != {"kind": "delegate", "sequence": 1} or not _result_allows(response):
                raise RuntimeError("action-1 was not accepted")
            await ctx.send_message("action-1")

    class ReplanOne(Executor):
        @handler
        async def request(self, message: str, ctx: WorkflowContext[str]) -> None:
            if message != "action-1":
                raise RuntimeError("unexpected action-1 handoff")
            await ctx.request_info({"kind": "replan", "sequence": 1}, dict, request_id="flow-replan-1")

        @response_handler(request=dict, response=dict, output=str)
        async def accepted(self, request: dict[str, Any], response: dict[str, Any], ctx: WorkflowContext[str]) -> None:
            if request != {"kind": "replan", "sequence": 1} or not _result_allows(response):
                raise RuntimeError("replan-1 was not accepted")
            await ctx.send_message("replan-1")

    class ActionTwo(Executor):
        @handler
        async def request(self, message: str, ctx: WorkflowContext[str]) -> None:
            if message != "replan-1":
                raise RuntimeError("unexpected replan-1 handoff")
            await ctx.request_info({"kind": "delegate", "sequence": 2}, dict, request_id="flow-action-2")

        @response_handler(request=dict, response=dict, output=str)
        async def accepted(self, request: dict[str, Any], response: dict[str, Any], ctx: WorkflowContext[str]) -> None:
            if request != {"kind": "delegate", "sequence": 2} or not _result_allows(response):
                raise RuntimeError("action-2 was not accepted")
            await ctx.send_message("action-2")

    class ReplanTwo(Executor):
        @handler
        async def request(self, message: str, ctx: WorkflowContext[str]) -> None:
            if message != "action-2":
                raise RuntimeError("unexpected action-2 handoff")
            await ctx.request_info({"kind": "replan", "sequence": 2}, dict, request_id="flow-replan-2")

        @response_handler(request=dict, response=dict, output=str)
        async def accepted(self, request: dict[str, Any], response: dict[str, Any], ctx: WorkflowContext[str]) -> None:
            if request != {"kind": "replan", "sequence": 2} or not _result_allows(response):
                raise RuntimeError("replan-2 was not accepted")
            await ctx.send_message("replan-2")

    class ReplanThree(Executor):
        @handler
        async def request(self, message: str, ctx: WorkflowContext[Never, dict[str, str]]) -> None:
            if message != "replan-2":
                raise RuntimeError("unexpected replan-2 handoff")
            await ctx.request_info({"kind": "replan", "sequence": 3}, dict, request_id="flow-replan-3")

        @response_handler(request=dict, response=dict, workflow_output=dict)
        async def denied(self, request: dict[str, Any], response: dict[str, Any], ctx: WorkflowContext[Never, dict[str, str]]) -> None:
            if request != {"kind": "replan", "sequence": 3} or response.get("status") not in {"denied", "denied_replan_cap"}:
                raise RuntimeError("replan-3 must be denied by Flow")
            await ctx.yield_output({"reason": "denied_replan_cap"})

    one, r1, two, r2, r3 = (ActionOne(id="flow-action-one"), ReplanOne(id="flow-replan-one"),
                             ActionTwo(id="flow-action-two"), ReplanTwo(id="flow-replan-two"),
                             ReplanThree(id="flow-replan-three"))
    return (WorkflowBuilder(start_executor=one, name="flow-maf-v2-initial")
            .add_chain([one, r1, two, r2, r3]).build())


def _build_action_three():
    from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler, response_handler

    class ActionThree(Executor):
        @handler
        async def start(self, message: str, ctx: WorkflowContext[Never, dict[str, str]]) -> None:
            if message != "start":
                raise RuntimeError("unexpected action-3 start")
            await ctx.request_info({"kind": "delegate", "sequence": 3}, dict, request_id="flow-action-3")

        @response_handler(request=dict, response=dict, workflow_output=dict)
        async def accepted(self, request: dict[str, Any], response: dict[str, Any], ctx: WorkflowContext[Never, dict[str, str]]) -> None:
            if request != {"kind": "delegate", "sequence": 3} or not _result_allows(response):
                raise RuntimeError("action-3 was not accepted")
            await ctx.yield_output({"reason": "action-3-complete"})

    action = ActionThree(id="flow-action-three")
    return WorkflowBuilder(start_executor=action, name="flow-maf-v2-action3").build()


async def _checkpoint_id(
    storage: Any, workflow_name: str, request_id: str, *, resumed_from: str | None = None
) -> str:
    """Find this run's pending checkpoint without borrowing an older branch.

    A crash after a parent has committed a result but before it records the
    next child checkpoint can cause a second restoration from the same barrier.
    MAF retains both branches.  Choose the newest leaf descended from the
    barrier used by this child and fail closed when lineage cannot distinguish
    candidates.
    """
    checkpoints = await storage.list_checkpoints(workflow_name=workflow_name)
    pending = [item for item in checkpoints if request_id in item.pending_request_info_events]
    if resumed_from is None:
        if len(pending) != 1:
            raise RuntimeError(f"expected one pending checkpoint for {request_id}; found {len(pending)}")
        return pending[0].checkpoint_id
    by_id = {item.checkpoint_id: item for item in checkpoints}
    if resumed_from not in by_id:
        raise RuntimeError("resumed checkpoint is absent from checkpoint storage")
    parents = {item.previous_checkpoint_id for item in checkpoints if item.previous_checkpoint_id is not None}

    def descends_from(item: Any) -> bool:
        seen: set[str] = set()
        current = item
        while current.previous_checkpoint_id is not None:
            previous = current.previous_checkpoint_id
            if previous == resumed_from:
                return True
            if previous in seen or previous not in by_id:
                raise RuntimeError("checkpoint lineage is cyclic or incomplete")
            seen.add(previous)
            current = by_id[previous]
        return False

    leaves = [item for item in pending if item.checkpoint_id not in parents and descends_from(item)]
    if not leaves:
        raise RuntimeError(f"no leaf pending checkpoint for {request_id} descends from the resumed barrier")
    newest_timestamp = max(item.timestamp for item in leaves)
    newest = [item for item in leaves if item.timestamp == newest_timestamp]
    if len(newest) != 1:
        raise RuntimeError(f"ambiguous newest leaf pending checkpoint for {request_id}")
    return newest[0].checkpoint_id


async def _run(start: dict[str, Any]) -> None:
    from agent_framework import FileCheckpointStorage

    envelope = start.get("envelope")
    if not isinstance(envelope, dict):
        raise RuntimeError("start requires an envelope")
    phase = start.get("phase")
    if phase not in {"initial", "action3"}:
        raise RuntimeError("start requires phase initial or action3")
    checkpoint_dir = start.get("checkpoint_dir")
    if not isinstance(checkpoint_dir, str) or not Path(checkpoint_dir).is_absolute():
        raise RuntimeError("start requires an absolute Flow-owned checkpoint_dir")
    storage = FileCheckpointStorage(Path(checkpoint_dir))
    work = _build_initial() if phase == "initial" else _build_action_three()
    resume = start.get("resume")
    resumed_from: str | None = None
    if resume is None:
        result = await work.run("start", checkpoint_storage=storage)
    else:
        if not isinstance(resume, dict):
            raise RuntimeError("invalid resume identity")
        checkpoint_id, request_id, result_value = _validate_resume(envelope, resume)
        resumed_from = checkpoint_id
        result = await work.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage,
                                responses={request_id: result_value})
    while True:
        requests = result.get_request_info_events()
        if not requests:
            outputs = result.get_outputs()
            _write({"protocol_version": PROTOCOL_VERSION, "type": "workflow_finished", "attempt_id": _required(envelope, "attempt_id"),
                    "phase": phase, "reason": outputs[-1].get("reason") if outputs and isinstance(outputs[-1], dict) else "completed",
                    "runtime_version": version(RUNTIME_VERSION)})
            return
        if len(requests) != 1 or not isinstance(requests[0].data, dict):
            raise RuntimeError("workflow produced an invalid number of pending requests")
        request = requests[0]
        kind, sequence = request.data.get("kind"), request.data.get("sequence")
        if kind not in {"delegate", "replan"} or not isinstance(sequence, int):
            raise RuntimeError("workflow produced an invalid pending request")
        checkpoint_id = await _checkpoint_id(storage, work.name, request.request_id, resumed_from=resumed_from)
        proposal = _proposal(envelope, kind, sequence)
        result_type = "action_result" if kind == "delegate" else "replan_result"
        id_field = "action_id" if kind == "delegate" else "replan_id"
        proposal.update({"protocol_version": PROTOCOL_VERSION, "type": "propose_action" if kind == "delegate" else "propose_replan",
                         "request_id": request.request_id, "checkpoint_id": checkpoint_id,
                         "runtime_version": version(RUNTIME_VERSION), "phase": phase})
        _write(proposal)
        reply = _read()
        if reply.get("type") != result_type or reply.get(id_field) != proposal[id_field] or not isinstance(reply.get("result"), dict):
            raise RuntimeError("parent returned an invalid result for the pending Flow proposal")
        result = await work.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage,
                                responses={request.request_id: reply["result"]})
        resumed_from = checkpoint_id


def main() -> int:
    try:
        start = _read()
        if start.get("type") != "start":
            raise RuntimeError("first parent message must be start")
        asyncio.run(_run(start))
        return 0
    except Exception as exc:
        _write({"protocol_version": PROTOCOL_VERSION, "type": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
