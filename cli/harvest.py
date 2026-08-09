"""CLI-facing wrapper around the harness collectors.

Thin by design, matching the rest of the split: argument resolution and
printing live here; parsing and persistence logic live in each collector
module (`codex_collector.py`, `claude_collector.py`).
"""

import sqlite3

import usage_store
from claude_collector import HARNESS as CLAUDE_HARNESS
from claude_collector import default_sessions_root as claude_sessions_root
from claude_collector import harvest_all as claude_harvest_all
from codex_collector import default_sessions_root as codex_sessions_root
from codex_collector import harvest_all as codex_harvest_all
from paths import HOME, SOURCE_DIR


def _connect(store) -> sqlite3.Connection:
    conn = sqlite3.connect(store)
    conn.execute("PRAGMA foreign_keys = ON")
    # A manual run racing a scheduled one (cron, a hook) should wait for the
    # other to finish rather than fail outright on "database is locked."
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


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

    sessions_root = codex_sessions_root(HOME)
    if not sessions_root.is_dir():
        print(f"no Codex sessions found at {sessions_root}")
        return 0

    conn = _connect(store)
    try:
        summary = codex_harvest_all(conn, sessions_root)
    finally:
        conn.close()

    print(
        f"codex harvest: {summary['files']} files, "
        f"{summary['turns']} turns, {summary['activity']} activity events"
    )
    if summary["skipped"]:
        print(f"  skipped {summary['skipped']} records with no resolvable session")
    for failure in summary["failures"]:
        line = failure["line"]
        where = f":{line}" if line is not None else ""
        print(f"  stopped: {failure['path']}{where} — {failure['reason']}")

    return 1 if summary["failures"] else 0


def _reset_claude_watermarks(conn: sqlite3.Connection) -> None:
    """Rewind every recorded Claude file to the start of the file.

    Used by `--backfill-titles`: replaying an already-harvested file from
    offset 0 is a free no-op for turns already in `turn_raw` (its natural key
    makes `INSERT OR IGNORE` idempotent), but it is the first time any
    `custom-title`/`ai-title` line in that file is seen by a collector new
    enough to read it. `last_size` is deliberately left alone —
    `harvest_file` recomputes it fresh from `path.stat()` on every run and
    never trusts the stored value for anything but reporting.
    """
    conn.execute(
        "UPDATE harvest SET last_offset = 0, last_line_no = 0, last_line_hash = NULL"
        " WHERE harness = ?",
        (CLAUDE_HARNESS,),
    )


def harvest_claude_command(backfill_titles: bool = False) -> int:
    """Harvest `~/.claude/projects/` into the usage store. Same contract as `harvest_codex_command`.

    `backfill_titles=True` rewinds every already-recorded Claude file's
    watermark first (see `_reset_claude_watermarks`), so sessions harvested
    before title capture existed pick up `session.title` retroactively.
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    sessions_root = claude_sessions_root(HOME)
    if not sessions_root.is_dir():
        print(f"no Claude Code sessions found at {sessions_root}")
        return 0

    conn = _connect(store)
    try:
        if backfill_titles:
            _reset_claude_watermarks(conn)
            conn.commit()
        summary = claude_harvest_all(conn, sessions_root)
    finally:
        conn.close()

    print(f"claude harvest: {summary['files']} files, {summary['turns']} turns")
    if summary["skipped"]:
        print(f"  skipped {summary['skipped']} records with no resolvable session")
    for failure in summary["failures"]:
        line = failure["line"]
        where = f":{line}" if line is not None else ""
        print(f"  stopped: {failure['path']}{where} — {failure['reason']}")

    return 1 if summary["failures"] else 0
