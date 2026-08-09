"""Codex session harvester: raw layer only.

Reads `~/.codex/sessions/**/*.jsonl` incrementally, against the `harvest`
table's per-file watermark, and writes `session`, `turn_raw`, and
`agent_activity_raw` rows. Nothing here normalizes, advises, or prints — see
`cli/harvest.py` for the CLI-facing wrapper.

No module-level path resolution, for the same reason as `usage_store.py`: a
directly-imported unit test must never be able to touch the real
`~/.codex/sessions/` or `~/.flow/usage.db`. `default_sessions_root()` resolves
lazily; callers pass an explicit path everywhere else.

## Field-shape ground truth this module encodes

Verified against all 81 local session files on the machine this was written
on, not inferred from documentation:

- `token_count` records carry neither `turn_id` nor `model`. Both come from
  `turn_context`, which shares the `turn_id` value with `task_started` /
  `task_complete`. A single logical turn can contain several `token_count`
  emissions — one per tool-call round trip within that turn, not one per
  turn — so `turn_id` alone is too coarse to be `turn_raw`'s row identity.
- The natural key is `f"{turn_id}:{source_line_no}"`. Piggybacking on the line
  number (already a `turn_raw` column) gives uniqueness and cross-run
  stability for free, without a separate per-turn ordinal counter that would
  need its own persisted state across incremental harvest runs.
- `session_meta.payload.source` is
  `{"subagent": {"thread_spawn": {"parent_thread_id": ..., ...}}}` for
  sessions spawned by Codex's local `thread_spawn` mechanism. That is
  `session.parent_session_id`. `is_subagent` is a session-level fact
  (non-null `parent_session_id`) projected onto every turn in that session —
  unlike Claude's `isSidechain`, which flags individual messages within one
  file, a Codex subagent is an entirely separate session file.
- **A subagent's file carries a second `session_meta`, for the parent, not
  itself.** Confirmed on 35 real files: line 1 declares the file's own `id`;
  a line shortly after is a verbatim copy of the *parent's* `session_meta`
  (different `id`), apparently injected so the child's transcript is
  self-contained. Session identity locks onto the first `session_meta` only —
  a second one with a different `id` is read like any other record, never
  re-established as identity. Getting this wrong silently misattributes every
  subsequent record in the file to the parent's session instead of the
  child's; caught by comparing a real end-to-end harvest count against a
  from-scratch count of the same file, not by any unit test.
- `sub_agent_activity.agent_thread_id` values match no local session id and
  point at paths like `/root/validation_design` — cloud/background-agent
  telemetry with no local transcript. Recorded via `agent_activity_raw`, with
  no attempt to attach token data that does not exist locally.
- `total_token_usage` does not reset across `compacted` events (checked
  before/after real occurrences). `rate_limits.secondary` was null in every
  sample. Both intentionally unused by this raw-layer collector; the payload
  is stored verbatim regardless, so either can be picked up in normalization
  later without a re-harvest.

## Malformed-line rule

A trailing line with no terminating `\\n` is a write in progress, not an
error — `_read_new_lines` never returns it, and the next harvest picks it up
once it's complete. A `\\n`-terminated line that fails to decode or parse is
different: genuine corruption. The first one encountered stops that file's
harvest; rows and the watermark for every earlier line in the batch are still
committed. JSONL is append-only, so a bad line at a fixed offset never
becomes valid — the stop reproduces every run until someone looks at it,
which is the intended behavior, not a bug.
"""

import hashlib
import json
import sqlite3
from pathlib import Path

COLLECTOR_VERSION = 1
HARNESS = "codex"


def default_sessions_root(home: Path | None = None) -> Path:
    """Resolve Codex's session directory lazily. See module docstring for why."""
    base = home if home is not None else Path.home()
    return base / ".codex" / "sessions"


class WatermarkAnomaly(Exception):
    """The file is smaller than the recorded watermark. Never a silent no-op.

    A file that shrank was not appended to — it was replaced or truncated.
    Silently re-harvesting from 0 would either skip data or double-count it
    depending on what actually happened, so this is raised rather than guessed
    at.
    """


# --------------------------------------------------------------------------
# line reading — bytes in, bytes out; decoding happens in the caller so a
# decode failure and a JSON failure funnel through the same hard-stop path
# --------------------------------------------------------------------------


def _read_new_lines(path: Path, last_offset: int) -> tuple[list[bytes], int, int]:
    """Read complete lines appended since `last_offset`, as raw bytes.

    Returns `(lines, new_offset, current_size)`. `new_offset` is the byte
    offset immediately after the last complete line — what the caller should
    persist as `harvest.last_offset` once those lines are committed. A
    trailing line with no terminating newline is left unread entirely; it is
    neither returned nor counted toward `new_offset`.
    """
    current_size = path.stat().st_size
    if current_size < last_offset:
        raise WatermarkAnomaly(
            f"{path}: size {current_size} < recorded offset {last_offset}"
        )
    if current_size == last_offset:
        return [], last_offset, current_size

    with path.open("rb") as fh:
        fh.seek(last_offset)
        chunk = fh.read()

    lines: list[bytes] = []
    start = 0
    while True:
        nl = chunk.find(b"\n", start)
        if nl == -1:
            break  # remainder, if any, is an incomplete trailing line
        lines.append(chunk[start:nl])
        start = nl + 1
    new_offset = last_offset + start
    return lines, new_offset, current_size


def _line_byte_length(raw: bytes) -> int:
    return len(raw) + 1  # +1 for the newline stripped during reading


def _line_hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# --------------------------------------------------------------------------
# session + lineage
# --------------------------------------------------------------------------


def _get_or_create_session(
    conn: sqlite3.Connection, session_id: str, meta: dict, path: Path
) -> int:
    row = conn.execute(
        "SELECT id FROM session WHERE harness = ? AND session_id = ?",
        (HARNESS, session_id),
    ).fetchone()
    if row is not None:
        return row[0]

    cur = conn.execute(
        "INSERT INTO session"
        " (harness, session_id, parent_session_id, started_at, cwd, title, source_path)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            HARNESS,
            session_id,
            _extract_parent_session_id(meta),
            meta.get("timestamp"),
            meta.get("cwd"),
            None,  # Codex session_meta carries no title field; left NULL.
            str(path),
        ),
    )
    return cur.lastrowid


def _extract_parent_session_id(meta: dict) -> str | None:
    """`session_meta.payload.source.subagent.thread_spawn.parent_thread_id`, if present.

    Only sessions spawned by Codex's local `thread_spawn` mechanism carry
    this. Everything else (plain sessions, VS Code-originated sessions) has
    `source` as a plain string or None — `.get` chains rather than assuming
    shape, since a Codex version without this field must degrade to NULL, not
    raise.
    """
    source = meta.get("source")
    if not isinstance(source, dict):
        return None
    subagent = source.get("subagent")
    if not isinstance(subagent, dict):
        return None
    thread_spawn = subagent.get("thread_spawn")
    if not isinstance(thread_spawn, dict):
        return None
    return thread_spawn.get("parent_thread_id")


def _lookup_session_for_path(conn: sqlite3.Connection, path: Path) -> int | None:
    """Find the session already associated with this file.

    Used when a harvest batch resumes mid-file and does not include the
    session_meta line — already processed and committed in an earlier run.
    Looks up `session.source_path` directly rather than inferring the session
    from a child row (`turn_raw` / `agent_activity_raw`): a file whose first
    harvest stopped right after `session_meta` — a truncated write, or a
    hard-stop on the very next line — has a session row but no child rows yet,
    which made the child-row inference this replaced return None exactly when
    it mattered most.
    """
    row = conn.execute(
        "SELECT id FROM session WHERE harness = ? AND source_path = ?",
        (HARNESS, str(path)),
    ).fetchone()
    return row[0] if row is not None else None


def _is_subagent(conn: sqlite3.Connection, session_row_id: int | None) -> int:
    if session_row_id is None:
        return 0
    row = conn.execute(
        "SELECT parent_session_id FROM session WHERE id = ?", (session_row_id,)
    ).fetchone()
    return 1 if row is not None and row[0] is not None else 0


# --------------------------------------------------------------------------
# open-turn state machine
# --------------------------------------------------------------------------


class _OpenTurnState:
    """Tracks the currently-open turn while walking one file sequentially.

    `token_count` records carry neither `turn_id` nor `model` — both are
    attributed from whichever turn is currently open, per the field-shape
    findings in the module docstring. A turn is open between `task_started`
    and `task_complete` / `turn_aborted`; `turn_context` records sharing that
    `turn_id` supply the model.

    `turn_context` is not guaranteed to arrive before the first `token_count`
    of its turn. When that happens `model` is None for that one row — stored
    as-is, a legitimate absent value, rather than buffered and reconciled
    retroactively. Reconciliation would mean the state machine is no longer a
    single forward pass over the file, which is the property that keeps this
    class simple.
    """

    def __init__(self) -> None:
        self.turn_id: str | None = None
        self.model: str | None = None

    def open(self, turn_id: str | None) -> None:
        self.turn_id = turn_id
        self.model = None

    def set_model_for(self, turn_id: str | None, model: str | None) -> None:
        if turn_id is not None and turn_id == self.turn_id:
            self.model = model

    def close(self) -> None:
        self.turn_id = None
        self.model = None


# --------------------------------------------------------------------------
# per-file harvest
# --------------------------------------------------------------------------


def _harvest_lines(
    conn: sqlite3.Connection,
    path: Path,
    raw_lines: list[bytes],
    starting_line_no: int,
) -> tuple[int, int, int, str | None, int | None]:
    """Process one batch of already-read raw lines.

    `starting_line_no` is the file-global line number of `raw_lines[0]`
    (1-indexed), so `source_line_no` reflects real file position rather than
    an offset restarting at 1 on every incremental run.

    Returns `(turns_written, activity_written, last_good_line_no,
    hard_stop_reason, hard_stop_line_no)`. `hard_stop_reason` is None on full
    success. Decode and JSON failures funnel through the same path: both are
    "this line is not valid content," and the caller does not need to
    distinguish them to decide what to do next.
    """
    session_row_id: int | None = None
    state = _OpenTurnState()
    turns_written = 0
    activity_written = 0
    last_good_line_no = starting_line_no - 1

    for offset, raw in enumerate(raw_lines):
        line_no = starting_line_no + offset
        try:
            text = raw.decode("utf-8")
            record = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return turns_written, activity_written, last_good_line_no, str(exc), line_no

        rtype = record.get("type")
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}

        if rtype == "session_meta" and session_row_id is None:
            # A subagent's file carries a SECOND session_meta shortly after its
            # own — a verbatim copy of the parent's, injected so the child's
            # transcript is self-contained. Confirmed against real data: it
            # declares a different `id` (the parent's), not a repeat of this
            # file's own. Locking identity to the first session_meta only
            # means that injected copy is read like any other record but never
            # treated as re-declaring which session this file belongs to —
            # without the `is None` guard, every record after that second line
            # silently misattributes to the parent's session row instead of
            # this file's own.
            sid = payload.get("id")
            if sid is not None:
                session_row_id = _get_or_create_session(conn, sid, payload, path)

        elif session_row_id is None:
            session_row_id = _lookup_session_for_path(conn, path)
            if session_row_id is None:
                # Nothing to attach this record to. Expected on a fresh file
                # whose first line in this batch isn't session_meta only if an
                # earlier batch already established the session; otherwise
                # this is a shape violation worth noting but not one that
                # should take the whole file down over a non-identity record.
                last_good_line_no = line_no
                continue

        if rtype == "event_msg" and payload.get("type") == "task_started":
            state.open(payload.get("turn_id"))

        elif rtype == "turn_context":
            state.set_model_for(payload.get("turn_id"), payload.get("model"))

        elif rtype == "event_msg" and payload.get("type") in ("task_complete", "turn_aborted"):
            state.close()

        elif rtype == "event_msg" and payload.get("type") == "token_count":
            natural_turn_id = (
                f"{state.turn_id}:{line_no}" if state.turn_id else f"untracked:{line_no}"
            )
            conn.execute(
                "INSERT OR IGNORE INTO turn_raw"
                " (session_row_id, natural_turn_id, turn_seq, is_subagent, ts, model,"
                "  payload, source_path, source_line_no, collector_version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_row_id,
                    natural_turn_id,
                    line_no,
                    _is_subagent(conn, session_row_id),
                    record.get("timestamp"),
                    state.model,
                    text,
                    str(path),
                    line_no,
                    COLLECTOR_VERSION,
                ),
            )
            turns_written += 1

        elif rtype == "event_msg" and payload.get("type") == "sub_agent_activity":
            conn.execute(
                "INSERT INTO agent_activity_raw"
                " (session_row_id, ts, kind, agent_thread_id, agent_path, payload,"
                "  source_path, source_line_no, collector_version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_row_id,
                    record.get("timestamp"),
                    payload.get("kind", ""),
                    payload.get("agent_thread_id"),
                    payload.get("agent_path"),
                    text,
                    str(path),
                    line_no,
                    COLLECTOR_VERSION,
                ),
            )
            activity_written += 1

        last_good_line_no = line_no

    return turns_written, activity_written, last_good_line_no, None, None


def harvest_file(conn: sqlite3.Connection, path: Path, host_id: str = "") -> dict:
    """Incrementally harvest one file. Returns a summary dict.

    `{"turns": n, "activity": n, "hard_stop": None | {"line": n, "reason": str}}`.
    A hard stop is a return value, not an exception — `harvest_all` needs to
    move on to the next file, and a caller testing this directly is better
    served by an assertable value than a control-flow exception for a
    condition that is expected and recoverable (the next run retries).
    """
    row = conn.execute(
        "SELECT last_offset, last_line_no FROM harvest"
        " WHERE harness = ? AND source_path = ? AND host_id = ?",
        (HARNESS, str(path), host_id),
    ).fetchone()
    last_offset, last_line_no = (row[0], row[1]) if row is not None else (0, 0)

    raw_lines, new_offset, current_size = _read_new_lines(path, last_offset)
    if not raw_lines:
        return {"turns": 0, "activity": 0, "hard_stop": None}

    with conn:  # rows, watermark, and any hard-stop truncation commit together
        turns, activity, last_good_line_no, reason, bad_line_no = _harvest_lines(
            conn, path, raw_lines, last_line_no + 1
        )

        if reason is not None:
            # Only lines up to last_good_line_no were committed. Recompute the
            # byte offset to match — using the full batch's new_offset would
            # mark bytes as "read" that were never actually processed, so a
            # later run would skip straight past the bad line instead of
            # re-reporting it.
            committed_offset = last_offset
            for offset, raw in enumerate(raw_lines):
                if last_line_no + 1 + offset > last_good_line_no:
                    break
                committed_offset += _line_byte_length(raw)
            watermark_offset = committed_offset
            watermark_hash = (
                _line_hash(raw_lines[last_good_line_no - last_line_no - 1])
                if last_good_line_no > last_line_no
                else None
            )
        else:
            watermark_offset = new_offset
            watermark_hash = _line_hash(raw_lines[-1])

        conn.execute(
            "INSERT INTO harvest"
            " (harness, source_path, host_id, last_size, last_offset, last_line_no,"
            "  last_line_hash, file_mtime, harvested_at, collector_version)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)"
            " ON CONFLICT(harness, source_path, host_id) DO UPDATE SET"
            "   last_size = excluded.last_size,"
            "   last_offset = excluded.last_offset,"
            "   last_line_no = excluded.last_line_no,"
            "   last_line_hash = excluded.last_line_hash,"
            "   file_mtime = excluded.file_mtime,"
            "   harvested_at = excluded.harvested_at,"
            "   collector_version = excluded.collector_version",
            (
                HARNESS,
                str(path),
                host_id,
                current_size,
                watermark_offset,
                last_good_line_no,
                watermark_hash,
                path.stat().st_mtime,
                COLLECTOR_VERSION,
            ),
        )

    hard_stop = {"line": bad_line_no, "reason": reason} if reason is not None else None
    return {"turns": turns, "activity": activity, "hard_stop": hard_stop}


def harvest_all(conn: sqlite3.Connection, sessions_root: Path, host_id: str = "") -> dict:
    """Discover and harvest every `*.jsonl` under `sessions_root`.

    One file's hard stop does not affect any other file — each is harvested in
    its own transaction via `harvest_file`. Returns
    `{"files": n, "turns": n, "activity": n, "failures": [{"path", "line", "reason"}, ...]}`.
    """
    files = sorted(sessions_root.glob("**/*.jsonl")) if sessions_root.is_dir() else []
    total_turns = 0
    total_activity = 0
    failures: list[dict] = []

    for path in files:
        result = harvest_file(conn, path, host_id=host_id)
        total_turns += result["turns"]
        total_activity += result["activity"]
        if result["hard_stop"] is not None:
            failures.append({"path": str(path), **result["hard_stop"]})

    return {
        "files": len(files),
        "turns": total_turns,
        "activity": total_activity,
        "failures": failures,
    }
