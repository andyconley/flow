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

SCHEMA_VERSION = 4

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

_V2 = """
-- A collector resuming a file mid-stream needs to find the session row for a
-- batch that doesn't include the session_meta line (already committed in an
-- earlier run). Without a direct pointer, that lookup has to infer the
-- session from a child row — turn_raw or agent_activity_raw — which does not
-- exist yet if the very first harvest of a file stopped (truncated write, or
-- a hard-stop) before writing any. source_path is nullable because it is a
-- convenience index for that one fallback path, not part of session
-- identity — (harness, session_id) remains the real key.
ALTER TABLE session ADD COLUMN source_path TEXT;
CREATE INDEX idx_session_source_path ON session(source_path);

-- Coarse activity log for events that describe an agent acting, but carry no
-- token usage of their own. First observed as Codex's `sub_agent_activity`
-- telemetry, which references an `agent_thread_id` matching no local session
-- file — almost certainly a cloud/background agent whose transcript and token
-- usage live server-side, not on this disk. There is nothing to normalize
-- here and no token_norm-shaped counterpart: this table exists so the event
-- itself is not silently dropped, not to make it queryable as usage.
CREATE TABLE agent_activity_raw (
  id                INTEGER PRIMARY KEY,
  session_row_id    INTEGER NOT NULL REFERENCES session(id),
  ts                TEXT NOT NULL,
  kind              TEXT NOT NULL,
  agent_thread_id   TEXT,
  agent_path        TEXT,
  payload           TEXT NOT NULL,
  source_path       TEXT NOT NULL,
  source_line_no    INTEGER NOT NULL,
  collector_version INTEGER NOT NULL,
  -- Same dedup shape as turn_raw's (session_row_id, natural_turn_id): one
  -- line in one session's file identifies at most one row. Without it,
  -- `INSERT OR IGNORE` in the collector has nothing to ignore against, and a
  -- line reprocessed for any reason inserts a duplicate rather than a no-op.
  UNIQUE (session_row_id, source_line_no)
);

CREATE INDEX idx_activity_session_ts ON agent_activity_raw(session_row_id, ts);
"""

_V3 = """
-- turn_norm shipped with only capacity_primary_* columns on the documented
-- assumption that Codex's `rate_limits.secondary` was unpopulated in
-- practice (true of every sample the schema was designed against). A
-- 16,260-row real-corpus check during the normalization pass that consumes
-- this table found secondary populated in 7.7% of rows — not negligible.
-- Columns named to mirror `capacity_primary_*` exactly, for the same reason
-- those were named `primary` rather than assuming which window they meant:
-- `rate_limits.primary` itself is not reliably "the weekly window" (real
-- data shows both a 300-minute and a 10080-minute value under that name),
-- so neither field is given interpretive meaning — both are stored verbatim
-- under Codex's own naming, and a consumer distinguishes them by the
-- window_minutes value actually stored, not by the column name alone.
ALTER TABLE turn_norm ADD COLUMN capacity_secondary_used_pct REAL;
ALTER TABLE turn_norm ADD COLUMN capacity_secondary_window_minutes INTEGER;
ALTER TABLE turn_norm ADD COLUMN capacity_secondary_resets_at INTEGER;
"""

_V4 = """
-- Genuine last-write-wins for Claude's `ai-title` records, which chunk 6
-- shipped as "first one wins, forever" (`WHERE title IS NULL`) because a
-- real last-write-wins needs to know which of several repeats came last.
-- A first design assumed the record itself carries a timestamp to compare —
-- wrong: all 6,340 real `custom-title`/`ai-title` records sampled on the
-- machine this was built on carry only `{type, aiTitle|customTitle,
-- sessionId}`, nothing else. What real data DOES have: records immediately
-- adjacent to a title line (user/assistant/system/...) usually carry a real
-- `timestamp`, and JSONL is strictly append-only, so the nearest preceding
-- timestamped record bounds when the title event actually happened.
--
-- `last_seen_ts` is a running high-water mark, advanced from every record
-- type that carries a `timestamp` (not just titles) — this is what makes an
-- `ai-title` record's *effective* timestamp available at all, despite having
-- none of its own. `title_source` records which kind last won (`custom`
-- always locks out every future `ai-title`, permanently, regardless of that
-- future record's effective timestamp). `title_ai_ts` is the effective
-- timestamp in force when the current title's `ai-title` write (if any) was
-- accepted, so a later-arriving `ai-title` can be compared against it.
--
-- Two title records with nothing timestamped between them (common — several
-- other record types carry no timestamp either) share one effective
-- timestamp, so only the first of that tied cluster is accepted — this does
-- not reconstruct a true last-line-wins for back-to-back repeats with no
-- time information between them. It does correctly resolve genuine
-- time-separated re-titling and the rare case of one session's title
-- records spread across more than one file (1 of 163 real sessions with any
-- title records, from a session-continuation event) — a purely in-memory or
-- file-local-line-number ordinal would get both of those wrong.
--
-- All three columns are NULL on every session that predates this migration.
-- This self-heals via `flow harvest claude --backfill`: replaying a file's
-- lines in original order re-derives all three correctly, converging to the
-- same terminal state chunk 6's tests already proved is order-independent —
-- but the self-heal only happens once that backfill actually runs.
ALTER TABLE session ADD COLUMN title_source TEXT CHECK (title_source IN ('custom', 'ai'));
ALTER TABLE session ADD COLUMN title_ai_ts TEXT;
ALTER TABLE session ADD COLUMN last_seen_ts TEXT;
"""

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "initial schema: raw + normalized layers, harvest watermark, capabilities", _V1),
    (2, "agent activity log for sub-agent telemetry with no local token data", _V2),
    (3, "secondary capacity window columns on turn_norm", _V3),
    (4, "title provenance and a session-level timestamp high-water mark", _V4),
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

    Each migration's ledger row and `user_version` pragma commit together —
    but the DDL itself does not, despite the comment on the `with` block
    below suggesting so: `executescript` implicitly commits any open
    transaction before running, so the ALTER/CREATE statements land outside
    it. A crash in the narrow window between the DDL and the ledger commit
    leaves the columns present with the old `user_version`, and the next
    `ensure_store` fails on "duplicate column name" rather than resuming.
    Known, accepted (flagged in chunk 7's review): present since v2, the
    window is milliseconds on a local SQLite file, and the recovery is a
    manual `PRAGMA user_version` bump — not worth reworking migrations to
    per-statement `execute` calls for a personal tool.
    """
    created = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)

    applied: list[int] = []
    conn = _connect(path)
    try:
        current = _user_version(conn)
        for version, description, sql in pending_migrations(current):
            with conn:  # ledger row + pragma commit together; DDL precedes (see docstring)
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
