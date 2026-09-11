"""Small, explicit mutmut result adapter; no mutation engine lives here."""

from __future__ import annotations

import re
import subprocess
import json
from pathlib import Path

_RESULT = re.compile(r"^\s*(?P<id>\S+):\s+(?P<status>[a-z ]+)$")


def collect_results(python_executable: str, workspace: Path, raw_path: Path) -> dict:
    """Read native mutmut results from an already-run disposable workspace."""
    completed = subprocess.run(
        [python_executable, "-m", "mutmut", "results"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    raw_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(f"mutmut results exited {completed.returncode}")
    records = []
    for line in completed.stdout.splitlines():
        match = _RESULT.match(line)
        if match:
            records.append({"id": match.group("id"), "status": match.group("status")})
    if not records:
        raise RuntimeError("mutmut reported no native outcomes")
    return {"tool": "mutmut", "records": records}


def collect_all_results(workspace: Path, raw_path: Path) -> dict:
    """Retain killed outcomes too; ``mutmut results`` intentionally hides them."""
    meta = workspace / "mutants" / "cli" / "jsonl_watermark.py.meta"
    data = json.loads(meta.read_text(encoding="utf-8"))
    raw_path.write_text(
        json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    statuses = {
        None: "not checked",
        0: "survived",
        1: "killed",
        3: "killed",
        -24: "timeout",
        33: "no tests",
    }
    records = [
        {
            "id": identity,
            "status": statuses.get(code, "suspicious"),
            "native_exit_code": code,
        }
        for identity, code in sorted(data.get("exit_code_by_key", {}).items())
    ]
    if not records:
        raise RuntimeError("mutmut metadata contains no native outcomes")
    return {"tool": "mutmut", "records": records}
