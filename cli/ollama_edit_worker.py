"""Flow-owned structured-edit mediator for Ollama producer proposals."""

from __future__ import annotations

import hashlib
import base64
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any, Callable

from execution_contracts import ContractError
from fsutil import write_atomic
from local_worker import call_local
from provider_selection import digest


MAX_SOURCE_FILES = 32
MAX_SOURCE_BYTES = 256 * 1024
MAX_EDITS = 16
MAX_EDIT_BYTES = 128 * 1024
EDIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "model", "bundle_digest", "edits"],
    "properties": {
        "schema_version": {"type": "integer", "const": 1},
        "model": {"type": "string"},
        "bundle_digest": {"type": "string"},
        "edits": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["path", "base_sha256", "content"],
            "properties": {"path": {"type": "string"}, "base_sha256": {"type": "string"},
                           "content": {"type": "string"}},
        }},
    },
}


def source_bundle(root: Path, paths: list[str]) -> dict[str, Any]:
    root = root.resolve()
    if not isinstance(paths, list) or not paths or len(paths) > MAX_SOURCE_FILES:
        raise ContractError("Ollama source bundle path count is invalid")
    files, total = [], 0
    for raw in sorted(set(paths)):
        target = _safe_target(root, raw, must_exist=True)
        data = target.read_bytes()
        total += len(data)
        if total > MAX_SOURCE_BYTES:
            raise ContractError("Ollama source bundle exceeds size limit")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ContractError("Ollama source bundle requires UTF-8 text") from exc
        files.append({"path": raw, "sha256": hashlib.sha256(data).hexdigest(), "content": content})
    bundle = {"schema_version": 1, "files": files}
    bundle["bundle_digest"] = digest(bundle)
    return bundle


def propose_edits(bundle: dict[str, Any], task: str, *, model: str, attempt_id: str,
                  transport: Callable[..., Any] | None = None,
                  timeout_seconds: int = 60) -> dict[str, Any]:
    envelope = {
        "provider": "ollama", "model": model, "attempt_id": attempt_id,
        "instructions": (
            "Return one JSON object only with exactly four top-level fields: "
            "schema_version, model, bundle_digest, and edits. Do not repeat source files. "
            "Each edit has path, base_sha256, and complete UTF-8 content. "
            f"The model field must be exactly {model}."
        ),
        "task": task + "\nSOURCE_BUNDLE=" + json.dumps(bundle, sort_keys=True, separators=(",", ":")),
    }
    result = call_local(envelope, transport=transport, correlation_id=f"{attempt_id}-edit",
                        timeout_seconds=timeout_seconds, response_schema=EDIT_SCHEMA)
    proposal = _extract_json_object(result["output"])
    if not isinstance(proposal, dict):
        raise ContractError("Ollama edit proposal must be an object")
    return proposal


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError("Ollama edit proposal must be exactly one JSON object") from exc
    if not isinstance(value, dict):
        raise ContractError("Ollama edit proposal must be an object")
    return value


def validate_and_apply(root: Path, bundle: dict[str, Any], proposal: dict[str, Any], *,
                       write_scopes: list[str], expected_model: str) -> dict[str, Any]:
    root = root.resolve()
    lock_path = Path(tempfile.gettempdir()) / f"flow-ollama-edit-{hashlib.sha256(str(root).encode()).hexdigest()}.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        return _validate_and_apply_locked(root, bundle, proposal, write_scopes=write_scopes,
                                          expected_model=expected_model)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _validate_and_apply_locked(root: Path, bundle: dict[str, Any], proposal: dict[str, Any], *,
                               write_scopes: list[str], expected_model: str) -> dict[str, Any]:
    journal = root / ".flow-ollama-edit-journal.json"
    if journal.exists():
        _recover_journal(root, journal)
    if set(proposal) != {"schema_version", "model", "bundle_digest", "edits"}:
        raise ContractError("Ollama edit proposal fields are invalid")
    if proposal.get("schema_version") != 1 or proposal.get("bundle_digest") != bundle.get("bundle_digest"):
        raise ContractError("Ollama edit proposal bundle binding is invalid")
    if proposal.get("model") != expected_model:
        raise ContractError("Ollama edit proposal model differs from grant")
    edits = proposal.get("edits")
    if not isinstance(edits, list) or not edits or len(edits) > MAX_EDITS:
        raise ContractError("Ollama edit count is invalid")
    bundle_files = {item["path"]: item for item in bundle.get("files", [])}
    scopes = [PurePosixPath(item) for item in write_scopes]
    prepared: list[tuple[Path, str, bytes, tuple[int, int, int], tuple[int, int]]] = []
    seen: set[str] = set()
    total = 0
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {"path", "base_sha256", "content"}:
            raise ContractError("Ollama edit fields are invalid")
        raw = edit["path"]
        if raw in seen or raw not in bundle_files:
            raise ContractError("Ollama edit target is absent or duplicated")
        seen.add(raw)
        path = PurePosixPath(raw)
        if not any(path == scope or scope in path.parents for scope in scopes):
            raise ContractError("Ollama edit target is outside write scope")
        target = _safe_target(root, raw, must_exist=True)
        current = target.read_bytes()
        if hashlib.sha256(current).hexdigest() != edit["base_sha256"] \
                or edit["base_sha256"] != bundle_files[raw]["sha256"]:
            raise ContractError("Ollama edit base digest is stale")
        content = edit["content"]
        if not isinstance(content, str):
            raise ContractError("Ollama edit content must be text")
        encoded = content.encode()
        total += len(encoded)
        if total > MAX_EDIT_BYTES:
            raise ContractError("Ollama edits exceed size limit")
        stat = target.stat(follow_symlinks=False)
        parent_stat = target.parent.stat(follow_symlinks=False)
        prepared.append((target, content, current, (stat.st_dev, stat.st_ino, stat.st_mode),
                         (parent_stat.st_dev, parent_stat.st_ino)))

    # Stage every replacement before mutating the workspace. Recheck the exact
    # inode immediately before each replace so a path cannot be swapped for a
    # symlink between validation and application. A failed commit is rolled
    # back from the already captured bytes.
    staged: list[tuple[Path, Path, bytes, tuple[int, int, int], tuple[int, int]]] = []
    for target, content, old, identity, parent_identity in prepared:
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.flow-edit-", suffix=".tmp")
        temp = Path(name)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, identity[2] & 0o7777)
            staged.append((target, temp, old, identity, parent_identity))
        except BaseException:
            temp.unlink(missing_ok=True)
            for _target, staged_temp, _old, _identity, _parent_identity in staged:
                staged_temp.unlink(missing_ok=True)
            raise

    journal_record = {
        "schema_version": 1,
        "state": "prepared",
        "files": [{"path": target.relative_to(root).as_posix(),
                   "old_base64": base64.b64encode(old).decode("ascii")}
                  for target, _temp, old, _identity, _parent_identity in staged],
    }
    write_atomic(journal, json.dumps(journal_record, sort_keys=True, separators=(",", ":")) + "\n",
                 mode=0o600)
    _fsync_directory(root)

    changed: list[tuple[Path, bytes]] = []
    try:
        for target, temp, old, identity, parent_identity in staged:
            parent_stat = target.parent.stat(follow_symlinks=False)
            stat = target.stat(follow_symlinks=False)
            if target.parent.is_symlink() or (parent_stat.st_dev, parent_stat.st_ino) != parent_identity \
                    or target.is_symlink() or (stat.st_dev, stat.st_ino, stat.st_mode) != identity \
                    or hashlib.sha256(target.read_bytes()).hexdigest() != hashlib.sha256(old).hexdigest():
                raise ContractError("Ollama edit target changed during application")
            os.replace(temp, target)
            _fsync_directory(target.parent)
            changed.append((target, old))
    except BaseException:
        for target, old in reversed(changed):
            write_atomic(target, old.decode("utf-8"))
        journal.unlink(missing_ok=True)
        _fsync_directory(root)
        raise
    finally:
        for _target, temp, _old, _identity, _parent_identity in staged:
            temp.unlink(missing_ok=True)
    journal.unlink(missing_ok=True)
    _fsync_directory(root)
    return {
        "schema_version": 1,
        "bundle_digest": bundle["bundle_digest"],
        "proposal_digest": digest(proposal),
        "changed_paths": [path.relative_to(root).as_posix() for path, _content, _old, _identity, _parent_identity in prepared],
        "result_digests": {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path, _content, _old, _identity, _parent_identity in prepared},
    }


def _recover_journal(root: Path, journal: Path) -> None:
    if journal.is_symlink():
        raise ContractError("Ollama edit recovery journal is unsafe")
    try:
        record = json.loads(journal.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError("Ollama edit recovery journal is invalid") from exc
    if not isinstance(record, dict) or set(record) != {"schema_version", "state", "files"} \
            or record.get("schema_version") != 1 or record.get("state") != "prepared" \
            or not isinstance(record.get("files"), list):
        raise ContractError("Ollama edit recovery journal is invalid")
    for item in record["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "old_base64"}:
            raise ContractError("Ollama edit recovery journal is invalid")
        target = _safe_target(root, item["path"], must_exist=True)
        try:
            old = base64.b64decode(item["old_base64"], validate=True)
            old.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ContractError("Ollama edit recovery journal is invalid") from exc
        write_atomic(target, old.decode("utf-8"))
        _fsync_directory(target.parent)
    journal.unlink()
    _fsync_directory(root)


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _safe_target(root: Path, raw: Any, *, must_exist: bool) -> Path:
    if not isinstance(raw, str) or not raw or PurePosixPath(raw).is_absolute() \
            or any(part in {"", ".", ".."} for part in PurePosixPath(raw).parts):
        raise ContractError("Ollama path is unsafe")
    target = root.joinpath(*PurePosixPath(raw).parts)
    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != root):
        raise ContractError("Ollama path traverses a symlink")
    if must_exist and (not target.is_file() or not target.resolve().is_relative_to(root)):
        raise ContractError("Ollama path is absent or outside workspace")
    return target
