"""Small diagnostic result model shared by support-facing commands."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_OK = "ok"
STATUS_WARNING = "warning"
STATUS_FAILED = "failed"
STATUS_NOT_APPLICABLE = "not_applicable"

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"


@dataclass(frozen=True)
class Diagnostic:
    id: str
    status: str
    severity: str
    category: str
    summary: str
    target: str | None = None
    path: str | None = None
    detail: str | None = None
    next_action: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


def diagnostic(
    id: str,
    status: str,
    severity: str,
    category: str,
    summary: str,
    *,
    target: str | None = None,
    path: Path | str | None = None,
    detail: str | None = None,
    next_action: str | None = None,
) -> Diagnostic:
    return Diagnostic(
        id=id,
        status=status,
        severity=severity,
        category=category,
        summary=summary,
        target=target,
        path=str(path) if path is not None else None,
        detail=detail,
        next_action=next_action,
    )


def support_payload(command: str, root: Path, diagnostics: list[Diagnostic], **extra: Any) -> dict[str, Any]:
    errors = sum(1 for item in diagnostics if item.severity == SEVERITY_ERROR)
    warnings = sum(1 for item in diagnostics if item.severity == SEVERITY_WARNING)
    payload = {
        "command": command,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "root": str(root),
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "diagnostics": [item.to_dict() for item in diagnostics],
    }
    payload.update(extra)
    return payload


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def exit_code(diagnostics: list[Diagnostic], *, check: bool, fail_on_warnings: bool = False) -> int:
    if not check:
        return 0
    fail_severities = {SEVERITY_ERROR}
    if fail_on_warnings:
        fail_severities.add(SEVERITY_WARNING)
    return 1 if any(item.severity in fail_severities for item in diagnostics) else 0
