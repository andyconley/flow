"""Credentialless stock Magentic Delivery Lead supervised by Flow.

The child runs MAF's StandardMagenticManager. All manager model requests and
selected participant requests cross the JSON-line boundary to Flow; this
process has neither provider credentials nor permission to dispatch work.
"""

import asyncio
import hashlib
import json
import os
import platform
import sys
import sysconfig
from importlib.metadata import version
from pathlib import Path
from typing import Any

from cli.delivery_selection import compute_binding

from runtime.maf_runner.limits import (MAX_ACTIONS, MAX_MANAGER_CALLS, MAX_MANAGER_MESSAGES_BYTES,
                                       MAX_MANAGER_ROUNDS, MAX_REPLANS, resolve_local_agent_budget)
from runtime.maf_runner.progress_parse import UNPARSABLE_SENTINEL, parse_progress

PROTOCOL_VERSION = 8
# Package compatibility identity retained for transactional updates from v8.
# The v9 route now constructs and executes the same pinned stock MAF surface.
SUPPORTED_PROTOCOLS = [5, 6, 7, 8]
_active_protocol_version: int | None = None
_active_local_profile = False
MAX_LINE_BYTES = 4 * 1024 * 1024
MAX_TASK_BYTES = 4096
# One progress step gets its first reply plus two retries (ADR 0018).
PROGRESS_ATTEMPTS = 3


class PolicyAbort(BaseException):
    """Escape MAF's recoverable progress-ledger Exception handler on denial."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def _runtime_identity() -> dict[str, Any]:
    """Compute, rather than echo, the interpreter identity Flow sealed."""
    root = Path(__file__).resolve().parents[2]
    lock = root / "runtime" / "maf_runner" / "requirements.lock"
    names = tuple(line.split("==", 1)[0] for line in lock.read_text().splitlines()
                  if line.strip() and not line.startswith("#"))
    packages = {name: version(name) for name in names}
    records = {}
    for name in names:
        import importlib.metadata as metadata
        distribution = metadata.distribution(name)
        record = distribution.locate_file(distribution._path.name + "/RECORD")
        records[name] = {"record": hashlib.sha256(record.read_bytes()).hexdigest(), "bad": []}
    protocols = SUPPORTED_PROTOCOLS
    identity = {"schema_version": 2, "interpreter": str(Path(sys.executable).resolve()),
                "python": list(sys.version_info[:3]), "packages": packages,
                "platform": sys.platform, "lock_digest": hashlib.sha256(lock.read_bytes()).hexdigest(),
                "runner_digest": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "protocols": protocols,
                "protocol_digest": _digest(protocols), "machine": platform.machine(),
                "implementation": platform.python_implementation(), "soabi": sysconfig.get_config_var("SOABI")}
    identity["record_digest"] = _digest(records)
    identity["runtime_digest"] = _digest(identity)
    return identity


def _write(value: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _read() -> dict[str, Any]:
    global _active_protocol_version, _active_local_profile
    line = sys.stdin.buffer.readline(MAX_LINE_BYTES + 1)
    if not line or len(line) > MAX_LINE_BYTES or not line.endswith(b"\n"):
        raise RuntimeError("invalid or missing parent protocol line")
    value = json.loads(line)
    if isinstance(value, dict) and value.get('type') == 'start':
        _active_local_profile = 'local_agent_profile' in value.get('envelope', {})
    if not _active_local_profile and len(line) > 1024 * 1024:
        raise RuntimeError('legacy parent protocol line exceeds size limit')
    if not isinstance(value, dict) or value.get("protocol_version") not in {5, 6, 7, 8, 9}:
        raise RuntimeError("unsupported parent protocol message")
    if _active_protocol_version is None:
        _active_protocol_version = value["protocol_version"]
    elif value["protocol_version"] != _active_protocol_version:
        raise RuntimeError("parent changed protocol version")
    return value


def _phase(prompt: str) -> str:
    """Classify stock manager prompts without replacing its decision methods."""
    if "pre-survey" in prompt and "GIVEN OR VERIFIED FACTS" in prompt:
        return "facts"
    if "we have assembled the following team" in prompt and "short bullet-point plan" in prompt:
        return "plan"
    if "Please rewrite the following fact sheet" in prompt:
        return "replan_facts"
    if "what went wrong on this last run" in prompt:
        return "replan_plan"
    if "pure JSON format" in prompt and "next_speaker" in prompt:
        return "progress"
    if "provide the final answer" in prompt:
        return "final"
    raise RuntimeError("unrecognized stock manager phase")


def _validate_progress(value: dict[str, Any], roster: set[str]) -> None:
    """Reject invalid speakers before MAF can fall back to the first worker."""
    selected = value["next_speaker"].get("answer")
    complete = value["is_request_satisfied"].get("answer")
    if not isinstance(selected, str) or selected not in roster:
        raise PolicyAbort("manager selected an unlisted specialist")
    if not isinstance(complete, bool):
        raise PolicyAbort("manager progress lacks completion decision")


def _maf_reads_canonical(canonical: str, value: dict[str, Any]) -> bool:
    """MAF must parse Flow's canonical text back to the object Flow validated."""
    from agent_framework_orchestrations._magentic import _extract_json
    try:
        return _extract_json(canonical) == value
    except Exception:
        return False


async def _run(start: dict[str, Any]) -> None:
    envelope = start.get("envelope")
    protocol_version = _active_protocol_version
    if not isinstance(envelope, dict) or envelope.get("execution_protocol_version") != protocol_version:
        raise RuntimeError("Delivery Lead envelope and transport protocol differ")
    if protocol_version == 9:
        await _run_v9(start)
        return
    # Prove that the real runner surface imports before asserting readiness.
    # The parent still receives no manager/action callback until it validates
    # the computed identity below.
    from agent_framework import AgentResponse, Executor, FileCheckpointStorage, Message, WorkflowContext, handler, response_handler
    from agent_framework_orchestrations import (
        GroupChatParticipantMessage, GroupChatRequestMessage, GroupChatResponseMessage,
        MagenticBuilder, StandardMagenticManager,
    )
    runtime = envelope.get("maf_runtime")
    if runtime is not None:
        if not isinstance(runtime, dict) or not isinstance(runtime.get("runtime_digest"), str):
            raise RuntimeError("Delivery Lead runtime identity is invalid")
        # This is intentionally before the first manager callback. The parent
        # compares it to its sealed envelope before permitting any provider
        # route, so a swapped interpreter cannot silently become a send.
        computed_runtime = _runtime_identity()
        _write({"protocol_version": protocol_version, "type": "runtime_ready", "runtime": computed_runtime})
    attempt_id = envelope.get("attempt_id")
    task = start.get("task")
    assignments = envelope.get("roster")
    checkpoint_dir = envelope.get("checkpoint_dir")
    if not isinstance(attempt_id, str) or not attempt_id or not isinstance(task, str) or not task.strip():
        raise RuntimeError("missing delivery attempt or task")
    if not isinstance(assignments, list) or not assignments or not isinstance(checkpoint_dir, str) or not Path(checkpoint_dir).is_absolute():
        raise RuntimeError("invalid roster or checkpoint directory")
    roster: dict[str, dict[str, Any]] = {}
    for assignment in assignments:
        if not isinstance(assignment, dict) or not isinstance(assignment.get("instance_id"), str):
            raise RuntimeError("invalid specialist assignment")
        instance = assignment["instance_id"]
        if not instance or instance in roster:
            raise RuntimeError("duplicate specialist instance")
        roster[instance] = assignment
    envelope_hash = _digest(envelope)
    storage = FileCheckpointStorage(Path(checkpoint_dir), allowed_checkpoint_types=[
        "agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatRequestMessage",
        "agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatParticipantMessage",
        "agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatResponseMessage",
        "agent_framework_orchestrations._magentic:MagenticContext",
        "agent_framework_orchestrations._magentic:MagenticProgressLedger",
        "agent_framework_orchestrations._magentic:MagenticProgressLedgerItem",
    ])
    # A credential-free construction milestone.  Flow will not permit a
    # manager/action callback until this proves the runner's storage surface
    # is usable under the sealed interpreter.
    _write({"protocol_version": protocol_version, "type": "runtime_initialized"})
    workflow_name = f"flow-magentic-delivery-v{protocol_version}"
    manager_call = 0
    manager_round = 1
    replan_sequence = 0
    action_number = 0
    previous_action_id: str | None = None
    selected_task = ""
    selected_reason = ""
    # Consecutive unparsable progress replies in the current progress step.
    unparsable_streak = 0
    job = envelope.get("job_contract") if protocol_version in {7, 8} else None

    def provider_choice(assignment: dict[str, Any]) -> dict[str, Any]:
        """Record MAF's selection among the Flow-approved capability set."""
        if not isinstance(job, dict):
            raise PolicyAbort("delivery job contract is absent")
        selected = assignment["instance_id"]
        if selected in job.get("producer_instance_ids", []):
            candidate_ids = job["producer_instance_ids"]
            capability_fact = "approved producer identity"
        elif selected in job.get("evidence_collector_instance_ids", []):
            candidate_ids = job["evidence_collector_instance_ids"]
            capability_fact = "approved evidence collector identity"
        elif selected in job.get("verifier_instance_ids", []):
            candidate_ids = job["verifier_instance_ids"]
            capability_fact = "approved verifier identity"
        else:
            raise PolicyAbort("selected specialist is outside the chartered job roster")
        candidates = [{key: roster[instance][key] for key in
                       ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model")}
                      for instance in candidate_ids if instance in roster]
        if len(candidates) != len(candidate_ids):
            raise PolicyAbort("selected specialist is outside its approved capability set")
        return {"eligible_candidates": candidates, "selected_candidate": selected,
                "rationale": {"manager_reason": selected_reason,
                              "facts": [capability_fact, "task selected by Magentic progress decision"]},
                "rejection_reasons": {
                    candidate["instance_id"]: {"reason": "Magentic selected a different approved candidate for the stated task.",
                                               "facts": ["candidate is authorized by the sealed Delivery Charter",
                                                         "Magentic progress decision selected another candidate"]}
                    for candidate in candidates if candidate["instance_id"] != selected}}

    class ManagerProxy:
        name = "flow-manager-proxy"

        def create_session(self) -> object:
            return object()

        async def run(self, messages: list[Message], *, session: object | None = None) -> AgentResponse:
            nonlocal manager_call, manager_round, replan_sequence, selected_task, selected_reason, unparsable_streak
            if not messages or not isinstance(messages[-1].text, str):
                raise RuntimeError("stock manager sent invalid messages")
            prompt = messages[-1].text
            phase = _phase(prompt)
            if phase == "replan_facts":
                replan_sequence += 1
            elif phase == "replan_plan" and replan_sequence == 0:
                raise PolicyAbort("replan plan arrived before revised facts")
            manager_call += 1
            if manager_call > MAX_MANAGER_CALLS:
                raise PolicyAbort("manager model call limit reached")
            # A retry of an unparsable progress reply is a new manager call but
            # not a new round: MAF's own round count does not move either.
            if phase == "progress" and manager_call > 3 and unparsable_streak == 0:
                manager_round += 1
            if manager_round > MAX_MANAGER_ROUNDS:
                raise PolicyAbort("manager round limit reached")
            serialized = [message.to_dict() for message in messages]
            if len(json.dumps(serialized, ensure_ascii=False).encode()) > MAX_MANAGER_MESSAGES_BYTES:
                raise PolicyAbort("manager message exceeds transport cap")
            prompt_digest = _digest(serialized)
            request = {"protocol_version": protocol_version, "schema_version": 1,
                    "type": "manager_request",
                    "attempt_id": attempt_id, "envelope_digest": envelope_hash, "sequence": manager_call,
                    "phase": phase, "prompt_digest": prompt_digest,
                    "manager_round": manager_round, "messages": serialized}
            if phase in {"replan_facts", "replan_plan"}:
                request["replan_sequence"] = replan_sequence
                request["replan_id"] = _digest({"attempt_id": attempt_id, "envelope_digest": envelope_hash,
                                                "execution_protocol_version": protocol_version,
                                                "kind": "replan", "sequence": replan_sequence})
            call_identity = {"kind": "manager_model", **{field: request[field] for field in
                ("attempt_id", "envelope_digest", "sequence", "phase", "manager_round", "prompt_digest")}}
            if phase in {"replan_facts", "replan_plan"}:
                call_identity.update({field: request[field] for field in ("replan_sequence", "replan_id")})
            request["call_id"] = _digest(call_identity)
            call_id = request["call_id"]
            _write(request)
            reply = _read()
            if reply.get("type") != "manager_response" or reply.get("call_id") != call_id or not isinstance(reply.get("text"), str):
                raise PolicyAbort("invalid Flow manager response")
            response_text = reply["text"]
            if phase == "progress":
                parsed = parse_progress(response_text)
                if parsed.value is None or not _maf_reads_canonical(parsed.canonical, parsed.value):
                    unparsable_streak += 1
                    if unparsable_streak >= PROGRESS_ATTEMPTS:
                        # A BaseException: MAF would otherwise catch its own
                        # exhausted-retry error and replan (ADR 0018).
                        raise PolicyAbort(f"manager progress unparsable after {PROGRESS_ATTEMPTS} attempts")
                    # MAF cannot parse the sentinel, so its loop retries.
                    return AgentResponse(messages=[Message(role="assistant", contents=[UNPARSABLE_SENTINEL])])
                unparsable_streak = 0
                progress = parsed.value
                _validate_progress(progress, set(roster))
                response_text = parsed.canonical
                selected_task = progress["instruction_or_question"]["answer"]
                selected_reason = progress["next_speaker"].get("reason")
                if not isinstance(selected_task, str) or not selected_task.strip() or not isinstance(selected_reason, str) or not selected_reason.strip():
                    raise PolicyAbort("manager progress lacks a bounded task and rationale")
                if len(selected_task.encode()) > MAX_TASK_BYTES or len(selected_reason.encode()) > MAX_TASK_BYTES:
                    raise PolicyAbort("manager-selected task exceeds Flow cap")
            return AgentResponse(messages=[Message(role="assistant", contents=[response_text])])

    class GuardedParticipant(Executor):
        def __init__(self, assignment: dict[str, Any]) -> None:
            self.assignment = assignment
            super().__init__(id=assignment["instance_id"])

        @handler
        async def broadcast(self, message: GroupChatParticipantMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
            return

        @handler
        async def request(self, message: GroupChatRequestMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
            nonlocal action_number
            action_number += 1
            if action_number > MAX_ACTIONS:
                raise PolicyAbort("delegation limit reached")
            assignment = self.assignment
            # MAF must pause and persist the selected request before Flow may
            # authorize the provider send. The task is Magentic's own choice.
            proposal = {"protocol_version": protocol_version, "schema_version": 1,
                        "type": "propose_action", "kind": "delegate",
                        "attempt_id": attempt_id, "envelope_digest": envelope_hash,
                        "sequence": action_number, "assignment_id": assignment["assignment_id"],
                        "definition_digest": assignment["definition_digest"], "instance_id": self.id,
                        "role": assignment["role"], "provider": assignment["provider"],
                        "model": assignment["model"], "manager_turn": manager_round,
                        "task": selected_task, "task_digest": hashlib.sha256(selected_task.encode()).hexdigest(),
                        "rationale": selected_reason,
                        "parent_action_id": previous_action_id}
            if protocol_version in {7, 8}:
                proposal["provider_choice"] = provider_choice(assignment)
            await ctx.request_info(proposal, dict, request_id=f"flow-magentic-action-{action_number}")

        @response_handler(request=dict, response=dict, output=GroupChatResponseMessage)
        async def accepted(self, request: dict[str, Any], result: dict[str, Any], ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
            summary = result.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                raise RuntimeError("Flow action result lacks summary")
            await ctx.send_message(GroupChatResponseMessage(message=Message(role="assistant", contents=[summary], author_name=self.id)))

    manager = StandardMagenticManager(ManagerProxy(), max_reset_count=MAX_REPLANS, max_round_count=MAX_MANAGER_ROUNDS,
                                      progress_ledger_retry_count=PROGRESS_ATTEMPTS)
    workflow = MagenticBuilder(participants=[GuardedParticipant(a) for a in assignments], manager=manager,
                               enable_plan_review=False, checkpoint_storage=storage, name=workflow_name).build()
    resume = start.get("resume") if start.get("type") == "resume" else None
    if resume is None:
        result = await workflow.run(task)
    else:
        if not isinstance(resume, dict) or not isinstance(resume.get("checkpoint_id"), str):
            raise PolicyAbort("invalid MAF restore request")
        if not isinstance(resume.get("manager_calls_committed"), int) or not 0 <= resume["manager_calls_committed"] <= MAX_MANAGER_CALLS:
            raise PolicyAbort("invalid manager replay position")
        if type(resume.get("replans_committed")) is not int or not 0 <= resume["replans_committed"] <= MAX_REPLANS:
            raise PolicyAbort("invalid approved replan position")
        checkpoint = await storage.load(resume["checkpoint_id"])
        orchestrator_state = checkpoint.state.get("_executor_state", {}).get("magentic_orchestrator", {})
        context_state = orchestrator_state.get("magentic_context", {})
        if context_state.get("reset_count") != resume["replans_committed"]:
            raise PolicyAbort("Flow replan position differs from MAF checkpoint")
        pending = checkpoint.pending_request_info_events
        request_id = resume.get("request_id")
        if not isinstance(request_id, str) or request_id not in pending or len(pending) != 1:
            raise PolicyAbort("restore checkpoint does not hold the exact action")
        saved = pending[request_id].data
        if not isinstance(saved, dict) or saved.get("attempt_id") != attempt_id:
            raise PolicyAbort("restore action differs from attempt")
        identity = {"kind": "delegate", **{field: (
            resume["checkpoint_id"] if field == "checkpoint_id" else saved[field]) for field in
            ("attempt_id", "envelope_digest", "assignment_id", "definition_digest", "instance_id",
             "sequence", "manager_turn", "task_digest", "parent_action_id", "checkpoint_id")}}
        if protocol_version in {7, 8}:
            identity["provider_choice"] = saved.get("provider_choice")
        expected_id = _digest(identity)
        # ``answer`` restores a completed action with Flow's reply. ``pending``
        # restores an action Flow never dispatched: the saved proposal is
        # re-emitted with its original checkpoint and identity so Flow can
        # re-grant it, and nothing is answered on Flow's behalf.
        mode = resume.get("kind", "answer")
        if mode not in {"answer", "pending"}:
            raise PolicyAbort("invalid MAF restore mode")
        if (resume.get("action_id") != expected_id
                or (mode == "answer") != isinstance(resume.get("result"), dict)
                or mode == "pending" and "result" in resume):
            raise PolicyAbort("restore action identity or result differs")
        manager_call = resume["manager_calls_committed"]
        manager_round = saved["manager_turn"]
        # A pending-action checkpoint exists only after a progress reply
        # parsed, so no retry is in flight at a restore point.
        unparsable_streak = 0
        replan_sequence = resume["replans_committed"]
        action_number = saved["sequence"]
        if mode == "answer":
            response = resume["result"]
        else:
            proposal = {**saved, "checkpoint_id": resume["checkpoint_id"], "action_id": expected_id}
            _write(proposal)
            reply = _read()
            if reply.get("type") != "action_result" or reply.get("action_id") != expected_id or not isinstance(reply.get("result"), dict):
                raise PolicyAbort("invalid Flow action result")
            response = reply["result"]
        previous_action_id = expected_id
        result = await workflow.run(checkpoint_id=resume["checkpoint_id"], checkpoint_storage=storage,
                                    responses={request_id: response})
    while requests := result.get_request_info_events():
        if len(requests) != 1:
            raise PolicyAbort("MAF has ambiguous pending specialist requests")
        event = requests[0]
        request_id = event.request_id
        proposal = event.data
        if not isinstance(proposal, dict) or request_id != f"flow-magentic-action-{proposal.get('sequence')}":
            raise PolicyAbort("MAF pending specialist identity mismatch")
        checkpoints = await storage.list_checkpoints(workflow_name=workflow_name)
        pending = [item for item in checkpoints if request_id in item.pending_request_info_events]
        if len(pending) != 1:
            raise PolicyAbort("MAF pending specialist checkpoint is absent or ambiguous")
        checkpoint_id = pending[0].checkpoint_id
        proposal["checkpoint_id"] = checkpoint_id
        identity = {"kind": "delegate", **{field: proposal[field] for field in
            ("attempt_id", "envelope_digest", "assignment_id", "definition_digest", "instance_id",
             "sequence", "manager_turn", "task_digest", "parent_action_id", "checkpoint_id")}}
        if protocol_version in {7, 8}:
            identity["provider_choice"] = proposal.get("provider_choice")
        proposal["action_id"] = _digest(identity)
        _write(proposal)
        reply = _read()
        if reply.get("type") != "action_result" or reply.get("action_id") != proposal["action_id"] or not isinstance(reply.get("result"), dict):
            raise PolicyAbort("invalid Flow action result")
        previous_action_id = proposal["action_id"]
        result = await workflow.run(checkpoint_id=checkpoint_id, checkpoint_storage=storage,
                                    responses={request_id: reply["result"]})
    output = result.get_outputs()
    _write({"protocol_version": protocol_version, "type": "workflow_finished", "attempt_id": attempt_id,
            "runtime_version": version("agent-framework-core"), "manager_calls": manager_call,
            "manager_rounds": manager_round, "actions": action_number,
            "summary": str(getattr(output[-1], "text", output[-1])) if output else "Magentic finished"})


async def _run_v9(start: dict[str, Any]) -> None:
    from agent_framework import AgentResponse, Executor, FileCheckpointStorage, Message, WorkflowContext, handler, response_handler
    from agent_framework_orchestrations import (
        GroupChatParticipantMessage, GroupChatRequestMessage, GroupChatResponseMessage,
        MagenticBuilder, StandardMagenticManager,
    )
    envelope = start['envelope']
    if envelope.get("maf_runtime") is not None:
        _write({"protocol_version": 9, "type": "runtime_ready", "runtime": _runtime_identity()})
    profile = (resolve_local_agent_budget(envelope['local_agent_profile'])
               if 'local_agent_profile' in envelope else None)
    call_limit = profile['manager_calls'] if profile else MAX_MANAGER_CALLS
    action_limit = profile['delegations'] if profile else MAX_ACTIONS
    message_limit = 4 * 1024 * 1024 if profile else MAX_MANAGER_MESSAGES_BYTES
    attempt_id = envelope['attempt_id']
    assignments = [a for a in envelope['logical_assignments'] if a['requirements']['operation'] != 'manage']
    completed = start.get('completed_assignments', [])
    if not isinstance(completed, list) or not set(completed) <= {a['assignment_id'] for a in assignments}:
        raise PolicyAbort('invalid completed assignment context')
    storage = FileCheckpointStorage(Path(envelope['checkpoint_dir']), allowed_checkpoint_types=[
        'agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatRequestMessage',
        'agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatParticipantMessage',
        'agent_framework_orchestrations._base_group_chat_orchestrator:GroupChatResponseMessage',
        'agent_framework_orchestrations._magentic:MagenticContext',
        'agent_framework_orchestrations._magentic:MagenticProgressLedger',
        'agent_framework_orchestrations._magentic:MagenticProgressLedgerItem',
    ])
    calls = actions = retries = 0
    selected_task = ''

    class ManagerProxy:
        name = 'flow-manager-proxy'

        def create_session(self):
            return object()

        async def run(self, messages, *, session=None):
            nonlocal calls, retries, selected_task
            phase = _phase(messages[-1].text)
            serialized = [m.to_dict() for m in messages]
            if len(json.dumps(serialized).encode()) > message_limit:
                raise PolicyAbort('manager message exceeds transport cap')
            calls += 1
            if call_limit is not None and calls > call_limit:
                raise PolicyAbort('manager call limit reached')
            _write({'protocol_version': 9, 'type': 'manager_request', 'attempt_id': attempt_id,
                    'sequence': calls, 'phase': phase, 'messages': serialized,
                    'prompt_digest': _digest(serialized)})
            reply = _read()
            if reply.get('type') != 'manager_response' or reply.get('sequence') != calls or not isinstance(reply.get('text'), str):
                raise PolicyAbort('invalid Flow manager response')
            text = reply['text']
            if phase == 'progress':
                parsed = parse_progress(text)
                if parsed.value is None or not _maf_reads_canonical(parsed.canonical, parsed.value):
                    retries += 1
                    if retries >= PROGRESS_ATTEMPTS:
                        raise PolicyAbort('manager progress retries exhausted')
                    return AgentResponse(messages=[Message(role='assistant', contents=[UNPARSABLE_SENTINEL])])
                retries = 0
                selected_task = parsed.value['instruction_or_question']['answer']
                text = parsed.canonical
            return AgentResponse(messages=[Message(role='assistant', contents=[text])])

    class GuardedParticipant(Executor):
        def __init__(self, assignment):
            self.assignment = assignment
            super().__init__(id=assignment['assignment_id'])

        @handler
        async def broadcast(self, message: GroupChatParticipantMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
            return

        @handler
        async def request(self, message: GroupChatRequestMessage, ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
            nonlocal actions
            actions += 1
            if (action_limit is not None and actions > action_limit) or not isinstance(selected_task, str) or not selected_task.strip():
                raise PolicyAbort('invalid or excessive worker request')
            if compute_binding(envelope, self.id).get('selected_binding') is None:
                raise PolicyAbort('no eligible binding for logical assignment')
            await ctx.request_info({'protocol_version': 9, 'type': 'propose_v9_action',
                                    'attempt_id': attempt_id, 'assignment_id': self.id,
                                    'task': selected_task, 'sequence': actions, 'manager_turn': calls},
                                   dict, request_id=f'flow-v9-action-{actions}')

        @response_handler(request=dict, response=dict, output=GroupChatResponseMessage)
        async def accepted(self, request: dict[str, Any], result: dict[str, Any], ctx: WorkflowContext[GroupChatResponseMessage]) -> None:
            summary = result.get('summary')
            if not isinstance(summary, str) or not summary.strip():
                raise PolicyAbort('Flow worker outcome lacks summary')
            await ctx.send_message(GroupChatResponseMessage(message=Message(role='assistant', contents=[summary], author_name=self.id)))

    manager = StandardMagenticManager(
        ManagerProxy(),
        max_reset_count=profile['replans'] if profile else min(MAX_REPLANS, envelope["limits"].get("max_replans", MAX_REPLANS)),
        max_round_count=profile['manager_rounds'] if profile else min(MAX_MANAGER_ROUNDS, envelope["limits"].get("max_manager_rounds", MAX_MANAGER_ROUNDS)),
        max_stall_count=profile['max_stall_count'] if profile else 3,
        progress_ledger_retry_count=PROGRESS_ATTEMPTS,
    )
    name = 'flow-magentic-delivery-v9-' + str(start.get('coordination_epoch', 1))
    workflow = MagenticBuilder(participants=[GuardedParticipant(a) for a in assignments], manager=manager,
                               enable_plan_review=False, checkpoint_storage=storage, name=name).build()
    _write({'protocol_version': 9, 'type': 'runtime_initialized', 'coordination': 'stock_magentic'})
    task = (start['task'] + '\nSealed logical assignments and dependencies: ' + json.dumps(assignments)
            + '\nFlow has already accepted these assignments: ' + json.dumps(completed))
    result = await workflow.run(task)
    while requests := result.get_request_info_events():
        if len(requests) != 1:
            raise PolicyAbort('ambiguous pending worker request')
        event = requests[0]
        checkpoints = await storage.list_checkpoints(workflow_name=name)
        pending = [c for c in checkpoints if event.request_id in c.pending_request_info_events]
        if len(pending) != 1:
            raise PolicyAbort('pending worker checkpoint absent or ambiguous')
        proposal = {**event.data, 'checkpoint_id': pending[0].checkpoint_id}
        proposal['proposal_id'] = _digest(proposal)
        _write(proposal)
        reply = _read()
        if reply.get('type') != 'action_result' or reply.get('proposal_id') != proposal['proposal_id'] or not isinstance(reply.get('result'), dict):
            raise PolicyAbort('invalid Flow action result')
        result = await workflow.run(checkpoint_id=pending[0].checkpoint_id, checkpoint_storage=storage,
                                    responses={event.request_id: reply['result']})
    _write({'protocol_version': 9, 'type': 'workflow_finished', 'attempt_id': attempt_id,
            'coordination': 'stock_magentic', 'manager_calls': calls, 'actions': actions,
            'summary': str(result.get_outputs())[:4096]})


def main() -> int:
    try:
        start = _read()
        if start.get("type") not in {"start", "resume"}:
            raise RuntimeError("delivery child requires start or resume")
        asyncio.run(_run(start))
        return 0
    except (Exception, PolicyAbort) as exc:
        _write({"protocol_version": _active_protocol_version or PROTOCOL_VERSION, "type": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
def provider_neutral_binding(envelope: dict[str, Any], assignment_id: str) -> dict[str, Any]:
    """Credentialless v9 child computation over Flow-sealed inputs."""
    if envelope.get("execution_protocol_version") != 9:
        raise PolicyAbort("provider-neutral binding requires protocol v9")
    return compute_binding(envelope, assignment_id)
