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
once it's complete. Everything else that keeps a line from becoming a row is
genuine corruption and stops that file's harvest at the first one: failing to
decode, failing to parse, parsing to something other than a JSON object, or
parsing to an object missing a field a row requires (`timestamp`, checked
explicitly before each insert — not left for the database to catch, because
the inserts use `INSERT OR IGNORE` for their real purpose of deduping on the
natural key, and SQLite applies that conflict resolution to every constraint
on the statement, not just the one it was written for. A NULL `timestamp`
would silently no-op there, identical to a legitimate duplicate, which is
worse than a crash — nothing would ever say the record was dropped). All of
these funnel through the same `_HardStop` path in `_harvest_lines`, because a
consumer deciding what to do next only needs to know "this line is not valid
content," not which way it failed. Rows and the watermark for every earlier
line in the batch are still committed. JSONL is append-only, so a bad line at
a fixed offset never becomes valid — the stop reproduces every run until
someone looks at it, which is the intended behavior, not a bug.
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

    `turn_context` is not guaranteed to arrive after `task_started` for the
    same turn — only that both carry the same `turn_id` — so a `turn_context`
    seen before its turn opens is held in `_pending_model` and applied when
    `open()` sees that `turn_id`. Losing this ordering silently nulled every
    `model` in the file, with no error, on the one real ordering variant this
    was not originally built against.

    `close()` and `set_model_for()` both check `turn_id` against the
    currently-open turn before acting. Without that check, a stale
    `task_complete` for a turn that already closed (or a `turn_context` for
    some other, not-currently-open turn) would silently close or re-target
    the wrong turn — attributing a live turn's remaining `token_count` records
    to `untracked:` instead.
    """

    def __init__(self) -> None:
        self.turn_id: str | None = None
        self.model: str | None = None
        self._pending_model: dict[str, str] = {}

    def open(self, turn_id: str | None) -> None:
        self.turn_id = turn_id
        self.model = self._pending_model.pop(turn_id, None) if turn_id is not None else None

    def set_model_for(self, turn_id: str | None, model: str | None) -> None:
        if turn_id is None:
            return
        if turn_id == self.turn_id:
            self.model = model
        else:
            # Not (yet, or any longer) the open turn. Held for a future
            # open() rather than discarded, since turn_context is not
            # guaranteed to follow task_started.
            self._pending_model[turn_id] = model

    def close(self, turn_id: str | None) -> None:
        if turn_id is None or turn_id == self.turn_id:
            self.turn_id = None
            self.model = None


# --------------------------------------------------------------------------
# per-file harvest
# --------------------------------------------------------------------------


class _HardStop(Exception):
    """Internal signal: stop this file's harvest at a specific line, with a reason.

    Raised from inside the per-line loop and caught once at the bottom of
    `_harvest_lines`, so every way a line can fail — decode, parse, shape, or a
    schema constraint the row itself violates — reports through the same path
    rather than each needing its own early-return plumbing.
    """

    def __init__(self, line_no: int, reason: str):
        self.line_no = line_no
        self.reason = reason


def _harvest_lines(
    conn: sqlite3.Connection,
    path: Path,
    raw_lines: list[bytes],
    starting_line_no: int,
) -> tuple[int, int, int, int, str | None, int | None]:
    """Process one batch of already-read raw lines.

    `starting_line_no` is the file-global line number of `raw_lines[0]`
    (1-indexed), so `source_line_no` reflects real file position rather than
    an offset restarting at 1 on every incremental run.

    Returns `(turns_written, activity_written, skipped, last_good_line_no,
    hard_stop_reason, hard_stop_line_no)`. `hard_stop_reason` is None on full
    success. `turns_written` / `activity_written` count rows this call
    actually inserted — `INSERT OR IGNORE` silently no-ops on a duplicate
    natural key, and counting the attempt instead of the outcome would hide
    exactly the kind of double-processing bug that constraint exists to catch.
    `skipped` counts records seen but not attached to any session — see the
    identity-resolution branch below; a file producing only skips is a shape
    violation worth surfacing, not a silent `0 turns` "success."

    Session identity is resolved ONCE, before the loop, via
    `_lookup_session_for_path` — not lazily on first need inside it. Resolving
    it lazily was the actual shape of a real bug: a batch that resumes
    mid-file (the incremental case this whole harvester exists for) starts
    with `session_row_id` unknown, and if the first `session_meta`-typed
    record encountered in *that batch* happened to be the parent's injected
    copy (see the module docstring) rather than this file's own — which,
    on a resumed harvest, `session_meta` from THIS file already passed and
    committed in an earlier batch — every record in the batch would misattach
    to the parent. Resolving identity from the file itself up front removes
    the ordering dependency entirely.
    """
    session_row_id: int | None = _lookup_session_for_path(conn, path)
    is_subagent = _is_subagent(conn, session_row_id) if session_row_id is not None else 0
    state = _OpenTurnState()
    turns_written = 0
    activity_written = 0
    skipped = 0
    last_good_line_no = starting_line_no - 1

    try:
        for offset, raw in enumerate(raw_lines):
            line_no = starting_line_no + offset
            try:
                text = raw.decode("utf-8")
                record = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise _HardStop(line_no, str(exc)) from exc
            if not isinstance(record, dict):
                # Valid JSON, wrong shape — `123` and `"a string"` both parse
                # cleanly but carry no `.get()`. Treated as malformed, same as
                # a decode/parse failure: this line is not valid content.
                raise _HardStop(line_no, f"expected a JSON object, got {type(record).__name__}")

            rtype = record.get("type")
            payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}

            if rtype == "session_meta" and session_row_id is None:
                # A subagent's file carries a SECOND session_meta shortly
                # after its own — a verbatim copy of the parent's, injected so
                # the child's transcript is self-contained. Confirmed against
                # real data: it declares a different `id` (the parent's), not
                # a repeat of this file's own. The `is None` guard means that
                # injected copy is read like any other record but never
                # re-establishes identity — combined with resolving identity
                # up front (see the docstring), this now holds regardless of
                # which batch boundary it falls on.
                sid = payload.get("id")
                if sid is not None:
                    session_row_id = _get_or_create_session(conn, sid, payload, path)
                    is_subagent = _is_subagent(conn, session_row_id)

            elif session_row_id is None:
                # Nothing to attach this record to — this file's own
                # session_meta has not been seen yet in this batch or any
                # prior one. A shape violation worth counting, not one that
                # should take the whole file down over a non-identity record.
                skipped += 1
                last_good_line_no = line_no
                continue

            if rtype == "event_msg" and payload.get("type") == "task_started":
                state.open(payload.get("turn_id"))

            elif rtype == "turn_context":
                state.set_model_for(payload.get("turn_id"), payload.get("model"))

            elif rtype == "event_msg" and payload.get("type") in ("task_complete", "turn_aborted"):
                state.close(payload.get("turn_id"))

            elif rtype == "event_msg" and payload.get("type") == "token_count":
                ts = record.get("timestamp")
                if ts is None:
                    # Checked explicitly rather than left for the database to
                    # catch: turn_raw.ts is NOT NULL, but this insert uses
                    # INSERT OR IGNORE for its actual purpose — dedup on the
                    # natural key — and SQLite's conflict resolution applies
                    # uniformly to every constraint on the statement. A NULL
                    # here does not raise; it silently no-ops, identical to a
                    # legitimate duplicate. That would make a record missing
                    # `timestamp` disappear with no error and no skipped count
                    # — worse than a crash, because nothing would ever say so.
                    raise _HardStop(line_no, "token_count record is missing timestamp")
                natural_turn_id = (
                    f"{state.turn_id}:{line_no}" if state.turn_id else f"untracked:{line_no}"
                )
                cur = conn.execute(
                    "INSERT OR IGNORE INTO turn_raw"
                    " (session_row_id, natural_turn_id, turn_seq, is_subagent, ts, model,"
                    "  payload, source_path, source_line_no, collector_version)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_row_id,
                        natural_turn_id,
                        line_no,
                        is_subagent,
                        ts,
                        state.model,
                        text,
                        str(path),
                        line_no,
                        COLLECTOR_VERSION,
                    ),
                )
                if cur.rowcount:
                    turns_written += 1

            elif rtype == "event_msg" and payload.get("type") == "sub_agent_activity":
                ts = record.get("timestamp")
                if ts is None:
                    raise _HardStop(line_no, "sub_agent_activity record is missing timestamp")
                cur = conn.execute(
                    "INSERT OR IGNORE INTO agent_activity_raw"
                    " (session_row_id, ts, kind, agent_thread_id, agent_path, payload,"
                    "  source_path, source_line_no, collector_version)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        session_row_id,
                        ts,
                        payload.get("kind", ""),
                        payload.get("agent_thread_id"),
                        payload.get("agent_path"),
                        text,
                        str(path),
                        line_no,
                        COLLECTOR_VERSION,
                    ),
                )
                if cur.rowcount:
                    activity_written += 1

            last_good_line_no = line_no
    except _HardStop as stop:
        return turns_written, activity_written, skipped, last_good_line_no, stop.reason, stop.line_no

    return turns_written, activity_written, skipped, last_good_line_no, None, None


def harvest_file(conn: sqlite3.Connection, path: Path, host_id: str = "") -> dict:
    """Incrementally harvest one file. Returns a summary dict.

    `{"turns": n, "activity": n, "skipped": n, "hard_stop": None | {"line": n, "reason": str}}`.
    A hard stop is a return value, not an exception — `harvest_all` needs to
    move on to the next file, and a caller testing this directly is better
    served by an assertable value than a control-flow exception for a
    condition that is expected and recoverable (the next run retries).

    `WatermarkAnomaly` still raises — a shrunk file is not "try again later,"
    it is a sign the file was replaced or truncated, and `harvest_all` decides
    how to treat that at the multi-file level rather than this function
    guessing on its behalf.
    """
    row = conn.execute(
        "SELECT last_offset, last_line_no, last_line_hash FROM harvest"
        " WHERE harness = ? AND source_path = ? AND host_id = ?",
        (HARNESS, str(path), host_id),
    ).fetchone()
    last_offset, last_line_no, prior_hash = row if row is not None else (0, 0, None)

    raw_lines, new_offset, current_size = _read_new_lines(path, last_offset)
    if not raw_lines:
        return {"turns": 0, "activity": 0, "skipped": 0, "hard_stop": None}

    with conn:  # rows, watermark, and any hard-stop truncation commit together
        turns, activity, skipped, last_good_line_no, reason, bad_line_no = _harvest_lines(
            conn, path, raw_lines, last_line_no + 1
        )

        if last_good_line_no == last_line_no:
            # Nothing in this batch committed — either a hard stop on the very
            # first line, or (unreachable today, but not assumed away) an
            # empty batch. The watermark does not move, so its hash must not
            # either: recomputing it as None here would erase a real prior
            # value on every repeat of the same hard stop.
            watermark_offset = last_offset
            watermark_hash = prior_hash
        elif reason is not None:
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
            watermark_hash = _line_hash(raw_lines[last_good_line_no - last_line_no - 1])
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
    return {"turns": turns, "activity": activity, "skipped": skipped, "hard_stop": hard_stop}


def harvest_all(conn: sqlite3.Connection, sessions_root: Path, host_id: str = "") -> dict:
    """Discover and harvest every `*.jsonl` under `sessions_root`.

    One file's failure does not affect any other file. `harvest_file` itself
    only ever raises `WatermarkAnomaly` — everything else it can detect is
    already a return-value hard stop — but a file can still disappear or
    become unreadable between the glob and the read (`OSError`), or a row can
    violate a constraint this collector did not anticipate despite the
    per-insert handling in `_harvest_lines` (`sqlite3.Error`, belt-and-braces).
    Catching both here, per file, is what makes "one file's hard stop does not
    affect any other file" true for every failure mode, not just the ones
    `_harvest_lines` already turns into a clean return value.

    Returns `{"files": n, "turns": n, "activity": n, "skipped": n,
    "failures": [{"path", "line", "reason"}, ...]}`. `line` is `None` for a
    failure caught here rather than reported by `_harvest_lines` itself.
    """
    files = sorted(sessions_root.glob("**/*.jsonl")) if sessions_root.is_dir() else []
    total_turns = 0
    total_activity = 0
    total_skipped = 0
    failures: list[dict] = []

    for path in files:
        try:
            result = harvest_file(conn, path, host_id=host_id)
        except (WatermarkAnomaly, OSError, sqlite3.Error) as exc:
            failures.append({"path": str(path), "line": None, "reason": str(exc)})
            continue
        total_turns += result["turns"]
        total_activity += result["activity"]
        total_skipped += result["skipped"]
        if result["hard_stop"] is not None:
            failures.append({"path": str(path), **result["hard_stop"]})

    return {
        "files": len(files),
        "turns": total_turns,
        "activity": total_activity,
        "skipped": total_skipped,
        "failures": failures,
    }
