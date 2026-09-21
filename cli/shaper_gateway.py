"""Bounded, single-project Shaper ingress for Flow's existing run lifecycle."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fsutil import write_atomic
from runstate import apply_transition

MAX_FIELD = 4000
MAX_EVIDENCE = 16000
MAX_RUNS_SCANNED = 200
MAX_RUN_PROJECTION = 65536
READABLE_ARTIFACTS = frozenset({
    "requirements.md", "acceptance-criteria.md", "solution.md", "plan.md",
    "review.md", "HANDOFF.md", "validation-results.md", "archive.md",
    "shaper-submission.json",
})


def _project(root: Path) -> Path:
    root = root.expanduser().resolve(strict=True)
    if (root / ".flow").is_symlink():
        raise ValueError("symlinked Flow overlay is not available through MCP")
    if not (root / ".flow" / "PROJECT.md").is_file():
        raise ValueError("configured root is not a Flow project")
    return root


def _text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    value = value.strip()
    if not value or len(value) > MAX_FIELD or "\x00" in value:
        raise ValueError(f"{name} must contain 1-{MAX_FIELD} characters")
    return value


def current_state(root: Path, limit: int = 20) -> dict[str, Any]:
    root = _project(root)
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    runs_root = root / ".flow" / "runs"
    if runs_root.is_symlink():
        raise ValueError("symlinked run storage is not readable through MCP")
    rows = []
    if runs_root.exists():
        for count, run_dir in enumerate(runs_root.iterdir(), start=1):
            if count > MAX_RUNS_SCANNED:
                raise ValueError("run inventory exceeds MCP scan limit")
            if run_dir.is_symlink():
                raise ValueError("symlinked run storage is not readable through MCP")
            if not run_dir.is_dir():
                continue
            projection = run_dir / "run.json"
            if projection.is_symlink():
                raise ValueError("symlinked run projection is not readable through MCP")
            if projection.is_file():
                if projection.stat().st_size > MAX_RUN_PROJECTION:
                    raise ValueError("run projection exceeds MCP read limit")
                row = json.loads(projection.read_text(encoding="utf-8"))
            else:
                row = {"work_id": run_dir.name, "state": "legacy/inferred", "lane": "legacy"}
            if row.get("state") != "archived":
                rows.append(row)
    rows.sort(key=lambda row: row.get("updated_at", ""), reverse=True)
    return {
        "project": root.name,
        "runs": [{key: (str(row.get(key))[:500] if key == "next_action" and row.get(key) else row.get(key))
                  for key in ("work_id", "state", "lane", "updated_at", "next_action")}
                 for row in rows[:limit]],
        "remaining_run_count": max(0, len(rows) - limit),
    }


def run_evidence(root: Path, work_id: str, artifact: str) -> dict[str, Any]:
    root = _project(root)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", work_id):
        raise ValueError("invalid work id")
    if artifact not in READABLE_ARTIFACTS:
        raise ValueError("artifact is not on the readable list")
    path = root / ".flow" / "runs" / work_id / artifact
    runs_path = root / ".flow" / "runs"
    if runs_path.is_symlink():
        raise FileNotFoundError("artifact not found")
    runs_root = runs_path.resolve()
    if (path.parent.is_symlink() or path.is_symlink() or
            path.resolve().parent != runs_root / work_id or not path.is_file()):
        raise FileNotFoundError("artifact not found")
    projection = path.parent / "run.json"
    if projection.is_symlink():
        raise FileNotFoundError("run projection not found")
    if projection.is_file():
        if projection.stat().st_size > MAX_RUN_PROJECTION:
            raise ValueError("run projection exceeds MCP read limit")
        run_state = json.loads(projection.read_text(encoding="utf-8"))["state"]
    else:
        run_state = "legacy/inferred"
    if path.stat().st_size > MAX_EVIDENCE:
        raise ValueError("artifact exceeds read limit")
    return {"work_id": work_id, "state": run_state, "artifact": artifact,
            "content": path.read_text(encoding="utf-8")}


def submit_charter(root: Path, *, goal: str, outcomes: str, constraints: str,
                   execution_envelope: str, source: str = "chatgpt-shaper") -> dict[str, Any]:
    root = _project(root)
    runs_root = root / ".flow" / "runs"
    if runs_root.is_symlink():
        raise ValueError("symlinked run storage is not writable through MCP")
    submission = {
        "schema_version": 1,
        "status": "proposed",
        "source": _text(source, "source"),
        "goal": _text(goal, "goal"),
        "outcomes": _text(outcomes, "outcomes"),
        "constraints": _text(constraints, "constraints"),
        "execution_envelope": _text(execution_envelope, "execution_envelope"),
        "submitted_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    work_id = f"shaper-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:12]}"
    relative = Path(".flow") / "runs" / work_id / "shaper-submission.json"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=False)
    write_atomic(path, json.dumps(submission, indent=2, sort_keys=True) + "\n", mode=0o600)
    ok, run, errors = apply_transition(
        work_id, "start-definition", root=root,
        artifacts={"shaper_submission": str(relative)},
        note="Review Shaper proposal and define requirements before approval or execution.",
    )
    if not ok:
        raise RuntimeError("Flow rejected Shaper submission: " + "; ".join(errors))
    return {"work_id": work_id, "state": run["state"], "submission": str(relative),
            "approval": "required", "execution_started": False}
