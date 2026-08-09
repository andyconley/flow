"""CLI-facing wrapper around the harness collectors.

Thin by design, matching the rest of the split: argument resolution and
printing live here; parsing and persistence logic live in each collector
module (`codex_collector.py` today, a `claude_collector.py` sibling later).
"""

import sqlite3

import usage_store
from codex_collector import default_sessions_root, harvest_all
from paths import HOME, SOURCE_DIR


def harvest_codex_command() -> int:
    """Harvest `~/.codex/sessions/` into the usage store.

    Ensures the store exists first — unlike `doctor`, this command writes
    data on purpose, so ensuring its own target rather than requiring
    `flow setup machine` to have run first is a real convenience, not scope
    creep on a reporting command.

    Returns 0 if every file harvested cleanly, 1 if any file hard-stopped on a
    malformed line. Files that succeeded still have their rows and watermark
    committed either way — a nonzero exit here means "look at the reported
    file," not "nothing happened."
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    sessions_root = default_sessions_root(HOME)
    if not sessions_root.is_dir():
        print(f"no Codex sessions found at {sessions_root}")
        return 0

    conn = sqlite3.connect(store)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        summary = harvest_all(conn, sessions_root)
    finally:
        conn.close()

    print(
        f"codex harvest: {summary['files']} files, "
        f"{summary['turns']} turns, {summary['activity']} activity events"
    )
    for failure in summary["failures"]:
        print(f"  stopped: {failure['path']}:{failure['line']} — {failure['reason']}")

    return 1 if summary["failures"] else 0
