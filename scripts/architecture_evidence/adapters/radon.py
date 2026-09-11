"""Radon collection with source-bound, retained raw output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def collect_complexity(
    python_executable: str, source_path: Path, symbol: str, raw_path: Path
) -> dict:
    """Collect Radon's CC value for one top-level function.

    The caller owns the executable choice; this adapter never installs a tool or
    substitutes a similarly named symbol.
    """
    completed = subprocess.run(
        [python_executable, "-m", "radon", "cc", "-j", str(source_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    raw_path.write_text(completed.stdout, encoding="utf-8")
    if completed.returncode:
        raise RuntimeError(
            f"radon exited {completed.returncode}: {completed.stderr.strip()}"
        )
    try:
        values = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("radon produced invalid JSON") from exc
    entries = next(
        (
            items
            for key, items in values.items()
            if Path(key).resolve() == source_path.resolve()
        ),
        None,
    )
    if entries is None:
        raise RuntimeError("radon did not report the selected source")
    matches = [
        item
        for item in entries
        if item.get("type") == "function" and item.get("name") == symbol
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"radon did not report exactly one selected function: {symbol}"
        )
    entry = matches[0]
    return {
        "method": "radon.cc",
        "value": entry["complexity"],
        "start_line": entry["lineno"],
        "end_line": entry["endline"],
    }
