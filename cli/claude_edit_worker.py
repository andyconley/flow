"""One bounded Claude Code edit in a Flow-approved isolated worktree.

The caller owns the grant, source pin, diff validation, and tests. This module
only runs a single CLI turn and reports what the CLI actually observed.
"""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

from claude_worker import CLAUDE_ENV_KEYS, _normalized_usage

MAX_PROMPT_BYTES = 32768
MAX_STDOUT_BYTES = 262144
MAX_RESULT_BYTES = 8192


class ClaudeEditError(RuntimeError):
    """The editing turn did not produce a verified terminal observation."""


def _result(raw: bytes, model: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaudeEditError("Claude edit emitted invalid JSON") from exc
    if (not isinstance(payload, dict) or payload.get("type") != "result"
            or payload.get("subtype") != "success" or payload.get("is_error") is not False):
        raise ClaudeEditError("Claude edit did not complete successfully")
    output = payload.get("result")
    turns = payload.get("num_turns")
    session = payload.get("session_id")
    if not isinstance(output, str) or not output.strip() or len(output.encode()) > MAX_RESULT_BYTES:
        raise ClaudeEditError("Claude edit result is missing or oversized")
    if isinstance(turns, bool) or not isinstance(turns, int) or not 1 <= turns <= 8:
        raise ClaudeEditError("Claude edit exceeded its turn bound")
    if not isinstance(session, str) or not session:
        raise ClaudeEditError("Claude edit session identity is missing")
    try:
        usage = _normalized_usage(payload.get("usage"))
    except Exception as exc:
        raise ClaudeEditError("Claude edit usage is invalid") from exc
    return {"schema_version": 1, "status": "completed", "provider": "claude",
            "model": model, "physical_call": True,
            "evidence_level": "flow_observed_claude_cli_edit_completed",
            "output": output, "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "usage": usage, "session_id": session, "num_turns": turns}


def call_claude_edit(*, instructions: str, task: str, workspace: Path, model: str,
                     timeout_seconds: int, claude_bin: str = "claude") -> dict[str, Any]:
    """Allow only Claude file tools; caller must verify every resulting edit."""
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
    if not instructions.strip() or not task.strip():
        raise ValueError("Claude task and instructions are required")
    prompt = ("Specialist instructions:\n" + instructions + "\n\nAuthorized task:\n" + task
              + "\n\nUse only Read, Glob, Grep, and Edit. Do not use shell, MCP, or subagents. "
                "Edit only the explicitly authorized files. Return a short summary.\n").encode()
    if len(prompt) > MAX_PROMPT_BYTES:
        raise ValueError("Claude prompt exceeds limit")
    argv = [claude_bin, "-p", "--output-format", "json", "--safe-mode", "--restricted",
            "--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands",
            "--permission-mode", "acceptEdits", "--tools", "Read,Glob,Grep,Edit",
            "--model", model]
    env = {key: os.environ[key] for key in CLAUDE_ENV_KEYS if key in os.environ}
    deadline = time.monotonic() + timeout_seconds
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, cwd=workspace, env=env,
                               start_new_session=True)
    if process.stdin is None or process.stdout is None:
        raise ClaudeEditError("Claude process pipes unavailable")
    try:
        chunks: list[bytes] = []
        size = written = 0
        selector = selectors.DefaultSelector()
        os.set_blocking(process.stdin.fileno(), False)
        selector.register(process.stdin, selectors.EVENT_WRITE)
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ClaudeEditError("Claude edit timed out")
                ready = selector.select(remaining)
                if not ready:
                    raise ClaudeEditError("Claude edit timed out")
                for key, _ in ready:
                    if key.fileobj is process.stdin:
                        count = os.write(process.stdin.fileno(), prompt[written:])
                        written += count
                        if written == len(prompt):
                            selector.unregister(process.stdin)
                            process.stdin.close()
                    else:
                        chunk = os.read(process.stdout.fileno(), min(8192, MAX_STDOUT_BYTES + 1 - size))
                        if not chunk:
                            selector.unregister(process.stdout)
                            continue
                        chunks.append(chunk)
                        size += len(chunk)
                        if size > MAX_STDOUT_BYTES:
                            raise ClaudeEditError("Claude edit output exceeds limit")
        finally:
            selector.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ClaudeEditError("Claude edit timed out")
        if process.wait(timeout=remaining) != 0:
            raise ClaudeEditError("Claude exited without a successful edit turn")
        return {**_result(b"".join(chunks), model),
                "input_sha256": hashlib.sha256(prompt).hexdigest()}
    except (subprocess.TimeoutExpired, BrokenPipeError) as exc:
        raise ClaudeEditError("Claude edit outcome uncertain") from exc
    finally:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()
