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
import subprocess
import time
from pathlib import Path
from typing import Any

MAX_PROMPT_BYTES = 16384
MAX_EVENT_BYTES = 262144
MAX_OUTPUT_BYTES = 4096
CODEX_ENV_KEYS = ("HOME", "CODEX_HOME", "PATH", "TMPDIR", "LANG", "LC_ALL",
                  "LC_CTYPE", "USER", "LOGNAME")


class CodexWorkerError(RuntimeError):
    """Codex may have acted, but Flow did not observe a valid completed turn."""


def _parse_events(raw: bytes, expected_model: str) -> dict[str, Any]:
    try:
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
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
    if len(output.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise CodexWorkerError("Codex final message exceeds output limit")
    usage = completed[0].get("usage")
    if usage is not None:
        if not isinstance(usage, dict) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in usage.values()
        ):
            raise CodexWorkerError("Codex usage is invalid")
    return {"schema_version": 1, "status": "completed", "provider": "codex",
            "model": expected_model, "physical_call": True,
            "evidence_level": "flow_observed_codex_cli_completed_turn",
            "output": output,
            "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
            "usage": usage, "thread_id": thread_id}


def call_codex(*, instructions: str, task: str, workspace: Path, model: str,
               timeout_seconds: int, codex_bin: str = "codex") -> dict[str, Any]:
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
    prompt = ("Specialist instructions:\n" + instructions + "\n\nAuthorized task:\n" + task
              + "\n\nWork only in this workspace. Do not spawn subagents or delegate. "
                "Complete this single task and report the change and checks.\n")
    prompt_bytes = prompt.encode("utf-8")
    if not instructions.strip() or not task.strip() or len(prompt_bytes) > MAX_PROMPT_BYTES:
        raise ValueError("Codex prompt is empty or too large")
    argv = [codex_bin, "exec", "--json", "--ephemeral", "--ignore-user-config",
            "--skip-git-repo-check", "--sandbox", "workspace-write",
            "--model", model, "--cd", str(workspace),
            "--config", 'approval_policy="never"',
            "--config", "features.multi_agent=false", "-"]
    # Auth is read from CODEX_HOME (or HOME/.codex). Do not inherit unrelated
    # credentials, cloud configuration, proxy variables, or project secrets.
    env = {key: os.environ[key] for key in CODEX_ENV_KEYS if key in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, cwd=workspace, env=env,
                               start_new_session=True)
    assert process.stdin is not None and process.stdout is not None
    try:
        process.stdin.write(prompt_bytes)
        process.stdin.close()
        deadline = time.monotonic() + timeout_seconds
        chunks: list[bytes] = []
        size = 0
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexWorkerError("Codex turn timed out")
                if not selector.select(remaining):
                    raise CodexWorkerError("Codex turn timed out")
                chunk = os.read(process.stdout.fileno(), min(8192, MAX_EVENT_BYTES + 1 - size))
                if not chunk:
                    selector.unregister(process.stdout)
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > MAX_EVENT_BYTES:
                    raise CodexWorkerError("Codex event stream exceeds limit")
        finally:
            selector.close()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CodexWorkerError("Codex turn timed out")
        if process.wait(timeout=remaining) != 0:
            raise CodexWorkerError("Codex exited without a successful turn")
        return _parse_events(b"".join(chunks), model)
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
        process.stdout.close()
