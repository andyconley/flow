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
  call has one clean identity. Confirmed the strong way: zero `requestId`
  groups span more than one `message.id` across 13,286 groups checked, so
  one `requestId` is exactly one `message.id` is exactly one API call.
- **Those repeated `usage` blocks are not actually identical, and the first
  version of this collector lost output because of it.** Every input field
  is byte-identical on every line of a group. `output_tokens` is not — it
  grows as the response streams, reaching its final value only on the line
  carrying `stop_reason`. A real group: `[4, 4, 4, 4, 4, 487]`. The original
  `INSERT OR IGNORE` kept the first line, so that turn was stored as 4
  output tokens instead of 487.
  The rule this implies is asymmetric — **inputs from any line, output from
  the maximum** — and both halves of it were measured against the Anthropic
  console for the same account and period before being believed:

  | strategy | cache_read vs console | output vs console |
  |---|---|---|
  | first (what shipped) | 49% | 67% |
  | last | 49% | 76% |
  | max | 49% | 76% |
  | sum | 88% | 151% |

  `sum` overshoots output by half because summing a group triple-counts one
  request's inputs; it is the intuitive fix and it is wrong. `max` is
  preferred over `last` — the two differ by 2 tokens across the whole corpus,
  but `max` is order-independent, which is what makes replaying a file
  incapable of corrupting a row and therefore what makes `--rescan` safe to
  run repeatedly. The residual 49% on cache_read is not a defect of this
  collector: it is traffic that never touched this machine (Claude Code on
  the Web, other hosts), which `harvest.host_id` exists to address and
  nothing yet populates.
- **`system` records with `subtype: "compact_boundary"` are the only explicit
  record of context management**, and they were dropped entirely by the
  non-assistant fallthrough until collector v3. All 29 in this machine's
  corpus carry `timestamp`, `sessionId`, and `cwd`, so they attach to a
  session by the ordinary path. `compactMetadata` carries `trigger`
  (`manual` | `auto`), `preTokens`, `postTokens`, `cumulativeDroppedTokens`,
  and `durationMs`. `trigger` is the field that matters and the reason the
  payload is stored verbatim rather than tallied: `manual` is deliberate
  hygiene and `auto` is hitting the ceiling, opposite signals about a
  session's health that a single count would destroy. They land in
  `agent_activity_raw`, not `turn_raw` — a compaction burns tokens but
  reports none of its own, and `turn_raw` is what every token sum reads.
  All 29 sit in main transcripts, none in `subagents/` files, none with
  `isSidechain: true`; compaction is a main-thread event. That matters
  because `agent_activity_raw`'s `UNIQUE (session_row_id, source_line_no)`
  was designed for Codex, where one session is exactly one file — for Claude
  a session's main file and its subagent files each number lines from 1 under
  one `session_row_id`, so a compact event in a subagent file could silently
  collide with one in the main file. Measured at zero occurrences and left
  documented rather than fixed, since the constraint is shared with Codex.
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
  expressed as idempotent, order-independent SQL rather than in-memory
  state: a `custom-title` record unconditionally overwrites `session.title`
  (a deliberate rename always wins, and locks out every future `ai-title`
  permanently — that's what `title_source = 'custom'` gates).
  Genuine last-write-wins for repeated `ai-title` records needed a real
  investigation, not just a second SQL statement. A session can carry
  *several* `ai-title` records (121 of 137 real files with any `ai-title`
  have more than one) — the first design here compared each record's own
  timestamp, which turned out not to exist: all 6,340 real
  `custom-title`/`ai-title` records sampled carry exactly
  `{type, aiTitle|customTitle, sessionId}`, nothing else. What real data
  *does* have: records adjacent to a title line (user/assistant/system/...)
  usually carry a real `timestamp`, and JSONL is strictly append-only, so
  the nearest preceding timestamped record bounds when the title event
  actually happened. `last_seen_ts` (schema v4, see `usage_store.py`'s
  migration comment for the full investigation) is a running high-water
  mark advanced from every record type that carries a timestamp — that
  value, read at the moment an `ai-title` line is processed, is that
  record's effective timestamp for comparison against `title_ai_ts`, the
  effective timestamp of the currently-accepted `ai-title`. Two title
  records with nothing timestamped between them (common — several other
  record types carry no timestamp either) share one effective timestamp, so
  only the first of that tied cluster is accepted — this does not
  reconstruct true last-line-wins for back-to-back repeats with no time
  information between them, but it does correctly resolve genuine
  time-separated re-titling and the one real case (1 of 163 real sessions
  with any title records) where a session's title records are split across
  more than one file, from a session-continuation event — a purely
  in-memory or file-local-line-number ordinal would get both of those
  wrong.
  A title record whose `session_row_id` cannot be resolved is
  counted as `skipped`, consistent with every other unresolvable record.
  `flow harvest claude --backfill` (see `cli/harvest.py`) resets the
  `harvest` watermark and replays already-harvested files so already-recorded
  sessions pick up titles, `cwd`, and title provenance retroactively — safe
  because `turn_raw`'s natural key makes replaying already-seen turns a free
  no-op, and every schema-v4 column is NULL on migration, so a session's
  provenance genuinely needs one replay to be derived at all.
- **`cwd` fills a gap on any record type that carries it, not just the
  identity-establishing one.** `_get_or_create_session` runs exactly once
  per file, so a file whose first record happens to be a `custom-title` or
  `ai-title` line (neither carries `cwd`) would otherwise leave
  `session.cwd` `NULL` forever — silently weakening `cost.py`'s
  title-then-`cwd`-then-id label fallback for that session, permanently.
"""

import json
import sqlite3
from pathlib import Path

from jsonl_watermark import WatermarkAnomaly, line_byte_length, line_hash, read_new_lines
from session_lookup import lookup_session_for_path

COLLECTOR_VERSION = 3
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


def _current_last_seen_ts(conn: sqlite3.Connection, session_row_id: int) -> str | None:
    """The session's current timestamp high-water mark, or `None` if never set.

    Read fresh rather than trusted from an in-memory variable across batches
    or files: a session created by one file can already have activity
    recorded against it by a different file processed earlier (or, for the
    one real multi-file-session case found in this machine's corpus, by an
    earlier line in a file this same call hasn't reached yet on a resumed
    harvest). See the module docstring's title-capture section for why this
    exists at all.
    """
    row = conn.execute("SELECT last_seen_ts FROM session WHERE id = ?", (session_row_id,)).fetchone()
    return row[0] if row is not None else None


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
) -> tuple[int, int, int, int, str | None, int | None]:
    """Process one batch of already-read raw lines.

    Returns `(turns_written, activity_written, skipped, last_good_line_no,
    hard_stop_reason, hard_stop_line_no)`. `activity_written` counts
    `compact_boundary` records — Claude's own context-management telemetry,
    which carries no token usage of its own and so lands in
    `agent_activity_raw` beside Codex's `sub_agent_activity` rather than in
    `turn_raw`.

    Session identity resolves once, up front, via `lookup_session_for_path` —
    not lazily on first need inside the loop. This is the same fix
    `codex_collector.py` needed after review found the lazy version only held
    within a single batch; doing it this way from the start means Claude's
    collector never has that bug to find.

    Dedup needs no extra bookkeeping beyond what the schema already provides:
    `natural_turn_id = requestId`, and `turn_raw`'s own
    `UNIQUE (session_row_id, natural_turn_id)` constraint is exactly the
    dedup rule — several assistant lines share one `requestId`, the first
    insert lands, every later one for the same call resolves through the
    upsert's conflict clause. This is much simpler than Codex's open-turn
    state machine, since one `requestId` here is already the right row
    identity with no correlation across separate record types required; a
    pre-check against an in-memory set of already-seen ids would only
    duplicate protection the constraint already gives for free.

    What the conflict clause does with the later lines is the part that took
    a measurement to get right — see the module docstring's streamed-output
    finding. The rule is: inputs from any line, output from the maximum.
    """
    session_row_id: int | None = lookup_session_for_path(conn, HARNESS, path)
    last_seen_ts: str | None = _current_last_seen_ts(conn, session_row_id) if session_row_id is not None else None
    # Once cwd is known to be set, skip the per-line gap-fill UPDATE — on a
    # full backfill that statement would otherwise run for essentially every
    # record in the corpus as a no-op. Deliberately starts False even when
    # the session already exists: one extra no-op UPDATE on the first
    # cwd-bearing line is cheaper than a second lookup query here.
    cwd_known = False

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
                raise _HardStop(line_no, f"expected a JSON object, got {type(record).__name__}")

            rtype = record.get("type")

            if session_row_id is None:
                sid = record.get("sessionId")
                if sid is not None:
                    session_row_id = _get_or_create_session(conn, sid, record, path)
                    last_seen_ts = _current_last_seen_ts(conn, session_row_id)
                else:
                    skipped += 1
                    last_good_line_no = line_no
                    continue

            # Fills a gap only, on ANY record type carrying `cwd` — not just
            # the identity-establishing one `_get_or_create_session` reads.
            # That function runs exactly once per file, so a file whose
            # first record happens to be a title record (no `cwd` field)
            # would otherwise leave `session.cwd` NULL forever, weakening
            # `cost.py`'s label fallback for that session permanently.
            cwd = record.get("cwd")
            if cwd and not cwd_known:
                conn.execute("UPDATE session SET cwd = ? WHERE id = ? AND cwd IS NULL", (cwd, session_row_id))
                cwd_known = True

            # A running high-water mark of the most recent real `timestamp`
            # observed anywhere in this session's stream — advanced from
            # every record type that carries one, not just titles. This is
            # the only reason an `ai-title` record (which carries none of
            # its own) has any effective timestamp to compare against at
            # all; see the schema v4 migration comment in `usage_store.py`
            # for the real-data investigation that led here.
            record_ts = record.get("timestamp")
            if record_ts and (last_seen_ts is None or record_ts > last_seen_ts):
                last_seen_ts = record_ts
                conn.execute("UPDATE session SET last_seen_ts = ? WHERE id = ?", (last_seen_ts, session_row_id))

            if rtype == "custom-title":
                # Unconditional — a deliberate rename always wins, regardless
                # of when it's seen relative to any ai-title. Clears
                # title_ai_ts too: once a real rename happens, no ai-title
                # write is ever eligible again (the WHERE clause below checks
                # title_source, not title_ai_ts, for that lockout — clearing
                # it here is just hygiene, not load-bearing).
                title = record.get("customTitle")
                if title:
                    conn.execute(
                        "UPDATE session SET title = ?, title_source = 'custom', title_ai_ts = NULL WHERE id = ?",
                        (title, session_row_id),
                    )
                last_good_line_no = line_no
                continue

            if rtype == "ai-title":
                # Genuine last-write-wins, bounded by last_seen_ts (this
                # record's own effective timestamp — it carries none of its
                # own). Accepted when: no custom-title has ever locked this
                # session out (title_source IS NULL or 'ai'), AND either (a)
                # there is no time information anywhere yet for this session
                # AND no title has ever been accepted (title_source IS NULL
                # too — without that third leg, every untimed ai-title in a
                # row would re-qualify and the LAST of an untimed cluster
                # would win, the opposite of the documented first-wins tie
                # rule; caught in review) or (b) last_seen_ts is real and
                # strictly newer than the stored title_ai_ts. An unknown
                # effective timestamp is never allowed to override a title
                # that already has a real title_ai_ts.
                #
                # Known, accepted limitation: two ai-title records with no
                # timestamped record between them (common — several other
                # record types carry no timestamp either) share one
                # effective timestamp, so only the first of that tied
                # cluster is accepted. This is not a full last-line-wins
                # reconstruction; it correctly resolves genuine
                # time-separated re-titling and the rare multi-file-session
                # case, which a purely in-memory or file-local-line-number
                # ordinal would not.
                title = record.get("aiTitle")
                if title:
                    conn.execute(
                        "UPDATE session SET title = ?, title_source = 'ai', title_ai_ts = ?"
                        " WHERE id = ?"
                        "   AND (title_source IS NULL OR title_source = 'ai')"
                        "   AND ("
                        "     (title_ai_ts IS NULL AND ? IS NULL AND title_source IS NULL)"
                        "     OR (? IS NOT NULL AND (title_ai_ts IS NULL OR ? > title_ai_ts))"
                        "   )",
                        (title, last_seen_ts, session_row_id, last_seen_ts, last_seen_ts, last_seen_ts),
                    )
                last_good_line_no = line_no
                continue

            if rtype == "system" and record.get("subtype") == "compact_boundary":
                # Keyed on `subtype`, not on `type == "system"` alone — other
                # system records exist and carry no compaction data.
                #
                # This is the one context-management event Claude records
                # explicitly, and it was being dropped at the fallthrough
                # below. `compactMetadata.trigger` is the field that matters:
                # `manual` is a deliberate /compact, `auto` is hitting the
                # ceiling. They are opposite signals about a session's health
                # and must never be summed into one count, which is why the
                # verbatim payload is stored rather than a single tally.
                #
                # agent_activity_raw rather than turn_raw: a compaction burns
                # tokens but reports none of its own, and turn_raw rows are
                # what every token sum reads. A row here cannot pollute a
                # total by construction — which is the same reason Codex's
                # `sub_agent_activity` lands in this table.
                ts = record.get("timestamp")
                if ts is None:
                    raise _HardStop(line_no, "compact_boundary record is missing timestamp")
                cur = conn.execute(
                    "INSERT OR IGNORE INTO agent_activity_raw"
                    " (session_row_id, ts, kind, agent_thread_id, agent_path, payload,"
                    "  source_path, source_line_no, collector_version)"
                    " VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?)",
                    (
                        session_row_id,
                        ts,
                        "compact_boundary",
                        text,
                        str(path),
                        line_no,
                        COLLECTOR_VERSION,
                    ),
                )
                if cur.rowcount:
                    activity_written += 1
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

            # Upsert, not INSERT OR IGNORE — see the module docstring's
            # streamed-output finding. The first line of a group wins for
            # every field except the one that grows.
            #
            # `source_path` moves with `source_line_no` because the two are
            # only meaningful as a pair. A group cannot span files in
            # practice — one requestId is one API call, written to one
            # transcript — but main and subagent files do share a
            # `session_row_id`, so a conflict across two files is
            # structurally reachable, and resolving it to file A's path with
            # file B's line number would be a silently wrong pointer.
            #
            # `ts` and `turn_seq` are deliberately absent from the SET list:
            # they keep the first line's values, which is when the turn
            # started. That is stable under re-harvest, and it stops a turn
            # migrating across a day boundary in a time-bucketed read surface
            # because the response happened to finish after midnight.
            #
            # COALESCE(..., -1) rather than a bare comparison: NULL loses every
            # comparison in SQL, so without it a stored row with no usage could
            # never be beaten by a row with a real count. -1 is below every
            # legal token count, so any real number wins over absent, and two
            # absent-usage rows do not update each other.
            #
            # The comparison runs in SQL rather than Python because its right
            # operand is the *stored* payload, which this function does not
            # hold — reading it back first would be a second query per line
            # across the whole corpus.
            cur = conn.execute(
                "INSERT INTO turn_raw"
                " (session_row_id, natural_turn_id, turn_seq, is_subagent, ts, model,"
                "  payload, source_path, source_line_no, collector_version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT (session_row_id, natural_turn_id) DO UPDATE SET"
                "   payload           = excluded.payload,"
                "   source_path       = excluded.source_path,"
                "   source_line_no    = excluded.source_line_no,"
                "   collector_version = excluded.collector_version"
                " WHERE COALESCE(json_extract(excluded.payload, '$.message.usage.output_tokens'), -1)"
                "     > COALESCE(json_extract(turn_raw.payload, '$.message.usage.output_tokens'), -1)",
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
            # rowcount counts inserts AND corrections, which is the honest
            # number for "rows this batch changed" but is no longer the same
            # as "new turns discovered" — on a --rescan the two diverge
            # sharply. The CLI wording says "turns" for both; that is
            # accurate for a normal incremental run, where a correction can
            # only happen for a group split across two batches.
            if cur.rowcount:
                turns_written += 1
                # A changed payload must invalidate its normalized row, and
                # this belongs here rather than in the rescan path because
                # the corruption it prevents needs no rescan to happen.
                #
                # `normalize_all` selects stale rows by `norm_version` alone.
                # Nothing else marks a `turn_norm` row stale, because until
                # this upsert existed a stored payload could never change.
                # So: `flow cost active` harvests and then normalizes. Run it
                # while a response is still streaming and the partial group is
                # stored at output 4 AND stamped with the current version. The
                # next harvest corrects `turn_raw` to 487 — the split-batch
                # case the tests pin — and `turn_norm` keeps 4 forever. That
                # is the same loss this collector version exists to fix,
                # reappearing in the layer every read surface actually queries,
                # with both tables self-consistent and nothing reporting it.
                #
                # `norm_version = -1` rather than DELETE: `turn_norm` is
                # disposable, but a delete would cascade into anything that
                # ever gains `REFERENCES turn_norm(...) ON DELETE CASCADE` —
                # the same hazard that made `normalize_all` prefer
                # `DO UPDATE` over `INSERT OR REPLACE`. -1 is below every real
                # version, so the ordinary staleness query selects it.
                #
                # A no-op for the common case: a freshly inserted turn has no
                # `turn_norm` counterpart yet, so this updates nothing.
                conn.execute(
                    "UPDATE turn_norm SET norm_version = -1 WHERE turn_raw_id ="
                    " (SELECT id FROM turn_raw WHERE session_row_id = ? AND natural_turn_id = ?)",
                    (session_row_id, natural_turn_id),
                )
            last_good_line_no = line_no
    except _HardStop as stop:
        return turns_written, activity_written, skipped, last_good_line_no, stop.reason, stop.line_no

    return turns_written, activity_written, skipped, last_good_line_no, None, None


def harvest_file(conn: sqlite3.Connection, path: Path, host_id: str = "") -> dict:
    """Incrementally harvest one file. Returns a summary dict.

    `{"turns": n, "activity": n, "skipped": n, "hard_stop": None | {"line": n,
    "reason": str}}`. Mirrors `codex_collector.harvest_file`'s contract exactly
    — see there for the reasoning on returning a hard stop rather than raising
    it, and on the watermark-preservation logic for a batch that commits
    nothing.
    """
    row = conn.execute(
        "SELECT last_offset, last_line_no, last_line_hash FROM harvest"
        " WHERE harness = ? AND source_path = ? AND host_id = ?",
        (HARNESS, str(path), host_id),
    ).fetchone()
    last_offset, last_line_no, prior_hash = row if row is not None else (0, 0, None)

    raw_lines, new_offset, current_size = read_new_lines(path, last_offset)
    if not raw_lines:
        return {"turns": 0, "activity": 0, "skipped": 0, "hard_stop": None}

    with conn:
        turns, activity, skipped, last_good_line_no, reason, bad_line_no = _harvest_lines(
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
    return {"turns": turns, "activity": activity, "skipped": skipped, "hard_stop": hard_stop}


def harvest_all(conn: sqlite3.Connection, sessions_root: Path, host_id: str = "") -> dict:
    """Discover and harvest every `*.jsonl` under `sessions_root`.

    One file's failure does not affect any other file — mirrors
    `codex_collector.harvest_all`'s isolation exactly, including catching
    `WatermarkAnomaly`/`OSError`/`sqlite3.Error` per file.
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
