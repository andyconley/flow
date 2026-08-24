"""`flow cost`: the first read surface over `turn_norm`.

The read/write split here is per-command, not module-wide. `summary` and
`sessions` only read: beyond `usage_store.ensure_store` (the same
schema-only convenience every command module gives itself — a fresh machine
gets a working `flow cost summary` rather than an error pointing at
`flow setup machine`), they never touch `turn_raw`, `turn_norm`, or
`session`. `active` is deliberately different: it runs the incremental
Claude harvest and a normalize pass before querying — writes to all three
tables — because a `turn_norm`-only read would lag the newest turns and a
"what needs attention right now" view that answers as-of-the-last-pipeline-
run defeats its own purpose.

`summary_rows`, `sessions_rows`, and `capacity_gauge` are pure query
functions — a connection and an optional cutoff in, a list of dicts (or, for
the gauge, a single dict or `None`) out. Nothing here decides how a caller
displays the result; `render_table` and `render_json` are two independent
renderers over the same shape, matching the convention `kubectl`/`docker`/
`gh` use: one canonical structured result, one default human-readable
rendering, one `--json` for the same data machine-readable. Both commands'
`--json` output shares one envelope, `{"rows": [...]}`, with `summary`
adding an optional sibling `"capacity"` key — a caller can always read
`payload["rows"]` without checking which subcommand produced it.

Codex's capacity percentages are handled separately from the token-total
rows, on purpose. `capacity_primary_used_pct` and its siblings are a
snapshot of the most recent reading in the window, not a quantity that sums
meaningfully across turns the way token counts do — blending a "percent
full right now" figure into a table of summed totals would misrepresent
both. `cost_summary_command` prints it as an adjacent line (table mode) or
an adjacent key (JSON mode) instead, and omits it entirely — not as a zero
or a blank — when no Codex row with capacity data falls inside the window.
The reading's own timestamp and each field's `window_minutes` are rendered
alongside the percentage: `usage_store.py`'s `_V3` migration documents that
`rate_limits.primary`/`secondary` are not reliably "the 5-hour window" and
"the weekly window" respectively (real data shows both a 300-minute and a
10080-minute value under the `primary` name) — a caller distinguishes them
by the window size actually stored, not by the column name, and a bare
percentage with no age shown would read as current when it may be up to a
full `--days` window stale.

No module-level path or connection resolution, matching every other command
module in `cli/`: a directly-imported unit test must never be able to touch
the real `~/.flow/usage.db`.
"""

import json
import math
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import usage_store
from claude_collector import HARNESS as CLAUDE_HARNESS
from claude_collector import default_sessions_root as claude_sessions_root
from claude_collector import harvest_all as claude_harvest_all
from claude_collector import harvest_file as claude_harvest_file
from codex_collector import HARNESS as CODEX_HARNESS
from codex_collector import default_sessions_root as codex_sessions_root
from codex_collector import harvest_all as codex_harvest_all
from codex_collector import harvest_file as codex_harvest_file
from hookio import log_hook_error as _log_hook_error
from hookio import read_hook_stdin as _read_hook_stdin
from hookio import safe_key as _safe_session_id
from normalize import normalize_all
from paths import HOME, SOURCE_DIR
from session_lookup import lookup_session_for_path
import telemetry_freshness

DEFAULT_WINDOW_DAYS = 7
DEFAULT_SESSIONS_LIMIT = 20
DEFAULT_ACTIVE_WITHIN_MINUTES = 60

# Context-window facts and judgment thresholds for `flow cost active`,
# carried over verbatim from `~/bin/token-report` (the tool this view
# supersedes), where each earned its value against real sessions:
# - Context windows aren't recorded in transcripts (the model field reads
#   "claude-opus-5" with no [1m] suffix), so anything observed above
#   LONG_THRESHOLD must have been the long-context variant; below it the
#   standard window is assumed unless the statusline recorded the exact one.
# - TOPIC_GAP_SEC: idle this long before the latest turn implies you came
#   back to new work — the signal that distinguishes /clear from /compact.
# - The 45/25 carry thresholds grade how urgently the recommendation reads.
STD_WINDOW = 200_000
LONG_WINDOW = 1_000_000
LONG_THRESHOLD = 190_000
TOPIC_GAP_SEC = 20 * 60
CARRY_NOW_PCT = 45
CARRY_NEXT_BREAK_PCT = 25

# Verdict thresholds, also carried over verbatim from token-report:
# - VERDICT_FLOOR: below this carry cannot matter on any window.
# - VERDICT_MIN_REQUESTS: a young session probably ends before carry
#   compounds; window-agnostic on purpose (the true window is only known
#   to the Claude statusline, which grades severity itself from the raw
#   numbers the verdict line carries).
# - WARN_CARRY_FLOOR / WARN_REWARN_STEP tune the pre-execution warning
#   (`flow cost warn --hook`): fire only above a carry heavy on ANY window
#   (100K is 50% of the standard window, 10% of the long one), and re-warn
#   only after carry grows another step — a warning that repeats on every
#   prompt trains the reader to ignore it, and each firing costs real
#   context tokens in the conversation it lands in.
VERDICT_FLOOR = 25_000
VERDICT_MIN_REQUESTS = 15
WARN_CARRY_FLOOR = 100_000
WARN_REWARN_STEP = 50_000

# Where verdict files and warn-throttle markers live. The Claude statusline
# reads /tmp/claude-verdict-<session_id> — the filename contract predates
# flow and is preserved exactly; the codex- twin exists for symmetry and
# for the warn hook, which reads whichever matches its own harness.
VERDICT_DIR = Path("/tmp")

# Fallback set of real context-window sizes, used only to snap a measured
# observation to the nearest one. `_known_windows()` prefers the sizes named
# in `data/model_context_windows.json` so the two cannot drift — that file
# already carries a 272,000 entry these two constants do not, and the `?`
# note tells the reader that adding a model there resolves its window, which
# would have been false for any size not listed here.
FALLBACK_WINDOWS = (STD_WINDOW, LONG_WINDOW)

# How far a recorded or observed context value may sit from a known window and
# still snap to it. A corrupt statusline file or a stray compaction reading
# that snapped confidently to the wrong window would be worse than the honest
# `~` inference, so anything further off falls through to the next source.
WINDOW_SNAP_TOLERANCE = 0.15


def _data_file(name: str) -> dict:
    """Load one JSON file from the release's `data/` directory.

    Not cached and not resolved at import time, matching every other path in
    this module: a test points `SOURCE_DIR` somewhere else, and a cache would
    make the second test in a process see the first one's file. These are a
    few hundred bytes read once per command.
    """
    path = SOURCE_DIR / "data" / name
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def token_weights() -> dict:
    """Billing multipliers for the input token classes, from `data/token_weights.json`.

    Falls back to the shipped value for any entry that is missing or
    unusable — a weighted number computed from a default is still comparable
    across buckets, which is what `trend` is for, whereas a crashed command
    reports nothing at all. See the file's own comment for why these are
    Claude-only.

    Each value must be a finite, non-negative real number, and the check is
    load-bearing rather than defensive tidiness: these are interpolated into
    SQL as numeric literals (see `_weighted_tokens_sql`), and `json.loads`
    accepts the bare literals `NaN`, `Infinity`, and `-Infinity`, which pass
    an `isinstance` check and then render as `nan`/`inf` — parsed by SQLite as
    *identifiers*, so the query fails with "no such column: nan" and the whole
    command dies. `bool` is excluded because it is an `int` subclass and
    `True` would silently mean 1.0. Negatives are excluded because they make
    weighted totals and `sub_pct` meaningless rather than merely wrong.

    A string can never reach the interpolation, so this is not the injection
    guard — that is the type check itself, and it is why the values are
    interpolated rather than bound (SQLite will not accept a parameter in the
    scalar position of an arithmetic literal inside an aggregate expression
    built this way).
    """
    weights = _data_file("token_weights.json").get("weights")
    merged = dict(_DEFAULT_WEIGHTS)
    if not isinstance(weights, dict):
        return merged
    for key, value in weights.items():
        if key not in merged:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if not math.isfinite(value) or value < 0:
            continue
        merged[key] = float(value)
    return merged


_DEFAULT_WEIGHTS = {
    "uncached_input": 1.0,
    "cache_read": 0.1,
    "cache_write_5m": 1.25,
    "cache_write_1h": 2.0,
    "cache_write_unsplit": 1.25,
}


def _model_windows() -> dict:
    return _data_file("model_context_windows.json").get("models") or {}


def _model_entry(model: str | None, models: dict) -> dict | None:
    """The table entry for a model id: exact match, else longest prefix.

    Real ids carry release-date suffixes (`claude-haiku-4-5-20251001`) that the
    table should not have to chase. Longest prefix rather than any prefix so a
    future `claude-opus-5-1` entry wins over `claude-opus-5` rather than tying
    with it and resolving by dict order.
    """
    if not model:
        return None
    if model in models:
        return models[model]
    candidates = [key for key in models if model.startswith(key)]
    if not candidates:
        return None
    return models[max(candidates, key=len)]


def _known_windows(models: dict | None = None) -> tuple:
    """Every real window size named in the model table, plus the fallbacks.

    Derived rather than hardcoded so the table and the snapper cannot
    disagree: `_render_active_table`'s `?` note tells the reader that adding a
    model to that file will resolve its window, and that is only true if the
    file's sizes are also the ones an observation can snap to.
    """
    if models is None:
        models = _model_windows()
    sizes = set(FALLBACK_WINDOWS)
    for entry in models.values():
        if not isinstance(entry, dict):
            continue
        for key in ("window", "long_window"):
            value = entry.get(key)
            if isinstance(value, int) and value > 0:
                sizes.add(value)
    return tuple(sorted(sizes))


def _snap_to_known_window(observed: int, models: dict | None = None) -> int | None:
    """The known window `observed` is closest to, if it is close enough."""
    windows = _known_windows(models)
    nearest = min(windows, key=lambda w: abs(w - observed))
    if abs(observed - nearest) <= nearest * WINDOW_SNAP_TOLERANCE:
        return nearest
    return None


def _cutoff(days: int) -> str:
    """UTC ISO8601 cutoff string for "the last `days` days."

    Compared lexicographically against `turn_norm.ts`, which is safe because
    ISO8601 sorts correctly as text — the same convention already used
    everywhere else in this schema (`harvest.harvested_at`, `turn_raw.ts`).
    This assumes every `ts` actually stored is UTC, same as this cutoff:
    `datetime.isoformat()` renders a `+00:00` suffix rather than the `Z` both
    collectors write, but the two compare correctly against each other
    lexicographically as long as both sides are UTC — a `ts` written with a
    non-UTC local offset would break the comparison silently, which is why
    both collectors are expected to keep stamping UTC.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def summary_rows(conn: sqlite3.Connection, since: str | None) -> list[dict]:
    """Token totals grouped by `(harness, model)`, within the window.

    `since=None` means `--all` — every row ever normalized, no cutoff.
    """
    where = "WHERE tn.ts >= ?" if since is not None else ""
    params = (since,) if since is not None else ()
    rows = conn.execute(
        f"""
        SELECT s.harness AS harness, tn.model AS model, COUNT(*) AS turns,
               SUM(tn.fresh_input_tokens) AS fresh_input_tokens,
               SUM(tn.cache_read_tokens) AS cache_read_tokens,
               SUM(tn.cache_write_tokens) AS cache_write_tokens,
               SUM(tn.output_tokens) AS output_tokens
        FROM turn_norm tn
        JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        JOIN session s ON s.id = tr.session_row_id
        {where}
        GROUP BY s.harness, tn.model
        ORDER BY s.harness, tn.model
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _session_label(title: str | None, cwd: str | None, session_id: str) -> str:
    if title:
        return title
    if cwd:
        return cwd
    return f"session:{session_id[:8]}"


def sessions_rows(conn: sqlite3.Connection, since: str | None, limit: int | None = DEFAULT_SESSIONS_LIMIT) -> list[dict]:
    """Token totals grouped by session, most recently active first.

    `title` and `cwd` are queried but not returned as separate columns —
    they're inputs to `label`, the three-tier fallback (`title` → `cwd` → a
    short id) computed here so every caller gets one usable display string
    instead of three raw, often-redundant ones to reconcile itself.

    `first_ts`/`last_ts` are the first and last activity *inside the window*,
    not the session's actual start and end — a `--days 7` run on a session
    that started three weeks ago reports `first_ts` from seven days ago, the
    earliest row the query is even allowed to see. `turns` and every token
    sum fold in subagent (sidechain) turns alongside main-thread ones; this
    module makes no distinction, matching `turn_norm.is_subagent` being
    ordinary queryable data rather than a filter applied here.

    `limit=None` means unlimited (the CLI maps `--limit 0` to this). The cap
    is applied here, in the query, rather than by truncating the result in
    either renderer — `--json` and the table must always see the identical
    set, the same invariant that keeps `capacity_gauge` a query-level concern
    rather than a rendering one.
    """
    where = "WHERE tn.ts >= ?" if since is not None else ""
    limit_clause = "LIMIT ?" if limit is not None else ""
    params = (since,) if since is not None else ()
    if limit is not None:
        params = (*params, limit)
    rows = conn.execute(
        f"""
        SELECT s.id AS session_row_id, s.harness AS harness, s.title AS title,
               s.cwd AS cwd, s.session_id AS session_id, COUNT(*) AS turns,
               MIN(tn.ts) AS first_ts, MAX(tn.ts) AS last_ts,
               SUM(tn.fresh_input_tokens) AS fresh_input_tokens,
               SUM(tn.cache_read_tokens) AS cache_read_tokens,
               SUM(tn.cache_write_tokens) AS cache_write_tokens,
               SUM(tn.output_tokens) AS output_tokens
        FROM turn_norm tn
        JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        JOIN session s ON s.id = tr.session_row_id
        {where}
        GROUP BY s.id
        ORDER BY last_ts DESC, s.id DESC
        {limit_clause}
        """,
        params,
    ).fetchall()
    result = []
    for row in rows:
        raw = dict(row)
        label = _session_label(raw["title"], raw["cwd"], raw["session_id"])
        result.append(
            {
                "session_row_id": raw["session_row_id"],
                "harness": raw["harness"],
                "label": label,
                "turns": raw["turns"],
                "first_ts": raw["first_ts"],
                "last_ts": raw["last_ts"],
                "fresh_input_tokens": raw["fresh_input_tokens"],
                "cache_read_tokens": raw["cache_read_tokens"],
                "cache_write_tokens": raw["cache_write_tokens"],
                "output_tokens": raw["output_tokens"],
                "session_id": raw["session_id"],
            }
        )
    return result


def capacity_gauge(
    conn: sqlite3.Connection, since: str | None, now: datetime | None = None
) -> dict | None:
    """The most recent Codex capacity reading in the window, expired fields dropped.

    A snapshot, not a sum — see the module docstring for why this is kept
    out of `summary_rows` entirely rather than joined in as extra columns.

    **Expiry is the point of the `now` parameter.** A capacity percentage
    describes a window that rolls, and `resets_at` says when. This view once
    reported `10080m window 96.0%` as of a reading taken six days earlier that
    expired 97 minutes after the run — still literally true when taken, wholly
    misleading when shown. The capacity window here is 10,080 minutes, exactly
    the length of the default `--days 7` summary window, so a reading anywhere
    in range can describe a period with almost no overlap with the present.

    The original docstring anticipated this ("most recent in the window can
    still be days old") and accepted it. That was the wrong call for a value
    that carries its own expiry: an expired gauge is absent, not dimmed.

    Suppressed **per field**, each against its own `resets_at`, rather than
    dropping the whole reading — primary and secondary are independent windows
    (see `usage_store._V3`: neither name reliably means "the short one"), and
    a live secondary should not disappear because an unrelated window rolled.
    Returns `None` only when nothing survives.

    `stale` marks a reading that is old relative to **its own** capacity
    window — more than half of it has elapsed since the sample was taken.

    The plan for this fix said to label a reading that "predates the summary
    window." That case cannot occur: the `since` filter is applied in the
    query, so a reading older than the window is never selected in the first
    place. The real hazard is the one actually observed — a sample taken six
    days into a seven-day window, unexpired and therefore shown, but
    describing usage that has had almost the whole window to move since. That
    is what this measures instead.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    where = "AND tn.ts >= ?" if since is not None else ""
    params = (since,) if since is not None else ()
    # Each field is resolved from its own most-recent non-NULL row, not from
    # one row that happens to carry both. Codex populates `secondary` in only
    # 7.7% of rows, so a single-row query almost always lands on one with a
    # NULL secondary and drops a live secondary reading — the exact outcome
    # this function's per-field rationale says must not happen. `ts` is
    # reported per field for the same reason: the two readings can be minutes
    # or days apart, and one shared "as of" would be wrong for at least one.
    gauge: dict = {}
    epoch_now = now.timestamp()
    for field in ("primary", "secondary"):
        row = conn.execute(
            f"""
            SELECT tn.ts AS ts,
                   tn.capacity_{field}_used_pct AS used_pct,
                   tn.capacity_{field}_window_minutes AS window_minutes,
                   tn.capacity_{field}_resets_at AS resets_at
            FROM turn_norm tn
            JOIN turn_raw tr ON tr.id = tn.turn_raw_id
            JOIN session s ON s.id = tr.session_row_id
            WHERE s.harness = ? AND tn.capacity_{field}_used_pct IS NOT NULL {where}
            ORDER BY tn.ts DESC
            LIMIT 1
            """,
            (CODEX_HARNESS, *params),
        ).fetchone()
        # A reading with no reset time cannot be shown to have expired, so it
        # survives — but it is not given the benefit of looking current
        # either; the renderer says its reset time is unknown.
        expired = (
            row is not None and row["resets_at"] is not None and epoch_now >= row["resets_at"]
        )
        keep = row is not None and not expired
        gauge[f"capacity_{field}_used_pct"] = row["used_pct"] if keep else None
        gauge[f"capacity_{field}_window_minutes"] = row["window_minutes"] if keep else None
        gauge[f"capacity_{field}_resets_at"] = row["resets_at"] if keep else None
        gauge[f"capacity_{field}_ts"] = row["ts"] if keep else None

    if all(gauge[f"capacity_{f}_used_pct"] is None for f in ("primary", "secondary")):
        return None

    # `ts` stays on the payload as the newest surviving reading, for callers
    # (and the existing --json shape) that expect one.
    timestamps = [gauge[f"capacity_{f}_ts"] for f in ("primary", "secondary") if gauge[f"capacity_{f}_ts"]]
    gauge["ts"] = max(timestamps)
    gauge["stale"] = _gauge_is_stale(gauge, now)
    return gauge


def _gauge_is_stale(gauge: dict, now: datetime) -> bool:
    """Is any surviving field more than halfway through its own window?

    Judged per field against that field's own age and window, then ORed —
    "its own window" is what the label claims, and a shared `max` would let a
    300-minute reading sampled four hours ago pass unlabelled because a
    10,080-minute reading beside it is still fresh. `False` when nothing is
    measurable: a claim of staleness needs evidence too.
    """
    for field in ("primary", "secondary"):
        if gauge.get(f"capacity_{field}_used_pct") is None:
            continue
        window = gauge.get(f"capacity_{field}_window_minutes")
        if not isinstance(window, (int, float)) or window <= 0:
            continue
        taken = _parse_ts(gauge.get(f"capacity_{field}_ts") or "")
        if taken is None:
            continue
        if (now - taken).total_seconds() / 60 > window / 2:
            return True
    return False


BUCKET_DAY = "day"
BUCKET_WEEK = "week"


def _bucket_expr(bucket: str, column: str) -> str:
    """SQL projecting a stored UTC timestamp onto a local calendar bucket.

    **Local, not UTC.** Stored timestamps are UTC and every other comparison
    in this module stays UTC, but a bucket is a label on a human day, and
    bucketing this view by UTC splits an evening across two rows for anyone
    west of Greenwich — measured on the corpus this was built against, 7% of
    a week's turns landed on the wrong side of a boundary. A trend meant to
    show whether a working habit is changing has to follow the days the work
    happened in.

    **A week is keyed by its Monday's date, not `%Y-W%W`.** `%W` numbers weeks
    within a calendar year and `%Y` is the calendar year, so the week of Mon
    2026-12-28 splits into `2026-W52` (4 days) and `2027-W00` (3 days), and a
    `--bucket week` run across New Year compares two partial weeks against
    full ones on every volume column. `date(..., '-6 days', 'weekday 1')`
    resolves any day to its own week's Monday, which partitions correctly,
    sorts correctly as text, and reads unambiguously.
    """
    if bucket == BUCKET_DAY:
        return f"date({column}, 'localtime')"
    if bucket == BUCKET_WEEK:
        return f"date({column}, 'localtime', '-6 days', 'weekday 1')"
    raise ValueError(f"unknown bucket {bucket!r}; expected one of {[BUCKET_DAY, BUCKET_WEEK]}")


def coverage_floor(conn: sqlite3.Connection) -> dict:
    """Earliest normalized turn per harness: `{harness: ts}`.

    A trend window reaching before this is showing absence of data, not
    absence of work, and the two are different facts. Derived at read time
    from the store rather than recorded anywhere — the floor moves whenever a
    transcript is pruned from disk or a new harness is harvested, so a stored
    value would be a second thing to keep true.
    """
    rows = conn.execute(
        """
        SELECT s.harness AS harness, MIN(tn.ts) AS first_ts
        FROM turn_norm tn
        JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        JOIN session s ON s.id = tr.session_row_id
        GROUP BY s.harness
        """
    ).fetchall()
    return {row["harness"]: row["first_ts"] for row in rows if row["first_ts"]}


def _median(values: list) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def trend_rows(
    conn: sqlite3.Connection,
    since: str | None,
    bucket: str = BUCKET_DAY,
    harness: str | None = None,
) -> list[dict]:
    """Efficiency per time bucket. One row per `(bucket, harness)`.

    Answers "is my session hygiene actually working," which `summary`,
    `sessions`, and `active` all cannot: they report levels, and this reports
    the shape of the levels over time.

    **One row per bucket AND harness, not per bucket.** Blending them would
    force either dropping the weighted columns or summing token classes whose
    semantics differ across harnesses — Codex's `cached_input_tokens` is a
    subset of its input where Claude's cache buckets are disjoint. Keeping
    them apart is the same reason the store has a normalized layer at all.

    `turns`, `sessions`, and `ctx_per_turn` are **main-agent only**
    (`is_subagent = 0`): a sidechain turn's context is a different
    conversation's size, so averaging it into a per-turn context figure
    measures nothing. `sub_pct` is precisely the subagent counterpart, and
    the weighted totals behind it span both.

    `wt_per_1k_out` is the headline. Raw burn per day conflates working less
    with working leaner; dividing by output normalizes for how busy the
    period was, so the number moves when efficiency moves.

    Weighted columns are Claude-only — `None` for Codex, never 0. See
    `data/token_weights.json`.
    """
    bucket_sql = _bucket_expr(bucket, "tn.ts")
    weights = token_weights()
    weighted = _weighted_tokens_sql(weights)
    filters = ["1 = 1"]
    params: list = []
    if since is not None:
        filters.append("tn.ts >= ?")
        params.append(since)
    if harness is not None:
        filters.append("s.harness = ?")
        params.append(harness)
    where = " AND ".join(filters)

    rows = conn.execute(
        f"""
        SELECT {bucket_sql} AS bucket, s.harness AS harness,
               SUM(CASE WHEN tn.is_subagent = 0 THEN 1 ELSE 0 END) AS turns,
               COUNT(DISTINCT CASE WHEN tn.is_subagent = 0 THEN s.id END) AS sessions,
               SUM(CASE WHEN tn.is_subagent = 0 THEN
                     COALESCE(tn.fresh_input_tokens, 0) + COALESCE(tn.cache_read_tokens, 0)
                     + COALESCE(tn.cache_write_tokens, 0) ELSE 0 END) AS main_ctx,
               SUM(COALESCE(tn.fresh_input_tokens, 0) + COALESCE(tn.cache_read_tokens, 0)
                   + COALESCE(tn.cache_write_tokens, 0)) AS total_input,
               SUM(COALESCE(tn.output_tokens, 0)) AS total_output,
               SUM({weighted}) AS weighted_total,
               SUM(CASE WHEN tn.is_subagent = 1 THEN {weighted} ELSE 0 END) AS weighted_sub
        FROM turn_norm tn
        JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        JOIN session s ON s.id = tr.session_row_id
        WHERE {where}
        GROUP BY bucket, s.harness
        ORDER BY bucket, s.harness
        """,
        params,
    ).fetchall()

    compactions = _compactions_by_bucket(conn, bucket, since)

    # A compaction can fall in a bucket that has no turns — a session that
    # compacts just after midnight and then ends contributes an event to that
    # day and no rows to it. Building buckets from `turn_norm` alone would
    # drop the event silently, which is the exact failure mode this view
    # exists to make visible. Zero occurrences in the corpus today; the union
    # is cheap and the alternative is a loss nothing reports.
    raw_rows = [dict(row) for row in rows]
    present = {(r["bucket"], r["harness"]) for r in raw_rows}
    for bucket_key, harness_key in sorted(compactions.keys() - present):
        if harness is not None and harness_key != harness:
            continue
        raw_rows.append(
            {
                "bucket": bucket_key, "harness": harness_key, "turns": 0, "sessions": 0,
                "main_ctx": 0, "total_input": 0, "total_output": 0,
                "weighted_total": 0, "weighted_sub": 0,
            }
        )
    raw_rows.sort(key=lambda r: (r["bucket"], r["harness"]))

    result = []
    for raw in raw_rows:
        is_claude = raw["harness"] == CLAUDE_HARNESS
        turns = raw["turns"] or 0
        output = raw["total_output"] or 0
        events = compactions.get((raw["bucket"], raw["harness"]), {})
        result.append(
            {
                "bucket": raw["bucket"],
                "harness": raw["harness"],
                "turns": turns,
                "sessions": raw["sessions"] or 0,
                # None rather than 0 for a bucket with only subagent turns:
                # "no main-agent turns to average" is not "zero context".
                "ctx_per_turn": round(raw["main_ctx"] / turns) if turns else None,
                # Input over output. None when nothing was output — a ratio
                # with a zero denominator is undefined, not infinite.
                "in_out": round((raw["total_input"] or 0) / output, 1) if output else None,
                "wt_per_1k_out": (
                    round((raw["weighted_total"] or 0) / output * 1000, 1)
                    if is_claude and output
                    else None
                ),
                "sub_pct": (
                    round((raw["weighted_sub"] or 0) / raw["weighted_total"] * 100, 1)
                    if is_claude and raw["weighted_total"]
                    else None
                ),
                "compact_manual": events.get("manual", 0) if is_claude else None,
                "compact_auto": events.get("auto", 0) if is_claude else None,
                "median_pre_manual": events.get("median_pre_manual") if is_claude else None,
            }
        )
    return result


def _compactions_by_bucket(conn: sqlite3.Connection, bucket: str, since: str | None) -> dict:
    """`compact_boundary` counts per `(bucket, harness)`, split by trigger.

    Split, never summed. `manual` is deliberate hygiene and `auto` is hitting
    the ceiling — opposite signals about a session's health, and one combined
    count would say nothing about either. The median `preTokens` at *manual*
    compaction is the useful companion: it is how full the context typically
    was when the user chose to cut, which is the number that says whether the
    habit is forming early or late.

    Read from `agent_activity_raw` rather than `turn_norm` because a
    compaction reports no tokens of its own and must never reach a token sum.
    """
    bucket_sql = _bucket_expr(bucket, "a.ts")
    where = "AND a.ts >= ?" if since is not None else ""
    params = (since,) if since is not None else ()
    rows = conn.execute(
        f"""
        SELECT {bucket_sql} AS bucket, s.harness AS harness,
               json_extract(a.payload, '$.compactMetadata.trigger') AS trigger,
               json_extract(a.payload, '$.compactMetadata.preTokens') AS pre_tokens
        FROM agent_activity_raw a
        JOIN session s ON s.id = a.session_row_id
        WHERE a.kind = 'compact_boundary' {where}
        """,
        params,
    ).fetchall()

    buckets: dict = {}
    for row in rows:
        key = (row["bucket"], row["harness"])
        entry = buckets.setdefault(key, {"manual": 0, "auto": 0, "_manual_pre": []})
        trigger = row["trigger"]
        if trigger in ("manual", "auto"):
            entry[trigger] += 1
        if trigger == "manual" and isinstance(row["pre_tokens"], int):
            entry["_manual_pre"].append(row["pre_tokens"])
    for entry in buckets.values():
        entry["median_pre_manual"] = _median(entry.pop("_manual_pre"))
    return buckets


def _parse_ts(value: str) -> datetime | None:
    """An aware datetime from a stored ISO8601 string, or None.

    Both `Z` and `+00:00` suffixes occur (collectors write `Z`; `_cutoff`
    writes `+00:00`); `fromisoformat` handles `Z` only from 3.11 — normalize
    rather than assume the interpreter.

    A timestamp carrying no offset at all is assumed UTC rather than returned
    naive. Collectors store the transcript's `timestamp` verbatim, so a record
    without a suffix is data-dependent rather than impossible — and a naive
    result gets subtracted from an aware `now` by two callers, which raises
    `TypeError` and takes down the entire view rather than degrading one row.
    UTC is the assumption the whole store already rests on (see `_cutoff`), so
    stating it here changes no correct case.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


# Where the statusline records each session's exact context window
# (`claude-window-<session_id>`). Module-level so tests can point it at a
# tmpdir instead of coupling to the host's real /tmp — the one place a
# stray real file could otherwise flip a test's expected window.
STATUSLINE_DIR = Path("/tmp")


def _statusline_window(session_id: str, models: dict | None = None) -> int | None:
    """The exact window the statusline recorded for this session, if any.

    The statusline derives it by dividing by an integer percentage, so the
    value carries a few percent of rounding error — hence the snap.
    """
    try:
        recorded = int((STATUSLINE_DIR / f"claude-window-{session_id}").read_text().strip())
    except (OSError, ValueError):
        return None
    return _snap_to_known_window(recorded, models)


def _compaction_window(
    conn: sqlite3.Connection, session_row_id: int, models: dict | None = None
) -> int | None:
    """This session's window, from the largest `preTokens` at an auto compaction.

    An auto compaction fires when the context hits the ceiling, so its
    `preTokens` is a direct observation of how much this session actually
    held — measured from the session's own transcript rather than looked up.
    On the corpus this was built against, 8 of 11 auto compactions read
    1,000,069–1,004,282 (auto fires just *past* the nominal 1M), and the
    remaining 3 read 857K–934K; all eleven snap to 1M.

    Deliberately scoped to one session, never generalized to the model. Every
    model that has auto-compacted here also runs in 200K sessions constantly,
    so a model-scoped rule would mislabel those — the observation says
    something about the session, not about the model.

    `manual` compactions are excluded: a deliberate `/compact` says where the
    user chose to cut, which is unrelated to the ceiling.
    """
    row = conn.execute(
        """
        SELECT MAX(json_extract(payload, '$.compactMetadata.preTokens'))
        FROM agent_activity_raw
        WHERE session_row_id = ? AND kind = 'compact_boundary'
          AND json_extract(payload, '$.compactMetadata.trigger') = 'auto'
        """,
        (session_row_id,),
    ).fetchone()
    observed = row[0] if row is not None else None
    if not isinstance(observed, int) or observed <= 0:
        return None
    return _snap_to_known_window(observed, models)


def _model_window(model: str | None, ctx: int, models: dict | None = None) -> int | None:
    """The window `data/model_context_windows.json` implies for this model.

    `None` for a model the table does not know — the caller suppresses the
    percentage rather than guessing. That blank is also the signal that the
    file needs a new entry.
    """
    entry = _model_entry(model, _model_windows() if models is None else models)
    if not isinstance(entry, dict):
        return None
    window = entry.get("window")
    long_window = entry.get("long_window")
    threshold = entry.get("long_threshold")
    if long_window is not None and threshold is not None and ctx > threshold:
        return long_window
    return window if isinstance(window, int) else None


def _resolve_window(
    conn: sqlite3.Connection,
    session_row_id: int,
    session_id: str,
    model: str | None,
    ctx: int,
    models: dict | None = None,
) -> tuple[int | None, str]:
    """`(window_tokens, source)` for a session's context window.

    `turn_norm.context_window` is NULL for every Claude turn and stays that
    way: that column means "the harness reported this," and filling it with a
    lookup would destroy the measured-versus-inferred distinction the `~`
    marker depends on, and silently change the meaning of historical rows. So
    resolution happens here, at read time, with the source carried alongside
    the number.

    Four sources, best first:

    1. `statusline` — the exact window, recorded by the Claude statusline from
       its own payload. The one signal that identifies a 1M session still
       under 190K context.
    2. `compaction` — `preTokens` at an auto compaction *in this session*. A
       real observation from the transcript, not a lookup.
    3. `model` — the table, with its long-variant threshold. Inferred: a model
       string carries no window suffix, so a 1M session under the threshold
       reads as standard and its percentage is overstated.
    4. `unknown` — the model is not in the table. Window `None`; the caller
       suppresses the percentage rather than guessing.

    **A source is discarded when the live context contradicts it.** The first
    two are point-in-time observations and a session can outgrow them: switch
    to the 1M variant with `/model` after a 200K auto compaction and context
    keeps climbing past the window that observation implied. Without this
    check the view reports `200%` and marks it *measured*, which is worse than
    the inference it displaced — the model source would have self-corrected
    via `long_threshold`. `ctx > window` is proof the observation is stale, so
    it falls through rather than being believed.

    `models` is passed in by callers looping over sessions so the table is
    read once rather than per row.
    """
    if models is None:
        models = _model_windows()

    window = _statusline_window(session_id, models)
    if window is not None and ctx <= window:
        return window, "statusline"
    window = _compaction_window(conn, session_row_id, models)
    if window is not None and ctx <= window:
        return window, "compaction"
    window = _model_window(model, ctx, models)
    if window is not None:
        return window, "model"
    return None, "unknown"


def _recommendation(carry_pct: float, action: str) -> str:
    if carry_pct >= CARRY_NOW_PCT:
        return f"/{action} now"
    if carry_pct >= CARRY_NEXT_BREAK_PCT:
        return f"/{action} at next break"
    return "fine"


def active_rows(
    conn: sqlite3.Connection,
    within_minutes: int = DEFAULT_ACTIVE_WITHIN_MINUTES,
    now: datetime | None = None,
) -> list[dict]:
    """Per-active-session context status, worst carry first.

    Supersedes `token-report --active`, store-backed instead of re-parsing
    transcripts. Semantics carried over with three deliberate divergences,
    all documented in the run plan: liveness/idle come from the latest
    main-thread turn's `ts` rather than transcript file mtime (misses a
    session where the user typed but no assistant turn landed yet — bounded
    by one turn); a session is one row here even when its subagent files
    would have surfaced as separate rows there; and a session whose only
    *recent* turns carry zero context (synthetic/empty-usage records) drops
    out of the view rather than showing its last known context — no context
    sample inside the window means no current context to report.

    Carry is measured from the session's first-ever context sample, matching
    token-report exactly — which means an already-/compact-ed session
    understates carry (the base predates the compact) and can even read
    negative right after one. Inherited deliberately rather than fixed;
    basing the floor on the minimum observed ctx is the known alternative if
    this ever misleads in practice.

    Context math is main-thread only (`is_subagent = 0`) on purpose: a
    sidechain turn's context is a different conversation's size, and the
    store interleaves them where token-report's per-file read never did.
    Rows with zero context are skipped, matching `_usage_ctx`'s `if not
    ctx` — a synthetic or empty-usage turn is not a context sample.

    `now` is injectable for deterministic tests; production callers omit it.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=within_minutes)).isoformat()

    weights = token_weights()
    # Read once, not per session: `_data_file` is deliberately uncached, and
    # `--within` is unbounded, so a wide window would otherwise reopen this
    # file once per row.
    models = _model_windows()
    sessions = conn.execute(
        f"""
        SELECT s.id AS session_row_id, s.session_id AS session_id,
               s.title AS title, s.cwd AS cwd, MAX(tn.ts) AS last_ts
        FROM turn_norm tn
        JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        JOIN session s ON s.id = tr.session_row_id
        WHERE s.harness = ? AND tn.is_subagent = 0 AND tn.ts >= ?
          AND COALESCE(tn.fresh_input_tokens, 0) + COALESCE(tn.cache_read_tokens, 0)
              + COALESCE(tn.cache_write_tokens, 0) > 0
        GROUP BY s.id
        """,
        (CLAUDE_HARNESS, cutoff),
    ).fetchall()

    result = []
    for sess in sessions:
        raw = dict(sess)
        # The two newest and the single oldest context samples for this
        # session: newest = current context and the gap to its predecessor;
        # oldest = the session's starting context, for carry.
        recent = conn.execute(
            """
            SELECT COALESCE(tn.fresh_input_tokens, 0) + COALESCE(tn.cache_read_tokens, 0)
                   + COALESCE(tn.cache_write_tokens, 0) AS ctx,
                   tn.ts AS ts
            FROM turn_norm tn
            JOIN turn_raw tr ON tr.id = tn.turn_raw_id
            WHERE tr.session_row_id = ? AND tn.is_subagent = 0
              AND COALESCE(tn.fresh_input_tokens, 0) + COALESCE(tn.cache_read_tokens, 0)
                  + COALESCE(tn.cache_write_tokens, 0) > 0
            ORDER BY tn.ts DESC, tr.id DESC LIMIT 2
            """,
            (raw["session_row_id"],),
        ).fetchall()
        first = conn.execute(
            """
            SELECT COALESCE(tn.fresh_input_tokens, 0) + COALESCE(tn.cache_read_tokens, 0)
                   + COALESCE(tn.cache_write_tokens, 0) AS ctx
            FROM turn_norm tn
            JOIN turn_raw tr ON tr.id = tn.turn_raw_id
            WHERE tr.session_row_id = ? AND tn.is_subagent = 0
              AND COALESCE(tn.fresh_input_tokens, 0) + COALESCE(tn.cache_read_tokens, 0)
                  + COALESCE(tn.cache_write_tokens, 0) > 0
            ORDER BY tn.ts ASC, tr.id ASC LIMIT 1
            """,
            (raw["session_row_id"],),
        ).fetchone()
        if not recent or first is None:
            continue

        ctx = recent[0]["ctx"]
        base_ctx = first["ctx"]
        carry = ctx - base_ctx

        gap = 0
        if len(recent) == 2:
            newer, older = _parse_ts(recent[0]["ts"]), _parse_ts(recent[1]["ts"])
            if newer and older:
                gap = max(0, int((newer - older).total_seconds()))

        model = conn.execute(
            "SELECT tn.model FROM turn_norm tn JOIN turn_raw tr ON tr.id = tn.turn_raw_id"
            " WHERE tr.session_row_id = ? AND tn.is_subagent = 0 AND tn.model IS NOT NULL"
            " ORDER BY tn.ts DESC LIMIT 1",
            (raw["session_row_id"],),
        ).fetchone()
        window, window_source = _resolve_window(
            conn,
            raw["session_row_id"],
            raw["session_id"],
            model[0] if model else None,
            ctx,
            models,
        )
        last = _parse_ts(raw["last_ts"])
        # None (not 0) when the timestamp is unparseable: 0 would render as
        # "0s" — the most attention-grabbing state — for a session of
        # genuinely unknown age.
        idle_sec = max(0, int((now - last).total_seconds())) if last else None
        action = "clear" if gap >= TOPIC_GAP_SEC else "compact"
        # An unknown window suppresses both percentages rather than guessing.
        # The recommendation goes with them: every threshold it grades against
        # is a percentage of the window, so with no window there is no
        # judgment to render — and "fine" for an unmeasurable session would be
        # a confident answer to a question that was never computed.
        carry_pct = carry / window * 100 if window else None

        result.append(
            {
                "id": raw["session_id"][:8],
                "label": _session_label(raw["title"], raw["cwd"], raw["session_id"]),
                "ctx_pct": round(ctx / window * 100, 1) if window else None,
                "carry_pct": round(carry_pct, 1) if carry_pct is not None else None,
                # Kept as the renderer's `~` gate, now derived from the source
                # rather than tracked separately: statusline and compaction are
                # both real observations, the model table is a lookup.
                "window_exact": window_source in ("statusline", "compaction"),
                "window_source": window_source,
                "sub_pct": _subagent_share(conn, raw["session_row_id"], weights),
                "idle_sec": idle_sec,
                "recommend": _recommendation(carry_pct, action) if carry_pct is not None else None,
                "session_id": raw["session_id"],
            }
        )
    # Unknown-window sessions sort last rather than first: `-carry_pct` on a
    # None would raise, and a session whose carry could not be computed is not
    # evidence of a problem.
    result.sort(key=lambda r: (r["carry_pct"] is None, -(r["carry_pct"] or 0), r["session_id"]))
    return result


def _weighted_tokens_sql(weights: dict, prefix: str = "tn.") -> str:
    """SQL summing one row's input classes into weighted tokens.

    Collapses the classes by billing multiplier so periods of different shapes
    are comparable. The write component prefers the TTL split and falls back to
    whatever part of the write total the split does not account for — which is
    the whole write for a row harvested before `usage.cache_creation` existed,
    and exactly zero for every row after the schema v5 backfill, since the
    halves sum to the total.

    Claude only. See `data/token_weights.json` for why applying these to Codex
    would be arithmetic without meaning.
    """
    w = weights
    return (
        f"COALESCE({prefix}fresh_input_tokens, 0) * {w['uncached_input']}"
        f" + COALESCE({prefix}cache_read_tokens, 0) * {w['cache_read']}"
        f" + COALESCE({prefix}cache_write_1h_tokens, 0) * {w['cache_write_1h']}"
        f" + COALESCE({prefix}cache_write_5m_tokens, 0) * {w['cache_write_5m']}"
        f" + MAX(0, COALESCE({prefix}cache_write_tokens, 0)"
        f"         - COALESCE({prefix}cache_write_1h_tokens, 0)"
        f"         - COALESCE({prefix}cache_write_5m_tokens, 0)) * {w['cache_write_unsplit']}"
    )


def _subagent_share(conn: sqlite3.Connection, session_row_id: int, weights: dict) -> float | None:
    """Subagent share of this session's weighted tokens, as a percentage.

    `carry` and `ctx` measure the main thread's window only, so a session that
    moves work into subagents looks like it improved. Subagent share moved
    4.8% → 12.9% over a window in which main-agent context fell 41% — part of
    that apparent improvement was work relocating rather than disappearing.
    A metric that improves when work is *moved* eventually gets optimized the
    wrong way, and the fix is to show both numbers side by side.

    Subagent turns carry the parent's own `sessionId`, so attribution needs no
    identity work beyond the flag already on the row. `None` when the session
    has no weighted tokens at all, rather than 0 — a share of nothing is not
    a share of zero.
    """
    weighted = _weighted_tokens_sql(weights)
    row = conn.execute(
        f"""
        SELECT SUM(CASE WHEN tn.is_subagent = 1 THEN {weighted} ELSE 0 END) AS sub,
               SUM({weighted}) AS total
        FROM turn_norm tn
        JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        WHERE tr.session_row_id = ?
        """,
        (session_row_id,),
    ).fetchone()
    if row is None or not row["total"]:
        return None
    return round(row["sub"] / row["total"] * 100, 1)


def _fmt_cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def render_table(rows: list[dict]) -> str:
    """Aligned, whitespace-separated columns — the default rendering for either view."""
    if not rows:
        return "(no data in range)"
    headers = list(rows[0].keys())
    str_rows = [[_fmt_cell(row.get(h)) for h in headers] for row in rows]
    widths = [
        max(len(h), *(len(r[i]) for r in str_rows)) for i, h in enumerate(headers)
    ]
    lines = ["  ".join(h.upper().ljust(widths[i]) for i, h in enumerate(headers))]
    for r in str_rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)))
    return "\n".join(lines)


def render_json(payload) -> str:
    """The same structured result, serialized instead of aligned.

    Generic on purpose — a plain `json.dumps`, not a shape-specific
    renderer. Both CLI wrappers pass a `{"rows": [...]}` dict (`summary`
    adds a sibling `"capacity"` key when present), but nothing here assumes
    that shape.
    """
    return json.dumps(payload, indent=2)


def _render_gauge_field(used_pct: float, window_minutes: int | None) -> str:
    # Labeled by the window size actually stored, not by "primary"/
    # "secondary" — those names don't reliably mean "the short window" and
    # "the long window" (see the module docstring), so the only honest label
    # is the number SQLite actually has.
    window = f"{window_minutes}m window" if window_minutes is not None else "window size unknown"
    return f"{window} {used_pct:.1f}%"


def _fmt_epoch(value) -> str:
    """A stored `resets_at` epoch as a readable UTC timestamp."""
    try:
        return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError, OverflowError):
        return "unknown"


def _render_gauge_line(gauge: dict) -> str:
    """The gauge with both timestamps it needs to be believable.

    `as of` alone was the defect: it says how old the reading is but not
    whether it still describes anything. `resets at` is the field that
    answers that, and it was stored all along and never shown. Expired
    fields never reach here — `capacity_gauge` drops them.
    """
    parts = []
    for field in ("primary", "secondary"):
        used = gauge.get(f"capacity_{field}_used_pct")
        if used is None:
            continue
        rendered = _render_gauge_field(used, gauge.get(f"capacity_{field}_window_minutes"))
        parts.append(f"{rendered} (resets at {_fmt_epoch(gauge.get(f'capacity_{field}_resets_at'))})")
    line = f"codex capacity (as of {gauge['ts']}): " + ", ".join(parts)
    if gauge.get("stale"):
        # Real and unexpired, but sampled long enough ago that usage has had
        # most of the window to move since. Saying so beats letting a six-day-
        # old sample of a seven-day window read as a current measurement.
        line += (
            "\n  note: sampled more than halfway through its own window — still valid,"
            " but usage may have moved since"
        )
    return line


def cost_summary_command(days: int = DEFAULT_WINDOW_DAYS, show_all: bool = False, as_json: bool = False) -> int:
    """CLI entry point for `flow cost summary`."""
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    since = None if show_all else _cutoff(days)

    conn = sqlite3.connect(store)
    conn.row_factory = sqlite3.Row
    try:
        rows = summary_rows(conn, since)
        gauge = capacity_gauge(conn, since)
        freshness = telemetry_freshness.usage_freshness(conn)
    finally:
        conn.close()

    if as_json:
        payload = {"rows": rows, "freshness": freshness}
        if gauge is not None:
            payload["capacity"] = gauge
        print(render_json(payload))
    else:
        print(render_table(rows))
        if gauge is not None:
            print()
            print(_render_gauge_line(gauge))
        notes = telemetry_freshness.freshness_notes(freshness, read_only=True)
        if notes:
            print()
            print("\n".join(notes))

    return 0


def cost_sessions_command(
    days: int = DEFAULT_WINDOW_DAYS,
    show_all: bool = False,
    as_json: bool = False,
    limit: int = DEFAULT_SESSIONS_LIMIT,
) -> int:
    """CLI entry point for `flow cost sessions`. `limit=0` means unlimited.

    Negative limits also map to unlimited rather than reaching SQLite, where
    `LIMIT -1` already silently means unlimited — mapping here makes that
    behavior deliberate and documented instead of an accident of the engine.
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    since = None if show_all else _cutoff(days)
    row_limit = None if limit <= 0 else limit

    conn = sqlite3.connect(store)
    conn.row_factory = sqlite3.Row
    try:
        rows = sessions_rows(conn, since, row_limit)
        freshness = telemetry_freshness.usage_freshness(conn)
    finally:
        conn.close()

    # Same envelope as `cost summary`'s --json — {"rows": [...]}, so a caller
    # never needs to know which subcommand produced a payload before reading
    # payload["rows"] out of it.
    if as_json:
        print(render_json({"rows": rows, "freshness": freshness}))
    else:
        print(render_table(rows))
        notes = telemetry_freshness.freshness_notes(freshness, read_only=True)
        if notes:
            print()
            print("\n".join(notes))
    return 0


def _coverage_notes(floor: dict, since: str | None, harness: str | None) -> list[str]:
    """One note per harness whose data starts after the window does.

    A window reaching before coverage shows absence of data, not absence of
    work. Labelled rather than silently truncated: truncating would make the
    earliest visible bucket look like the beginning of the record, which is
    the one reading that turns a coverage gap into a false trend.
    """
    if since is None:
        return []
    notes = []
    for name in sorted(floor):
        if harness is not None and name != harness:
            continue
        if floor[name] > since:
            notes.append(
                f"{name} coverage begins {floor[name][:10]} — this window reaches"
                f" back to {since[:10]}, and the buckets before that first date are"
                " absent from the store, not empty."
            )
    return notes


def _render_trend_table(rows: list[dict], notes: list[str]) -> str:
    if not rows:
        body = "(no data in range)"
    else:
        display = []
        for r in rows:
            display.append(
                {
                    "bucket": r["bucket"],
                    "harness": r["harness"],
                    "turns": r["turns"],
                    "sessions": r["sessions"],
                    "ctx/turn": "" if r["ctx_per_turn"] is None else f"{r['ctx_per_turn']:,}",
                    "in:out": "" if r["in_out"] is None else f"{r['in_out']:.1f}:1",
                    "wt/1k out": "" if r["wt_per_1k_out"] is None else f"{r['wt_per_1k_out']:,.0f}",
                    "sub%": "" if r["sub_pct"] is None else f"{r['sub_pct']:.1f}%",
                    "cmpct man": "" if r["compact_manual"] is None else r["compact_manual"],
                    "cmpct auto": "" if r["compact_auto"] is None else r["compact_auto"],
                    "med pre man": (
                        "" if not r["median_pre_manual"] else f"{r['median_pre_manual']:,.0f}"
                    ),
                }
            )
        body = render_table(display)
    if any(r["wt_per_1k_out"] is None and r["harness"] != CLAUDE_HARNESS for r in rows):
        notes = notes + [
            "wt/1k out and sub% are blank for codex: the weights are Anthropic cache"
            " multipliers, and codex reports no cache writes and a different cache-read"
            " semantics, so the same arithmetic would not mean the same thing."
        ]
    return body + ("\n\n" + "\n\n".join(notes) if notes else "")


def cost_trend_command(
    days: int = DEFAULT_WINDOW_DAYS,
    show_all: bool = False,
    bucket: str = BUCKET_DAY,
    harness: str | None = None,
    as_json: bool = False,
) -> int:
    """CLI entry point for `flow cost trend`.

    Read-only, like `summary` and `sessions` — it answers from whatever the
    store holds. Unlike `active`, it does not harvest first: a trend over
    completed periods does not become wrong for want of the last few minutes,
    and paying a harvest to render history would be the wrong trade.
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    since = None if show_all else _cutoff(days)

    conn = sqlite3.connect(store)
    conn.row_factory = sqlite3.Row
    try:
        rows = trend_rows(conn, since, bucket=bucket, harness=harness)
        floor = coverage_floor(conn)
        freshness = telemetry_freshness.usage_freshness(conn)
    finally:
        conn.close()

    notes = _coverage_notes(floor, since, harness) + telemetry_freshness.freshness_notes(
        freshness, read_only=True
    )
    if as_json:
        # `coverage` rides alongside `rows` rather than being folded into
        # them: it is a property of the store, not of any bucket, and a
        # caller checking whether its window was fully covered should not
        # have to infer that from which rows happen to be present.
        print(render_json({"rows": rows, "coverage": floor, "freshness": freshness}))
    else:
        print(_render_trend_table(rows, notes))
    return 0


def _fmt_idle(idle_sec: int | None) -> str:
    if idle_sec is None:
        return "?"
    if idle_sec >= 3600:
        return f"{idle_sec // 3600}h{(idle_sec % 3600) // 60}m"
    if idle_sec >= 60:
        return f"{idle_sec // 60}m"
    return f"{idle_sec}s"


def _render_active_table(rows: list[dict]) -> str:
    """`active`'s table needs formatting the generic renderer can't do:
    percentage suffixes, the `~` inferred-window marker fused to the ctx
    figure, and idle rendered as `2h5m`/`35m`/`12s` (`?` when the latest
    turn's timestamp couldn't be parsed). The JSON path still gets the raw
    structured values — the formatting below is display-only.
    """
    if not rows:
        return "(no active sessions in range)"
    display = []
    for r in rows:
        marker = "" if r["window_exact"] else "~"
        unknown = r["ctx_pct"] is None
        display.append(
            {
                "id": r["id"],
                "session": r["label"][:39] + "…" if len(r["label"]) > 40 else r["label"],
                # "?" rather than a blank: a blank cell reads as zero at a
                # glance, and this is the opposite claim — the number was not
                # computable, not small.
                "ctx": "?" if unknown else f"{marker}{r['ctx_pct']:.0f}%",
                "carry": "?" if r["carry_pct"] is None else f"{r['carry_pct']:.0f}%",
                "sub": "" if r["sub_pct"] is None else f"{r['sub_pct']:.0f}%",
                "idle": _fmt_idle(r["idle_sec"]),
                "recommend": r["recommend"] or "window unknown",
            }
        )
    out = render_table(display)
    notes = []
    if any(r["window_source"] == "model" for r in rows):
        notes.append(
            f"~ = context window inferred from the model, not measured: a session under"
            f" {LONG_THRESHOLD // 1000}K context is assumed to be on the"
            f" {STD_WINDOW // 1000}K window, which overstates percentages if"
            " it is actually running the 1M variant."
        )
    if any(r["window_source"] == "unknown" for r in rows):
        notes.append(
            "? = this model is not in data/model_context_windows.json, so there is"
            " no window to measure against. Percentages are suppressed rather than"
            " guessed; add the model to that file to resolve it."
        )
    if any(r["sub_pct"] for r in rows):
        notes.append(
            "sub = subagent share of the session's weighted tokens. ctx and carry"
            " measure the main thread only, so work moved into subagents leaves"
            " them looking better without costing less."
        )
    return out + ("\n\n" + "\n\n".join(notes) if notes else "")


def cost_active_command(
    within: int = DEFAULT_ACTIVE_WITHIN_MINUTES, as_json: bool = False
) -> int:
    """CLI entry point for `flow cost active`.

    Harvest-and-normalize first: runs the incremental Claude harvest AND a
    normalize pass before querying, so the answer reflects the transcripts
    as they are right now rather than as of whenever those last happened to
    run. The normalize step is not optional — `active_rows` reads
    `turn_norm`, and a freshly harvested turn exists only in `turn_raw`
    until normalization projects it; skipping it would silently report the
    state as of the previous normalize, defeating the harvest-first point.
    Quiet on success — this is a status view, not a pipeline report. A
    file's hard stop or a row's normalize failure is reported in one line
    but never aborts the view: a status command must not die because one
    transcript has a bad line; it renders whatever the store has.
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    conn = sqlite3.connect(store)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    try:
        sessions_root = claude_sessions_root(HOME)
        if sessions_root.is_dir():
            summary = claude_harvest_all(conn, sessions_root)
            for failure in summary["failures"]:
                line = failure["line"]
                where = f":{line}" if line is not None else ""
                print(f"note: skipped {failure['path']}{where} — {failure['reason']}")
        codex_root = codex_sessions_root(HOME)
        if codex_root.is_dir():
            summary = codex_harvest_all(conn, codex_root)
            for failure in summary["failures"]:
                line = failure["line"]
                where = f":{line}" if line is not None else ""
                print(f"note: skipped {failure['path']}{where} — {failure['reason']}")
        norm_result = normalize_all(conn)
        for failure in norm_result["failures"]:
            print(f"note: could not normalize turn_raw id {failure['turn_raw_id']} — {failure['reason']}")
        rows = active_rows(conn, within)
        freshness = telemetry_freshness.usage_freshness(conn)
    finally:
        conn.close()

    if as_json:
        print(render_json({"rows": rows, "freshness": freshness}))
    else:
        print(_render_active_table(rows))
        notes = telemetry_freshness.freshness_notes(freshness, read_only=False)
        if notes:
            print()
            print("\n".join(notes))
    return 0


def _harness_for_transcript(path: Path) -> str:
    """Which harness owns this transcript, from its path.

    `/.codex/` vs anything else (Claude transcripts live under
    `~/.claude/projects/`, but a copied or symlinked path should still
    default to Claude rather than fail — Claude is the richer contract and
    the only wrong-guess consequence is a harvest that skips every line).
    """
    return CODEX_HARNESS if "/.codex/" in str(path) else CLAUDE_HARNESS


def _session_context_samples(conn: sqlite3.Connection, session_row_id: int) -> tuple[list, dict | None, int]:
    """(newest-two samples, oldest sample, main-thread turn count) for one session.

    The same three queries `active_rows` runs per session, shared by the
    verdict engine. Zero-context rows are skipped and sidechain turns are
    excluded for the same reasons documented there.
    """
    ctx_expr = (
        "COALESCE(tn.fresh_input_tokens, 0) + COALESCE(tn.cache_read_tokens, 0)"
        " + COALESCE(tn.cache_write_tokens, 0)"
    )
    recent = conn.execute(
        f"""
        SELECT {ctx_expr} AS ctx, tn.ts AS ts
        FROM turn_norm tn JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        WHERE tr.session_row_id = ? AND tn.is_subagent = 0 AND {ctx_expr} > 0
        ORDER BY tn.ts DESC, tr.id DESC LIMIT 2
        """,
        (session_row_id,),
    ).fetchall()
    first = conn.execute(
        f"""
        SELECT {ctx_expr} AS ctx
        FROM turn_norm tn JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        WHERE tr.session_row_id = ? AND tn.is_subagent = 0 AND {ctx_expr} > 0
        ORDER BY tn.ts ASC, tr.id ASC LIMIT 1
        """,
        (session_row_id,),
    ).fetchone()
    requests = conn.execute(
        "SELECT COUNT(*) FROM turn_norm tn JOIN turn_raw tr ON tr.id = tn.turn_raw_id"
        " WHERE tr.session_row_id = ? AND tn.is_subagent = 0",
        (session_row_id,),
    ).fetchone()[0]
    return [dict(r) for r in recent], (dict(first) if first is not None else None), requests


def verdict_for_transcript(conn: sqlite3.Connection, transcript: Path, session_id: str | None = None) -> dict | None:
    """Live judgment for one transcript: should this session /clear or /compact now?

    Supersedes `token-report --verdict`. Store-backed: incrementally
    harvests just this file, normalizes, then judges from `turn_norm` —
    the per-Stop cost is one watermark check plus whatever lines the turn
    just appended. Thresholds and semantics carried over verbatim:
    absolute carry floor (the true window is only known to the statusline,
    which grades severity itself from the raw numbers), minimum request
    count, and the idle gap before the latest turn as the only live signal
    that distinguishes /clear (came back to new work) from /compact (same
    work, heavy context).

    Returns None when there is nothing to say — below the floor, too
    young, or the session can't be resolved. `session_id` (from the hook's
    stdin JSON) is the primary session key when provided; the transcript
    path is the fallback for manual invocations.

    Codex limitation, documented not hidden: same math, but Codex has no
    statusline consuming these numbers, so nothing downstream grades carry
    against a real window — the warn hook applies the window-agnostic
    absolute thresholds instead.
    """
    harness = _harness_for_transcript(transcript)
    harvest = claude_harvest_file if harness == CLAUDE_HARNESS else codex_harvest_file
    try:
        harvest(conn, transcript)
    except OSError:
        return None
    normalize_all(conn)

    session_row_id = None
    if session_id:
        row = conn.execute(
            "SELECT id FROM session WHERE harness = ? AND session_id = ?", (harness, session_id)
        ).fetchone()
        session_row_id = row[0] if row else None
    if session_row_id is None:
        session_row_id = lookup_session_for_path(conn, harness, transcript)
    if session_row_id is None:
        return None

    recent, first, requests = _session_context_samples(conn, session_row_id)
    if not recent or first is None:
        return None

    ctx = recent[0]["ctx"]
    carry = ctx - first["ctx"]

    gap = 0
    if len(recent) == 2:
        newer, older = _parse_ts(recent[0]["ts"]), _parse_ts(recent[1]["ts"])
        if newer and older:
            gap = max(0, int((newer - older).total_seconds()))

    if carry < VERDICT_FLOOR or requests < VERDICT_MIN_REQUESTS:
        return None

    if gap >= TOPIC_GAP_SEC:
        action, why = "clear", f"idle {gap // 60}m"
    else:
        action, why = "compact", ""  # the carry number already says it

    return {"harness": harness, "action": action, "carry": carry, "ctx": ctx, "why": why}


def _verdict_path(harness: str, session_id: str) -> Path:
    return VERDICT_DIR / f"{harness}-verdict-{session_id}"


def _run_verdict_hook() -> int:
    """The whole `--hook` body, guarded in one place by its caller.

    Anything here may raise (a locked store past busy_timeout, a full
    disk, the half-applied-migration state `ensure_store` refuses) — the
    caller converts every failure to exit 0, because an advisory hook
    erroring on every Stop of every session is the loudest possible
    failure of a feature whose premise is silence.
    """
    payload = _read_hook_stdin()
    if payload is None:
        return 0
    sid = payload.get("session_id")
    tpath = payload.get("transcript_path")
    if not _safe_session_id(sid) or not tpath or not Path(tpath).is_file():
        return 0

    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    conn = sqlite3.connect(store)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    try:
        v = verdict_for_transcript(conn, Path(tpath), session_id=sid)
    finally:
        conn.close()

    harness = _harness_for_transcript(Path(tpath))
    out = _verdict_path(harness, sid)
    if v is not None:
        # Atomic replace: the statusline reads this file on its own
        # schedule and must never observe a truncated half-write.
        import os

        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(f"/{v['action']}?\t{v['carry']}\t{v['ctx']}\t{v['why']}\n")
        os.replace(tmp, out)
    else:
        # Below threshold or freshly cleared: remove the file so the
        # statusline field (and any pending warning) disappears — and the
        # warn hook's high-water marker with it, or a /compact that drops
        # carry would leave re-warning suppressed until carry exceeded the
        # PRE-compact high plus a step, giving the heaviest sessions the
        # least warning.
        out.unlink(missing_ok=True)
        (VERDICT_DIR / f"{harness}-warned-{sid}").unlink(missing_ok=True)
    return 0


def cost_verdict_command(transcript: str | None = None, hook: bool = False) -> int:
    """CLI entry point for `flow cost verdict`.

    Two modes:
    - `--hook`: read the runtime's hook JSON from stdin (both harnesses
      send `session_id` + `transcript_path`), compute, and write/remove
      the verdict file. Prints NOTHING on purpose — Stop-hook stdout is
      fed back into the conversation on both runtimes, which would mean
      spending tokens to say you are spending too many; the statusline
      and the warn hook read the file for free. Exits 0 unconditionally,
      including on internal errors (breadcrumbed to
      ~/.flow/logs/hook-errors.log): a broken verdict must never block a
      Stop, and exit code 2 actively would.
    - `--transcript PATH`: compute and print the same line
      `token-report --verdict` printed (`/{action}?\\t{carry}\\t{ctx}\\t{why}`,
      raw token counts — the statusline grades them against the window it
      alone knows). Manual/debug surface; silence when nothing to say.
    """
    if hook:
        try:
            return _run_verdict_hook()
        except Exception as exc:
            # The verdict file is left as-is on an internal error rather
            # than removed — stale beats flapping.
            _log_hook_error("verdict", exc)
            return 0

    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    if not transcript:
        print("usage: flow cost verdict --transcript PATH | --hook")
        return 1

    conn = sqlite3.connect(store)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.row_factory = sqlite3.Row
    try:
        v = verdict_for_transcript(conn, Path(transcript))
    finally:
        conn.close()

    if v is not None:
        print(f"/{v['action']}?\t{v['carry']}\t{v['ctx']}\t{v['why']}")
    return 0


def cost_warn_command() -> int:
    """CLI entry point for `flow cost warn --hook` (UserPromptSubmit, both harnesses).

    The pre-execution warning: reads the verdict file the Stop hook last
    wrote — zero computation at prompt time — and, when carry is heavy on
    ANY window (>= WARN_CARRY_FLOOR) prints one line, which the runtime
    injects as context so both the model and the user see it before the
    next expensive turn. Throttled: re-warns only after carry grows
    another WARN_REWARN_STEP since the last warning (marker file beside
    the verdict), because a warning on every prompt is noise that costs
    context tokens each time it fires. Always exits 0 and prints nothing
    in every other case — including any internal error — because blocking
    or polluting a prompt over advisory telemetry would invert the
    feature's whole point.
    """
    try:
        payload = _read_hook_stdin()
        if payload is None:
            return 0
        sid = payload.get("session_id")
        tpath = payload.get("transcript_path")
        # Missing transcript_path = bail, matching the verdict command
        # exactly — guessing a harness here would silently read a verdict
        # file the other harness never writes, making the warn a permanent
        # no-op with no signal.
        if not _safe_session_id(sid) or not tpath:
            return 0

        harness = _harness_for_transcript(Path(tpath))
        verdict_file = _verdict_path(harness, sid)
        try:
            parts = verdict_file.read_text().strip().split("\t")
            carry = int(parts[1])
        except (OSError, ValueError, IndexError):
            return 0
        if carry < WARN_CARRY_FLOOR:
            return 0

        marker = VERDICT_DIR / f"{harness}-warned-{sid}"
        try:
            last_warned = int(marker.read_text().strip())
        except (OSError, ValueError):
            last_warned = 0
        if carry < last_warned + WARN_REWARN_STEP:
            return 0

        action = parts[0].strip("/?") or "compact"
        print(
            f"flow advisory: this session is carrying ~{carry // 1000}K tokens above its start, "
            f"re-sent on every request. /{action} at the next natural break would cut per-request cost. "
            "(Informational only — continue if the thread is still earning its context.)"
        )
        try:
            marker.write_text(str(carry))
        except OSError:
            pass
        return 0
    except Exception as exc:
        _log_hook_error("warn", exc)
        return 0
