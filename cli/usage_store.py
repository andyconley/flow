"""SQLite store for harvested harness usage data.

Holds per-turn token usage collected from agent-harness transcripts (Claude
Code, Codex) so flow can report on consumption and, later, advise on it.

Two layers, deliberately:

  raw       `session` + `turn_raw` — what the harness actually said, in its
            own semantics, including the source record verbatim. Durable.
  derived   `turn_norm` — one convention across harnesses. Disposable and
            recomputable from raw at any time.

The split exists because the harnesses disagree about what their own numbers
mean. Codex reports `cached_input_tokens` as a *subset* of `input_tokens`;
Claude's cache buckets are disjoint from its input tokens and are summed. A
single shared column would make cross-harness totals quietly wrong. Rather
than transform on write and hope the rule is right, raw keeps each harness's
meaning and the normalized layer is regenerated whenever the rule changes.

That property is what makes the retention promise survivable: history is never
rebuilt, because a wrong normalization rule costs a recompute, not a re-harvest.

No module-level path constant on purpose. Resolving the store location at
import time would mean a directly-imported unit test operates on the real
~/.flow/usage.db. Callers pass a path; `default_store_path()` resolves lazily.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

STATE_ABSENT = "absent"
STATE_OK = "ok"
STATE_EMPTY = "empty"
STATE_STALE = "stale"
STATE_ERROR = "error"


def default_store_path(home: Path | None = None) -> Path:
    """Resolve the store path lazily. See module docstring for why not a constant."""
    base = home if home is not None else Path.home()
    return base / ".flow" / "usage.db"


def default_capabilities_path(source_dir: Path) -> Path:
    return source_dir / "data" / "harness_capabilities.json"


# --------------------------------------------------------------------------
# migrations — forward-only, additive, never destructive
#
# Every entry is (version, description, sql). A migration may add tables,
# columns, or indexes. It may not drop or rewrite anything: history has to
# survive every schema change, so a correction that needs existing rows
# rewritten is not a migration — it is a normalized-layer recompute.
# --------------------------------------------------------------------------

_V1 = """
CREATE TABLE schema_migration (
  version     INTEGER PRIMARY KEY,
  applied_at  TEXT NOT NULL,
  description TEXT NOT NULL
);

CREATE TABLE harness_capability (
  harness   TEXT NOT NULL,
  field     TEXT NOT NULL,
  supported INTEGER NOT NULL CHECK (supported IN (0, 1)),
  PRIMARY KEY (harness, field)
);

CREATE TABLE harvest (
  harness           TEXT NOT NULL,
  source_path       TEXT NOT NULL,
  host_id           TEXT NOT NULL DEFAULT '',
  last_size         INTEGER NOT NULL,
  last_offset       INTEGER NOT NULL,
  last_line_no      INTEGER NOT NULL,
  last_line_hash    TEXT,
  file_mtime        REAL,
  harvested_at      TEXT NOT NULL,
  collector_version INTEGER NOT NULL,
  PRIMARY KEY (harness, source_path, host_id)
);

CREATE TABLE session (
  id                INTEGER PRIMARY KEY,
  harness           TEXT NOT NULL CHECK (harness IN ('claude', 'codex')),
  session_id        TEXT NOT NULL,
  parent_session_id TEXT,
  started_at        TEXT,
  cwd               TEXT,
  title             TEXT,
  UNIQUE (harness, session_id)
);

CREATE TABLE turn_raw (
  id                INTEGER PRIMARY KEY,
  session_row_id    INTEGER NOT NULL REFERENCES session(id),
  natural_turn_id   TEXT,
  turn_seq          INTEGER NOT NULL,
  is_subagent       INTEGER NOT NULL DEFAULT 0 CHECK (is_subagent IN (0, 1)),
  ts                TEXT NOT NULL,
  model             TEXT,
  payload           TEXT NOT NULL,
  source_path       TEXT NOT NULL,
  source_line_no    INTEGER NOT NULL,
  collector_version INTEGER NOT NULL,
  UNIQUE (session_row_id, natural_turn_id)
);

CREATE TABLE turn_norm (
  turn_raw_id                     INTEGER PRIMARY KEY
                                  REFERENCES turn_raw(id) ON DELETE CASCADE,
  ts                              TEXT NOT NULL,
  model                           TEXT,
  is_subagent                     INTEGER NOT NULL,
  fresh_input_tokens              INTEGER,
  cache_read_tokens               INTEGER,
  cache_write_tokens              INTEGER,
  output_tokens                   INTEGER,
  reasoning_tokens                INTEGER,
  context_window                  INTEGER,
  capacity_primary_used_pct       REAL,
  capacity_primary_window_minutes INTEGER,
  capacity_primary_resets_at      INTEGER,
  norm_version                    INTEGER NOT NULL
);

CREATE INDEX idx_turn_raw_session_ts ON turn_raw(session_row_id, ts);
CREATE INDEX idx_norm_ts             ON turn_norm(ts);
CREATE INDEX idx_norm_model_ts       ON turn_norm(model, ts);
"""

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "initial schema: raw + normalized layers, harvest watermark, capabilities", _V1),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def pending_migrations(current: int) -> list[tuple[int, str, str]]:
    return [m for m in MIGRATIONS if m[0] > current]


def ensure_store(
    path: Path, capabilities_path: Path | None = None
) -> tuple[bool, list[int]]:
    """Create the store if absent and apply any pending migrations.

    Returns (created, applied_versions). Idempotent: safe to run on every
    `flow setup machine` and every release update.

    Each migration and its ledger row commit together. If the process dies
    mid-migration the transaction rolls back, so `user_version` and the ledger
    cannot disagree — `user_version` stays authoritative for what runs next.
    """
    created = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)

    applied: list[int] = []
    conn = _connect(path)
    try:
        current = _user_version(conn)
        for version, description, sql in pending_migrations(current):
            with conn:  # commits the DDL, the ledger row, and the pragma together
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migration (version, applied_at, description)"
                    " VALUES (?, ?, ?)",
                    (version, _now(), description),
                )
                conn.execute(f"PRAGMA user_version = {version}")
            applied.append(version)

        if capabilities_path is not None and capabilities_path.is_file():
            _seed_capabilities(conn, capabilities_path)
    finally:
        conn.close()

    return created, applied


def _seed_capabilities(conn: sqlite3.Connection, capabilities_path: Path) -> None:
    """Upsert the shipped capability rows.

    Re-seeded on every ensure_store so a harness added to the data file — or a
    field a harness starts reporting — lands without a code change. Only
    touches harness_capability; no other table is read or written.
    """
    data = json.loads(capabilities_path.read_text())
    rows = [
        (row["harness"], row["field"], int(row["supported"]))
        for row in data.get("capabilities", [])
    ]
    if not rows:
        return
    with conn:
        conn.executemany(
            "INSERT INTO harness_capability (harness, field, supported)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(harness, field) DO UPDATE SET supported = excluded.supported",
            rows,
        )


def store_status(path: Path) -> dict:
    """Report the store's state without creating or modifying anything.

    Read-only by contract. `sqlite3.connect` would create an empty file, so an
    absent store is detected by path check before any connection is opened —
    otherwise asking about the store would bring it into existence and the
    absent state could never be observed.
    """
    if not path.exists():
        return {"state": STATE_ABSENT, "path": path}

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return {"state": STATE_ERROR, "path": path, "error": str(exc)}

    try:
        version = _user_version(conn)
        pending = [m[0] for m in pending_migrations(version)]
        if pending:
            return {
                "state": STATE_STALE,
                "path": path,
                "user_version": version,
                "pending": pending,
            }
        turns = int(conn.execute("SELECT count(*) FROM turn_raw").fetchone()[0])
        sessions = int(conn.execute("SELECT count(*) FROM session").fetchone()[0])
        return {
            "state": STATE_EMPTY if turns == 0 else STATE_OK,
            "path": path,
            "user_version": version,
            "sessions": sessions,
            "turns": turns,
        }
    except sqlite3.Error as exc:
        return {"state": STATE_ERROR, "path": path, "error": str(exc)}
    finally:
        conn.close()


def format_status(status: dict) -> str:
    """One-line summary for `flow doctor`.

    Every state renders something. An omitted line would be indistinguishable
    from a healthy store with nothing in it.
    """
    state = status["state"]
    if state == STATE_ABSENT:
        return "not created — run `flow setup machine`"
    if state == STATE_ERROR:
        return f"error — {status.get('error', 'unreadable')}"
    if state == STATE_STALE:
        pending = ", ".join(str(v) for v in status["pending"])
        return (
            f"stale, {len(status['pending'])} pending (v{pending})"
            " — run `flow setup machine`"
        )
    if state == STATE_EMPTY:
        return f"ok, empty (schema v{status['user_version']}, no turns harvested)"
    return (
        f"ok (schema v{status['user_version']}, "
        f"{status['sessions']} sessions, {status['turns']} turns)"
    )
