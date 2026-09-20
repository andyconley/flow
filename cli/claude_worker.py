"""One bounded Claude Code CLI turn in an isolated Flow-supplied workspace.

The installed Claude Code login is used; no API key is required. Flow owns
the authorization and receipt around this call, intended for the future v4
read-only quality-reviewer step. A failed or incomplete turn is uncertain
and must never be retried automatically.
"""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import time
from pathlib import Path
from typing import Any

MAX_PROMPT_BYTES = 32768
MAX_STDOUT_BYTES = 262144
MAX_OUTPUT_BYTES = 4096
MAX_STDERR_BYTES = 8192
CLAUDE_ENV_KEYS = ("HOME", "PATH", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE",
                   "USER", "LOGNAME")


class ClaudeWorkerError(RuntimeError):
    """Claude may have acted, but Flow did not observe a valid completed turn."""


def _failure_category(stdout: bytes, stderr: bytes) -> str:
    """Return a fixed diagnostic label without retaining provider text."""
    evidence = (stdout[:MAX_STDERR_BYTES] + b"\n" + stderr[:MAX_STDERR_BYTES]).decode(
        "utf-8", errors="replace").lower()
    if any(marker in evidence for marker in ("not logged in", "not authenticated", "authentication required", "please log in")):
        return "authentication_unavailable"
    if any(marker in evidence for marker in ("unknown option", "unknown argument", "unrecognized option")):
        return "unsupported_cli_option"
    if any(marker in evidence for marker in ("rate limit", "rate_limit")):
        return "rate_limited"
    if any(marker in evidence for marker in ("model not found", "invalid model", "model unavailable")):
        return "model_unavailable"
    return "unclassified"


def _normalized_usage(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    if not isinstance(usage, dict):
        raise ClaudeWorkerError("Claude usage is invalid")
    # Claude's result also includes service labels and nested provider details.
    # Flow records only the observed integer token counters it can validate.
    fields = ("input_tokens", "output_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens")
    normalized: dict[str, int] = {}
    for field in fields:
        if field in usage:
            value = usage[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ClaudeWorkerError("Claude usage is invalid")
            normalized[field] = value
    return normalized or None


def _parse_result(raw: bytes, expected_model: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ClaudeWorkerError("Claude emitted invalid output encoding") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaudeWorkerError("Claude emitted invalid JSON result") from exc
    if not isinstance(payload, dict):
        raise ClaudeWorkerError("Claude result is not a JSON object")
    if payload.get("type") != "result" or payload.get("subtype") != "success":
        raise ClaudeWorkerError("Claude terminal result is invalid")
    if payload.get("is_error") is not False:
        raise ClaudeWorkerError("Claude turn did not complete unambiguously")
    result = payload.get("result")
    if not isinstance(result, str) or not result.strip():
        raise ClaudeWorkerError("Claude final result missing")
    if len(result.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ClaudeWorkerError("Claude final result exceeds output limit")
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise ClaudeWorkerError("Claude session identity missing")
    num_turns = payload.get("num_turns")
    if isinstance(num_turns, bool) or not isinstance(num_turns, int) or not 1 <= num_turns <= 1:
        raise ClaudeWorkerError("Claude turn count is invalid")
    usage = _normalized_usage(payload.get("usage"))
    return {"schema_version": 1, "status": "completed", "provider": "claude",
            "model": expected_model, "physical_call": True,
            "evidence_level": "flow_observed_claude_cli_completed_turn",
            "output": result,
            "output_sha256": hashlib.sha256(result.encode()).hexdigest(),
            "usage": usage, "session_id": session_id}


def build_prompt(instructions: str, task: str) -> bytes:
    prompt = ("Specialist instructions:\n" + instructions + "\n\nAuthorized task:\n" + task
              + "\n\nWork only on the supplied source text. Do not spawn subagents or delegate. "
                "Complete this single review and report your findings.\n")
    prompt_bytes = prompt.encode("utf-8")
    if not instructions.strip() or not task.strip() or len(prompt_bytes) > MAX_PROMPT_BYTES:
        raise ValueError("Claude prompt is empty or too large")
    return prompt_bytes


def call_claude(*, instructions: str, task: str, workspace: Path, model: str,
                timeout_seconds: int, claude_bin: str = "claude",
                prompt_override: str | None = None) -> dict[str, Any]:
    """Run one Claude Code turn; fail closed on timeout, malformed or incomplete output.

    The caller must create and approve the isolated workspace before dispatch.
    The CLI is given no tools, no persisted session, and no ambient permission
    bypass. This is a read-only review call: Claude is not expected to write.
    """
    raw_workspace = Path(workspace)
    if raw_workspace.is_symlink():
        raise ValueError("Claude workspace must be a real directory")
    workspace = raw_workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise ValueError("Claude workspace must be a real directory")
    if not isinstance(model, str) or not model.strip() or any(c.isspace() for c in model):
        raise ValueError("Claude model must be explicit")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 600:
        raise ValueError("Claude timeout must be 1 to 600 seconds")
    if prompt_override is None:
        prompt_bytes = build_prompt(instructions, task)
    else:
        if not isinstance(prompt_override, str) or not prompt_override.strip():
            raise ValueError("Claude manager prompt is empty")
        prompt_bytes = prompt_override.encode("utf-8")
        if len(prompt_bytes) > MAX_PROMPT_BYTES:
            raise ValueError("Claude manager prompt exceeds limit")
    argv = [claude_bin, "-p", "--output-format", "json",
            "--safe-mode", "--no-session-persistence",
            "--permission-mode", "dontAsk", "--tools", "",
            "--model", model]
    # Auth is read from the installed Claude Code login under HOME. Do not
    # inherit unrelated credentials, cloud configuration, proxy variables,
    # or project secrets.
    env = {key: os.environ[key] for key in CLAUDE_ENV_KEYS if key in os.environ}
    deadline = time.monotonic() + timeout_seconds
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, cwd=workspace, env=env,
                               start_new_session=True)
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise ClaudeWorkerError("Claude process pipes unavailable")
    try:
        chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []
        size = 0
        stderr_size = 0
        written = 0
        selector = selectors.DefaultSelector()
        os.set_blocking(process.stdin.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE)
        selector.register(process.stdout, selectors.EVENT_READ)
        selector.register(process.stderr, selectors.EVENT_READ)
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ClaudeWorkerError("Claude turn timed out")
                ready = selector.select(remaining)
                if not ready:
                    raise ClaudeWorkerError("Claude turn timed out")
                for key, _ in ready:
                    if key.fileobj is process.stdin:
                        count = os.write(process.stdin.fileno(), prompt_bytes[written:])
                        written += count
                        if written == len(prompt_bytes):
                            selector.unregister(process.stdin)
                            process.stdin.close()
                    elif key.fileobj is process.stdout:
                        chunk = os.read(process.stdout.fileno(), min(8192, MAX_STDOUT_BYTES + 1 - size))
                        if not chunk:
                            selector.unregister(process.stdout)
                            continue
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > MAX_STDOUT_BYTES:
                            raise ClaudeWorkerError("Claude output stream exceeds limit")
                    else:
                        chunk = os.read(process.stderr.fileno(), min(8192, MAX_STDERR_BYTES + 1 - stderr_size))
                        if not chunk:
                            selector.unregister(process.stderr)
                            continue
                        stderr_chunks.append(chunk)
                        stderr_size += len(chunk)
                        if stderr_size > MAX_STDERR_BYTES:
                            raise ClaudeWorkerError("Claude error stream exceeds limit")
        finally:
            selector.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ClaudeWorkerError("Claude turn timed out")
        exit_code = process.wait(timeout=remaining)
        if exit_code != 0:
            category = _failure_category(b"".join(chunks), b"".join(stderr_chunks))
            raise ClaudeWorkerError(f"Claude exited without a successful turn (status {exit_code}; category {category})")
        return {**_parse_result(b"".join(chunks), model),
                "input_sha256": hashlib.sha256(prompt_bytes).hexdigest()}
    except (subprocess.TimeoutExpired, BrokenPipeError) as exc:
        raise ClaudeWorkerError("Claude turn outcome uncertain") from exc
    finally:
        if process.poll() is None:
            import signal
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()
        process.stderr.close()
