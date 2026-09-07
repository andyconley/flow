"""Machine-local FTS5 detection. Retrieval reads receipts; install/doctor probe."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sqlite3
import sys
import _sqlite3
from archive_store import atomic_write, encode


def runtime_identity():
    paths = [Path(sys.executable).resolve(), Path(_sqlite3.__file__).resolve()]
    return {"executable": str(paths[0]), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "build_files": [{"path": str(p), "size": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns, "inode": p.stat().st_ino} for p in paths]}


def remedy():
    if sys.platform == "darwin":
        return "brew install python@3.12; select its interpreter with FLOW_PYTHON when rerunning install-flow.sh, then run flow doctor"
    return "select an FTS5-enabled CPython build (Ubuntu: install python3 and libsqlite3-0 with apt); rerun install-flow.sh with FLOW_PYTHON=/path/to/python and run flow doctor; verify that exact build"


def receipt_path():
    return Path.home() / ".flow" / "retrieval-capabilities.json"


def probe(persist=True):
    value = {"schema_version": 1, "runtime": runtime_identity(), "observed_at": datetime.now(timezone.utc).isoformat(), "capability": "FTS5", "state": "available", "remedy": remedy()}
    try:
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
    except sqlite3.Error as error:
        value.update(state="unavailable", detail=str(error))
    if persist:
        try:
            atomic_write(receipt_path(), encode(value), Path.home())
        except (OSError, ValueError) as error:
            value.update(state="preflight_required", detail="capability receipt not persisted: " + str(error))
    return value


def current():
    try:
        value = json.loads(receipt_path().read_text())
        if isinstance(value, dict) and value.get("schema_version") == 1 and value.get("runtime") == runtime_identity() and value.get("state") in {"available", "unavailable"}:
            return value
    except (OSError, ValueError, TypeError):
        pass
    return {"state": "preflight_required", "capability": "FTS5", "remedy": "run flow doctor for this interpreter before retrieval", "runtime": runtime_identity()}


def report():
    try:
        value = probe()
        runtime = value["runtime"]
        print(f"retrieval FTS5: {value['state']} — {runtime['executable']} (Python {runtime['python']}, SQLite {runtime['sqlite']})")
        if value["state"] != "available":
            print("  " + value["remedy"])
        return value
    except Exception as error:
        print("retrieval FTS5: preflight_required; run flow doctor — " + str(error))
        return {"state": "preflight_required"}


if __name__ == "__main__":
    report()
