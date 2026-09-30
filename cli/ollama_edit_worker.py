"""Flow-owned structured-edit mediator for Ollama producer proposals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
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
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ContractError("Ollama edit proposal is malformed JSON")


def validate_and_apply(root: Path, bundle: dict[str, Any], proposal: dict[str, Any], *,
                       write_scopes: list[str], expected_model: str) -> dict[str, Any]:
    root = root.resolve()
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
    prepared: list[tuple[Path, str, bytes]] = []
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
        prepared.append((target, content, current))
    changed = []
    try:
        for target, content, _old in prepared:
            write_atomic(target, content)
            changed.append(target)
    except BaseException:
        for target, _content, old in prepared:
            if target in changed:
                write_atomic(target, old.decode("utf-8"))
        raise
    return {
        "schema_version": 1,
        "bundle_digest": bundle["bundle_digest"],
        "proposal_digest": digest(proposal),
        "changed_paths": [path.relative_to(root).as_posix() for path, _content, _old in prepared],
        "result_digests": {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path, _content, _old in prepared},
    }


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
