"""Prepare and validate auditable live evidence for session-model advice.

This harness intentionally does not invoke a provider or decide that a missing
client is success.  It prepares a synced, isolated runtime surface and records
the ten required cells as blocked until an authenticated operator attaches
redacted evidence and an independent reviewer marks each cell passed.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
FLOW = REPO / "cli" / "flow.py"
RUNTIMES = ("claude", "codex")
LANES = ("boot", "resume", "define", "solution", "plan")
SCENARIOS = (
    "unknown_boot",
    "suitable_parent",
    "architectural_ambiguity",
    "unchanged_then_material_change",
    "plan_coordinator_and_delegation",
)
VALID_STATUSES = {"passed", "failed", "blocked"}
PROFILES = ("mechanical", "working", "judgment", "demanding")
PASS_CELL_FIELDS = {
    "client_version",
    "cli_version",
    "selected_mapping",
    "session_binding",
    "response_evidence",
    "legal_timing",
    "recommendation",
    "parent_provenance",
    "lane_continuation",
    "reviewer",
    "reviewer_disposition",
}
PASS_MAPPING_FIELDS = {
    "model",
    "effort",
    "intended_use",
    "source_url",
    "source_accessed_at",
    "configuration_provenance",
    "syntax_validation",
    "account_availability",
    "live_result",
    "reviewer_disposition",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(argv: list[str], cwd: Path, env: dict[str, str]) -> dict[str, object]:
    completed = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True)
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _skill(home: Path, runtime: str, lane: str) -> Path:
    root = home / ".claude" / "skills" if runtime == "claude" else home / ".agents" / "skills"
    return root / f"flow-{lane}" / "SKILL.md"


def _validate_response_evidence(cell: dict, repository: Path) -> None:
    """Verify ordered live-response records without allowing path escape."""
    records = cell.get("response_evidence")
    if not isinstance(records, list) or not records:
        raise ValueError(f"passed cell {cell.get('id')} needs nonempty ordered response_evidence")
    verified_records: list[dict] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"passed cell {cell.get('id')} response_evidence[{index}] must be a record")
        raw_path = record.get("path")
        expected_digest = record.get("sha256")
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError(f"passed cell {cell.get('id')} response_evidence[{index}] needs a path")
        if not isinstance(expected_digest, str) or len(expected_digest) != 64:
            raise ValueError(f"passed cell {cell.get('id')} response_evidence[{index}] needs a SHA-256")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ValueError(f"passed cell {cell.get('id')} response evidence path must be repository-relative")
        candidate = (repository / relative).resolve()
        if not candidate.is_relative_to(repository):
            raise ValueError(f"passed cell {cell.get('id')} response evidence escapes the repository")
        if not candidate.is_file():
            raise ValueError(f"passed cell {cell.get('id')} response evidence is missing: {raw_path}")
        if _sha256(candidate) != expected_digest:
            raise ValueError(f"passed cell {cell.get('id')} response evidence hash mismatch: {raw_path}")
        verified_records.append(record)
    expected_aggregate = cell.get("response_evidence_sha256")
    if not isinstance(expected_aggregate, str) or len(expected_aggregate) != 64:
        raise ValueError(f"passed cell {cell.get('id')} needs response_evidence_sha256")
    canonical = json.dumps(verified_records, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(canonical).hexdigest() != expected_aggregate:
        raise ValueError(f"passed cell {cell.get('id')} response evidence aggregate hash mismatch")


def prepare(destination: Path) -> Path:
    """Create isolated synced surfaces and a blocked-until-reviewed ledger."""
    destination = destination.resolve()
    repository = REPO.resolve()
    if destination.is_relative_to(repository):
        raise ValueError(
            f"live-evidence destination must be outside the Flow repository: {destination}"
        )
    home = destination / "home"
    home.mkdir(parents=True, exist_ok=True)
    flow_home = home / ".flow"
    flow_home.mkdir(exist_ok=True)
    source = flow_home / "source"
    if not source.exists():
        source.symlink_to(REPO, target_is_directory=True)
    env = {**os.environ, "HOME": str(home), "NO_COLOR": "1"}
    sync = {
        runtime: _run([sys.executable, str(FLOW), "sync", runtime, "--user"], destination, env)
        for runtime in RUNTIMES
    }
    failures = [runtime for runtime, result in sync.items() if result["returncode"] != 0]
    if failures:
        raise RuntimeError(f"runtime sync failed: {', '.join(failures)}")

    cells: list[dict[str, object]] = []
    for runtime in RUNTIMES:
        for lane in LANES:
            skill = _skill(home, runtime, lane)
            if not skill.exists():
                raise RuntimeError(f"missing generated {runtime} skill for {lane}: {skill}")
            cells.append({
                "id": f"{runtime}-{lane}",
                "runtime": runtime,
                "lane": lane,
                "scenarios": list(SCENARIOS),
                "generated_skill": str(skill),
                "generated_skill_sha256": _sha256(skill),
                "status": "blocked",
                "blocker": "requires authenticated client, exercised configured mapping, and independent review",
                "required_evidence": [
                    "client and CLI version",
                    "selected mapping and native effort",
                    "current-session binding and parent provenance",
                    "redacted response or transcript location",
                    "legal timing, recommendation, lane-continuation, and reviewer disposition",
                ],
            })
    inventory = {
        "schema_version": 1,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(REPO),
        "source_revision": _run(["git", "rev-parse", "HEAD"], REPO, os.environ.copy())["stdout"].strip(),
        "runtime_sync": sync,
        "cells": cells,
        "mapping_ledger": [
            {
                "id": f"{runtime}-{profile}",
                "runtime": runtime,
                "profile": profile,
                "status": "blocked",
                "blocker": "requires exercised authenticated client result and independent review",
            }
            for runtime in RUNTIMES for profile in PROFILES
        ],
        "mapping_ledger_requirement": "Every enabled profile/runtime mapping needs an exercised authenticated result; catalog syntax alone is insufficient.",
    }
    path = destination / "model-advice-live-inventory.json"
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    return path


def validate(inventory_path: Path) -> int:
    """Return nonzero unless every required live cell has independent passing evidence."""
    inventory = json.loads(inventory_path.read_text())
    cells = inventory.get("cells")
    if not isinstance(cells, list):
        raise ValueError("inventory has no cells list")
    required = {f"{runtime}-{lane}" for runtime in RUNTIMES for lane in LANES}
    found = {cell.get("id") for cell in cells if isinstance(cell, dict)}
    if found != required:
        raise ValueError(f"inventory cells differ from required matrix: {sorted(found ^ required)}")
    invalid = [cell.get("id") for cell in cells if cell.get("status") not in VALID_STATUSES]
    if invalid:
        raise ValueError(f"inventory has invalid statuses: {invalid}")
    passed_missing = {
        cell["id"]: sorted(field for field in PASS_CELL_FIELDS if not cell.get(field))
        for cell in cells
        if cell.get("status") == "passed"
    }
    passed_missing = {identifier: fields for identifier, fields in passed_missing.items() if fields}
    if passed_missing:
        raise ValueError(f"passed cells lack required evidence: {passed_missing}")
    raw_repository = inventory.get("repository")
    if not isinstance(raw_repository, str) or not raw_repository:
        raise ValueError("inventory has no repository path")
    repository = Path(raw_repository).resolve()
    if not repository.is_dir():
        raise ValueError(f"inventory repository does not exist: {repository}")
    for cell in cells:
        if cell.get("status") == "passed":
            _validate_response_evidence(cell, repository)
    ledger = inventory.get("mapping_ledger")
    if not isinstance(ledger, list):
        raise ValueError("inventory has no mapping_ledger list")
    expected_mappings = {f"{runtime}-{profile}" for runtime in RUNTIMES for profile in PROFILES}
    ledger_by_id = {row.get("id"): row for row in ledger if isinstance(row, dict)}
    if set(ledger_by_id) != expected_mappings:
        raise ValueError(f"mapping ledger differs from required rows: {sorted(set(ledger_by_id) ^ expected_mappings)}")
    invalid_mappings = [identifier for identifier, row in ledger_by_id.items() if row.get("status") not in VALID_STATUSES]
    if invalid_mappings:
        raise ValueError(f"mapping ledger has invalid statuses: {invalid_mappings}")
    passed_mapping_missing = {
        identifier: sorted(field for field in PASS_MAPPING_FIELDS if not row.get(field))
        for identifier, row in ledger_by_id.items()
        if row.get("status") == "passed"
    }
    passed_mapping_missing = {identifier: fields for identifier, fields in passed_mapping_missing.items() if fields}
    if passed_mapping_missing:
        raise ValueError(f"passed mapping rows lack required evidence: {passed_mapping_missing}")
    pending = [cell.get("id") for cell in cells if cell.get("status") != "passed"]
    pending_mappings = [identifier for identifier, row in ledger_by_id.items() if row.get("status") != "passed"]
    print(json.dumps({"passed": not pending and not pending_mappings, "pending": pending, "pending_mappings": pending_mappings}, sort_keys=True))
    return 0 if not pending and not pending_mappings else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="prepare or check session-model live evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare", help="sync isolated generated surfaces and write a blocked ledger")
    prepare_parser.add_argument("destination", type=Path)
    validate_parser = sub.add_parser("validate", help="fail while any live matrix cell is blocked or failed")
    validate_parser.add_argument("inventory", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(args.destination))
        return 0
    return validate(args.inventory)


if __name__ == "__main__":
    raise SystemExit(main())
