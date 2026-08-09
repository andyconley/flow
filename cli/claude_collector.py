"""Claude Code session harvester: raw layer only.

Reads `~/.claude/projects/**/*.jsonl` incrementally, against the `harvest`
table's per-file watermark, and writes `session` + `turn_raw` rows. Nothing
here normalizes, advises, or prints — see `cli/harvest.py` for the CLI-facing
wrapper.

No module-level path resolution, matching `codex_collector.py` and
`usage_store.py`, for the same reason: a directly-imported unit test must
never be able to touch the real `~/.claude/projects/` or `~/.flow/usage.db`.

## Field-shape ground truth this module encodes

Verified against real transcripts on the machine this was written on,
including this session's own file, not inferred from `~/bin/token-report`'s
existing behavior:

- **A single API response is written as several `assistant`-type JSONL
  lines** (text, thinking, tool_use blocks each repeating the same `usage`
  block), all sharing one top-level `requestId`. Deduping by `requestId` is
  still necessary and correct: one real 3,620-line sample had 2,341 distinct
  `requestId`s, 1,022 of them appearing more than once. Unlike Codex, where
  the natural key needed the line number appended (`turn_id:source_line_no`)
  because one `turn_id` legitimately spans several real model calls,
  `requestId` alone is already the right granularity here — one real API
  call has one clean identity.
- **`isSidechain` does flag subagent turns — `token-report`'s original
  assumption was right.** A first pass concluded otherwise (zero
  `isSidechain: true` across a scan of every file this collector's own
  `default_sessions_root()` glob reaches) and shipped `is_subagent = 0`
  always. That scan used a *non-recursive* glob and never looked inside the
  `subagents/<parent-session-uuid>/agent-<agent-id>.jsonl` files that current
  Claude Code writes for background/queued agent invocations — 362 of 714
  files on this machine, and 19,139 real `isSidechain: true` records once
  scanned correctly. Every record in a subagent file — including its full,
  real `usage` block — carries `isSidechain: true` and, notably, the
  *parent's own* `sessionId`, not a distinct child id: `is_subagent` is
  therefore read per record from `isSidechain`, not derived from a
  session-level lookup the way Codex's `is_subagent` is. There is a second,
  narrower subagent surface — synchronous, in-process `Agent`/`Task` tool
  calls — whose `tool_result` really does contain only final text with no
  nested transcript or usage data on this machine; that one genuinely has no
  local token data to recover, and this collector does nothing special for
  it because there is nothing here to attribute.
- **One file is one session** for ordinary main-thread transcripts.
  `sessionId` matches the file's own UUID (its filename). Subagent files are
  the one exception, and a deliberate one: they share the parent's
  `sessionId` rather than declaring their own, so `_get_or_create_session`
  naturally finds and reuses the parent's existing session row — subagent
  turns land in the same session as the work they were spawned from, exactly
  matching Claude's own logical grouping. `session.source_path` may end up
  pointing at whichever of a session's several files (main plus any
  subagents) is harvested first, not necessarily the main one — in practice
  this means a subagent file's own `source_path` almost never resolves
  anything, since `lookup_session_for_path` looks it up by *that file's own
  path*, and a session's identity almost always got recorded against a
  different file. Every subagent-file batch therefore falls back to
  re-deriving identity from `sessionId` on its own records — which works,
  because the one property this actually depends on is that *every* record
  type this collector writes a row for (`assistant`, always) carries
  `sessionId`. A record type that carries `usage` but not `sessionId` would
  break this silently; none is known to exist. Records that lack `sessionId`
  entirely (`file-history-snapshot`, `file-history-delta`, and a handful of
  others) are counted as `skipped` rather than misattributed or lost — but
  that is a property of those specific record types, not a general guarantee
  that anything unresolvable degrades safely.
- **`usage` carries more than `token-report` reads.** Beyond
  `input_tokens`/`cache_read_input_tokens`/`cache_creation_input_tokens`/
  `output_tokens`, real data now includes `cache_creation` (a breakdown of
  `ephemeral_1h_input_tokens` vs `ephemeral_5m_input_tokens` — the cache-TTL
  split `data/harness_capabilities.json` already claims for Claude), plus
  `server_tool_use`, `service_tier`, `inference_geo`, `iterations`, `speed`.
  None of it is extracted here — the raw payload is stored verbatim
  regardless, so normalization can pick any of it up later without a
  re-harvest.
- **`custom-title` and `ai-title` records populate `session.title`.**
  `token-report` computes this precedence in one in-memory pass per file:
  `custom-title` always wins and last-one-wins on repeats; `ai-title` only
  fills in when no `custom-title` has ever appeared. This collector persists
  incrementally across separate runs instead, so the same precedence is
  expressed as two idempotent, order-independent SQL statements rather than
  in-memory state: a `custom-title` record unconditionally overwrites
  `session.title` (a deliberate rename always wins, regardless of when it's
  seen relative to any `ai-title`); an `ai-title` record only fills the
  column when it is still `NULL` (a genuine gap, never a real title). Either
  can be encountered first, in this batch or a future one, and the result is
  the same. A title record whose `session_row_id` cannot be resolved is
  counted as `skipped`, consistent with every other unresolvable record.
  `flow harvest claude --backfill-titles` (see `cli/harvest.py`) resets the
  `harvest` watermark and replays already-harvested files so already-recorded
  sessions pick up titles retroactively — safe because `turn_raw`'s natural
  key makes replaying already-seen turns a free no-op.
"""

import json
import sqlite3
from pathlib import Path

from jsonl_watermark import WatermarkAnomaly, line_byte_length, line_hash, read_new_lines
from session_lookup import lookup_session_for_path

COLLECTOR_VERSION = 1
HARNESS = "claude"


def default_sessions_root(home: Path | None = None) -> Path:
    """Resolve Claude Code's transcript directory lazily. See module docstring for why."""
    base = home if home is not None else Path.home()
    return base / ".claude" / "projects"


def _get_or_create_session(conn: sqlite3.Connection, session_id: str, meta: dict, path: Path) -> int:
    """`parent_session_id` is always NULL — Claude's subagent files don't need it.

    Unlike Codex, where a subagent gets a distinct session id linked back to
    its parent via a lineage field, Claude's subagent files declare the
    *parent's own* `sessionId` rather than a distinct one — see the module
    docstring's `isSidechain` finding. There is no separate child identity to
    record a parent link against; `is_subagent` (set per record from
    `isSidechain`, not here) is what distinguishes those turns instead.
    """
    row = conn.execute(
        "SELECT id FROM session WHERE harness = ? AND session_id = ?",
        (HARNESS, session_id),
    ).fetchone()
    if row is not None:
        return row[0]

    cur = conn.execute(
        "INSERT INTO session (harness, session_id, parent_session_id, started_at, cwd, title, source_path)"
        " VALUES (?, ?, NULL, ?, ?, ?, ?)",
        (
            HARNESS,
            session_id,
            meta.get("timestamp"),
            meta.get("cwd"),
            None,  # No dedicated title field on the identity-establishing record.
            str(path),
        ),
    )
    return cur.lastrowid


class _HardStop(Exception):
    """Internal signal: stop this file's harvest at a specific line, with a reason.

    Same shape as `codex_collector._HardStop` — decode, parse, shape, and
    schema-constraint failures all funnel through one path.
    """

    def __init__(self, line_no: int, reason: str):
        self.line_no = line_no
        self.reason = reason


def _harvest_lines(
    conn: sqlite3.Connection,
    path: Path,
    raw_lines: list[bytes],
    starting_line_no: int,
) -> tuple[int, int, int, str | None, int | None]:
    """Process one batch of already-read raw lines.

    Returns `(turns_written, skipped, last_good_line_no, hard_stop_reason,
    hard_stop_line_no)`. No `activity_written` — Claude has nothing analogous
    to Codex's `sub_agent_activity` telemetry, so there is no `agent_activity_raw`
    counterpart to populate here.

    Session identity resolves once, up front, via `lookup_session_for_path` —
    not lazily on first need inside the loop. This is the same fix
    `codex_collector.py` needed after review found the lazy version only held
    within a single batch; doing it this way from the start means Claude's
    collector never has that bug to find.

    Dedup needs no extra bookkeeping beyond what the schema already provides:
    `natural_turn_id = requestId`, and `turn_raw`'s own
    `UNIQUE (session_row_id, natural_turn_id)` constraint is exactly the
    dedup rule — several assistant lines share one `requestId`, the first
    insert lands, every later one for the same call is an `INSERT OR IGNORE`
    no-op. This is much simpler than Codex's open-turn state machine, since
    one `requestId` here is already the right row identity with no
    correlation across separate record types required; a pre-check against an
    in-memory set of already-seen ids would only duplicate protection the
    constraint already gives for free.
    """
    session_row_id: int | None = lookup_session_for_path(conn, HARNESS, path)

    turns_written = 0
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
                raise _HardStop(line_no, f"expected a JSON object, got {type(record).__name__}")

            rtype = record.get("type")

            if session_row_id is None:
                sid = record.get("sessionId")
                if sid is not None:
                    session_row_id = _get_or_create_session(conn, sid, record, path)
                else:
                    skipped += 1
                    last_good_line_no = line_no
                    continue

            if rtype == "custom-title":
                # Unconditional — a deliberate rename always wins, and the
                # last one seen (whether within this batch or a future one)
                # is correct regardless of when this line is encountered
                # relative to any ai-title.
                title = record.get("customTitle")
                if title:
                    conn.execute("UPDATE session SET title = ? WHERE id = ?", (title, session_row_id))
                last_good_line_no = line_no
                continue

            if rtype == "ai-title":
                # Fills a gap only. `AND title IS NULL` is what makes this
                # order-independent across incremental runs without needing
                # to remember "have I already seen a custom-title" in memory
                # the way a single in-memory pass (token-report's approach)
                # would: if a custom-title already set the title, this is a
                # no-op forever, from any batch, in any order.
                title = record.get("aiTitle")
                if title:
                    conn.execute(
                        "UPDATE session SET title = ? WHERE id = ? AND title IS NULL", (title, session_row_id)
                    )
                last_good_line_no = line_no
                continue

            if rtype != "assistant":
                # Every other record type (user, system, agent-name,
                # attachment, ...) carries no usage data. Not counted as
                # skipped — these are ordinary, expected content, unlike a
                # record this collector genuinely couldn't attach to a
                # session.
                last_good_line_no = line_no
                continue

            request_id = record.get("requestId")
            msg = record.get("message") if isinstance(record.get("message"), dict) else {}
            usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else None
            if usage is None:
                # An assistant entry with no usage block at all (seen for
                # some non-text content blocks). Nothing to record; not a
                # shape violation, so not counted as skipped.
                last_good_line_no = line_no
                continue

            ts = record.get("timestamp")
            if ts is None:
                raise _HardStop(line_no, "assistant record is missing timestamp")

            # The fallback includes the filename, not just the line number.
            # `untracked:{line_no}` was safe for Codex because one Codex
            # session is exactly one file; for Claude, a session's own file
            # and every subagents/<parent-uuid>/agent-*.jsonl file sharing
            # that session_row_id each number their own lines from 1, and
            # sibling agent files are similar enough in structure that two
            # colliding on the same line number is a real, if rare,
            # possibility — confirmed against real data: assistant records
            # with a usage block but no requestId do occur, just uncommonly.
            # Without the filename, a collision is a fully silent row drop:
            # INSERT OR IGNORE no-ops, rowcount is 0, and nothing counts it.
            natural_turn_id = request_id if request_id is not None else f"untracked:{path.name}:{line_no}"
            model = msg.get("model")
            # Per-record, not session-level: a subagent invocation is a
            # distinct file that shares the parent's sessionId rather than
            # declaring its own, so the session-level fact Codex's
            # is_subagent relies on does not exist for Claude. isSidechain is
            # the real, per-record signal here — confirmed against 19,139
            # real occurrences, not the near-zero a non-recursive directory
            # scan first suggested.
            is_subagent_value = 1 if record.get("isSidechain") is True else 0

            cur = conn.execute(
                "INSERT OR IGNORE INTO turn_raw"
                " (session_row_id, natural_turn_id, turn_seq, is_subagent, ts, model,"
                "  payload, source_path, source_line_no, collector_version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_row_id,
                    natural_turn_id,
                    line_no,
                    is_subagent_value,
                    ts,
                    model,
                    text,
                    str(path),
                    line_no,
                    COLLECTOR_VERSION,
                ),
            )
            # rowcount, not an unconditional increment — INSERT OR IGNORE
            # silently no-ops on the duplicate-requestId case above, and
            # counting the attempt instead of the outcome would hide the
            # same class of miscount chunk 3's review caught for Codex.
            if cur.rowcount:
                turns_written += 1
            last_good_line_no = line_no
    except _HardStop as stop:
        return turns_written, skipped, last_good_line_no, stop.reason, stop.line_no

    return turns_written, skipped, last_good_line_no, None, None


def harvest_file(conn: sqlite3.Connection, path: Path, host_id: str = "") -> dict:
    """Incrementally harvest one file. Returns a summary dict.

    `{"turns": n, "skipped": n, "hard_stop": None | {"line": n, "reason": str}}`.
    Mirrors `codex_collector.harvest_file`'s contract exactly — see there for
    the reasoning on returning a hard stop rather than raising it, and on the
    watermark-preservation logic for a batch that commits nothing.
    """
    row = conn.execute(
        "SELECT last_offset, last_line_no, last_line_hash FROM harvest"
        " WHERE harness = ? AND source_path = ? AND host_id = ?",
        (HARNESS, str(path), host_id),
    ).fetchone()
    last_offset, last_line_no, prior_hash = row if row is not None else (0, 0, None)

    raw_lines, new_offset, current_size = read_new_lines(path, last_offset)
    if not raw_lines:
        return {"turns": 0, "skipped": 0, "hard_stop": None}

    with conn:
        turns, skipped, last_good_line_no, reason, bad_line_no = _harvest_lines(
            conn, path, raw_lines, last_line_no + 1
        )

        if last_good_line_no == last_line_no:
            watermark_offset = last_offset
            watermark_hash = prior_hash
        elif reason is not None:
            committed_offset = last_offset
            for offset, raw in enumerate(raw_lines):
                if last_line_no + 1 + offset > last_good_line_no:
                    break
                committed_offset += line_byte_length(raw)
            watermark_offset = committed_offset
            watermark_hash = line_hash(raw_lines[last_good_line_no - last_line_no - 1])
        else:
            watermark_offset = new_offset
            watermark_hash = line_hash(raw_lines[-1])

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
    return {"turns": turns, "skipped": skipped, "hard_stop": hard_stop}


def harvest_all(conn: sqlite3.Connection, sessions_root: Path, host_id: str = "") -> dict:
    """Discover and harvest every `*.jsonl` under `sessions_root`.

    One file's failure does not affect any other file — mirrors
    `codex_collector.harvest_all`'s isolation exactly, including catching
    `WatermarkAnomaly`/`OSError`/`sqlite3.Error` per file.
    """
    files = sorted(sessions_root.glob("**/*.jsonl")) if sessions_root.is_dir() else []
    total_turns = 0
    total_skipped = 0
    failures: list[dict] = []

    for path in files:
        try:
            result = harvest_file(conn, path, host_id=host_id)
        except (WatermarkAnomaly, OSError, sqlite3.Error) as exc:
            failures.append({"path": str(path), "line": None, "reason": str(exc)})
            continue
        total_turns += result["turns"]
        total_skipped += result["skipped"]
        if result["hard_stop"] is not None:
            failures.append({"path": str(path), **result["hard_stop"]})

    return {
        "files": len(files),
        "turns": total_turns,
        "skipped": total_skipped,
        "failures": failures,
    }
