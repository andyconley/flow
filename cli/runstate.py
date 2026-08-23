"""C-lite run state for Flow's gated workflow.

The run protocol is deliberately small: ``run.json`` is the current-state
projection and ``events.jsonl`` is the append-only history.  The transition
table below is the only place that decides whether a lifecycle move is legal.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fsutil import ensure_dir, repo_root, write_atomic


SCHEMA_VERSION = 1
RUNS_DIR = Path(".flow") / "runs"
RUN_FILE = "run.json"
EVENTS_FILE = "events.jsonl"

STATE_DEFINING = "defining"
STATE_DEFINITION_APPROVED = "definition_approved"
STATE_SOLUTIONING = "solutioning"
STATE_SOLUTION_APPROVED = "solution_approved"
STATE_PLANNING = "planning"
STATE_PLAN_APPROVED = "plan_approved"
STATE_IMPLEMENTING = "implementing"
STATE_HANDBACK_READY = "handback_ready"
STATE_REVIEWING = "reviewing"
STATE_REVIEW_ACCEPTED = "review_accepted"
STATE_ARCHIVED = "archived"
STATE_PAUSED = "paused"
STATE_BLOCKED = "blocked"
STATE_LEGACY = "legacy/inferred"
STATE_RETURN = "__return__"

STATE_LANES = {
    STATE_DEFINING: "define",
    STATE_DEFINITION_APPROVED: "define",
    STATE_SOLUTIONING: "solution",
    STATE_SOLUTION_APPROVED: "solution",
    STATE_PLANNING: "plan",
    STATE_PLAN_APPROVED: "plan",
    STATE_IMPLEMENTING: "implement",
    STATE_HANDBACK_READY: "implement",
    STATE_REVIEWING: "review",
    STATE_REVIEW_ACCEPTED: "review",
    STATE_ARCHIVED: "archive",
}


@dataclass(frozen=True)
class Transition:
    event: str
    from_states: tuple[str | None, ...]
    to_state: str
    lane: str
    required_artifacts: tuple[str, ...] = ()
    required_dispositions: tuple[str, ...] = ()
    gate: str = ""


TRANSITIONS: dict[str, Transition] = {
    "start-definition": Transition(
        "start-definition", (None,), STATE_DEFINING, "define"
    ),
    "approve-definition": Transition(
        "approve-definition",
        (STATE_DEFINING,),
        STATE_DEFINITION_APPROVED,
        "define",
        required_artifacts=("requirements", "acceptance_criteria"),
        gate="definition approval",
    ),
    "start-solution": Transition(
        "start-solution",
        (STATE_DEFINITION_APPROVED,),
        STATE_SOLUTIONING,
        "solution",
        gate="approved definition before solution",
    ),
    "approve-solution": Transition(
        "approve-solution",
        (STATE_SOLUTIONING,),
        STATE_SOLUTION_APPROVED,
        "solution",
        required_artifacts=("solution",),
        required_dispositions=("risk",),
        gate="solution approval",
    ),
    "start-plan": Transition(
        "start-plan",
        (STATE_DEFINITION_APPROVED, STATE_SOLUTION_APPROVED),
        STATE_PLANNING,
        "plan",
        gate="approved definition or approved solution before plan",
    ),
    "approve-plan": Transition(
        "approve-plan",
        (STATE_PLANNING,),
        STATE_PLAN_APPROVED,
        "plan",
        required_artifacts=("plan", "handoff", "validation_plan"),
        gate="plan approval",
    ),
    "start-implementation": Transition(
        "start-implementation",
        (STATE_PLAN_APPROVED,),
        STATE_IMPLEMENTING,
        "implement",
        gate="approved plan before implementation",
    ),
    "mark-handback-ready": Transition(
        "mark-handback-ready",
        (STATE_IMPLEMENTING,),
        STATE_HANDBACK_READY,
        "implement",
        required_artifacts=("implementation_evidence", "handback"),
        gate="implementation handback",
    ),
    "start-review": Transition(
        "start-review",
        (STATE_HANDBACK_READY,),
        STATE_REVIEWING,
        "review",
        gate="implementation handback before review",
    ),
    "accept-review": Transition(
        "accept-review",
        (STATE_REVIEWING,),
        STATE_REVIEW_ACCEPTED,
        "review",
        required_artifacts=("review",),
        gate="accepted review",
    ),
    "archive": Transition(
        "archive",
        (STATE_REVIEW_ACCEPTED,),
        STATE_ARCHIVED,
        "archive",
        required_dispositions=("capability_gaps", "memory"),
        gate="archive closure",
    ),
    "archive-scout": Transition(
        "archive-scout",
        (None,),
        STATE_ARCHIVED,
        "scout",
        required_artifacts=("scout_summary",),
        required_dispositions=("capability_gaps", "memory"),
        gate="scout archive closure",
    ),
    "pause": Transition(
        "pause",
        (
            STATE_DEFINING,
            STATE_DEFINITION_APPROVED,
            STATE_SOLUTIONING,
            STATE_SOLUTION_APPROVED,
            STATE_PLANNING,
            STATE_PLAN_APPROVED,
            STATE_IMPLEMENTING,
            STATE_HANDBACK_READY,
            STATE_REVIEWING,
            STATE_REVIEW_ACCEPTED,
        ),
        STATE_PAUSED,
        "run",
    ),
    "block": Transition(
        "block",
        (
            STATE_DEFINING,
            STATE_DEFINITION_APPROVED,
            STATE_SOLUTIONING,
            STATE_SOLUTION_APPROVED,
            STATE_PLANNING,
            STATE_PLAN_APPROVED,
            STATE_IMPLEMENTING,
            STATE_HANDBACK_READY,
            STATE_REVIEWING,
            STATE_REVIEW_ACCEPTED,
        ),
        STATE_BLOCKED,
        "run",
    ),
    "resume": Transition(
        "resume",
        (STATE_PAUSED, STATE_BLOCKED),
        STATE_RETURN,
        "run",
        gate="paused or blocked run resume",
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _runs_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / RUNS_DIR


def _run_dir(work_id: str, root: Path | None = None) -> Path:
    return _runs_root(root) / work_id


def _run_path(work_id: str, root: Path | None = None) -> Path:
    return _run_dir(work_id, root) / RUN_FILE


def _events_path(work_id: str, root: Path | None = None) -> Path:
    return _run_dir(work_id, root) / EVENTS_FILE


def parse_assignments(values: list[str] | None, label: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError(f"{label} must use NAME=VALUE: {value}")
        key, item = value.split("=", 1)
        key = key.strip()
        item = item.strip()
        if not key or not item:
            raise ValueError(f"{label} must use NAME=VALUE: {value}")
        parsed[key] = item
    return parsed


def _load_run(work_id: str, root: Path | None = None) -> dict[str, Any] | None:
    path = _run_path(work_id, root)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write_run(work_id: str, payload: dict[str, Any], root: Path | None = None) -> None:
    path = _run_path(work_id, root)
    ensure_dir(path.parent)
    write_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _append_event(work_id: str, event: dict[str, Any], root: Path | None = None) -> None:
    path = _events_path(work_id, root)
    ensure_dir(path.parent)
    with path.open("a") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")


def _load_events(work_id: str, root: Path | None = None) -> list[dict[str, Any]]:
    path = _events_path(work_id, root)
    if not path.exists():
        return []
    events = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{EVENTS_FILE}:{line_no}: {exc.msg}") from exc
    return events


def _legacy_summary(work_id: str, root: Path | None = None) -> dict[str, Any]:
    run_dir = _run_dir(work_id, root)
    artifacts = [
        path.relative_to(run_dir).as_posix()
        for path in sorted(run_dir.rglob("*"))
        if path.is_file() and path.name not in {RUN_FILE, EVENTS_FILE}
    ]
    return {
        "work_id": work_id,
        "state": STATE_LEGACY,
        "lane": "legacy",
        "phase": "inferred",
        "artifacts": artifacts,
        "run_dir": str(run_dir),
    }


def list_runs(root: Path | None = None, include_archived: bool = False) -> list[dict[str, Any]]:
    runs_root = _runs_root(root)
    if not runs_root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for run_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        payload = _load_run(run_dir.name, root)
        if payload is None:
            payload = _legacy_summary(run_dir.name, root)
        if not include_archived and payload.get("state") == STATE_ARCHIVED:
            continue
        rows.append(payload)
    return rows


def status(work_id: str, root: Path | None = None) -> dict[str, Any]:
    payload = _load_run(work_id, root)
    if payload is not None:
        return payload
    run_dir = _run_dir(work_id, root)
    if run_dir.exists():
        return _legacy_summary(work_id, root)
    raise FileNotFoundError(f"run not found: {work_id}")


def history(work_id: str, root: Path | None = None) -> list[dict[str, Any]]:
    if _load_run(work_id, root) is None and not _run_dir(work_id, root).exists():
        raise FileNotFoundError(f"run not found: {work_id}")
    return _load_events(work_id, root)


def _missing_gate_items(payload: dict[str, Any], transition: Transition) -> list[str]:
    artifacts = payload.get("artifacts", {})
    dispositions = payload.get("dispositions", {})
    missing = [
        f"artifact:{name}"
        for name in transition.required_artifacts
        if not artifacts.get(name)
    ]
    missing.extend(
        f"disposition:{name}"
        for name in transition.required_dispositions
        if not dispositions.get(name)
    )
    return missing


def apply_transition(
    work_id: str,
    event_name: str,
    *,
    artifacts: dict[str, str] | None = None,
    dispositions: dict[str, str] | None = None,
    note: str | None = None,
    root: Path | None = None,
) -> tuple[bool, dict[str, Any], list[str]]:
    if event_name not in TRANSITIONS:
        return False, {}, [f"unknown event: {event_name}"]
    transition = TRANSITIONS[event_name]
    current = _load_run(work_id, root)
    current_state = current.get("state") if current else None
    if current_state not in transition.from_states:
        expected = ", ".join(state or "<new>" for state in transition.from_states)
        actual = current_state or "<new>"
        return False, current or {}, [
            f"invalid transition: {event_name} requires {expected}; current state is {actual}"
        ]

    now = _now()
    payload = dict(current or {})
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("work_id", work_id)
    payload.setdefault("created_at", now)
    payload.setdefault("artifacts", {})
    payload.setdefault("dispositions", {})
    payload.setdefault("gates", {})
    payload["artifacts"].update(artifacts or {})
    payload["dispositions"].update(dispositions or {})

    missing = _missing_gate_items(payload, transition)
    if missing:
        gate = f" for {transition.gate}" if transition.gate else ""
        return False, current or {}, [f"missing{gate}: {item}" for item in missing]

    previous_state = current_state
    if transition.to_state == STATE_RETURN:
        next_state = payload.get("return_state")
        if not next_state or next_state in {STATE_PAUSED, STATE_BLOCKED, STATE_ARCHIVED}:
            return False, current or {}, ["missing valid return_state for resume"]
        payload.pop("return_state", None)
        next_lane = payload.pop("return_lane", None) or STATE_LANES.get(next_state, transition.lane)
    else:
        next_state = transition.to_state
        next_lane = transition.lane
    if event_name in {"pause", "block"} and previous_state:
        payload["return_state"] = previous_state
        payload["return_lane"] = payload.get("lane") or STATE_LANES.get(previous_state)
    payload["state"] = next_state
    payload["lane"] = next_lane
    payload["phase"] = next_state
    payload["updated_at"] = now
    payload["last_event"] = event_name
    payload["gates"][event_name] = now
    if note:
        payload["next_action"] = note
    else:
        payload.pop("next_action", None)

    event = {
        "at": now,
        "event": event_name,
        "from": previous_state,
        "to": next_state,
        "artifacts": artifacts or {},
        "dispositions": dispositions or {},
    }
    if note:
        event["note"] = note

    _write_run(work_id, payload, root)
    _append_event(work_id, event, root)
    return True, payload, []


def verify(work_id: str, root: Path | None = None) -> tuple[bool, list[str], dict[str, Any]]:
    payload = status(work_id, root)
    if payload.get("state") == STATE_LEGACY:
        return True, ["legacy/inferred: no canonical run.json"], payload
    messages: list[str] = []
    ok = True
    if payload.get("schema_version") != SCHEMA_VERSION:
        ok = False
        messages.append(f"schema_version: expected {SCHEMA_VERSION}")
    try:
        events = _load_events(work_id, root)
    except ValueError as exc:
        return False, [str(exc)], payload
    if not events:
        ok = False
        messages.append("events: missing transition history")
    elif events[-1].get("to") != payload.get("state"):
        ok = False
        messages.append(
            f"state/history mismatch: run.json={payload.get('state')} events.jsonl={events[-1].get('to')}"
        )
    if payload.get("last_event") and events and events[-1].get("event") != payload.get("last_event"):
        ok = False
        messages.append("last_event does not match latest history event")
    if ok:
        messages.append("ok")
    return ok, messages, payload


def _print_run(payload: dict[str, Any]) -> None:
    print(f"work id:     {payload.get('work_id')}")
    print(f"state:       {payload.get('state')}")
    print(f"lane:        {payload.get('lane', 'n/a')}")
    print(f"phase:       {payload.get('phase', 'n/a')}")
    if payload.get("updated_at"):
        print(f"updated:     {payload['updated_at']}")
    if payload.get("next_action"):
        print(f"next action: {payload['next_action']}")
    artifacts = payload.get("artifacts") or {}
    if isinstance(artifacts, dict) and artifacts:
        print("artifacts:")
        for key, value in sorted(artifacts.items()):
            print(f"- {key}: {value}")
    elif isinstance(artifacts, list) and artifacts:
        print("artifacts:")
        for value in artifacts:
            print(f"- {value}")
    dispositions = payload.get("dispositions") or {}
    if dispositions:
        print("dispositions:")
        for key, value in sorted(dispositions.items()):
            print(f"- {key}: {value}")


def cmd_list(args) -> int:
    rows = list_runs(include_archived=args.all)
    if args.json:
        print(json.dumps({"runs": rows}, indent=2, sort_keys=True))
        return 0
    if not rows:
        print("no runs")
        return 0
    print("WORK ID                         STATE                  LANE        UPDATED")
    for payload in rows:
        print(
            f"{payload.get('work_id', ''):<31} "
            f"{payload.get('state', ''):<22} "
            f"{payload.get('lane', 'n/a'):<11} "
            f"{payload.get('updated_at', 'n/a')}"
        )
    return 0


def cmd_status(args) -> int:
    try:
        payload = status(args.work_id)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    _print_run(payload)
    return 0


def cmd_history(args) -> int:
    try:
        events = history(args.work_id)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return 1
    if args.json:
        print(json.dumps({"events": events}, indent=2, sort_keys=True))
        return 0
    if not events:
        print("no events")
        return 0
    for event in events:
        print(f"{event.get('at')}  {event.get('event')}  {event.get('from')} -> {event.get('to')}")
    return 0


def cmd_verify(args) -> int:
    try:
        ok, messages, payload = verify(args.work_id)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(str(exc))
        return 1
    if args.json:
        print(json.dumps({"ok": ok, "messages": messages, "run": payload}, indent=2, sort_keys=True))
        return 0 if ok else 1
    for message in messages:
        print(message)
    return 0 if ok else 1


def cmd_transition(args) -> int:
    try:
        artifacts = parse_assignments(args.artifact, "--artifact")
        dispositions = parse_assignments(args.disposition, "--disposition")
    except ValueError as exc:
        print(str(exc))
        return 1
    ok, payload, errors = apply_transition(
        args.work_id,
        args.event,
        artifacts=artifacts,
        dispositions=dispositions,
        note=args.note,
    )
    if args.json:
        print(json.dumps({"ok": ok, "errors": errors, "run": payload}, indent=2, sort_keys=True))
        return 0 if ok else 1
    if not ok:
        print(f"transition refused: {args.event}")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"transition accepted: {args.event}")
    print(f"state: {payload.get('state')}")
    return 0
