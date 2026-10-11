"""Workflow stages and artifacts over OpenHands-owned execution sessions.

run.json owns workflow state; SDK persistence owns conversation state. Session
references below are links, not a second execution ledger or checkpoint system.
"""
from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from uuid import UUID, uuid4
import json
import time

from delivery_control import run_lock
from fsutil import repo_root, write_atomic
from openhands_config import STAGES, OUTPUTS, RuntimeConfigurationError, select
import runstate
import openhands_runtime


APPROVALS = {"define": "approve-definition", "solution": "approve-solution", "plan": "approve-plan", "review": "accept-review"}


def _root(args) -> Path:
    return (args.project_root or repo_root()).resolve()


def _run(root: Path, work_id: str) -> tuple[Path, dict]:
    directory = runstate._run_dir(work_id, root)
    payload = runstate.status(work_id, root)
    if payload.get("runtime") != "openhands" or payload.get("protocol_revision") != 3:
        raise RuntimeConfigurationError("historical runs are not resumed by the replacement runtime; create a new workflow with the prior artifacts as context")
    return directory, payload


def _transition(root: Path, work_id: str, event: str, **kwargs) -> dict:
    ok, payload, errors = runstate.apply_transition(work_id, event, root=root, **kwargs)
    if not ok:
        raise RuntimeConfigurationError("; ".join(errors))
    return payload


def initialize(args) -> dict:
    root = _root(args)
    if runstate._run_path(args.work_id, root).exists():
        raise RuntimeConfigurationError("run already exists; use execute to continue it")
    return _transition(root, args.work_id, "start-definition", protocol_revision=3)


def _stage_prompt(root: Path, directory: Path, payload: dict, stage: str, task: str) -> str:
    outputs = "\n".join(f"- {name}: {(directory / filename).relative_to(root)}" for name, filename in OUTPUTS[stage].items())
    inputs = "\n".join(f"- {name}: {relative}" for name, relative in payload.get("artifacts", {}).items())
    return (f"Flow workflow {payload['work_id']}, stage {stage}.\n"
            f"Project workspace: {root}\nExisting project artifacts:\n{inputs}\n"
            f"Produce the following durable stage outputs, with actual evidence and unresolved questions:\n{outputs}\n"
            "Flow owns lifecycle approvals; do not change run.json, events.jsonl, or runtime session storage. "
            "A stage response does not approve the work. Follow project instructions and actual workspace permissions.\n\n"
            f"Requested outcome:\n{task}")


def execute(args) -> dict:
    from openhands_runtime import conversation
    root = _root(args)
    directory, payload = _run(root, args.work_id)
    stage = args.stage or payload.get("lane")
    if stage not in STAGES:
        raise RuntimeConfigurationError("choose an executable stage: define, solution, plan, implement, review")
    selection = select(root, stage, args.role, args.profile)
    # Consent to stock native permission handling is consequential: the pinned
    # Claude bridge may offer allow_always first and update native rules.
    if selection.provider["kind"] != "local" and selection.provider.get("permission_requests") != "stock-openhands":
        raise RuntimeConfigurationError("Native access decision required: see docs/native-access-decision.md before selecting permission_requests=stock-openhands.")
    # Profile validation does not manufacture a workspace or native access grant.
    from openhands_runtime import probe
    if not probe()["ready"]:
        raise RuntimeConfigurationError("pinned OpenHands runtime unavailable; see flow workflow runtime")
    task_path = (root / args.task_file).resolve()
    if not task_path.is_file():
        raise RuntimeConfigurationError("task file does not exist")
    task = task_path.read_text()
    if not task.strip():
        raise RuntimeConfigurationError("task file is empty")
    with run_lock(directory):
        directory, payload = _run(root, args.work_id)
        start_event, stage_state, _ = STAGES[stage]
        if payload["state"] != stage_state:
            payload = _transition(root, args.work_id, start_event, _lock_held=True)
        key = f"{stage}:{selection.role}"
        sessions = dict(payload.get("sessions", {}))
        reference = sessions.get(key)
        binding = selection.fingerprint()
        if reference and not args.new_session:
            if reference["binding"] != binding:
                raise RuntimeConfigurationError("provider, role, or workspace changed; use --new-session to keep the prior conversation intact")
            conversation_id = UUID(reference["conversation_id"])
        else:
            conversation_id = uuid4()
        reference = {"conversation_id": str(conversation_id), "binding": binding,
                     "role": selection.role, "profile": selection.profile, "stage": stage,
                     "workspace": selection.workspace, "status": "starting"}
        previous = sessions.get(key)
        if previous and args.new_session:
            payload.setdefault("prior_sessions", []).append(previous)
        sessions[key] = reference
        payload["sessions"] = sessions
        runstate._write_run(args.work_id, payload, root)
        # SDK events stay in SDK persistence. Flow records stage outcomes and a
        # compact metrics projection, rather than duplicating each tool event.
        def progress(event):
            if getattr(event, "source", None) == "agent" and getattr(event, "tool_name", None) == "finish":
                reference["response"] = event.action.message
            if getattr(event, "source", None) == "agent" and hasattr(event, "llm_message"):
                reference["response"] = "\n".join(getattr(item, "text", "") for item in event.llm_message.content if hasattr(item, "text"))
        started = time.monotonic()
        try:
            with conversation(selection, root, directory / "openhands", conversation_id, progress) as session:
                from openhands.sdk.conversation.state import ConversationExecutionStatus, ConversationState
                waiting = session.state.execution_status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
                if waiting:
                    if getattr(args, "reject_pending", None):
                        session.reject_pending_actions(args.reject_pending)
                        session.run()
                    elif getattr(args, "confirm_pending", False):
                        session.run()  # SDK's documented explicit continuation confirms pending actions.
                    else:
                        reference["status"] = session.state.execution_status.value
                        reference["pending_actions"] = [event.action.model_dump(mode="json") for event in ConversationState.get_unmatched_actions(session.state.active_branch())]
                        return {"work_id": args.work_id, "stage": stage, "session": reference,
                                "next_action": "Inspect pending_actions; use --confirm-pending or --reject-pending REASON."}
                else:
                    if getattr(args, "confirm_pending", False) or getattr(args, "reject_pending", None):
                        raise RuntimeConfigurationError("no SDK actions are waiting for confirmation")
                    session.send_message(_stage_prompt(root, directory, payload, stage, task))
                    session.run()
                reference["status"] = session.state.execution_status.value
                if session.state.execution_status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION:
                    reference["pending_actions"] = [event.action.model_dump(mode="json") for event in ConversationState.get_unmatched_actions(session.state.active_branch())]
                else:
                    reference.pop("pending_actions", None)
                reference["metrics"] = session.conversation_stats.get_combined_metrics().model_dump(mode="json")
        except BaseException as exc:
            reference["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "error"
            # Raw provider errors can contain credentials. Keep the detailed
            # SDK diagnostic in its own masked logs, not Flow's artifact text.
            reference["error_type"] = type(exc).__name__
            raise
        finally:
            reference["elapsed_seconds"] = round(time.monotonic() - started, 3)
            runstate._write_run(args.work_id, payload, root)
            report = {"work_id": args.work_id, **reference}
            write_atomic(directory / f"{stage}-{selection.role}-outcome.json", json.dumps(report, indent=2) + "\n")
        return {"work_id": args.work_id, "stage": stage, "session": reference,
                "outputs": {name: str(directory / filename) for name, filename in OUTPUTS[stage].items()}}


def approve(args) -> dict:
    root = _root(args)
    directory, payload = _run(root, args.work_id)
    stage = args.stage or payload["lane"]
    if stage not in {*APPROVALS, "implement"}:
        raise RuntimeConfigurationError("this stage has no approval transition")
    artifacts = {name: (directory / filename).relative_to(root).as_posix() for name, filename in OUTPUTS[stage].items()}
    for name, relative in artifacts.items():
        path = root / relative
        if not path.is_file() or not path.read_text().strip():
            raise RuntimeConfigurationError(f"missing or empty stage output: {name} ({relative})")
    dispositions = runstate.parse_assignments(args.disposition, "disposition")
    if stage == "implement":
        with run_lock(directory):
            _transition(root, args.work_id, "mark-handback-ready", artifacts=artifacts, _lock_held=True)
            return _transition(root, args.work_id, "start-review", _lock_held=True)
    return _transition(root, args.work_id, APPROVALS[stage], artifacts=artifacts, dispositions=dispositions)


def native_handoff(args) -> dict:
    root = _root(args)
    directory, payload = _run(root, args.work_id)
    stage = args.stage or payload["lane"]
    selection = select(root, stage, args.role, args.profile)
    if selection.provider["kind"] not in {"codex", "claude"}:
        raise RuntimeConfigurationError("native-handoff requires a codex or claude profile")
    task = (root / args.task_file).read_text()
    start_event, stage_state, _ = STAGES[stage]
    if payload["state"] != stage_state:
        payload = _transition(root, args.work_id, start_event)
    from openhands_runtime import ACP_BLOCKER
    text = (f"# Flow {stage}: {args.work_id}\n\n"
            f"Use your existing interactive {selection.provider['kind']} session in {root}.\n"
            "Use its current account, permission settings and native tools.\n\n"
            f"{ACP_BLOCKER}\n\n"
            f"## Specialist context\n\n{selection.role_file.read_text()}\n\n"
            f"## Task\n\n{_stage_prompt(root, directory, payload, stage, task)}\n")
    path = directory / f"{stage}-{selection.role}-native-handoff.md"
    write_atomic(path, text)
    return {"status": "native_handoff", "provider": selection.provider["kind"], "artifact": str(path),
            "next_action": "Use the artifact in the existing official native session; approve stage outputs with flow workflow approve."}


def archive(args) -> dict:
    root = _root(args)
    directory, payload = _run(root, args.work_id)
    dispositions = runstate.parse_assignments(args.disposition, "disposition")
    if payload["state"] != "review_accepted" or not all(dispositions.get(key) for key in ("memory", "capability_gaps")):
        raise RuntimeConfigurationError("archive requires accepted review and memory/capability_gaps dispositions")
    summary = directory / "archive.md"
    if not summary.exists():
        sources = "\n".join(f"- {name}: {path}" for name, path in payload["artifacts"].items())
        write_atomic(summary, f"# Archive Summary: {args.work_id}\n\n## Work Closed\n\nAccepted review. Detailed outcomes and evidence are in the approved artifacts below.\n\n{sources}\n\n## Dispositions\n\n" + "\n".join(f"- {key}: {value}" for key, value in dispositions.items()) + "\n")
    if summary.is_symlink() or not summary.resolve().is_relative_to(directory.resolve()):
        raise RuntimeConfigurationError("archive summary must be a current-run regular file")
    return _transition(root, args.work_id, "archive", dispositions=dispositions,
                       artifacts={"archive": summary.relative_to(root).as_posix()})


def show(args) -> dict:
    return _run(_root(args), args.work_id)[1]


def runtime_info(args) -> dict:
    from openhands_runtime import probe
    return probe()


def _handler(function):
    def handle(args):
        try:
            result = function(args)
        except (ValueError, FileNotFoundError, ImportError) as exc:
            print(json.dumps({"status": "error", "reason": str(exc)}) if args.json else f"Flow workflow: {exc}")
            return 1
        except KeyboardInterrupt:
            print("Flow workflow interrupted; OpenHands session persistence is retained.")
            return 130
        except Exception as exc:
            print(json.dumps({"status": "error", "error_type": type(exc).__name__, "reason": "SDK execution failed; inspect the preserved session and masked runtime diagnostic."}))
            return 1
        print(json.dumps(result, indent=2, default=str) if args.json else _summary(result))
        return 0
    return handle


def _summary(result):
    if "artifact" in result:
        return f"{result['status']}: {result['artifact']}"
    if "session" in result:
        return f"{result['work_id']} {result['stage']}: {result['session']['status']} ({result['session']['conversation_id']})"
    if "state" in result:
        return f"{result['work_id']}: {result['state']}"
    return json.dumps(result, indent=2)


def register_commands(sub):
    parser = sub.add_parser("workflow", help="Flow stages and artifacts executed by OpenHands")
    commands = parser.add_subparsers(dest="workflow_command", required=True)
    for name, function, help_text in (
        ("init", initialize, "start a new OpenHands-backed definition"),
        ("execute", execute, "execute or continue a specialist using SDK persistence"),
        ("approve", approve, "approve durable stage outputs and advance the workflow"),
        ("native-handoff", native_handoff, "prepare context for an existing official native-agent session"),
        ("archive", archive, "archive an accepted review with project dispositions"),
        ("status", show, "show workflow and SDK session references"),
        ("runtime", runtime_info, "inspect exact runtime versions and native access limitation"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.set_defaults(openhands_handler=_handler(function))
        command.add_argument("--project-root", type=Path)
        command.add_argument("--json", action="store_true")
        if name != "runtime":
            command.add_argument("work_id")
        if name in {"execute", "native-handoff", "approve"}:
            command.add_argument("--stage", choices=tuple(STAGES))
        if name in {"execute", "native-handoff"}:
            command.add_argument("--role")
            command.add_argument("--profile")
            command.add_argument("--task-file", required=True, type=Path)
        if name == "execute":
            confirmation = command.add_mutually_exclusive_group()
            confirmation.add_argument("--confirm-pending", action="store_true", help="confirm the SDK actions shown by status")
            confirmation.add_argument("--reject-pending", metavar="REASON", help="reject waiting actions through the SDK")
            command.add_argument("--new-session", action="store_true", help="retain the old conversation and start a new one")
        if name in {"approve", "archive"}:
            command.add_argument("--disposition", action="append", default=[], metavar="NAME=VALUE")
