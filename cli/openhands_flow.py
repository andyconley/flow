"""Workflow stages and artifacts over OpenHands-owned execution sessions.

run.json owns workflow state; SDK persistence owns conversation state. Session
references below are links, not a second execution ledger or checkpoint system.
"""
from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4
import json
import asyncio
import time
import verification
import review_output

from acp_permissions import Terminal
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
    errors = runstate.openhands_approval_errors(work_id, payload, root)
    if errors:
        raise RuntimeConfigurationError("; ".join(errors))
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


STAGE_COORDINATION = {
    "solution": "After explicit solution approval, the host assistant assumes Delivery Lead coordination and initiates planning. Solution approval does not authorize implementation.",
    "review": "Review implementation correctness against approved criteria separately from test equivalence. Fixing a misspelled test import without changing assertions can be equivalent; correcting implementation logic to satisfy those assertions is implementation work, not a criterion change. Write exactly one Verdict: ACCEPT or REJECT in review.md. If evaluation inputs changed, also write exactly one Test equivalence: EQUIVALENT, MATERIAL or UNCERTAIN with before/after rationale. An ACCEPT does not itself authorize a test-change receipt. Missing output needs bounded repair; do not synthesize approval.",
    "plan": "Prepare technical planning and validation from the approved solution when available, otherwise the approved definition; the solution stage is optional. Supply evidence for plan.md, handoff.md and validation-plan.md to the host assistant, who owns Delivery Lead coordination and requests explicit plan approval from the user. The executing specialist supplies technical expertise and does not take over host coordination. Do not start implementation until the plan is approved.",
}


def _stage_prompt(root: Path, directory: Path, payload: dict, stage: str, task: str) -> str:
    outputs = "\n".join(f"- {name}: {(directory / filename).relative_to(root)}" for name, filename in specialist_outputs(payload, stage).items())
    inputs = "\n".join(f"- {name}: {relative}" for name, relative in payload.get("artifacts", {}).items())
    planning_basis = (
        "Planning basis: the approved solution takes precedence over the retained definition."
        if "solution" in payload.get("artifacts", {}) else
        "Planning basis: the approved definition; the optional solution stage was skipped."
    ) if stage == "plan" else ""
    return (f"Flow workflow {payload['work_id']}, stage {stage}.\n"
            f"Project workspace: {root}\nExisting project artifacts:\n{inputs}\n"
            f"Produce the following durable stage outputs, with actual evidence and unresolved questions:\n{outputs}\n"
            "Flow owns lifecycle approvals; do not change run.json, events.jsonl, or runtime session storage. "
            "A stage response does not approve the work. Follow project instructions and actual workspace permissions.\n\n"
            f"For verification-v1 work, follow {Path(__file__).resolve().parent.parent / 'docs/verification-evidence.md'}. Register checks and evaluation inputs "
            "in verification-plan.json before plan approval. The host runs workflow check after workflow execute returns; "
            "SDK specialists run tests through their tools and must not invoke Flow check/repair/lifecycle commands "
            "inside the running execute, which holds the run lock. The host alone creates verification.json after execute returns. Specialists must not create, edit, or synthesize verification.json or its captured logs; "
            "record actual session/assignment identities. Never weaken approved criteria or tests to obtain a pass. "
            "Equivalent test repairs require independent evidence review; material or uncertain criterion changes "
            "require separate user approval in a successor workflow. Targeted repair allocations persist across sessions.\n\n"
            f"{STAGE_COORDINATION.get(stage, '')}\n{planning_basis}\n\n"
            f"Requested outcome:\n{task}")


def stage_outputs(payload, stage):
    return {**OUTPUTS[stage], **(verification.EXTRAS.get(stage, {}) if verification.enabled(payload) else {})}


def specialist_outputs(payload, stage):
    """Separate specialist deliverables from host-captured approval inputs."""
    return {name: path for name, path in stage_outputs(payload, stage).items()
            if name != "verification"}


def _run_session(session, review_result):
    if review_result is None:
        return session.run()
    # Use the pinned SDK's own async cancellation, not a new executor loop.
    async def run_review():
        remaining = (verification.parse_time(review_result["deadline"]) - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise RuntimeConfigurationError("review deadline exhausted; block and escalate")
        timer = asyncio.get_running_loop().call_later(remaining, session.interrupt)
        try:
            await session.arun()
        finally:
            timer.cancel()
    return asyncio.run(run_review())


def execute(args) -> dict:
    from openhands_runtime import conversation
    root = _root(args)
    directory, payload = _run(root, args.work_id)
    stage = args.stage or payload.get("lane")
    if stage not in STAGES:
        raise RuntimeConfigurationError("choose an executable stage: define, solution, plan, implement, review")
    selection = select(root, stage, args.role, args.profile)
    native_permissions = []
    if stage == 'implement':
        from openhands_policy import specialist_selections, subscription_readiness
        from openhands_config import load_config
        from dataclasses import replace
        if selection.provider['kind'] not in {'local', 'openai-subscription'}:
            raise RuntimeConfigurationError('implementation requires an OpenHands SDK coordinator; bind native profiles to worker roles, not the coordinator')
        if selection.workspace.get('kind', 'local') != 'local':
            raise RuntimeConfigurationError('policy coordinator requires a local SDK workspace')
        if selection.role_options.get('model_routing'):
            raise RuntimeConfigurationError('policy coordinator cannot use model_routing; use fixed worker profile bindings')
        if 'task' not in selection.role_options.get('tools', ['task']):
            raise RuntimeConfigurationError('implementation coordinator requires the task tool; existing restriction was preserved')
        if selection.provider['kind'] == 'openai-subscription' and not subscription_readiness()['credential_file_present']:
            raise RuntimeConfigurationError('OpenHands subscription sign-in required; no stage was started. Run the documented human SDK sign-in; native CLI login is separate.')
        children = specialist_selections(root, selection, load_config(root))
        selection = replace(selection, role_options={**selection.role_options, 'policy_dispatch': True},
                            routing_profiles={role: child.fingerprint() for role, child in children.items()})
        native_permissions = [child.provider.get('permission_requests', 'interactive') for child in children.values()
                              if child.provider['kind'] in {'claude', 'codex'}]
    # Consent to stock native permission handling is consequential: the pinned
    # Claude bridge may offer allow_always first and update native rules.
    if selection.provider["kind"] in {'claude', 'codex'} and selection.provider.get("permission_requests", "interactive") not in {"interactive", "stock-openhands"}:
        raise RuntimeConfigurationError("permission_requests must be interactive or explicitly acknowledged stock-openhands")
    if 'interactive' in native_permissions or (selection.provider["kind"] in {'claude', 'codex'} and selection.provider.get("permission_requests", "interactive") == "interactive"):
        try:
            terminal = Terminal()
            terminal.close()
        except OSError as exc:
            raise RuntimeConfigurationError("Interactive ACP requires a human controlling terminal; no stage was started. Use a human terminal; no automatic approval fallback.") from exc
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
        equivalence_review = stage == "review" and verification.enabled(payload) and payload["state"] == "implementing"
        if payload["state"] != stage_state and not equivalence_review:
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
        previous = sessions.get(key)
        reference = {**(previous if previous and not args.new_session else {}),
                     "conversation_id": str(conversation_id), "binding": binding,
                     "role": selection.role, "profile": selection.profile, "stage": stage,
                     "workspace": selection.workspace, "status": "starting"}
        review_result = None
        if stage == "review" and verification.enabled(payload):
            review_result, review_before = review_output.begin(root, payload, str(conversation_id),
                continuing=bool(previous and not args.new_session and previous.get("status") == "waiting_for_confirmation"))
        reference.pop("error_type", None)
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
        elapsed_before = reference.get("elapsed_seconds", 0)
        session = None
        reference["provider"] = selection.provider["kind"]
        reference["model"] = selection.provider.get("model")
        try:
            with conversation(selection, root, directory / "openhands", conversation_id, progress) as session:
                from openhands.sdk.conversation.state import ConversationExecutionStatus, ConversationState
                waiting = session.state.execution_status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION
                if waiting:
                    if getattr(args, "reject_pending", None):
                        session.reject_pending_actions(args.reject_pending)
                        _run_session(session, review_result)
                    elif getattr(args, "confirm_pending", False):
                        _run_session(session, review_result)  # SDK's documented explicit continuation confirms pending actions.
                    else:
                        reference["status"] = session.state.execution_status.value
                        reference["pending_actions"] = [event.action.model_dump(mode="json") for event in ConversationState.get_unmatched_actions(session.state.active_branch())]
                        return {"work_id": args.work_id, "stage": stage, "session": reference,
                                "next_action": "Inspect pending_actions; use --confirm-pending or --reject-pending REASON."}
                else:
                    if getattr(args, "confirm_pending", False) or getattr(args, "reject_pending", None):
                        raise RuntimeConfigurationError("no SDK actions are waiting for confirmation")
                    session.send_message(_stage_prompt(root, directory, payload, stage, task))
                    _run_session(session, review_result)
                reference["status"] = session.state.execution_status.value
                if session.state.execution_status == ConversationExecutionStatus.WAITING_FOR_CONFIRMATION:
                    reference["pending_actions"] = [event.action.model_dump(mode="json") for event in ConversationState.get_unmatched_actions(session.state.active_branch())]
                else:
                    reference.pop("pending_actions", None)
                if review_result is not None and reference["status"] == "finished":
                    review_output.finish(root, payload, review_result, review_before)
                    if review_result["status"] != "complete":
                        reference["status"] = "incomplete_review"
                    reference["review_output"] = review_result
                if review_result is not None and datetime.now(timezone.utc) >= verification.parse_time(review_result["deadline"]):
                    review_result["status"] = "incomplete"
                    review_result["reason"] = "review deadline exhausted; block and escalate"
                    reference["status"] = "incomplete_review"
                    reference["review_output"] = review_result
                reference["metrics"] = session.conversation_stats.get_combined_metrics().model_dump(mode="json")
        except BaseException as exc:
            reference["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "error"
            # Raw provider errors can contain credentials. Keep the detailed
            # SDK diagnostic in its own masked logs, not Flow's artifact text.
            reference["error_type"] = type(exc).__name__
            raise
        finally:
            reference["elapsed_seconds"] = round(elapsed_before + time.monotonic() - started, 3)
            # Also refresh on waiting, provider failures and Ctrl-C. The context
            # manager has persisted/closed the SDK conversation before this runs.
            if session is not None:
                try:
                    stats = getattr(session, "conversation_stats", None)
                    if stats is not None:
                        reference["metrics"] = stats.get_combined_metrics().model_dump(mode="json")
                        reference["metrics_by_usage"] = stats.model_dump(mode="json")["usage_to_metrics"]
                        reference.pop("metrics_error_type", None)
                except Exception as metrics_error:
                    reference["metrics_error_type"] = type(metrics_error).__name__
            reference["metrics_observed_at"] = datetime.now(timezone.utc).isoformat()
            runstate._write_run(args.work_id, payload, root)
            report = {"work_id": args.work_id, **reference}
            write_atomic(directory / f"{stage}-{selection.role}-outcome.json", json.dumps(report, indent=2) + "\n")
            if review_result is not None:
                write_atomic(directory / "review-outcomes" / f"{review_result['id']}.json", json.dumps(report, indent=2) + "\n")
        return {"work_id": args.work_id, "stage": stage, "session": reference,
                "outputs": {name: str(directory / filename) for name, filename in specialist_outputs(payload, stage).items()},
                "host_recorded_outputs": {name: str(directory / filename) for name, filename in stage_outputs(payload, stage).items()
                                          if name not in specialist_outputs(payload, stage)}}


def approve(args) -> dict:
    root = _root(args)
    directory, payload = _run(root, args.work_id)
    stage = args.stage or payload["lane"]
    if stage not in {*APPROVALS, "implement"}:
        raise RuntimeConfigurationError("this stage has no approval transition")
    artifacts = {name: (directory / filename).relative_to(root).as_posix() for name, filename in stage_outputs(payload, stage).items()}
    for name, relative in (artifacts.items() if stage != "implement" else ()):
        path = root / relative
        if not path.is_file() or not path.read_text().strip():
            raise RuntimeConfigurationError(f"missing or empty stage output: {name} ({relative})")
    dispositions = runstate.parse_assignments(args.disposition, "disposition")
    if stage == "review":
        review_output.validate_approval(root, payload)
    if stage == "implement":
        with run_lock(directory):
            _, current = _run(root, args.work_id)
            if current["state"] != runstate.STATE_HANDBACK_READY:
                _transition(root, args.work_id, "mark-handback-ready", artifacts=artifacts, _lock_held=True)
            return _transition(root, args.work_id, "start-review", _lock_held=True)
    return _transition(root, args.work_id, APPROVALS[stage], artifacts=artifacts, dispositions=dispositions)


def native_handoff(args) -> dict:
    root = _root(args)
    directory, payload = _run(root, args.work_id)
    stage = args.stage or payload["lane"]
    if stage == 'implement':
        raise RuntimeConfigurationError('implementation coordination belongs to OpenHands; native-handoff is for shaping and review')
    selection = select(root, stage, args.role, args.profile)
    if selection.provider["kind"] not in {"codex", "claude"}:
        raise RuntimeConfigurationError("native-handoff requires a codex or claude profile")
    task = (root / args.task_file).read_text()
    start_event, stage_state, _ = STAGES[stage]
    if payload["state"] != stage_state:
        payload = _transition(root, args.work_id, start_event)
    from openhands_runtime import ACP_BLOCKER, role_context
    metadata, composed_role = role_context(selection)
    references = [".flow/PROJECT.md", *selection.role_options.get("context", []),
                  *selection.role_options.get("skills", [])]
    context_guidance = ("## Context and skills\n\nRead existing project instructions and these configured references: "
                        + ", ".join(str(p) for p in references) + ".\n"
                        + "Resolve declared role skills through native skill discovery: "
                        + ", ".join(metadata.get("skills", [])) + ".\n\n")
    host_guidance = (
        "## Host coordination\n\n"
        "As the host assistant, assume Delivery Lead coordination for planning from the approved solution "
        "when available, otherwise the approved definition. Coordinate specialists and validation through the existing "
        "session, reconcile their evidence, and present the plan for explicit user approval before implementation. "
        "The specialist delegation reference and technical task below do not transfer host ownership.\n\n"
    ) if stage == "plan" else ""
    specialist_context = (
        f"## Specialist delegation reference\n\n"
        f"Technical planning specialist: {selection.role}. Role file: {selection.role_file}.\n"
        "These role instructions apply only to a separately invoked specialist, not to the host assistant.\n\n"
    ) if stage == "plan" else f"## Specialist context\n\n{composed_role}\n\n"
    text = (f"# Flow {stage}: {args.work_id}\n\n"
            f"Use your existing interactive {selection.provider['kind']} session in {root}.\n"
            "Use its current account, permission settings and native tools.\n\n"
            f"{ACP_BLOCKER}\n\n"
            f"{host_guidance}"
            f"{context_guidance}"
            f"{specialist_context}"
            f"## Task\n\n{_stage_prompt(root, directory, payload, stage, task)}\n")
    path = directory / f"{stage}-{selection.role}-native-handoff.md"
    write_atomic(path, text)
    return {"status": "native_handoff", "provider": selection.provider["kind"], "artifact": str(path),
            "next_action": "Use the artifact in the existing official native session; approve stage outputs with flow workflow approve."}


def archive(args) -> dict:
    root = _root(args)
    directory, payload = _run(root, args.work_id)
    dispositions = runstate.parse_assignments(args.disposition, "disposition")
    if payload["state"] not in {"review_accepted", "archived"} or not all(dispositions.get(key) for key in ("memory", "capability_gaps")):
        raise RuntimeConfigurationError("archive requires accepted review and memory/capability_gaps dispositions")
    summary = directory / "archive.md"
    if not summary.exists():
        sources = "\n".join(f"- {name}: {path}" for name, path in payload["artifacts"].items())
        write_atomic(summary, f"# Archive Summary: {args.work_id}\n\n## Work Closed\n\nAccepted review. Detailed outcomes and evidence are in the approved artifacts below.\n\n{sources}\n\n## Dispositions\n\n" + "\n".join(f"- {key}: {value}" for key, value in dispositions.items()) + "\n")
    if summary.is_symlink() or not summary.resolve().is_relative_to(directory.resolve()):
        raise RuntimeConfigurationError("archive summary must be a current-run regular file")
    from archive_service import archive_transition_result
    result = archive_transition_result(root, args.work_id, dispositions=dispositions,
                                      artifacts={"archive": summary.relative_to(root).as_posix()})
    if not result["ok"]:
        raise RuntimeConfigurationError("; ".join(result["errors"]))
    return {**result["run"], "enrichment_diagnostics": result["enrichment_diagnostics"],
            "archive_coverage": result["archive_coverage"]}


def show(args) -> dict:
    root = _root(args)
    payload = runstate.status(args.work_id, root)
    if payload.get("runtime") != "openhands" or payload.get("protocol_revision") != 3:
        raise RuntimeConfigurationError("this is not an OpenHands workflow; use flow run status for historical runs")
    result = dict(payload)
    errors = runstate.openhands_approval_errors(args.work_id, payload, root)
    if errors:
        result["approval_integrity"] = {"ok": False, "errors": errors}
    result["verification_status"] = "required" if verification.enabled(payload) else "historical_unbound"
    return result


def check(args) -> dict:
    root = _root(args)
    with run_lock(runstate._run_dir(args.work_id, root), blocking=False):
        _, payload = _run(root, args.work_id)
        result = verification.capture(root, payload, args.check_id, args.session_id,
                                      args.assignment_id, args.environment, args.timeout)
        if result["status"] == "failed" and result["repair_attempt"] >= verification.REPAIR_LIMIT:
            _transition(root, args.work_id, "block", note="Repair budget exhausted; escalate to the user.", _lock_held=True)
        return result


def repair(args) -> dict:
    root = _root(args)
    with run_lock(runstate._run_dir(args.work_id, root), blocking=False):
        _, payload = _run(root, args.work_id)
        if not verification.enabled(payload):
            raise RuntimeConfigurationError("bounded repair requires a new verification-v1 workflow")
        used = sum(a["check_id"] == args.check_id for a in payload.get("repair_attempts", []))
        if used >= verification.REPAIR_LIMIT:
            blocked = payload if payload["state"] == "blocked" else _transition(
                root, args.work_id, "block", note="Repair budget exhausted; escalate to the user.", _lock_held=True)
            return {**blocked, "status": "blocked"}
        return _transition(root, args.work_id, "request-refinement", _lock_held=True,
            dispositions={"failed_check": args.check_id, "specialist": args.specialist,
                          "narrowed_scope": args.scope, "reason": args.reason,
                          "failure_evidence": args.failure_evidence})


def review_test_change(args) -> dict:
    root = _root(args)
    with run_lock(runstate._run_dir(args.work_id, root), blocking=False):
        _, payload = _run(root, args.work_id)
        return verification.review_change(root, payload, args.reviewer, args.reviewer_session_id,
                                          args.rationale, args.evidence, args.disposition)


def evidence_report(args) -> dict:
    root = _root(args)
    _, payload = _run(root, args.work_id)
    rows = None
    if getattr(args, "usage_store", None):
        import sqlite3
        from openhands_usage import reporting_rows
        with sqlite3.connect(args.usage_store.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = reporting_rows(conn)
    return verification.report(root, payload, rows)


def runtime_info(args) -> dict:
    from openhands_runtime import probe
    from openhands_config import wiring_report
    result = probe()
    return {**result, "sdk_ready": result["ready"], "readiness_scope": "sdk_packages_only",
            "wiring": wiring_report(_root(args))}


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
        return 1 if result.get("session", {}).get("status") in {"error", "interrupted", "incomplete_review"} or result.get("status") in {"failed", "blocked"} else 0
    return handle


def _summary(result):
    if "artifact" in result:
        return f"{result['status']}: {result['artifact']}"
    if "session" in result:
        return f"{result['work_id']} {result['stage']}: {result['session']['status']} ({result['session']['conversation_id']})"
    if "state" in result:
        text = f"{result['work_id']}: {result['state']}"
        integrity = result.get("approval_integrity", {})
        if integrity.get("errors"):
            text += "\napproval integrity: " + "; ".join(integrity["errors"])
        if result.get("enrichment_diagnostics"):
            text += "\narchive enrichment: " + "; ".join(result["enrichment_diagnostics"])
        return text
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
        ("check", check, "run an approved check and record workspace-bound evidence"),
        ("repair", repair, "allocate a bounded targeted repair or escalate"),
        ("review-test-change", review_test_change, "record independent evidence for an equivalent test repair"),
        ("evidence-report", evidence_report, "report verification attempts and existing usage join identities"),
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
        if name in {"check", "repair"}:
            command.add_argument("--check-id", required=True)
        if name == "check":
            command.add_argument("--session-id", required=True)
            command.add_argument("--assignment-id", required=True)
            command.add_argument("--environment", required=True)
            command.add_argument("--timeout", type=int, default=1800)
        if name == "repair":
            command.add_argument("--specialist", required=True)
            command.add_argument("--scope", required=True)
            command.add_argument("--reason", required=True)
            command.add_argument("--failure-evidence", required=True)
        if name == "review-test-change":
            command.add_argument("--reviewer", required=True)
            command.add_argument("--reviewer-session-id", required=True)
            command.add_argument("--rationale", required=True)
            command.add_argument("--evidence", required=True)
            command.add_argument("--disposition", choices=("equivalent", "material", "uncertain"), required=True)
        if name == "evidence-report":
            command.add_argument("--usage-store", type=Path, help="read an already harvested usage store without modifying it")
        if name in {"approve", "archive"}:
            command.add_argument("--disposition", action="append", default=[], metavar="NAME=VALUE")
