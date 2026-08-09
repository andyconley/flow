"""Session-table lookups shared across harness collectors.

Both `codex_collector.py` and `claude_collector.py` need to answer "which
session does this file/row belong to" and "is this session a subagent's."
The SQL is identical for both harnesses — only the harness name differs —
so it lives here once rather than twice.

`_get_or_create_session` (session creation, including lineage extraction)
deliberately stays per-collector rather than joining these: Codex's version
extracts `parent_session_id` from `thread_spawn` metadata that has no Claude
analog at all. Forcing that into a shared function would need a callback or a
harness-specific hook parameter — more machinery than the two collectors'
genuinely different lineage models justify.
"""

import sqlite3
from pathlib import Path


def lookup_session_for_path(conn: sqlite3.Connection, harness: str, path: Path) -> int | None:
    """Find the session already associated with this file.

    Used when a harvest batch resumes mid-file and does not include the
    file's identity-establishing line (already processed and committed in an
    earlier run). Looks up `session.source_path` directly rather than
    inferring the session from a child row: a file whose first harvest
    stopped right after establishing identity — a truncated write, or an
    immediate hard-stop — has a session row but no child rows yet, which
    would make child-row inference return None exactly when it matters most.
    """
    row = conn.execute(
        "SELECT id FROM session WHERE harness = ? AND source_path = ?",
        (harness, str(path)),
    ).fetchone()
    return row[0] if row is not None else None


def is_subagent(conn: sqlite3.Connection, session_row_id: int | None) -> int:
    if session_row_id is None:
        return 0
    row = conn.execute(
        "SELECT parent_session_id FROM session WHERE id = ?", (session_row_id,)
    ).fetchone()
    return 1 if row is not None and row[0] is not None else 0
