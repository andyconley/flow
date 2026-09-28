"""Stock-manager request files for v8 delivery attempts (ADR 0020).

Each allowed manager call gets one canonical file in the attempt directory,
written before its grant is consumed, so the exact request that a send used
can be read and re-digested offline. The file is evidence, not authority.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

from execution_contracts import ContractError, canonical, digest

REQUEST_DIR = "manager-requests"
MAX_REQUEST_BYTES = 65536
_CALL_ID = re.compile(r"^[0-9a-f]{64}$")


def render_manager_prompt(messages: Any) -> str:
    """Render stock-manager messages to the exact prompt text Claude is sent.

    Pure, so the Claude ``input_sha256`` (the sha256 of these bytes) can be
    recomputed from a request file without a provider.
    """
    if not isinstance(messages, list) or not messages:
        raise ContractError("stock manager prompt structure is invalid")
    turns = []
    for item in messages:
        contents = item.get("contents") if isinstance(item, dict) else None
        role = item.get("role") if isinstance(item, dict) else None
        if not isinstance(role, str) or not isinstance(contents, list) or not contents:
            raise ContractError("stock manager prompt structure is invalid")
        parts = [part.get("text") for part in contents if isinstance(part, dict) and part.get("type") == "text"]
        if len(parts) != len(contents) or any(not isinstance(part, str) for part in parts):
            raise ContractError("stock manager message contains unsupported content")
        turns.append(f"{role}:\n" + "\n".join(parts))
    prompt = "\n\n".join(turns)
    if not prompt.strip():
        raise ContractError("stock manager prompt text is absent")
    return prompt


def request_bytes(call_id: str, prompt_digest: str, messages: Any) -> bytes:
    """The canonical file content for one manager call; refuses a digest mismatch."""
    if not isinstance(call_id, str) or not _CALL_ID.match(call_id):
        raise ContractError("manager request call id is invalid")
    if digest(messages) != prompt_digest:
        raise ContractError("manager request messages differ from their prompt digest")
    data = (canonical({"call_id": call_id, "messages": messages, "prompt_digest": prompt_digest}) + "\n").encode()
    if len(data) > MAX_REQUEST_BYTES:
        raise ContractError("manager request exceeds its size limit")
    return data


def _request_dir(attempt_dir: Path, *, create: bool) -> Path:
    directory = Path(attempt_dir) / REQUEST_DIR
    if directory.is_symlink():
        raise ContractError("manager request directory is unsafe")
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink() or not directory.is_dir():
            raise ContractError("manager request directory is unsafe")
    return directory


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_bounded(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as handle:
        data = handle.read(MAX_REQUEST_BYTES + 1)
    if len(data) > MAX_REQUEST_BYTES:
        raise ContractError("manager request file exceeds its size limit")
    return data


def write_request_file(attempt_dir: Path, call_id: str, data: bytes) -> Path:
    """Link ``data`` into place for ``call_id``; identical bytes are reused, different bytes refuse.

    A temporary file is written, fsynced and hard-linked to the final name, so
    the final path is never partial and never overwritten. The directory is
    fsynced before returning, so the name is durable before the grant is used.
    """
    if not isinstance(call_id, str) or not _CALL_ID.match(call_id):
        raise ContractError("manager request call id is invalid")
    directory = _request_dir(attempt_dir, create=True)
    final = directory / f"{call_id}.json"
    temporary = directory / f".{call_id}.{uuid.uuid4().hex}.tmp"
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, final)
        except FileExistsError:
            if final.is_symlink() or _read_bounded(final) != data:
                raise ContractError("manager request file conflicts with this call") from None
        _fsync_dir(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return final


def read_request_file(attempt_dir: Path, call_id: str) -> bytes | None:
    """The stored request bytes for ``call_id``, or None when there is no file."""
    directory = _request_dir(attempt_dir, create=False)
    path = directory / f"{call_id}.json"
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink():
        raise ContractError("manager request file is unsafe")
    return _read_bounded(path)


def list_request_files(attempt_dir: Path) -> tuple[list[str], list[str]]:
    """The call ids with request files, and any leftover temporary names (informational)."""
    directory = Path(attempt_dir) / REQUEST_DIR
    if not directory.is_dir() or directory.is_symlink():
        return [], []
    calls, leftovers = [], []
    for entry in sorted(directory.iterdir()):
        name = entry.name
        if name.startswith(".") and name.endswith(".tmp"):
            leftovers.append(name)
        elif name.endswith(".json"):
            calls.append(name[:-5])
        else:
            leftovers.append(name)
    return calls, leftovers
