"""Cancel and abandon a chartered v8 attempt, keeping its uncertainty sealed (ADR 0019)."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import signal
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager, suppress as contextlib_suppress
from pathlib import Path
from typing import Any, Callable, Iterator

import process_identity
from delivery_cancel import CANCEL_REQUEST
from claude_edit_worker import MAX_TRACE_BYTES
from delivery_control import run_lock
from delivery_projection import lead_claim_active
from delivery_recovery import (ATTEMPT_DIR_UNSAFE, ATTEMPT_FINISHED, ATTEMPT_NOT_LIVE, ATTEMPT_NOT_STARTED,
                               CANCEL_TIMEOUT, CANCEL_UNSUPPORTED, FOREIGN_MACHINE, LEAD_GUARD_LEDGER_UNREADABLE,
                               OWNER_GENERATION_STALE, PROCESS_IDENTITY_MISMATCH, RecoveryRefused,
                               build_recovery_block, recovery_eligibility)
from execution_contracts import ContractError, canonical, envelope_digest, validate_receipt
from execution_ledger import ExecutionLedger, utc_now
from fsutil import repo_root

# The receipt validator's own bound on either trace (execution_contracts).
MAX_SEALED_TRACE_BYTES = MAX_TRACE_BYTES
TRACE_FILES = ("claude-implementer.debug.log", "claude-implementer.events.ndjson")
TRACE_FIELDS = {"claude-implementer.debug.log": "diagnostic_trace", "claude-implementer.events.ndjson": "event_trace"}


def _file_digest(path: Path) -> tuple[str, int] | None:
    """Digest and size of a regular file, streamed: no symlink, no FIFO, no unbounded read."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(fd, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        return digest.hexdigest(), size
    finally:
        os.close(fd)


def build_terminal_receipt(envelope: dict[str, Any], attempt_dir: Path, snapshot: dict[str, Any],
                           blocks: dict[str, Any], *, status: str, termination: dict[str, Any]) -> dict[str, Any]:
    """Render a cancelled or abandoned receipt from one ledger snapshot and the envelope.

    Pure apart from reading attempt files: it makes no ledger or lock call,
    runs no test, and never touches the worktree. Evidence Flow can no longer
    read is recorded as null with an ``evidence_damage`` entry instead of
    refusing, so a damaged attempt can still be sealed.
    """
    damage: list[dict[str, Any]] = []
    raw_baseline = process_identity.read_bounded(attempt_dir / "baseline.json")
    try:
        baseline = json.loads(raw_baseline) if raw_baseline is not None else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        baseline = None
    if not isinstance(baseline, dict):
        baseline = None
        damage.append({"kind": "baseline_missing"})
    evidence: dict[str, Any] = {"source_commit": envelope["source_commit"], "worktree": envelope["worktree"],
                                "allowed_paths": envelope["allowed_paths"], "baseline": baseline,
                                "edit": None, "tests": None, "verifier_input_sha256": None}
    for name in TRACE_FILES:
        found = _file_digest(attempt_dir / name)
        if found is None:
            continue
        record = {"path": name, "sha256": found[0], "bytes": found[1]}
        if found[1] > MAX_SEALED_TRACE_BYTES:
            damage.append({"kind": "trace_oversized", **record})
        else:
            evidence[TRACE_FIELDS[name]] = record
    draft = _file_digest(attempt_dir / "receipt.json")
    replaced = draft[0] if draft is not None else None
    if replaced is not None:
        damage.append({"kind": "draft_receipt_replaced", "sha256": replaced})
    receipt: dict[str, Any] = {
        "schema_version": 1, "execution_protocol_version": envelope["execution_protocol_version"],
        "work_id": envelope["work_id"], "attempt_id": envelope["attempt_id"],
        "envelope_digest": envelope_digest(envelope), "charter_digest": envelope["charter_digest"],
        "manifest_digest": envelope["manifest_digest"], "charter_sources": envelope["charter_sources"],
        "run_protocol_revision": 2, "roster": envelope["roster"], "status": status, "reason": termination["cause"],
        "manager_calls": snapshot["manager_calls"], "actions": snapshot["actions"], "replans": snapshot["replans"],
        "checkpoints": snapshot.get("magentic_checkpoints", []), "failure_detail": "",
        "evidence": evidence, "created_at": utc_now(),
        "verifier_inputs": snapshot.get("verifier_inputs", []),
        "verifier_evaluations": snapshot.get("verifier_evaluations", []),
        "verifier_usage": snapshot["verifier_usage"],
    }
    for key in ("lineage_usage", "expansion", "manager_progress"):
        if blocks.get(key) is not None:
            receipt[key] = blocks[key]
    if snapshot.get("recoveries"):
        receipt["recovery"] = build_recovery_block(snapshot, replaced_draft_sha256=replaced)
    receipt.update({field: envelope[field] for field in ("shaper_contract_digest", "delivery_charter_digest",
                                                          "handoff_digest", "delivery_lead_claim_digest",
                                                          "delivery_lead_claim")})
    receipt["termination"] = {"actor": termination["actor"], "explanation": termination["explanation"],
                              "cause": termination["cause"], "owner_generation": snapshot["owner_generation"],
                              "lead_generation": envelope["delivery_lead_claim"]["generation"]}
    receipt["evidence_damage"] = damage
    return receipt


def terminal_receipt_renderer(envelope: dict[str, Any], attempt_dir: Path, *, status: str, actor: str,
                              explanation: str, cause: str) -> Callable[[dict[str, Any], dict[str, Any]], bytes]:
    """The ``build_receipt`` callback a terminal seal runs inside its transaction."""
    def render(snapshot: dict[str, Any], blocks: dict[str, Any]) -> bytes:
        receipt = build_terminal_receipt(envelope, attempt_dir, snapshot, blocks, status=status,
                                         termination={"actor": actor, "explanation": explanation, "cause": cause})
        validate_receipt(envelope, receipt)
        return (canonical(receipt) + "\n").encode()
    return render


def _attempt_paths(root: Path | None, work_id: str, attempt_id: str, *,
                   create: bool = False) -> tuple[Path, Path, Path]:
    project_root = (root or repo_root()).resolve()
    if (not isinstance(work_id, str) or not work_id or any(part in {"", ".", ".."} for part in work_id.split("/"))
            or "/" in work_id or not isinstance(attempt_id, str) or not attempt_id
            or any(char not in "0123456789abcdef" for char in attempt_id)):
        raise ContractError("work id or attempt id is invalid")
    runs_dir = project_root / ".flow" / "runs"
    run_dir = runs_dir / work_id
    execution_dir = run_dir / "execution"
    ledger_path = execution_dir / "ledger.sqlite"
    if (any(path.is_symlink() for path in (project_root / ".flow", runs_dir, run_dir, execution_dir))
            or ledger_path.is_symlink() or not ledger_path.is_file()):
        raise RecoveryRefused(LEAD_GUARD_LEDGER_UNREADABLE, "the delivery ledger is absent or unsafe")
    attempt_dir = execution_dir / attempt_id
    if create and not os.path.lexists(attempt_dir):
        # A lost attempt directory must not dead-end the work id: abandon
        # seals into a fresh private one and records the missing evidence.
        attempt_dir.mkdir(mode=0o700)
    if attempt_dir.is_symlink() or not attempt_dir.is_dir():
        raise RecoveryRefused(ATTEMPT_DIR_UNSAFE, "the attempt directory is absent or a symlink")
    if not attempt_dir.resolve().is_relative_to(runs_dir.resolve()):
        raise RecoveryRefused(ATTEMPT_DIR_UNSAFE, "the attempt directory is outside the runs directory")
    return run_dir, attempt_dir, ledger_path


def _read_snapshot(ledger_path: Path, attempt_id: str) -> dict[str, Any]:
    try:
        snapshot = ExecutionLedger(ledger_path, read_only=True).snapshot(attempt_id)
    except (sqlite3.Error, ContractError, OSError, ValueError) as exc:
        raise RecoveryRefused(LEAD_GUARD_LEDGER_UNREADABLE, str(exc)) from None
    if snapshot["execution_protocol_version"] != 8:
        raise ContractError("cancel and abandon apply to protocol v8 attempts only")
    return snapshot


def _check_started(snapshot: dict[str, Any], expected_generation: int) -> None:
    if snapshot["status"] != "started":
        raise RecoveryRefused(ATTEMPT_NOT_STARTED, f"attempt is {snapshot['status']}")
    if snapshot["owner_generation"] != expected_generation:
        raise RecoveryRefused(OWNER_GENERATION_STALE, f"current owner generation is {snapshot['owner_generation']}")


def abandon_cause(snapshot: dict[str, Any]) -> str:
    """Why the attempt stopped, from the ledger: a pending expansion, else its latest interruption."""
    if any(item.get("status") == "pending" for item in snapshot.get("expansions", [])):
        return "expansion_paused"
    interruptions = snapshot.get("interruptions", [])
    return interruptions[-1]["cause"] if interruptions else "unmarked_process_exit"


def abandon_delivery(work_id: str, attempt_id: str, *, actor: str, explanation: str, expected_generation: int,
                     root: Path | None = None) -> dict[str, Any]:
    """Seal a stuck started v8 attempt as abandoned after reaping its recorded process groups.

    Fences: a non-blocking claim of the attempt's recovery lock held until
    the seal (a live run refuses as ``attempt_running``, a recovery or
    decision as ``recovery_in_progress``), then the run lock, then the send
    lock and the ledger transaction. Claiming the recovery lock first means a
    live parent holding the run lock through a guarded send is refused at once.
    It works whatever the lead status is and never changes the lead claim.
    """
    if type(expected_generation) is not int:
        raise ContractError("expected generation is required")
    try:
        run_dir, attempt_dir, ledger_path = _attempt_paths(root, work_id, attempt_id)
    except RecoveryRefused as exc:
        project_root = (root or repo_root()).resolve()
        execution_dir = project_root / ".flow" / "runs" / work_id / "execution"
        if exc.reason != ATTEMPT_DIR_UNSAFE or os.path.lexists(execution_dir / attempt_id):
            raise
        # Only a started attempt of this run gets its lost directory recreated.
        try:
            probe = _read_snapshot(execution_dir / "ledger.sqlite", attempt_id)
        except (RecoveryRefused, ContractError):
            raise exc from None
        if probe["envelope"]["work_id"] != work_id:
            raise exc from None
        _check_started(probe, expected_generation)
        run_dir, attempt_dir, ledger_path = _attempt_paths(root, work_id, attempt_id, create=True)
    ledger = ExecutionLedger(ledger_path)
    # The attempt's own fence first and without waiting (a live parent holds
    # the run lock through a whole send), then the run lock: the ADR 0016 order.
    with ledger.recovery_lock(attempt_id, holder="recovery"), run_lock(run_dir):
        snapshot = _read_snapshot(ledger_path, attempt_id)
        if snapshot["envelope"]["work_id"] != work_id:
            raise ContractError("attempt belongs to another run")
        _check_started(snapshot, expected_generation)
        reaped = process_identity.reap(attempt_dir)
        cause = abandon_cause(snapshot)
        with ledger.send_lock():
            sealed = ledger.seal_terminal_uncertain(
                attempt_id, "abandoned", expected_generation=expected_generation, actor=actor,
                explanation=explanation, cause=cause, receipt_path=attempt_dir / "receipt.json",
                build_receipt=terminal_receipt_renderer(snapshot["envelope"], attempt_dir, status="abandoned",
                                                        actor=actor, explanation=explanation, cause=cause))
    return {**sealed, "work_id": work_id, "cause": cause, "reaped": reaped}


def control_view(attempt_dir: Path, ledger: ExecutionLedger, attempt_id: str) -> dict[str, Any]:
    """Who, if anyone, is running the attempt: control records first, the lock probe as corroboration."""
    found = process_identity.records(attempt_dir)
    latest = found[-1] if found else None
    parent = process_identity.parent_live(latest) if latest else "unrecorded"
    return {"parent": parent, "live": parent == "live", "lock": ledger.probe_recovery_lock(attempt_id),
            "cancel_supported": bool(latest and latest.get("cancel_supported")),
            "records": [{"owner_generation": item["owner_generation"], "pid": item.get("pid"),
                         "closed": item["closed"], "verdict": process_identity.parent_live(item),
                         "groups": [{"pgid": group["pgid"], "kind": group["kind"],
                                     "alive": process_identity.group_alive(group, item)} for group in item["groups"]]}
                        for item in found]}


def next_command(work_id: str, snapshot: dict[str, Any], control: dict[str, Any], *, lead_active: bool) -> str | None:
    """The single command that moves a started v8 attempt forward, or None once it is terminal."""
    if snapshot["status"] != "started":
        return None
    attempt_id, generation = snapshot["attempt_id"], snapshot["owner_generation"]
    stop = f"--actor NAME --explanation TEXT --expected-generation {generation}"
    if control["live"]:
        return f"flow run cancel-delivery {work_id} {attempt_id} {stop}"
    if control["lock"] == "held":
        # A recovery or decision holds the fence with no live dispatching parent.
        return f"flow run inspect-delivery {work_id} --attempt-id {attempt_id}"
    pending = [item["request_id"] for item in snapshot.get("expansions", []) if item.get("status") == "pending"]
    if pending:
        return (f"flow run decide-expansion {work_id} {attempt_id} {pending[0]} --approve|--deny "
                f"--expected-generation {generation} --actor NAME --explanation TEXT")
    if recovery_eligibility(snapshot["envelope"], snapshot, lead_active=lead_active)["recoverable"]:
        return f"flow run recover-delivery-lead {work_id} {attempt_id} --actor NAME"
    return f"flow run abandon-delivery {work_id} {attempt_id} {stop}"


def stuck_attempts(root: Path | None = None) -> list[dict[str, Any]]:
    """Every started v8 attempt in the project, each with its single next command. Read-only."""
    project_root = (root or repo_root()).resolve()
    runs_dir = project_root / ".flow" / "runs"
    found: list[dict[str, Any]] = []
    if runs_dir.is_symlink() or not runs_dir.is_dir():
        return found
    for run_dir in sorted(runs_dir.iterdir()):
        ledger_path = run_dir / "execution" / "ledger.sqlite"
        if run_dir.is_symlink() or ledger_path.is_symlink() or not ledger_path.is_file():
            continue
        try:
            delivery = json.loads((run_dir / "run.json").read_text()).get("delivery")
        except (OSError, json.JSONDecodeError, AttributeError):
            delivery = None
        try:
            ledger = ExecutionLedger(ledger_path, read_only=True)
            with sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True) as db:
                columns = {row[1] for row in db.execute("PRAGMA table_info(attempts)")}
                # A ledger that predates the protocol column holds no v8 attempt.
                ids = [row[0] for row in db.execute("SELECT attempt_id FROM attempts WHERE status='started' "
                                                    "AND execution_protocol_version=8 ORDER BY rowid")
                       ] if "execution_protocol_version" in columns else []
            snapshots = [ledger.snapshot(attempt_id) for attempt_id in ids]
        except (sqlite3.Error, ContractError, OSError, ValueError) as exc:
            found.append({"work_id": run_dir.name, "attempt_id": None, "error": f"ledger unreadable: {exc}"})
            continue
        for snapshot in snapshots:
            attempt_dir = run_dir / "execution" / snapshot["attempt_id"]
            try:
                control = control_view(attempt_dir, ledger, snapshot["attempt_id"])
            except (OSError, ContractError, ValueError) as exc:
                found.append({"work_id": snapshot["work_id"], "attempt_id": snapshot["attempt_id"],
                              "error": f"control records unreadable: {exc}"})
                continue
            active = lead_claim_active(delivery, snapshot["envelope"])
            rows = snapshot["actions"] + snapshot["manager_calls"]
            found.append({
                "work_id": snapshot["work_id"], "attempt_id": snapshot["attempt_id"],
                "owner_generation": snapshot["owner_generation"], "live": control["live"],
                "parent": control["parent"], "lock": control["lock"],
                "lead_status": (delivery or {}).get("owner_status"),
                "uncertain": {"started": sum(item["status"] == "started" for item in rows),
                              "unknown": sum(item["status"] == "unknown" for item in rows)},
                "open_expansion": next((item["request_id"] for item in snapshot.get("expansions", [])
                                        if item.get("status") == "pending"), None),
                "next_command": next_command(snapshot["work_id"], snapshot, control, lead_active=active)})
    return found


SEAL_DEADLINE_SECONDS = 30
CANCEL_WAIT_SECONDS = 45


class LockDeadline(Exception):
    """A fence could not be taken before the shutdown deadline."""


@contextmanager
def _polled_flock(path: Path, deadline: float, *, private: bool = False) -> Iterator[None]:
    """Take one flock without ever blocking indefinitely: poll until ``deadline``."""
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (private and info.st_nlink != 1):
            raise ContractError(f"{path.name} must be a private regular file")
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockDeadline(path.name) from None
                time.sleep(0.02)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def parent_fences(attempt_dir: Path, ledger: ExecutionLedger, deadline: float) -> Iterator[None]:
    """The run lock then the send lock, polled; the caller already holds the recovery lock (ADR 0016 order)."""
    with _polled_flock(attempt_dir.parents[1] / ".delivery.lock", deadline), \
            _polled_flock(ledger.path.with_suffix(".send.lock"), deadline, private=True):
        yield


def valid_cancel_request(attempt_dir: Path, attempt_id: str, generation: int) -> dict[str, Any] | None:
    """The cancel request for exactly this attempt and owner generation, or None."""
    raw = process_identity.read_bounded(attempt_dir / CANCEL_REQUEST, 64 * 1024)
    try:
        request = json.loads(raw) if raw is not None else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    text = lambda value, limit: isinstance(value, str) and value.strip() and len(value) <= limit
    if (not isinstance(request, dict) or request.get("schema_version") != 1 or request.get("attempt_id") != attempt_id
            or request.get("owner_generation") != generation or not text(request.get("actor"), 256)
            or not text(request.get("explanation"), 2048) or not isinstance(request.get("nonce"), str)
            or len(request["nonce"]) != 32):
        return None
    return request


def _write_cancel_request(attempt_dir: Path, request: dict[str, Any]) -> None:
    path = attempt_dir / CANCEL_REQUEST
    if path.is_symlink():
        raise RecoveryRefused(ATTEMPT_DIR_UNSAFE, "the cancel request path is a symlink")
    temporary = attempt_dir / f".{CANCEL_REQUEST}.{uuid.uuid4().hex}"
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(canonical(request) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def stop_on_cancel(envelope: dict[str, Any], attempt_dir: Path, ledger: ExecutionLedger, *, generation: int,
                   detail: str) -> dict[str, Any]:
    """What a live parent does once SIGTERM was requested, after its stack unwound.

    Every recorded group is killed first. With a valid cancel request for this
    attempt and generation the attempt seals ``cancelled``; otherwise (a bare
    SIGTERM, a stale request, a missed fence deadline or a moved generation)
    it records a ``cancel_signal`` interruption and stays started, so abandon
    or recovery can finish it. Fences are polled, never waited on, and the
    lead claim is not consulted (the seal must work under any lead status).
    """
    aid = envelope["attempt_id"]
    try:
        reaped = process_identity.reap(attempt_dir)
    except (OSError, ValueError) as exc:
        # A failed reap must not skip the seal or the interruption; abandon reaps again.
        reaped = [{"action": "reap_failed", "detail": str(exc)[:256]}]
    deadline = time.monotonic() + SEAL_DEADLINE_SECONDS
    request = valid_cancel_request(attempt_dir, aid, generation)
    refusal = "no valid cancel request for this attempt and generation"
    if request is not None:
        try:
            with parent_fences(attempt_dir, ledger, deadline):
                sealed = ledger.seal_terminal_uncertain(
                    aid, "cancelled", expected_generation=generation, actor=request["actor"],
                    explanation=request["explanation"], cause="cancel_request",
                    receipt_path=attempt_dir / "receipt.json",
                    build_receipt=terminal_receipt_renderer(envelope, attempt_dir, status="cancelled",
                                                            actor=request["actor"], explanation=request["explanation"],
                                                            cause="cancel_request"))
            return {**sealed, "reason": "cancel_request", "reaped": reaped}
        except (LockDeadline, ContractError, OSError, sqlite3.Error) as exc:
            refusal = f"cancelled seal refused: {exc}"
    try:
        with parent_fences(attempt_dir, ledger, deadline):
            interruption = ledger.record_interruption(aid, "cancel_signal", f"{refusal}; {detail}"[:512],
                                                      generation=generation)
    except (LockDeadline, ContractError, OSError, sqlite3.Error) as exc:
        # The claim records the process exit instead when recovery starts.
        return {"attempt_id": aid, "status": "interrupted", "reason": "cancel_signal", "receipt_path": None,
                "detail": f"{refusal}; interruption not recorded: {exc}"[:512], "reaped": reaped}
    return {"attempt_id": aid, "status": "interrupted", "reason": "cancel_signal", "receipt_path": None,
            "interruption_id": interruption["interruption_id"], "detail": refusal, "reaped": reaped}


def _signal_parent(record: dict[str, Any], closed: Path) -> None:
    """Re-check the parent's identity immediately before signalling it (via a pidfd where the OS has one).

    The parent marks its record closed before it restores the default SIGTERM
    action, so a closed record means the handler may already be gone.
    """
    pid = record["pid"]
    pidfd = None
    if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
        try:
            pidfd = os.pidfd_open(pid)
        except OSError:
            raise RecoveryRefused(ATTEMPT_NOT_LIVE, "the parent exited before it was signalled") from None
    try:
        if process_identity.start_time(pid) != record["start_time"]:
            raise RecoveryRefused(PROCESS_IDENTITY_MISMATCH, "the parent pid was reused before it was signalled")
        if os.path.lexists(closed):
            raise RecoveryRefused(ATTEMPT_NOT_LIVE, "the parent finished before it was signalled")
        if pidfd is not None:
            signal.pidfd_send_signal(pidfd, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        raise RecoveryRefused(ATTEMPT_NOT_LIVE, "the parent exited before it was signalled") from None
    finally:
        if pidfd is not None:
            os.close(pidfd)


def cancel_delivery(work_id: str, attempt_id: str, *, actor: str, explanation: str, expected_generation: int,
                    root: Path | None = None, wait_seconds: float = CANCEL_WAIT_SECONDS) -> dict[str, Any]:
    """Ask a live v8 parent to stop: verify it, write the request, SIGTERM it, and wait for its seal.

    Takes no lock (the parent holds them all). Its generation check reads a
    snapshot and is advisory; the parent re-checks it when it seals.
    """
    for value, limit in ((actor, 256), (explanation, 2048)):
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ContractError("cancel actor or explanation is invalid")
    if type(expected_generation) is not int:
        raise ContractError("expected generation is required")
    run_dir, attempt_dir, ledger_path = _attempt_paths(root, work_id, attempt_id)
    snapshot = _read_snapshot(ledger_path, attempt_id)
    _check_started(snapshot, expected_generation)
    record = next((item for item in process_identity.records(attempt_dir)
                   if item["owner_generation"] == expected_generation), None)
    if record is None:
        raise RecoveryRefused(ATTEMPT_NOT_LIVE, "no process recorded itself as this generation's parent")
    verdict = process_identity.parent_live(record)
    if verdict == "foreign":
        host = "".join(char for char in str(record.get("host")) if char.isprintable())[:64]
        raise RecoveryRefused(FOREIGN_MACHINE, f"the parent ran on {host}")
    if verdict == "mismatch":
        raise RecoveryRefused(PROCESS_IDENTITY_MISMATCH, "the recorded pid now belongs to another process")
    if verdict != "live":
        raise RecoveryRefused(ATTEMPT_NOT_LIVE, f"the recorded parent is {verdict}")
    if not record.get("cancel_supported"):
        raise RecoveryRefused(CANCEL_UNSUPPORTED, "the parent could not install its cancel handler")
    request = {"schema_version": 1, "attempt_id": attempt_id, "owner_generation": expected_generation,
               "actor": actor.strip(), "explanation": explanation.strip(), "nonce": uuid.uuid4().hex,
               "requested_at": utc_now()}
    _write_cancel_request(attempt_dir, request)
    closed = attempt_dir / f"control-g{expected_generation}.closed"
    finished = False
    try:
        _signal_parent(record, closed)
        reader = ExecutionLedger(ledger_path, read_only=True)
        deadline = time.monotonic() + wait_seconds
        while True:
            # Liveness first, status second: a parent that sealed and exited in
            # between is then read as finished, not as stopped without a seal.
            parent_gone = process_identity.parent_live({**record, "closed": closed.exists()}) != "live"
            current = reader.snapshot(attempt_id)
            if current["status"] == "cancelled":
                finished = True
                return {"status": "cancelled", "work_id": work_id, "attempt_id": attempt_id,
                        "receipt_path": current["receipt_path"], "owner_generation": current["owner_generation"]}
            if current["status"] != "started":
                finished = True
                return {"status": ATTEMPT_FINISHED, "work_id": work_id, "attempt_id": attempt_id,
                        "terminal_status": current["status"], "receipt_path": current["receipt_path"]}
            if parent_gone:
                raise RecoveryRefused(CANCEL_TIMEOUT, "the parent stopped without sealing; the attempt stays started "
                                                      "(see its interruption in inspect-delivery)")
            if time.monotonic() >= deadline:
                raise RecoveryRefused(CANCEL_TIMEOUT, f"no terminal status within {wait_seconds:g} s; "
                                                      "the attempt stays started")
            time.sleep(0.1)
    finally:
        if not finished:
            # A request that did not end in a seal must not cancel a later SIGTERM.
            with contextlib_suppress(OSError):
                (attempt_dir / CANCEL_REQUEST).unlink()
