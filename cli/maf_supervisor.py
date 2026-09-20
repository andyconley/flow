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
    from execution_contracts import validate_action, validate_replan
except ModuleNotFoundError:  # pragma: no cover - exercised by package consumers
    from cli.execution_contracts import validate_action, validate_replan


PROTOCOL_VERSION = 1
MULTITURN_PROTOCOL_VERSION = 2
PINNED_MAF_CORE_VERSION = "1.19.0"
MAX_LINE_BYTES = 256 * 1024


class MafProtocolError(RuntimeError):
    """The supervised runtime sent an invalid or unsafe protocol message."""


class MafTransportError(MafProtocolError):
    """The supervised child disappeared or stopped moving within the deadline."""


class MafChildError(MafProtocolError):
    """The child reported a deterministic workflow or policy failure."""


def _json_line(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _write_bounded(fd: int, value: dict[str, Any], deadline: float) -> None:
    """Write a bounded protocol line without letting a nonreading child hang Flow."""
    payload = _json_line(value)
    if len(payload) > MAX_LINE_BYTES:
        raise MafProtocolError("Flow protocol line exceeds the bounded size")
    os.set_blocking(fd, False)
    sent = 0
    while sent < len(payload):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise MafTransportError("MAF child timed out while reading a protocol message")
        _, ready, _ = select.select([], [fd], [], remaining)
        if not ready:
            raise MafTransportError("MAF child timed out while reading a protocol message")
        try:
            sent += os.write(fd, payload[sent:])
        except BlockingIOError:
            continue
        except BrokenPipeError as exc:
            raise MafTransportError("MAF child closed stdin during a protocol message") from exc


def _read_message(fd: int, deadline: float, pending: bytearray, protocol_version: int = PROTOCOL_VERSION) -> dict[str, Any]:
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
            raise MafTransportError("MAF child timed out before sending a protocol message")
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            raise MafTransportError("MAF child timed out before sending a protocol message")
        chunk = os.read(fd, min(65536, MAX_LINE_BYTES + 1 - len(pending)))
        if not chunk:
            raise MafTransportError("MAF child closed stdout before workflow_finished")
        pending.extend(chunk)
    try:
        message = json.loads(line)
    except (TypeError, ValueError) as exc:
        raise MafProtocolError("MAF child sent invalid JSON") from exc
    if not isinstance(message, dict):
        raise MafProtocolError("MAF child protocol message must be an object")
    if message.get("protocol_version") != protocol_version or not isinstance(message.get("type"), str):
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


def run_maf_multiturn(
    envelope: dict[str, Any],
    on_action: Callable[[dict[str, Any]], dict[str, Any]],
    on_replan: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    phase: str,
    timeout_s: float = 120,
    python_path: str | None = None,
    resume: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Supervise one bounded v2 MAF phase through Flow-owned callbacks.

    The denied third replan ends the initial child. The third action requires a
    distinct ``action3`` invocation after Flow has inspected the denial state.
    """
    if envelope.get("execution_protocol_version") != 2 or phase not in {"initial", "action3"}:
        raise MafProtocolError("unsupported multi-turn envelope or phase")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    expected = ([ ("delegate", 1), ("replan", 1), ("delegate", 2),
                  ("replan", 2), ("replan", 3) ] if phase == "initial" else [("delegate", 3)])
    if resume is not None:
        if (phase != "initial" or resume.get("kind") != "delegate"
                or resume.get("sequence") not in {1, 2}
                or not isinstance(resume.get("checkpoint_id"), str)
                or not isinstance(resume.get("request_id"), str)
                or resume.get("type") != "action_result"
                or not isinstance(resume.get("action_id"), str)
                or not isinstance(resume.get("result"), dict)):
            raise MafProtocolError("unsupported multi-turn resume position")
        expected = expected[1 if resume["sequence"] == 1 else 3:]
    executable = python_path or os.environ.get("FLOW_MAF_PYTHON") or sys.executable
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [executable, "-m", "runtime.maf_runner.multiturn"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=root, env={"PYTHONPATH": str(root)}, bufsize=0,
    )
    assert process.stdin is not None and process.stdout is not None
    deadline = time.monotonic() + timeout_s
    pending = bytearray()
    position = 0
    try:
        process.stdin.write(_json_line({"protocol_version": 2, "type": "start", "phase": phase,
                                        "envelope": envelope, "checkpoint_dir": envelope["checkpoint_dir"],
                                        "resume": resume}))
        process.stdin.flush()
        while True:
            message = _read_message(process.stdout.fileno(), deadline, pending, 2)
            kind = "delegate" if message["type"] == "propose_action" else "replan" if message["type"] == "propose_replan" else None
            if kind is not None:
                if position >= len(expected) or expected[position] != (kind, message.get("sequence")):
                    raise MafProtocolError("MAF child proposed an unexpected multi-turn position")
                required = ("schema_version", "kind", "attempt_id", "role", "instance_id", "provider", "model",
                            "task_digest", "envelope_digest", "sequence", "checkpoint_id", "runtime_version")
                if kind == "delegate":
                    required += ("action_id",)
                else:
                    required += ("replan_id", "proposal")
                proposal = {key: message.get(key) for key in required}
                if any(value is None for value in proposal.values()):
                    raise MafProtocolError("MAF child omitted a multi-turn identity field")
                if not isinstance(proposal["checkpoint_id"], str) or not isinstance(proposal["runtime_version"], str):
                    raise MafProtocolError("MAF child checkpoint identity is invalid")
                if proposal["runtime_version"] != PINNED_MAF_CORE_VERSION:
                    raise MafProtocolError("MAF child runtime version differs from the pinned version")
                try:
                    (validate_action if kind == "delegate" else validate_replan)(envelope, proposal)
                except (TypeError, ValueError) as exc:
                    raise MafProtocolError(f"MAF child proposal is not bound to the envelope: {exc}") from exc
                decision = (on_action if kind == "delegate" else on_replan)(proposal)
                if not isinstance(decision, dict):
                    raise MafProtocolError("Flow callback must return a normalized decision")
                response_type = "action_result" if kind == "delegate" else "replan_result"
                identity_key = "action_id" if kind == "delegate" else "replan_id"
                process.stdin.write(_json_line({"protocol_version": 2, "type": response_type,
                                                identity_key: proposal[identity_key],
                                                "request_id": message.get("request_id"), "result": decision}))
                process.stdin.flush()
                position += 1
                continue
            if message["type"] == "workflow_finished":
                if position != len(expected) or message.get("attempt_id") != envelope["attempt_id"] or message.get("phase") != phase:
                    raise MafProtocolError("MAF child finished before the approved phase ended")
                if phase == "initial" and message.get("reason") != "denied_replan_cap":
                    raise MafProtocolError("initial phase did not halt at the third replan denial")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MafProtocolError("MAF child timed out before clean exit")
                try:
                    code = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired as exc:
                    raise MafProtocolError("MAF child did not exit after workflow_finished") from exc
                if code != 0:
                    raise MafProtocolError(f"MAF child exited {code} after workflow_finished")
                return message
            if message["type"] == "error":
                raise RuntimeError(f"MAF child failed: {message.get('message')}")
            raise MafProtocolError(f"MAF child sent unexpected message type: {message['type']}")
    except BaseException:
        process.kill()
        process.wait(timeout=5)
        raise
    finally:
        for stream in (process.stdin, process.stdout):
            if stream is not None and not stream.closed:
                stream.close()


def _run_maf_pair(
    envelope: dict[str, Any],
    on_action: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    timeout_s: float = 240,
    python_path: str | None = None,
    protocol_version: int = 3,
) -> dict[str, Any]:
    """Supervise exactly two ordered MAF proposals through Flow callbacks."""
    if protocol_version not in {3, 4} or envelope.get("execution_protocol_version") != protocol_version or timeout_s <= 0:
        raise MafProtocolError("paired execution requires a matching envelope and positive timeout")
    executable = python_path or os.environ.get("FLOW_MAF_PYTHON") or sys.executable
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [executable, "-m", "runtime.maf_runner.mixed" if protocol_version == 3 else "runtime.maf_runner.claude_review"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=root, env={"PYTHONPATH": str(root)}, bufsize=0,
    )
    assert process.stdin is not None and process.stdout is not None
    deadline = time.monotonic() + timeout_s
    pending = bytearray()
    position = 0
    try:
        process.stdin.write(_json_line({"protocol_version": protocol_version, "type": "start", "envelope": envelope}))
        process.stdin.flush()
        while True:
            message = _read_message(process.stdout.fileno(), deadline, pending, protocol_version)
            if message["type"] == "propose_action":
                position += 1
                if position > 2 or message.get("sequence") != position:
                    raise MafProtocolError("MAF child proposed an extra or out-of-order mixed action")
                required = ("schema_version", "kind", "attempt_id", "action_id", "envelope_digest",
                            "assignment_id", "definition_digest", "role", "instance_id", "provider", "model",
                            "task_digest", "sequence", "checkpoint_id", "runtime_version", "request_id")
                if any(message.get(key) is None for key in required):
                    raise MafProtocolError("MAF child omitted a mixed action identity")
                if message["request_id"] != f"flow-mixed-action-{position}" or message["runtime_version"] != PINNED_MAF_CORE_VERSION:
                    raise MafProtocolError("MAF child mixed checkpoint or runtime identity differs")
                proposal = {key: message[key] for key in required if key not in {"checkpoint_id", "runtime_version", "request_id"}}
                try:
                    validate_action(envelope, proposal)
                except (TypeError, ValueError) as exc:
                    raise MafProtocolError(f"MAF child mixed proposal differs from Flow envelope: {exc}") from exc
                decision = on_action({**proposal, "checkpoint_id": message["checkpoint_id"],
                                      "runtime_version": message["runtime_version"],
                                      "request_id": message["request_id"]})
                if not isinstance(decision, dict):
                    raise MafProtocolError("Flow mixed callback did not return a result")
                process.stdin.write(_json_line({"protocol_version": protocol_version, "type": "action_result",
                                                "action_id": proposal["action_id"],
                                                "request_id": message["request_id"], "result": decision}))
                process.stdin.flush()
                continue
            if message["type"] == "workflow_finished":
                if position != 2 or message.get("attempt_id") != envelope["attempt_id"] or message.get("reason") != "mixed-job-complete":
                    raise MafProtocolError("MAF child finished without the two approved actions")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MafProtocolError("MAF child timed out before clean exit")
                try:
                    code = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired as exc:
                    raise MafProtocolError("MAF child did not exit after mixed completion") from exc
                if code != 0:
                    raise MafProtocolError(f"MAF child exited {code} after mixed completion")
                return message
            if message["type"] == "error":
                raise RuntimeError(f"MAF mixed child failed: {message.get('message')}")
            raise MafProtocolError(f"MAF child sent unexpected mixed message: {message['type']}")
    except BaseException:
        process.kill()
        process.wait(timeout=5)
        raise
    finally:
        for stream in (process.stdin, process.stdout):
            if stream is not None and not stream.closed:
                stream.close()


def run_maf_mixed(envelope: dict[str, Any], on_action: Callable[[dict[str, Any]], dict[str, Any]],
                  *, timeout_s: float = 240, python_path: str | None = None) -> dict[str, Any]:
    return _run_maf_pair(envelope, on_action, timeout_s=timeout_s, python_path=python_path, protocol_version=3)


def run_maf_claude(envelope: dict[str, Any], on_action: Callable[[dict[str, Any]], dict[str, Any]],
                   *, timeout_s: float = 240, python_path: str | None = None) -> dict[str, Any]:
    return _run_maf_pair(envelope, on_action, timeout_s=timeout_s, python_path=python_path, protocol_version=4)


def run_maf_delivery(envelope: dict[str, Any], task: str,
                     on_manager: Callable[[dict[str, Any]], str],
                     on_action: Callable[[dict[str, Any]], dict[str, Any]], *,
                     timeout_s: float = 900, python_path: str | None = None,
                     resume: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run credentialless stock Magentic behind Flow's two guarded callbacks."""
    if envelope.get("execution_protocol_version") != 5 or not isinstance(task, str) or not task.strip():
        raise MafProtocolError("delivery requires a v5 envelope and task")
    if not callable(on_manager) or not callable(on_action) or not 0 < timeout_s <= 900:
        raise MafProtocolError("delivery callbacks or timeout are invalid")
    executable = python_path or os.environ.get("FLOW_MAF_PYTHON") or sys.executable
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [executable, "-m", "runtime.maf_runner.delivery_lead"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=root, env={"PYTHONPATH": str(root)}, bufsize=0,
        start_new_session=True,
    )
    assert process.stdin is not None and process.stdout is not None
    deadline = time.monotonic() + timeout_s
    pending = bytearray()
    manager_calls = actions = 0
    try:
        _write_bounded(process.stdin.fileno(), {"protocol_version": 5, "type": "resume" if resume else "start",
                                                   "envelope": envelope, "task": task, "resume": resume}, deadline)
        while True:
            message = _read_message(process.stdout.fileno(), deadline, pending, 5)
            kind = message["type"]
            if kind == "manager_request":
                manager_calls += 1
                if manager_calls > envelope["limits"]["max_manager_calls"] + 1:
                    raise MafProtocolError("MAF manager exceeded the bounded call protocol")
                if message.get("attempt_id") != envelope["attempt_id"]:
                    raise MafProtocolError("MAF manager request attempt differs")
                text = on_manager(message)
                if not isinstance(text, str) or not text.strip() or len(text.encode()) > MAX_LINE_BYTES // 2:
                    raise MafProtocolError("Flow manager callback returned invalid text")
                _write_bounded(process.stdin.fileno(), {"protocol_version": 5, "type": "manager_response",
                                                           "call_id": message.get("call_id"), "text": text}, deadline)
                continue
            if kind == "propose_action":
                actions += 1
                if actions > envelope["limits"]["max_delegations"] + 1:
                    raise MafProtocolError("MAF proposed too many specialist calls")
                if message.get("attempt_id") != envelope["attempt_id"]:
                    raise MafProtocolError("MAF action attempt differs")
                result = on_action(message)
                if not isinstance(result, dict):
                    raise MafProtocolError("Flow action callback returned invalid result")
                _write_bounded(process.stdin.fileno(), {"protocol_version": 5, "type": "action_result",
                                                           "action_id": result.get("action_id", message.get("action_id")), "result": result}, deadline)
                continue
            if kind == "workflow_finished":
                if message.get("attempt_id") != envelope["attempt_id"]:
                    raise MafProtocolError("MAF finished a different attempt")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MafProtocolError("MAF timed out before exit")
                if process.wait(timeout=remaining) != 0:
                    raise MafProtocolError("MAF failed after workflow_finished")
                return message
            if kind == "error":
                raise MafChildError("MAF delivery child failed: " + str(message.get("message", "unknown"))[:512])
            raise MafProtocolError("MAF delivery child sent an unexpected message")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()


def run_maf_action3_continuation(
    envelope: dict[str, Any],
    resume: dict[str, Any],
    on_ready: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    timeout_s: float = 120,
    python_path: str | None = None,
) -> dict[str, Any]:
    """Restore action 3 first; invoke Flow's send boundary only after MAF readiness."""
    if envelope.get("execution_protocol_version") != 2 or not callable(on_ready):
        raise MafProtocolError("invalid action-3 continuation envelope or callback")
    if (not isinstance(resume, dict) or resume.get("schema_version") != 2
            or not isinstance(resume.get("checkpoint_id"), str) or not resume["checkpoint_id"]
            or resume.get("request_id") != "flow-action-3"
            or not isinstance(resume.get("action_id"), str)):
        raise MafProtocolError("invalid action-3 continuation resume identity")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")
    executable = python_path or os.environ.get("FLOW_MAF_PYTHON") or sys.executable
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [executable, "-m", "runtime.maf_runner.multiturn"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=root, env={"PYTHONPATH": str(root)}, bufsize=0,
    )
    assert process.stdin is not None and process.stdout is not None
    deadline = time.monotonic() + timeout_s
    pending = bytearray()
    ready_seen = False
    try:
        process.stdin.write(_json_line({"protocol_version": 2, "type": "start", "phase": "action3",
                                        "continuation": True, "envelope": envelope,
                                        "checkpoint_dir": envelope["checkpoint_dir"], "resume": resume}))
        process.stdin.flush()
        while True:
            message = _read_message(process.stdout.fileno(), deadline, pending, 2)
            if message["type"] == "continuation_ready":
                if ready_seen or message.get("phase") != "action3" or message.get("kind") != "delegate" or message.get("sequence") != 3:
                    raise MafProtocolError("MAF child sent unexpected continuation readiness")
                if (message.get("request_id") != resume["request_id"]
                        or message.get("checkpoint_id") != resume["checkpoint_id"]
                        or message.get("action_id") != resume["action_id"]
                        or message.get("runtime_version") != PINNED_MAF_CORE_VERSION):
                    raise MafProtocolError("MAF child readiness does not match the pinned action-3 barrier")
                try:
                    validate_action(envelope, message)
                except (TypeError, ValueError) as exc:
                    raise MafProtocolError(f"MAF child readiness is not bound to the envelope: {exc}") from exc
                ready_seen = True
                result = on_ready(dict(message))
                if not isinstance(result, dict):
                    raise MafProtocolError("Flow readiness callback must return a normalized result")
                process.stdin.write(_json_line({"protocol_version": 2, "type": "action_result",
                                                "action_id": resume["action_id"], "request_id": resume["request_id"],
                                                "result": result}))
                process.stdin.flush()
                continue
            if message["type"] == "workflow_finished":
                if (not ready_seen or message.get("attempt_id") != envelope.get("attempt_id")
                        or message.get("phase") != "action3" or message.get("reason") != "action-3-complete"
                        or message.get("runtime_version") != PINNED_MAF_CORE_VERSION):
                    raise MafProtocolError("MAF child did not acknowledge the continued action 3")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise MafProtocolError("MAF child timed out before clean exit")
                try:
                    code = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired as exc:
                    raise MafProtocolError("MAF child did not exit after continuation") from exc
                if code != 0:
                    raise MafProtocolError(f"MAF child exited {code} after continuation")
                return message
            if message["type"] == "error":
                raise RuntimeError(f"MAF child failed: {message.get('message')}")
            raise MafProtocolError(f"MAF child sent unexpected message type: {message['type']}")
    except BaseException:
        process.kill()
        process.wait(timeout=5)
        raise
    finally:
        for stream in (process.stdin, process.stdout):
            if stream is not None and not stream.closed:
                stream.close()
