"""MAF child process for Flow's first supervised local-worker slice.

Only this process imports Microsoft Agent Framework.  Its stdout is a strict
JSON-lines protocol; diagnostics are reported through an ``error`` record.
"""

import asyncio
import hashlib
import json
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 256 * 1024


def _write(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _read() -> dict[str, Any]:
    line = sys.stdin.buffer.readline(MAX_LINE_BYTES + 1)
    if not line or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
        raise RuntimeError("invalid or missing parent protocol line")
    value = json.loads(line)
    if not isinstance(value, dict) or value.get("protocol_version") != PROTOCOL_VERSION:
        raise RuntimeError("unsupported parent protocol message")
    return value


def _required(envelope: dict[str, Any], key: str) -> str:
    value = envelope.get(key)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"envelope missing {key}")
    return value


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


async def _run(envelope: dict[str, Any], resume: dict[str, Any] | None = None) -> None:
    # Imports are intentionally child-only so Flow's normal CLI has no MAF dep.
    from agent_framework import Executor, FileCheckpointStorage, Message, WorkflowContext, handler
    from agent_framework_orchestrations import (
        GroupChatParticipantMessage,
        GroupChatRequestMessage,
        GroupChatResponseMessage,
        MagenticBuilder,
        MagenticManagerBase,
        MagenticProgressLedger,
        MagenticProgressLedgerItem,
    )

    attempt_id = _required(envelope, "attempt_id")
    role = _required(envelope, "role")
    instance_id = _required(envelope, "instance_id")
    provider = _required(envelope, "provider")
    model = _required(envelope, "model")
    task_digest = _required(envelope, "task_digest")
    if role != "test-engineer" or provider not in {"ollama", "local-stub"}:
        raise RuntimeError("envelope requests a disallowed local specialist route")
    charter_digest = _required(envelope, "charter_digest")
    definition_digest = _required(envelope, "definition_digest")
    if envelope.get("schema_version") != PROTOCOL_VERSION:
        raise RuntimeError("unsupported Flow execution envelope schema")
    action_id = _digest({
        "attempt_id": attempt_id,
        "charter_digest": charter_digest,
        "definition_digest": definition_digest,
        "instance_id": instance_id,
        "kind": "delegate",
        "sequence": 1,
    })

    class OneCallManager(MagenticManagerBase):
        def __init__(self) -> None:
            super().__init__(max_round_count=2, max_reset_count=1)
            self.calls = 0

        async def plan(self, _context):
            return Message(role="assistant", contents=["Ask the guarded Flow specialist once."])

        async def replan(self, _context):
            raise RuntimeError("replanning is unavailable in the first supervised slice")

        async def create_progress_ledger(self, _context):
            self.calls += 1
            item = MagenticProgressLedgerItem
            done = self.calls > 1
            return MagenticProgressLedger(
                is_request_satisfied=item(reason="one guarded action", answer=done),
                is_in_loop=item(reason="one guarded action", answer=False),
                is_progress_being_made=item(reason="one guarded action", answer=True),
                next_speaker=item(reason="guarded Flow worker", answer=instance_id),
                instruction_or_question=item(reason="bounded task", answer="Return Flow's normalized result."),
            )

        async def prepare_final_answer(self, _context):
            return Message(role="assistant", contents=["Flow-authorized local worker completed."])

    class GuardedSpecialist(Executor):
        """A MAF participant with no agent object, provider client, or credentials."""

        def __init__(self) -> None:
            super().__init__(id=instance_id)

        @handler
        async def broadcast(self, message: GroupChatParticipantMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
            return

        @handler
        async def request(self, message: GroupChatRequestMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
            _write({
                "protocol_version": PROTOCOL_VERSION,
                "type": "propose_action",
                "schema_version": PROTOCOL_VERSION,
                "kind": "delegate",
                "attempt_id": attempt_id,
                "action_id": action_id,
                "role": role,
                "instance_id": instance_id,
                "provider": provider,
                "model": model,
                "task_digest": task_digest,
                "envelope_digest": _digest(envelope),
                "sequence": 1,
            })
            reply = _read()
            if reply.get("type") != "action_result" or reply.get("action_id") != action_id or not isinstance(reply.get("result"), dict):
                raise RuntimeError("parent returned invalid action_result")
            result = reply["result"]
            text = result.get("summary") or result.get("status") or "Flow returned an action result."
            if not isinstance(text, str):
                raise RuntimeError("action_result summary must be text")
            await ctx.send_message(GroupChatResponseMessage(message=Message(role="assistant", contents=[text], author_name=instance_id)))

    # There is no raw-participant parameter.  Construction begins with envelope
    # values and always installs the GuardedSpecialist above.
    checkpoint_dir = envelope.get("checkpoint_dir")
    checkpoint_storage = None
    if checkpoint_dir is not None:
        if not isinstance(checkpoint_dir, str) or not Path(checkpoint_dir).is_absolute():
            raise RuntimeError("checkpoint_dir must be an absolute Flow-owned path")
        checkpoint_storage = FileCheckpointStorage(Path(checkpoint_dir))
    workflow = MagenticBuilder(
        participants=[GuardedSpecialist()], manager=OneCallManager(), enable_plan_review=False,
        checkpoint_storage=checkpoint_storage, name="flow-supervised-local-worker"
    ).build()
    if resume is None:
        result = await workflow.run("Execute the one Flow-authorized bounded task.")
    else:
        if (resume.get("schema_version") != 2 or resume.get("attempt_id") != attempt_id
                or not isinstance(resume.get("checkpoint_id"), str)
                or resume.get("runtime_version") != version("agent-framework-core")):
            raise RuntimeError("invalid Flow resume identity")
        result = await workflow.run(checkpoint_id=resume["checkpoint_id"], checkpoint_storage=checkpoint_storage)
    outputs = result.get_outputs()
    summary = next((str(getattr(output, "text", output)) for output in reversed(outputs)), "MAF workflow completed")
    checkpoint_id = None
    if checkpoint_storage is not None:
        checkpoints = await checkpoint_storage.list_checkpoints(workflow_name=workflow.name)
        # The lineage root is the stable barrier before the guarded specialist
        # request. Restoring a later terminal checkpoint would never re-propose
        # the action, so Flow could not replay its committed result to MAF.
        roots = [item for item in checkpoints if item.previous_checkpoint_id is None]
        if len(roots) != 1:
            raise RuntimeError("MAF pre-action checkpoint barrier is absent or ambiguous")
        checkpoint_id = roots[0].checkpoint_id
    _write({"protocol_version": PROTOCOL_VERSION, "type": "workflow_finished", "attempt_id": attempt_id, "checkpoint_id": checkpoint_id, "runtime_version": version("agent-framework-core"), "summary": summary})


def main() -> int:
    try:
        start = _read()
        if start.get("type") not in {"start", "resume"} or not isinstance(start.get("envelope"), dict):
            raise RuntimeError("first parent message must be start or resume with an envelope")
        asyncio.run(_run(start["envelope"], start.get("resume") if start["type"] == "resume" else None))
        return 0
    except Exception as exc:
        _write({"protocol_version": PROTOCOL_VERSION, "type": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
