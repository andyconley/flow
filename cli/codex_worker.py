"""One bounded Codex CLI turn in an isolated Flow-supplied workspace.

The installed Codex login is used; no API key is required. Flow owns the
authorization and receipt around this call. A failed or incomplete turn is
uncertain and must never be retried automatically.
"""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from delivery_cancel import interruptible
from execution_contracts import usage_values_valid

MAX_PROMPT_BYTES = 1024 * 1024
MAX_OUTPUT_BYTES = 4096
MAX_STDERR_BYTES = 8192
CODEX_ENV_KEYS = ("HOME", "CODEX_HOME", "PATH", "TMPDIR", "LANG", "LC_ALL",
                  "LC_CTYPE", "USER", "LOGNAME")


class CodexWorkerError(RuntimeError):
    """Codex may have acted, but Flow did not observe a valid completed turn."""


def _failure_category(stderr: bytes) -> str:
    """Return a fixed diagnostic label without retaining provider text."""
    evidence = stderr[:MAX_STDERR_BYTES].decode("utf-8", errors="replace").lower()
    if any(marker in evidence for marker in (
        "not logged in", "not authenticated", "authentication required", "please log in",
    )):
        return "authentication_unavailable"
    if any(marker in evidence for marker in (
        "operation not permitted", "permission denied", "readonly database", "read-only database",
    )):
        return "filesystem_access_denied"
    if any(marker in evidence for marker in ("unknown option", "unknown argument", "unrecognized option")):
        return "unsupported_cli_option"
    if any(marker in evidence for marker in ("rate limit", "rate_limit")):
        return "rate_limited"
    if any(marker in evidence for marker in ("model not found", "invalid model", "model unavailable")):
        return "model_unavailable"
    return "unclassified"


def _parse_event_lines(lines, expected_model: str, *, max_output_bytes: int = MAX_OUTPUT_BYTES) -> dict[str, Any]:
    try:
        events = [json.loads(line) for line in lines if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodexWorkerError("Codex emitted invalid JSONL") from exc
    if not events or any(not isinstance(event, dict) for event in events):
        raise CodexWorkerError("Codex emitted no valid events")
    starts = [event for event in events if event.get("type") == "thread.started"]
    completed = [event for event in events if event.get("type") == "turn.completed"]
    if len(starts) != 1 or len(completed) != 1 or any(
        event.get("type") in {"turn.failed", "error"} for event in events
    ):
        raise CodexWorkerError("Codex turn did not complete unambiguously")
    thread_id = starts[0].get("thread_id")
    if not isinstance(thread_id, str) or not thread_id:
        raise CodexWorkerError("Codex thread identity missing")
    messages = [event["item"].get("text") for event in events
                if event.get("type") == "item.completed"
                and isinstance(event.get("item"), dict)
                and event["item"].get("type") == "agent_message"]
    if not messages or not isinstance(messages[-1], str) or not messages[-1].strip():
        raise CodexWorkerError("Codex final message missing")
    output = messages[-1]
    if len(output.encode("utf-8")) > max_output_bytes:
        raise CodexWorkerError("Codex final message exceeds output limit")
    usage = completed[0].get("usage")
    # Known counters must be non-negative integers; a key a newer Codex adds is
    # kept and ignored, so it never turns a paid call into an unknown (ADR 0020).
    if not usage_values_valid(usage):
        raise CodexWorkerError("Codex usage is invalid")
    return {"schema_version": 1, "status": "completed", "provider": "codex",
            "model": expected_model, "physical_call": True,
            "evidence_level": "flow_observed_codex_cli_completed_turn",
            "output": output,
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "usage": usage, "thread_id": thread_id}


def _parse_events(raw: bytes, expected_model: str, *, max_output_bytes: int = MAX_OUTPUT_BYTES) -> dict[str, Any]:
    return _parse_event_lines(raw.splitlines(), expected_model, max_output_bytes=max_output_bytes)


def call_codex(*, instructions: str, task: str, workspace: Path, model: str,
               timeout_seconds: int, codex_bin: str = "codex",
               sandbox: str = "workspace-write", max_prompt_bytes: int | None = None,
               max_output_bytes: int = MAX_OUTPUT_BYTES,
               on_process_group: Callable[[int, str], None] | None = None) -> dict[str, Any]:
    """Run one Codex turn; fail closed on timeout, malformed or incomplete output.

    The caller must create and approve the isolated workspace before dispatch.
    The CLI is given no additional writable directories or persisted session.
    """
    workspace = Path(workspace).resolve(strict=True)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ValueError("Codex workspace must be a real directory")
    if not isinstance(model, str) or not model.strip() or any(c.isspace() for c in model):
        raise ValueError("Codex model must be explicit")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 600:
        raise ValueError("Codex timeout must be 1 to 600 seconds")
    if sandbox not in {"workspace-write", "read-only"}:
        raise ValueError("Codex sandbox must be explicit and supported")
    if max_prompt_bytes is None:
        max_prompt_bytes = MAX_PROMPT_BYTES
    if (type(max_prompt_bytes) is not int or not 1 <= max_prompt_bytes <= MAX_PROMPT_BYTES
            or type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 32768):
        raise ValueError("Codex prompt or output limit is invalid")
    prompt = ("Specialist instructions:\n" + instructions + "\n\nAuthorized task:\n" + task
              + "\n\nWork only in this workspace. Do not spawn subagents or delegate. "
                "Complete this single task and report the change and checks.\n")
    prompt_bytes = prompt.encode("utf-8")
    if not instructions.strip() or not task.strip() or len(prompt_bytes) > max_prompt_bytes:
        raise ValueError("Codex prompt is empty or too large")
    argv = [codex_bin, "exec", "--json", "--ephemeral", "--ignore-user-config",
            "--skip-git-repo-check", "--sandbox", sandbox,
            "--model", model, "--cd", str(workspace),
            "--config", 'approval_policy="never"',
            "--config", "features.multi_agent=false", "-"]
    # Codex writes runtime state even with --ephemeral. Give the nested sandbox
    # a private writable home containing only the installed login, rather than
    # exposing the user's normal state database to writes.
    env = {key: os.environ[key] for key in CODEX_ENV_KEYS if key in os.environ}
    source_home = Path(os.environ.get("CODEX_HOME", str(Path(os.environ.get("HOME", "")) / ".codex")))
    isolated_home = tempfile.TemporaryDirectory(prefix="flow-codex-home-")
    isolated_home_path = Path(isolated_home.name)
    auth_path = source_home / "auth.json"
    if auth_path.is_file() and not auth_path.is_symlink():
        isolated_auth = isolated_home_path / "auth.json"
        shutil.copyfile(auth_path, isolated_auth)
        isolated_auth.chmod(0o600)
    env["CODEX_HOME"] = str(isolated_home_path)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, cwd=workspace, env=env,
                               start_new_session=True)
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    deadline = time.monotonic() + timeout_seconds
    try:
        if on_process_group is not None:
            # Recorded before any byte is sent, so a stuck turn can be reaped.
            on_process_group(process.pid, "provider")
        with interruptible():  # a cancel breaks this wait once; the finally below kills the group
            written = 0
            stderr_chunks: list[bytes] = []
            stderr_size = 0
            selector = selectors.DefaultSelector()
            with tempfile.TemporaryFile() as event_file:
                try:
                    os.set_blocking(process.stdin.fileno(), False)
                    selector.register(process.stdin, selectors.EVENT_WRITE)
                    selector.register(process.stdout, selectors.EVENT_READ)
                    selector.register(process.stderr, selectors.EVENT_READ)
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise CodexWorkerError("Codex turn timed out")
                        ready = selector.select(remaining)
                        if not ready:
                            raise CodexWorkerError("Codex turn timed out")
                        for key, _ in ready:
                            if key.fileobj is process.stdin:
                                count = os.write(process.stdin.fileno(), prompt_bytes[written:])
                                written += count
                                if written == len(prompt_bytes):
                                    selector.unregister(process.stdin)
                                    process.stdin.close()
                            elif key.fileobj is process.stdout:
                                chunk = os.read(process.stdout.fileno(), 8192)
                                if not chunk:
                                    selector.unregister(process.stdout)
                                    continue
                                event_file.write(chunk)
                            else:
                                chunk = os.read(process.stderr.fileno(), min(8192, MAX_STDERR_BYTES + 1 - stderr_size))
                                if not chunk:
                                    selector.unregister(process.stderr)
                                    continue
                                stderr_chunks.append(chunk)
                                stderr_size += len(chunk)
                                if stderr_size > MAX_STDERR_BYTES:
                                    raise CodexWorkerError("Codex error stream exceeds limit")
                finally:
                    selector.close()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexWorkerError("Codex turn timed out")
                exit_code = process.wait(timeout=remaining)
                if exit_code != 0:
                    category = _failure_category(b"".join(stderr_chunks))
                    raise CodexWorkerError(
                        f"Codex exited without a successful turn (status {exit_code}; category {category})"
                    )
                event_file.seek(0)
                return _parse_event_lines(event_file, model, max_output_bytes=max_output_bytes)
    except (subprocess.TimeoutExpired, BrokenPipeError) as exc:
        raise CodexWorkerError("Codex turn outcome uncertain") from exc
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
        isolated_home.cleanup()
