"""Flow-owned parent for the optional supervised MAF runtime.

The child process is a coordinator only.  It cannot reach a Flow ledger or a
provider through this interface: it proposes exactly one action and waits for
the parent to return Flow's normalized result.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:  # flow.py runs siblings directly; package imports use the second path.
    from execution_contracts import validate_action
except ModuleNotFoundError:  # pragma: no cover - exercised by package consumers
    from cli.execution_contracts import validate_action


PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 256 * 1024


class MafProtocolError(RuntimeError):
    """The supervised runtime sent an invalid or unsafe protocol message."""


def _json_line(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _read_message(fd: int, deadline: float, pending: bytearray) -> dict[str, Any]:
    """Read one bounded protocol line without allowing partial output to hang.

    ``readline`` after ``select`` can block when a child wrote only part of a
    line.  This loop reads only currently-ready bytes and checks the monotonic
    deadline after each chunk.  ``pending`` preserves a second complete line
    delivered by the same pipe read.
    """
    while True:
        newline = pending.find(b"\n")
        if newline >= 0:
            if newline > MAX_LINE_BYTES:
                raise MafProtocolError("MAF child sent an oversized protocol line")
            line = bytes(pending[:newline + 1])
            del pending[:newline + 1]
            break
        if len(pending) > MAX_LINE_BYTES:
            raise MafProtocolError("MAF child sent an oversized unterminated protocol line")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MafProtocolError("MAF child timed out before sending a protocol message")
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            raise MafProtocolError("MAF child timed out before sending a protocol message")
        chunk = os.read(fd, min(65536, MAX_LINE_BYTES + 1 - len(pending)))
        if not chunk:
            raise MafProtocolError("MAF child closed stdout before workflow_finished")
        pending.extend(chunk)
    try:
        message = json.loads(line)
    except (TypeError, ValueError) as exc:
        raise MafProtocolError("MAF child sent invalid JSON") from exc
    if not isinstance(message, dict):
        raise MafProtocolError("MAF child protocol message must be an object")
    if message.get("protocol_version") != PROTOCOL_VERSION or not isinstance(message.get("type"), str):
        raise MafProtocolError("MAF child sent an unsupported protocol message")
    return message


def _validate_proposal(message: dict[str, Any]) -> dict[str, Any]:
    required = ("schema_version", "kind", "attempt_id", "action_id", "role", "instance_id", "provider", "model", "task_digest", "envelope_digest", "sequence")
    proposal = {key: message.get(key) for key in required}
    if any(value is None for value in proposal.values()):
        raise MafProtocolError("MAF child propose_action omitted a required identity field")
    if not all(isinstance(proposal[key], str) and proposal[key] for key in required[1:-1]):
        raise MafProtocolError("MAF child propose_action has invalid identity fields")
    if not isinstance(proposal["sequence"], int) or proposal["sequence"] < 1:
        raise MafProtocolError("MAF child propose_action has an invalid sequence")
    return proposal


def _verify_envelope_binding(proposal: dict[str, Any], envelope: dict[str, Any]) -> None:
    """Reject a child proposal that is not the exact authorized envelope route."""
    try:
        validate_action(envelope, proposal)
    except (TypeError, ValueError) as exc:
        raise MafProtocolError(f"MAF child proposal is not bound to the envelope: {exc}") from exc


def run_maf(
    envelope: dict[str, Any],
    on_propose: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    timeout_s: float = 120,
    python_path: str | None = None,
    resume: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run one guarded MAF turn and return its terminal protocol record.

    ``on_propose`` is Flow's only dispatch boundary.  It receives an immutable
    action proposal and returns Flow's normalized policy/result object; the
    object is relayed unchanged to the child as ``action_result``.
    """
    if not isinstance(envelope, dict):
        raise TypeError("envelope must be a dict")
    if not callable(on_propose):
        raise TypeError("on_propose must be callable")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    executable = python_path or os.environ.get("FLOW_MAF_PYTHON") or sys.executable
    root = Path(__file__).resolve().parents[1]
    child_env = {"PYTHONPATH": str(root)}
    # Deliberately do not inherit credentials or provider-specific environment.
    process = subprocess.Popen(
        [executable, "-m", "runtime.maf_runner"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        # Child diagnostics are represented by its bounded ``error`` protocol
        # record. Keeping stderr out of a pipe prevents an untrusted child
        # diagnostic stream from blocking the supervised workflow.
        stderr=subprocess.DEVNULL,
        cwd=root,
        env=child_env,
        bufsize=0,
    )
    assert process.stdin is not None and process.stdout is not None
    deadline = time.monotonic() + timeout_s
    pending = bytearray()
    try:
        if resume is not None:
            if resume.get("schema_version") != 2 or not isinstance(resume.get("checkpoint_id"), str):
                raise MafProtocolError("invalid Flow resume message")
        process.stdin.write(_json_line({"protocol_version": PROTOCOL_VERSION, "type": "resume" if resume else "start", "envelope": envelope, "resume": resume}))
        process.stdin.flush()
        proposals = 0
        while True:
            message = _read_message(process.stdout.fileno(), deadline, pending)
            if message["type"] == "propose_action":
                proposals += 1
                if proposals != 1:
                    raise MafProtocolError("MAF child proposed more than one action in the bounded slice")
                proposal = _validate_proposal(message)
                _verify_envelope_binding(proposal, envelope)
                try:
                    result = on_propose(dict(proposal))
                except Exception as exc:
                    raise RuntimeError("Flow rejected the MAF action proposal") from exc
                if not isinstance(result, dict):
                    raise MafProtocolError("Flow action callback must return a dict")
                process.stdin.write(_json_line({"protocol_version": PROTOCOL_VERSION, "type": "action_result", "action_id": proposal["action_id"], "result": result}))
                process.stdin.flush()
                continue
            if message["type"] == "workflow_finished":
                if proposals != 1:
                    raise MafProtocolError("MAF child finished without one action proposal")
                if not isinstance(message.get("attempt_id"), str) or not isinstance(message.get("summary"), str):
                    raise MafProtocolError("MAF child sent an invalid workflow_finished record")
                if message["attempt_id"] != envelope.get("attempt_id"):
                    raise MafProtocolError("MAF child finished a different execution attempt")
                checkpoint_id = message.get("checkpoint_id")
                if checkpoint_id is not None and not isinstance(checkpoint_id, str):
                    raise MafProtocolError("MAF child sent an invalid checkpoint ID")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MafProtocolError("MAF child timed out before clean exit")
                try:
                    code = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired as exc:
                    raise MafProtocolError("MAF child did not exit after workflow_finished") from exc
                if code != 0:
                    raise RuntimeError(f"MAF child exited {code} after workflow_finished")
                return message
            if message["type"] == "error":
                detail = message.get("message")
                raise RuntimeError(f"MAF child failed: {detail if isinstance(detail, str) else 'unknown error'}")
            raise MafProtocolError(f"MAF child sent unexpected message type: {message['type']}")
    except BaseException:
        process.kill()
        process.wait(timeout=5)
        raise
    finally:
        try:
            if process.poll() is None:
                # Closing stdin tells a well-behaved child that no more Flow
                # protocol input will arrive before the parent reaps it.
                if not process.stdin.closed:
                    process.stdin.close()
                try:
                    process.wait(timeout=max(0.1, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        finally:
            # Popen does not own these descriptors after construction. Close
            # both outcomes (including protocol failure) without replacing the
            # primary exception that tells Flow how to seal its receipt.
            for stream in (process.stdin, process.stdout):
                try:
                    if stream is not None and not stream.closed:
                        stream.close()
                except OSError:
                    pass
