"""Read-only inspection for pre-Delivery-Charter execution records.

The version-six Magentic envelope remains historical evidence.  It is not a
source of authority for a new Delivery Charter, so this module intentionally
does not expose a conversion or dispatch API.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


LEGACY_PROTOCOL_VERSION = 6


class LegacyDeliveryError(ValueError):
    """A caller attempted to use an inspect-only historical record."""


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                   allow_nan=False).encode("utf-8")
    ).hexdigest()


def _diagnostic(code: str, message: str, *, severity: str = "error") -> dict[str, str]:
    return {"code": code, "severity": severity, "message": message}


def _read_raw(source: Path | bytes | str | dict[str, Any]) -> tuple[bytes, str | None]:
    if isinstance(source, Path):
        return source.read_bytes(), str(source)
    if isinstance(source, bytes):
        return source, None
    if isinstance(source, str):
        return source.encode("utf-8"), None
    if isinstance(source, dict):
        return json.dumps(source, indent=2, sort_keys=True).encode("utf-8"), None
    raise TypeError("legacy delivery source must be a path, bytes, JSON text, or object")


def _known_fields(record: dict[str, Any]) -> dict[str, Any]:
    """Return only stable inspection fields without normalizing raw evidence."""
    return {
        key: record[key]
        for key in (
            "schema_version", "execution_protocol_version", "work_id", "attempt_id",
            "charter_digest", "manifest_digest", "source_commit", "worktree",
            "allowed_paths", "roster", "job_contract", "status",
        )
        if key in record
    }


def inspect_legacy_delivery(source: Path | bytes | str | dict[str, Any]) -> dict[str, Any]:
    """Inspect v6 JSON without validating it as a current executable contract.

    The returned ``raw_sha256`` always identifies the exact supplied bytes.
    Diagnostics are structured so callers can display useful evidence even for
    malformed or partially migrated historical files.
    """
    raw, path = _read_raw(source)
    report: dict[str, Any] = {
        "compatibility": "v6-inspection-only",
        "readable": False,
        "executable": False,
        "resumable": False,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
        "diagnostics": [],
        "integrity": {"status": "unknown", "checks": []},
        "normalized": {},
    }
    if path is not None:
        report["source_path"] = path
    try:
        value = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        report["diagnostics"].append(_diagnostic("legacy_utf8_invalid", "record is not UTF-8 JSON"))
        return report
    except json.JSONDecodeError as exc:
        report["diagnostics"].append(
            _diagnostic("legacy_json_invalid", f"record is malformed JSON at line {exc.lineno}, column {exc.colno}")
        )
        return report
    if not isinstance(value, dict):
        report["diagnostics"].append(_diagnostic("legacy_record_invalid", "record root must be a JSON object"))
        return report

    report["readable"] = True
    report["normalized"] = _known_fields(value)
    protocol = value.get("execution_protocol_version")
    if protocol != LEGACY_PROTOCOL_VERSION:
        report["diagnostics"].append(
            _diagnostic("legacy_protocol_unexpected", f"expected execution protocol v6, found {protocol!r}")
        )
        return report

    checks: list[dict[str, Any]] = []
    failures = 0

    sources = value.get("charter_sources")
    charter_digest = value.get("charter_digest")
    if isinstance(sources, dict) and isinstance(sources.get("requirements"), dict) and isinstance(sources.get("acceptance"), dict):
        expected = _digest({
            "requirements": sources["requirements"].get("sha256"),
            "acceptance": sources["acceptance"].get("sha256"),
        })
        passed = charter_digest == expected
        checks.append({"name": "charter_digest", "status": "passed" if passed else "failed", "expected": expected, "actual": charter_digest})
        if not passed:
            failures += 1
            report["diagnostics"].append(_diagnostic("legacy_charter_digest_mismatch", "charter digest does not match recorded source digests"))
    else:
        checks.append({"name": "charter_digest", "status": "not_checked"})
        report["diagnostics"].append(_diagnostic("legacy_charter_sources_missing", "charter source digests are unavailable", severity="warning"))

    roster = value.get("roster")
    if isinstance(roster, list):
        for index, member in enumerate(roster):
            if not isinstance(member, dict):
                checks.append({"name": "definition_digest", "index": index, "status": "not_checked"})
                continue
            expected = _digest({"role": member.get("role"), "instructions": member.get("instructions")})
            passed = member.get("definition_digest") == expected
            checks.append({"name": "definition_digest", "index": index, "status": "passed" if passed else "failed", "expected": expected, "actual": member.get("definition_digest")})
            if not passed:
                failures += 1
                report["diagnostics"].append(_diagnostic("legacy_definition_digest_mismatch", f"roster entry {index} definition digest does not match its recorded role and instructions"))
    else:
        checks.append({"name": "definition_digest", "status": "not_checked"})
        report["diagnostics"].append(_diagnostic("legacy_roster_missing", "roster is unavailable", severity="warning"))

    report["integrity"] = {"status": "failed" if failures else "passed", "checks": checks}
    report["diagnostics"].append(_diagnostic("legacy_v6_inspection_only", "v6 records are readable historical evidence and cannot execute or resume", severity="warning"))
    return report


def refuse_legacy_execution(inspection: dict[str, Any], operation: str) -> None:
    """Raise the actionable refusal used by current execution and resume paths."""
    if operation not in {"execute", "resume"}:
        raise ValueError("legacy operation must be execute or resume")
    if inspection.get("compatibility") == "v6-inspection-only":
        raise LegacyDeliveryError(
            f"execution protocol v6 is inspect-only and cannot {operation}; create a new Delivery Charter and attempt"
        )
