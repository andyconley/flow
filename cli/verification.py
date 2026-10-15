"""Version-bound evidence at Flow lifecycle boundaries, not an execution controller.

OpenHands owns execution. These records bind operator-run checks and reviewed
changes to approved artifacts. They do not authenticate people sharing an OS user.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4
import hashlib
import json
import math
import os
import subprocess
import time

from fsutil import write_atomic

REVISION = 1
REPAIR_LIMIT = 2
EXTRAS = {"plan": {"verification_plan": "verification-plan.json"},
          "implement": {"verification": "verification.json"}}


def enabled(run):
    return run.get("runtime") == "openhands" and run.get("verification_revision") == REVISION


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def stamp():
    return datetime.now(timezone.utc).isoformat()


def parse_time(value):
    # Python 3.10's fromisoformat does not accept runstate's trailing Z.
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("verification timestamps require an explicit timezone")
    return parsed


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"verification: {label} must be nonempty text")
    return value


def regular(root, relative, *, run_dir=None):
    text(relative, "path")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or ".." in parts.parts or "\\" in relative or str(parts) != relative:
        raise ValueError("verification: paths must be canonical project-relative paths")
    path = root / relative
    if any((root.joinpath(*parts.parts[:i])).is_symlink() for i in range(1, len(parts.parts) + 1)):
        raise ValueError(f"verification: symlink not allowed: {relative}")
    if not path.is_file() or not path.resolve().is_relative_to((run_dir or root).resolve()):
        raise ValueError(f"verification: missing or escaping regular file: {relative}")
    return path


def file_identity(root, relative):
    path = regular(root, relative)
    return {"sha256": file_sha(path), "executable": bool(path.stat().st_mode & 0o111)}


def workspace(root):
    """Include tracked, deleted and nonignored untracked files, modes and HEAD.

    Only .flow/runs (evidence/session output) and Git metadata are omitted.
    Ignored dependencies must be registered explicitly as evaluation inputs.
    """
    def git(*args, optional=False):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
        if result.returncode and not optional:
            raise ValueError("verification requires the Git project root; cannot fingerprint workspace")
        return result.stdout
    if Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve() != root.resolve():
        raise ValueError("verification requires the Git project root")
    head = git("rev-parse", "--verify", "HEAD", optional=True).decode().strip() or None
    names = set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").split(b"\0")) - {b""}
    files = {}
    for name in sorted(names):
        relative = os.fsdecode(name)
        if relative == ".flow/runs" or relative.startswith(".flow/runs/"):
            continue
        path = root / relative
        if path.is_symlink():
            raise ValueError(f"verification: workspace symlink requires explicit external verification: {relative}")
        if not path.exists():
            files[relative] = None
        else:
            files[relative] = file_identity(root, relative)
    return {"head": head, "sha256": digest({"head": head, "files": files})}


def load_plan(root, run):
    content = regular(root, run["artifacts"]["verification_plan"]).read_bytes()
    approved = run.get("approved_artifact_digests", {}).get("verification_plan")
    if approved is not None and sha(content) != approved:
        raise ValueError("verification plan changed after approval")
    plan = json.loads(content)
    if not isinstance(plan, dict) or plan.get("schema_version") != REVISION or plan.get("repair_limit") != REPAIR_LIMIT:
        raise ValueError("verification plan requires schema_version=1 and repair_limit=2")
    checks = plan.get("checks")
    inputs = plan.get("evaluation_inputs")
    if not isinstance(checks, list) or not checks or not isinstance(inputs, list) or not inputs:
        raise ValueError("verification plan requires checks and registered evaluation_inputs")
    ids = []
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("verification plan check must be an object")
        ids.append(text(check.get("id"), "check id"))
        if check["id"] == "review-output":
            raise ValueError("review-output is reserved for review contract repairs")
        text(check.get("criterion"), "criterion reference")
        argv = check.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(v, str) and v for v in argv):
            raise ValueError("verification check argv must be a nonempty string array")
    if len(ids) != len(set(ids)) or len(inputs) != len(set(inputs)):
        raise ValueError("verification check IDs and evaluation inputs must be unique")
    for relative in inputs:
        text(relative, "evaluation input")
        if relative.startswith((".flow/runs/", ".git/")) or relative == ".git":
            raise ValueError("evaluation inputs cannot be runtime output or Git metadata")
        regular(root, relative)
    return plan


def registered(root, plan):
    return {relative: file_identity(root, relative) for relative in plan["evaluation_inputs"]}


def bindings(run):
    return {key: run.get("approved_artifact_digests", {}).get(key)
            for key in ("requirements", "acceptance_criteria", "plan", "handoff", "validation_plan", "verification_plan")}


def read_record(root, run):
    regular(root, f".flow/runs/{run['work_id']}/run.json")
    path = root / ".flow/runs" / run["work_id"] / "verification.json"
    if not path.exists():
        return {"schema_version": REVISION, "work_id": run["work_id"], "approved": bindings(run),
                "checks": [], "test_change_reviews": []}
    record = json.loads(regular(root, path.relative_to(root).as_posix()).read_text())
    if (not isinstance(record, dict) or record.get("schema_version") != REVISION
            or record.get("work_id") != run["work_id"] or record.get("approved") != bindings(run)
            or not isinstance(record.get("checks"), list) or not isinstance(record.get("test_change_reviews"), list)):
        raise ValueError("verification record does not bind to this approved workflow")
    return record


def latest(record):
    return {check["check_id"]: check for check in record["checks"]}


def save_record(root, run, record):
    regular(root, f".flow/runs/{run['work_id']}/run.json")
    path = root / ".flow/runs" / run["work_id"] / "verification.json"
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("verification output must be a current-run regular file")
    write_atomic(path, json.dumps(record, indent=2) + "\n")


def gate(root, run, event, dispositions):
    """Validate/mutate a tentative run projection, before its existing commit point."""
    if not enabled(run):
        return
    directory = root / ".flow/runs" / run["work_id"]
    if event == "approve-plan":
        plan = load_plan(root, run)
        workspace(root)  # fail early for unsupported roots/files
        run["evaluation_baseline"] = registered(root, plan)
    elif event in {"mark-handback-ready", "start-review", "accept-review"}:
        if event == "mark-handback-ready" and run.get("review_outputs") and run["review_outputs"][-1]["status"] != "complete":
            raise ValueError("incomplete independent review must be repaired before handback")
        if event == "accept-review":
            import review_output
            review_output.validate_approval(root, run)
        plan = load_plan(root, run)
        record = read_record(root, run)
        current = registered(root, plan)
        expected_workspace = workspace(root)
        results = latest(record)
        for result in record["checks"]:
            for field in ("id", "check_id", "session_id", "assignment_id", "environment", "started_at"):
                text(result.get(field), field)
            parse_time(result["started_at"])
            log = regular(root, result["log"]["path"], run_dir=directory)
            if result.get("status") == "incomplete":
                if any(result.get(field) is not None for field in ("exit_code", "elapsed_seconds", "finished_at")) or result["log"].get("sha256") is not None:
                    raise ValueError("verification: incomplete check must retain unknown outcome fields")
                if not any(a["after_record"] == result["id"] for a in run.get("repair_attempts", [])):
                    raise ValueError("verification: incomplete check requires a targeted repair allocation")
                # A lost process never supplied a trustworthy final result or
                # log digest. Keep those unknown; only a later completed check
                # can satisfy the acceptance gate.
                continue
            text(result.get("finished_at"), "finished_at")
            elapsed = result.get("elapsed_seconds")
            if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError("verification: invalid elapsed_seconds")
            if type(result.get("exit_code")) is not int:
                raise ValueError("verification: exit_code must be an integer")
            if parse_time(result["finished_at"]) < parse_time(result["started_at"]):
                raise ValueError("verification: check timestamps out of order")
            if file_sha(log) != result["log"]["sha256"]:
                raise ValueError("verification: test log changed")
        for attempt in run.get("repair_attempts", []):
            if attempt["check_id"] == "review-output":
                if not any(r["id"] == attempt["after_record"] and r["status"] == "incomplete" for r in run.get("review_outputs", [])):
                    raise ValueError("review repair requires its incomplete output record")
                proof = regular(root, attempt["failure_evidence"]["path"], run_dir=directory)
                if sha(proof.read_bytes()) != attempt["failure_evidence"]["sha256"]:
                    raise ValueError("review repair failure evidence changed")
                continue
            if not any(c["id"] == attempt["after_record"] and c["check_id"] == attempt["check_id"] for c in record["checks"]):
                raise ValueError("verification: repair failure result missing from evidence")
            proof = regular(root, attempt["failure_evidence"]["path"], run_dir=directory)
            if sha(proof.read_bytes()) != attempt["failure_evidence"]["sha256"]:
                raise ValueError("verification: repair failure evidence changed")
        for check in plan["checks"]:
            result = results.get(check["id"], {})
            if (result.get("exit_code") != 0 or result.get("status") != "passed"
                    or result.get("argv") != check["argv"] or result.get("workspace") != expected_workspace
                    or result.get("evaluation_inputs") != current):
                raise ValueError(f"verification: missing, failed or stale check: {check['id']}")
        baseline = run["evaluation_baseline"]
        changes = {path: {"approved": before, "current": current[path]}
                   for path, before in baseline.items() if before != current[path]}
        if changes:
            producer_sessions = {result["session_id"] for result in record["checks"]}
            valid = False
            for review in record["test_change_reviews"]:
                if (review.get("changes") == changes and review.get("disposition") == "equivalent"
                        and review.get("reviewer_session_id") not in producer_sessions):
                    text(review.get("reviewer"), "reviewer")
                    text(review.get("reviewer_session_id"), "reviewer session")
                    text(review.get("rationale"), "test repair rationale")
                    proof = regular(root, review["evidence"]["path"], run_dir=directory)
                    valid = bool(proof.read_bytes().strip()) and sha(proof.read_bytes()) == review["evidence"]["sha256"]
                    if valid:
                        break
            if not valid:
                raise ValueError("verification: changed evaluation inputs need independent equivalence review; material criterion changes need separate user approval in a successor workflow")
        run["artifacts"]["verification"] = (directory / "verification.json").relative_to(root).as_posix()
    elif event == "request-refinement":
        plan = load_plan(root, run)
        check_id = text(dispositions.get("failed_check"), "failed_check")
        review_repair = check_id == "review-output"
        if not review_repair and check_id not in {c["id"] for c in plan["checks"]}:
            raise ValueError("verification: failed_check is not in the approved plan")
        for field in ("specialist", "narrowed_scope", "reason"):
            text(dispositions.get(field), field)
        proof = regular(root, dispositions.get("failure_evidence"), run_dir=directory)
        if not proof.read_bytes().strip():
            raise ValueError("verification: failure evidence must be nonempty")
        attempts = list(run.get("repair_attempts", []))
        used = sum(a["check_id"] == check_id for a in attempts)
        if used >= REPAIR_LIMIT:
            raise ValueError("verification: repair budget exhausted; block and escalate to the user")
        if review_repair:
            outcome = (run.get("review_outputs") or [{}])[-1]
            if outcome.get("status") != "incomplete":
                raise ValueError("review repair requires a recorded incomplete review")
            if parse_time(stamp()) >= parse_time(outcome["deadline"]):
                raise ValueError("review deadline exhausted; block and escalate to the user")
            previous = outcome["id"]
        else:
            previous = latest(read_record(root, run)).get(check_id, {}).get("id")
        if previous is None:
            raise ValueError("verification: record the check before allocating its repair")
        if any(a["check_id"] == check_id and a["after_record"] == previous for a in attempts):
            raise ValueError("verification: repair already allocated; run the check before allocating another")
        attempts.append({"check_id": check_id, "attempt": used + 1, "after_record": previous,
                         "at": stamp(), "specialist": dispositions["specialist"],
                         "narrowed_scope": dispositions["narrowed_scope"], "reason": dispositions["reason"],
                         "failure_evidence": {"path": dispositions["failure_evidence"], "sha256": sha(proof.read_bytes())}})
        run["repair_attempts"] = attempts


def capture(root, run, check_id, session_id, assignment_id, environment, timeout=1800):
    if not enabled(run) or run["state"] != "implementing":
        raise ValueError("verification checks require an implementing verification-v1 workflow")
    for value, label in ((session_id, "session"), (assignment_id, "assignment"), (environment, "environment")):
        text(value, label)
    if not 0 < timeout <= 1800:
        raise ValueError("verification timeout must be between 1 and 1800 seconds")
    plan = load_plan(root, run)
    check = next((c for c in plan["checks"] if c["id"] == check_id), None)
    if check is None:
        raise ValueError("verification: unknown check ID")
    record = read_record(root, run)
    previous = latest(record).get(check_id)
    allocations = [a for a in run.get("repair_attempts", []) if a["check_id"] == check_id]
    if previous and previous["status"] != "passed" and not any(a["after_record"] == previous["id"] for a in allocations):
        raise ValueError("verification: failed check requires targeted repair allocation; exhausted budgets must escalate")
    before, inputs = workspace(root), registered(root, plan)
    identifier = uuid4().hex
    relative = f".flow/runs/{run['work_id']}/verification/{identifier}.log"
    log = root / relative
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.parent.is_symlink() or not log.parent.resolve().is_relative_to((root / ".flow/runs" / run['work_id']).resolve()):
        raise ValueError("verification log directory escapes run")
    started, clock = stamp(), time.monotonic()
    result = {"id": identifier, "check_id": check_id, "argv": check["argv"],
              "session_id": session_id, "assignment_id": assignment_id, "environment": environment,
              "started_at": started, "finished_at": None, "elapsed_seconds": None,
              "exit_code": None, "status": "incomplete", "workspace": before, "evaluation_inputs": inputs,
              "log": {"path": relative, "sha256": None}, "repair_attempt": len(allocations)}
    # Commands are the operator-approved argv, never parsed as a shell string.
    # A file streams output without accumulating unbounded test output in memory.
    with log.open("xb") as output:
        # Persist the invocation before running any code. A crash after launch
        # consumes this allocation instead of silently reusing it on resume.
        record["checks"].append(result)
        save_record(root, run, record)
        try:
            process = subprocess.Popen(check["argv"], cwd=root, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            try:
                code = process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                import signal
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                code = 124
        except OSError as exc:
            output.write(f"Could not start approved check: {type(exc).__name__}\n".encode())
            code = 127
    after = workspace(root)
    result.update({"finished_at": stamp(), "elapsed_seconds": round(time.monotonic() - clock, 3),
              "exit_code": code, "status": "passed" if code == 0 and before == after and inputs == registered(root, plan) else "failed",
              "log": {"path": relative, "sha256": file_sha(log)}})
    save_record(root, run, record)
    return result


def review_change(root, run, reviewer, reviewer_session_id, rationale, evidence, disposition):
    if not enabled(run) or run["state"] != "implementing":
        raise ValueError("test-change review requires an implementing verification-v1 workflow")
    if disposition != "equivalent":
        raise ValueError("material or uncertain criterion changes require separate user approval in a successor workflow; this command cannot approve them")
    record = read_record(root, run)
    for value, label in ((reviewer, "reviewer"), (reviewer_session_id, "reviewer session"), (rationale, "rationale")):
        text(value, label)
    if reviewer_session_id in {c["session_id"] for c in record["checks"]}:
        raise ValueError("test-change reviewer must be independent of producing sessions")
    current = registered(root, load_plan(root, run))
    changes = {path: {"approved": before, "current": current[path]}
               for path, before in run["evaluation_baseline"].items() if before != current[path]}
    if not changes:
        raise ValueError("no registered evaluation input changed")
    directory = root / ".flow/runs" / run["work_id"]
    proof = regular(root, evidence, run_dir=directory)
    if not proof.read_bytes().strip():
        raise ValueError("test-change review needs nonempty before/after proof")
    if run.get("review_outputs"):
        import review_output
        outcome = run["review_outputs"][-1]
        if (outcome["status"] != "complete" or outcome.get("test_equivalence") != "EQUIVALENT"
                or outcome["session_id"] != reviewer_session_id
                or outcome["evidence"]["path"] != evidence):
            raise ValueError("equivalence receipt requires the current independent explicit review output")
        review_output.current(root, run, outcome)
    record["test_change_reviews"].append({"reviewer": reviewer, "reviewer_session_id": reviewer_session_id,
        "rationale": rationale, "disposition": disposition, "changes": changes, "at": stamp(),
        "evidence": {"path": evidence, "sha256": sha(proof.read_bytes())}})
    save_record(root, run, record)
    return {"status": "recorded", "changes": changes}


def report(root, run, usage_rows=None):
    if not enabled(run):
        return {"status": "historical_unbound", "actual_billed_cost": None}
    if "verification_plan" not in run.get("artifacts", {}):
        return {"status": "awaiting_plan", "aggregate_generated_tokens": None, "sdk_estimated_cost": None,
                "actual_billed_cost": None, "human_review_seconds": None}
    record = read_record(root, run)
    attempts = run.get("repair_attempts", [])
    sessions = [*run.get("sessions", {}).values(), *run.get("prior_sessions", [])]
    import runstate
    rejections = [e for e in runstate.history(run["work_id"], root) if e["event"] == "verification-rejection"]
    rows = [row for row in (usage_rows or []) if row["work_id"] == run["work_id"]]
    estimates = [r.get("sdk_estimated_cost") for r in rows]
    elapsed = [c.get("elapsed_seconds") for c in record["checks"]]
    # Combined SDK estimates already have an existing deduplicating usage store.
    # Do not sum parent/child rollups or label absent native bills as zero.
    return {"status": "verification_v1", "checks_recorded": len(record["checks"]),
            "failed_checks": sum(c["status"] == "failed" for c in record["checks"]),
            "incomplete_checks": sum(c["status"] == "incomplete" for c in record["checks"]),
            "repair_attempts": len(attempts), "repair_limit_per_check": REPAIR_LIMIT,
            "repairs_by_check": {c["id"]: sum(a["check_id"] == c["id"] for a in attempts)
                                 for c in load_plan(root, run)["checks"]},
            "test_change_reviews": len(record["test_change_reviews"]),
            "gate_rejections": len(rejections),
            "handoff_rejections": sum(e["gate"] in {"mark-handback-ready", "start-review"} for e in rejections),
            "check_elapsed_seconds": sum(elapsed) if all(isinstance(v, (int, float)) for v in elapsed) else None,
            "observed_check_elapsed_seconds": sum(v for v in elapsed if isinstance(v, (int, float))),
            "session_ids": [s["conversation_id"] for s in sessions],
            "usage_join": {"work_id": run["work_id"], "source": "existing openhands_usage reporting_rows"},
            "aggregate_generated_tokens": None,
            "observed_sdk_estimated_cost": sum(estimates) if estimates and all(isinstance(c, (int, float)) for c in estimates) else None,
            "usage_coverage": "observed imported rows only; whole-workflow completeness is not established",
            "sdk_estimated_cost": None,
            "actual_billed_cost": None,
            "human_review_seconds": None,
            "workflow_elapsed_seconds": (parse_time(run["updated_at"]) - parse_time(run["created_at"])).total_seconds()}
