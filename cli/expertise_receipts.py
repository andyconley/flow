"""Private immutable pre-agent and linked disposition receipts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from typing import Any

from expertise_model import canonical_json, validate_disposition_record
from expertise_paths import PrivatePathError, checked_path


SCHEMA_VERSION = 1
RETENTION_DAYS = 30
BANNED_KEYS = frozenset({
    "task", "query", "normalized_text", "task_facts", "facts", "evidence_span",
    "query_vector", "vector", "trigger_view", "failure_mode_view", "abstract",
    "flow:trigger", "flow:requiredBehavior", "flow:failureMode", "flow:source",
    "method", "model_input", "model_output", "free_form_reason", "exception",
    "credentials", "secret",
})


class ExpertiseReceiptError(ValueError):
    pass


def receipt_root(project_root: Path | None, flow_home: Path) -> Path:
    if project_root is not None and (Path(project_root) / ".flow").is_dir():
        return Path(project_root) / ".flow" / ".cache" / "expertise" / "receipts"
    return Path(flow_home) / "cache" / "expertise" / "receipts"


def _contained(path: Path, root: Path) -> Path:
    try:
        return checked_path(path, root, anchor=Path(root).absolute().parents[2])
    except PrivatePathError as error:
        raise ExpertiseReceiptError("receipt path escapes or redirects its private root") from error


def _assert_allowlisted(value: Any, path: str = "receipt") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in BANNED_KEYS:
                raise ExpertiseReceiptError(f"private content field is prohibited in {path}: {key}")
            _assert_allowlisted(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_allowlisted(item, f"{path}[{index}]")
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise ExpertiseReceiptError(f"unsupported receipt value at {path}")


def _write_once(path: Path, value: dict, root: Path) -> str:
    _assert_allowlisted(value)
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError as error:
        raise ExpertiseReceiptError("receipt path escapes its private root") from error
    root = _contained(root, root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    path = _contained(root / relative, root)
    payload = (canonical_json(value) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError as error:
        raise ExpertiseReceiptError("immutable receipt already exists") from error
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return hashlib.sha256(payload).hexdigest()


def _secret(flow_home: Path) -> bytes:
    root = Path(flow_home) / "cache" / "expertise"
    root = _contained(root, root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    path = _contained(root / "receipt.key", root)
    if not path.exists():
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(secrets.token_bytes(32))
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
    data = path.read_bytes()
    if len(data) != 32 or path.stat().st_mode & 0o077:
        raise ExpertiseReceiptError("receipt key is invalid or not private")
    return data


def query_hmac(flow_home: Path, normalized_query: str) -> str:
    return hmac.new(_secret(flow_home), normalized_query.encode("utf-8"), hashlib.sha256).hexdigest()


def safe_pre_receipt(outcome: dict, *, query_digest: str, created_at: str) -> dict:
    ranking = outcome["ranking"]
    admission = outcome["admission"]
    delivery = outcome["delivery"]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "pre-agent",
        "created_at": created_at,
        "request_id": outcome["request_id"],
        "role": outcome["role"],
        "query_hmac": query_digest,
        "state": outcome["state"],
        "cause": outcome["cause"],
        "eligibility": {
            "state": outcome["eligibility"]["state"],
            "identity": outcome["eligibility"]["identity"],
            "eligible_ids": outcome["eligibility"]["eligible_ids"],
            "excluded": outcome["eligibility"]["excluded"],
        },
        "ranking": {
            "state": ranking["state"], "reason": ranking["reason"],
            "provider_calls": ranking["provider_calls"], "identity": ranking["identity"],
            "candidates": [{key: row[key] for key in ("entry_id", "ordinal", "provider_score", "entry_digest", "score_semantics", "structured_exact_match")} for row in ranking["candidates"]],
        },
        "admission": admission,
        "delivery": {
            "state": delivery["state"], "reason": delivery["reason"],
            "delivered_ids": delivery["delivered_ids"], "withheld_ids": delivery["withheld_ids"],
            "actual_bytes": delivery["actual_bytes"], "limits": delivery["limits"],
            "identity": delivery["identity"],
        },
        "elapsed_ms": outcome.get("elapsed_ms"),
    }


def write_pre(root: Path, flow_home: Path, outcome: dict, normalized_query: str) -> dict:
    root = _contained(root, root)
    created_at = datetime.now(timezone.utc).isoformat()
    value = safe_pre_receipt(outcome, query_digest=query_hmac(flow_home, normalized_query), created_at=created_at)
    path = root / f"{outcome['request_id']}.pre.json"
    receipt_digest = _write_once(path, value, root)
    return {"path": str(path), "digest": receipt_digest, "receipt": value}


def write_post(root: Path, value: dict, delivered_ids: list[str]) -> dict:
    root = _contained(root, root)
    record = dict(value)
    record["created_at"] = datetime.now(timezone.utc).isoformat()
    validate_disposition_record(record, delivered_ids)
    path = root / f"{record['request_id']}.post.json"
    receipt_digest = _write_once(path, record, root)
    return {"path": str(path), "digest": receipt_digest, "receipt": record}


def inspect_receipts(root: Path) -> dict:
    root = _contained(root, root)
    if not root.exists():
        return {"state": "ready", "count": 0, "receipts": []}
    rows = []
    for path in sorted(root.glob("*.json")):
        try:
            path = _contained(path, root)
            value = json.loads(path.read_text())
            _assert_allowlisted(value)
            value.pop("query_hmac", None)
            rows.append({"file": path.name, "state": "valid", "receipt": value})
        except (OSError, ValueError, json.JSONDecodeError) as error:
            rows.append({"file": path.name, "state": "invalid", "diagnostic": type(error).__name__})
    return {"state": "ready", "count": len(rows), "receipts": rows}


def purge(root: Path, *, now: datetime | None = None, days: int = RETENTION_DAYS) -> dict:
    if not isinstance(days, int) or isinstance(days, bool) or days < 0:
        raise ExpertiseReceiptError("retention days must be non-negative")
    root = _contained(root, root)
    if not root.exists():
        return {"state": "complete", "deleted": 0, "invalid": []}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    deleted = 0
    invalid = []
    for path in sorted(root.glob("*.json")):
        try:
            path = _contained(path, root)
            value = json.loads(path.read_text())
            created = datetime.fromisoformat(str(value["created_at"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                raise ValueError("timestamp lacks timezone")
            if created.astimezone(timezone.utc) < cutoff:
                path.unlink()
                deleted += 1
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            invalid.append(path.name)
    return {"state": "complete", "deleted": deleted, "invalid": invalid}
