"""`flow cost baseline`: the always-on token floor, and when it moved.

Every session pays a static prefix before any work happens — system prompt,
tool definitions, MCP server instructions, agent and skill descriptions,
`CLAUDE.md`, memory files. Nothing else in `flow cost` reports it, because
every other surface measures what a session *spent*, and this measures what
it *started at*. The distinction matters: a session that burns little can
still be expensive to open, and enabling a plugin raises that opening cost
permanently and invisibly.

The estimator is `cache_read_tokens` on a session's first turn. On a first
turn there is no conversation yet, so that number is the cached static
prefix and nothing else — it excludes the user's opening message and any
SessionStart hook output, both of which land in `fresh_input_tokens`. The
obvious alternative, `fresh + cache_read + cache_write`, is available on
more sessions but reads high for exactly that reason, so it is not used.

`cache_read_tokens = 0` on a first turn means *cache miss*, not *new
conversation*. Anthropic's prompt cache is keyed by prefix hash across the
account, not per session, so a genuinely new session started soon after
another with the same prefix reads the whole thing from cache. Those
sessions are the good population here; cache misses are the ones that carry
no reading and are excluded.

Read-only by contract. This module never writes to `turn_raw`, `turn_norm`,
`session`, or `agent_activity_raw`, and it adds no schema. Everything it
needs already exists, which is what keeps it off the `verdict`/`warn` hook
paths entirely — nothing here can regress a live hook.

Nothing in `cost.py` imports from this module. The dependency runs one way,
so a change here cannot reach the surfaces that already ship.
"""

import sqlite3
from datetime import date, timedelta

import usage_store
import telemetry_freshness
from cost import DEFAULT_WINDOW_DAYS, _bucket_expr, _cutoff, _data_file, render_json
from paths import HOME, SOURCE_DIR

HARNESSES = ("claude", "codex")

# Fallbacks for every tunable, used when `data/baseline_thresholds.json` is
# missing or unreadable. Same reasoning as `token_weights`: a number computed
# from a shipped default is still comparable across buckets, which is the
# point of the surface, whereas a crashed command reports nothing at all.
DEFAULT_THRESHOLDS = {
    "min_pct": 0.15,
    "min_abs": 2500,
    "min_n": 5,
    "line_threshold": 20,
}

# The quantile the floor is reported at. Low on purpose, and lower than it
# first looks like it needs to be.
#
# Prefix readings are not a distribution — they are a handful of exact,
# repeated plateaus, because the prompt cache returns the same number for
# every session sharing a prefix. One measured week had all 13 of its
# sessions read exactly 22,489; another had all 41 read exactly 21,830.
#
# That breaks any mid-range quantile. When two configurations coexist in a
# week, p25 lands wherever the *mix* between the plateaus falls, and it
# jumps discontinuously when the mix shifts rather than when the floor
# does. On the real corpus p25 manufactured a +35% spike and a -28% return
# across two weeks in which no configuration changed at all; the underlying
# weeks read 22,489 / 22,595 / 21,830.
#
# At p10 the same series is flat, and p10 is identical to the minimum in
# every measured week — the plateaus repeat, so nothing sits below the
# lowest one. It is also the semantically right statistic: the floor is the
# leanest prefix a session actually started from, not a typical one.
#
# p10 rather than a bare `min` to absorb a single freak low reading — but
# only where the sample is large enough for the two to differ. At nearest
# rank `ceil(0.10 * n) == 1` for every n up to 10, so in any bucket at or
# below ten sessions p10 *is* the minimum and offers no protection at all.
# Worth stating rather than implying: the guard arrives only with volume.
FLOOR_QUANTILE = 0.10

COMPACT_BOUNDARY_KIND = "compact_boundary"


def thresholds() -> dict:
    """Calibration parameters, from `data/baseline_thresholds.json`.

    Per-key fallback rather than all-or-nothing: a file that has drifted and
    lost one key still yields a usable surface for the others.
    """
    data = _data_file("baseline_thresholds.json")
    resolved = dict(DEFAULT_THRESHOLDS)
    for key in DEFAULT_THRESHOLDS:
        value = data.get(key)
        # Strictly positive, and `bool` rejected explicitly because it is an
        # `int` subclass. Zero is not a permissive setting here, it is a
        # broken one: `min_pct` or `min_abs` at 0 makes every bucket a
        # changepoint, and `min_n` at 0 reports a quantile over an empty
        # sample. A malformed file falls back rather than disabling the
        # guards it exists to configure.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value > 0:
            resolved[key] = value
    return resolved


def _percentile(values: list, q: float):
    """Nearest-rank percentile over a list of numbers.

    Defined here rather than generalizing `cost._median`, which computes the
    50th percentile only. Widening a helper that the live `verdict` and
    `warn` hooks reach would put this feature's risk onto their path for no
    behavioural gain; a local twelve-line function costs nothing and keeps
    `cost.py` untouched by this work.

    Nearest-rank, not linear interpolation: token counts are integers and
    the populations here are small, so an interpolated value is a number no
    session actually reported. Reporting a real observation is easier to
    reconcile against the store when someone asks where a figure came from.
    """
    if not values:
        return None
    ordered = sorted(values)
    if q <= 0:
        return ordered[0]
    rank = int(-(-q * len(ordered) // 1))  # ceil, without importing math
    index = min(max(rank - 1, 0), len(ordered) - 1)
    return ordered[index]


def harness_supports(conn: sqlite3.Connection, harness: str, field: str) -> bool:
    """Whether `harness` can report `field` at all, per `harness_capability`.

    Absent rows read as unsupported. A harness the seed has never heard of
    should degrade to "cannot filter" and say so, rather than silently
    behaving as though it could.
    """
    row = conn.execute(
        "SELECT supported FROM harness_capability WHERE harness = ? AND field = ?",
        (harness, field),
    ).fetchone()
    return bool(row and row[0])


def qualifying_observations(
    conn: sqlite3.Connection,
    harness: str,
    since: str | None = None,
    line_threshold: int | None = None,
    filter_compaction: bool = True,
) -> list[dict]:
    """One first-turn prefix reading per qualifying session.

    Four rules, each of which removes a specific way a turn can look like a
    first turn without being one:

    1. the row is `MIN(turn_seq)` among the session's non-subagent turns.
       `turn_seq` is the transcript line number — `claude_collector` passes
       the same value for `turn_seq` and `source_line_no` — so it orders
       correctly but does not start at 1, and a subagent turn can precede
       the main thread's first turn in the file.
    2. that row's `source_line_no` is at or below `line_threshold`. A larger
       value means the collector first attached partway through the file, so
       the earliest row it holds is mid-conversation and its `cache_read` is
       conversation, not prefix.
    3. no `compact_boundary` at or before the turn. A compacted session
       resumes with a summary already in context. Only applied when the
       harness can report the event — Codex cannot, and pretending otherwise
       would claim a filter that never ran.
    4. `cache_read_tokens > 0`. Zero is a cache miss carrying no prefix
       reading, not a session whose prefix is empty.

    Returns `{session_row_id, cwd, ts, bucket, cache_read_tokens}` per
    session. `bucket` is the Monday-keyed local week, computed with the same
    expression `cost.trend` uses so the two surfaces never disagree about
    which week a turn falls in.
    """
    limits = thresholds()
    if line_threshold is None:
        line_threshold = limits["line_threshold"]

    params: list = [harness, int(line_threshold)]
    compaction_clause = ""
    if filter_compaction and harness_supports(conn, harness, COMPACT_BOUNDARY_KIND):
        compaction_clause = (
            " AND NOT EXISTS ("
            "   SELECT 1 FROM agent_activity_raw a"
            "   WHERE a.session_row_id = tr.session_row_id"
            "     AND a.kind = ?"
            "     AND a.ts <= tr.ts"
            " )"
        )
        params.append(COMPACT_BOUNDARY_KIND)

    since_clause = ""
    if since is not None:
        since_clause = " AND tn.ts >= ?"
        params.append(since)

    sql = (
        "SELECT s.id AS session_row_id, s.cwd AS cwd, tn.ts AS ts,"
        f"       {_bucket_expr('week', 'tn.ts')} AS bucket,"
        "       tn.cache_read_tokens AS cache_read_tokens"
        " FROM turn_raw tr"
        " JOIN turn_norm tn ON tn.turn_raw_id = tr.id"
        " JOIN session s ON s.id = tr.session_row_id"
        " WHERE s.harness = ?"
        "   AND tr.is_subagent = 0"
        "   AND tr.source_line_no <= ?"
        "   AND tn.cache_read_tokens > 0"
        "   AND tr.turn_seq = ("
        "     SELECT MIN(tr2.turn_seq) FROM turn_raw tr2"
        "     WHERE tr2.session_row_id = tr.session_row_id AND tr2.is_subagent = 0"
        "   )"
        + compaction_clause
        + since_clause
    )
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def weekly_floor(
    rows: list[dict], min_n: int | None = None, by_cwd: bool = False
) -> list[dict]:
    """Per-week floor estimates, blanked where the sample is too small.

    Pooled across projects by default. Grouping by `cwd` is available but is
    not the default, because it fragments the population past the point of
    usefulness: measured against the real corpus, 166 observations spread
    over 24 directories left only three with 20 or more, and 20 with fewer
    than five. It is also largely unnecessary — the floor's dominant
    contributors (plugins, MCP definitions, agent and skill descriptions,
    the global CLAUDE.md) are the same everywhere, and the three directories
    with enough observations to compare agreed to within 6% (20,568 /
    20,737 / 21,830).

    A bucket below `min_n` keeps its row and its count but reports
    `floor=None`. Dropping the row would make a thin week indistinguishable
    from a week with no sessions at all, and reporting its quantile anyway
    would dress up noise as a measurement.
    """
    limits = thresholds()
    if min_n is None:
        min_n = limits["min_n"]

    grouped: dict = {}
    for row in rows:
        key = (row["bucket"], row["cwd"] if by_cwd else None)
        grouped.setdefault(key, []).append(row["cache_read_tokens"])

    out = []
    for (bucket, cwd), values in sorted(grouped.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        enough = len(values) >= min_n
        out.append(
            {
                "bucket": bucket,
                "cwd": cwd,
                "n": len(values),
                "floor": _percentile(values, FLOOR_QUANTILE) if enough else None,
            }
        )
    return out


def detect_changepoints(
    weekly: list[dict], min_pct: float | None = None, min_abs: int | None = None
) -> list[dict]:
    """Weeks where the floor moved enough to mean something.

    A move registers only when it clears `min_pct` *and* `min_abs`. Either
    alone misfires at one end of the range — a percentage on a small floor,
    an absolute on a large one — and the whole value of this surface rests
    on not crying wolf.

    Buckets without a floor (too few sessions) are skipped rather than
    treated as zero, and comparison resumes from the last bucket that had
    one. A thin week should not manufacture a drop and a recovery.

    **The input must be a single series in time order.** Rows for two
    directories in the same week are not a series, and comparing them
    reports the difference between two projects as though it were a change
    over time. `baseline_rows` splits by directory before calling this;
    nothing else should call it with mixed rows.

    Both endpoints are recorded, and a comparison that skips weeks is
    marked. Buckets exist only for weeks that had observations, so two
    adjacent rows can be months apart — reporting only the later date would
    date a change to a week it may not have happened in.

    The consequence of the thresholds is real and belongs in the caller's
    output: a change smaller than them is invisible here. This detects
    deliberate reconfiguration, not gradual creep.
    """
    limits = thresholds()
    if min_pct is None:
        min_pct = limits["min_pct"]
    if min_abs is None:
        min_abs = limits["min_abs"]

    changes = []
    previous = None
    previous_bucket = None
    for row in weekly:
        floor = row.get("floor")
        if floor is None:
            continue
        if previous is not None:
            delta = floor - previous
            if abs(delta) >= min_abs and abs(delta) >= min_pct * previous:
                changes.append(
                    {
                        "date": row["bucket"],
                        "previous_bucket": previous_bucket,
                        "floor": floor,
                        "previous": previous,
                        "delta": delta,
                        "n": row["n"],
                        "adjacent": _is_next_week(previous_bucket, row["bucket"]),
                    }
                )
        previous = floor
        previous_bucket = row["bucket"]
    return changes


def _is_next_week(earlier: str | None, later: str | None) -> bool:
    """Whether two Monday-keyed bucket labels are consecutive weeks.

    Unparseable labels report False — an unknown span should read as a gap
    rather than quietly claim adjacency it cannot establish.
    """
    try:
        return date.fromisoformat(later) - date.fromisoformat(earlier) == timedelta(days=7)
    except (TypeError, ValueError):
        return False


def baseline_rows(
    conn: sqlite3.Connection,
    harness: str,
    since: str | None = None,
    by_cwd: bool = False,
) -> dict:
    """The whole result: current floor, history, and what produced them.

    One dict, not a list of rows, because the surface is a headline figure
    plus a change log rather than a table — the renderers split it, they do
    not reshape it.

    `compaction_filtered` is reported rather than assumed. It is the
    difference between "resumed sessions were excluded" and "resumed
    sessions could not be identified", and a reader deciding how much to
    trust the number needs to know which one they are looking at.
    `compaction_boundaries` accompanies it because capability is not
    coverage: a store harvested before the collector recorded these events
    has the capability and no rows, and would otherwise claim a filter that
    matched nothing.

    Results are grouped into one series per directory when `by_cwd`, and a
    single pooled series otherwise. Changepoints are detected *within* a
    series and never across them — two directories in one week are not a
    sequence, and comparing them would report the gap between two projects
    as a change over time.
    """
    limits = thresholds()
    compaction_filtered = harness_supports(conn, harness, COMPACT_BOUNDARY_KIND)
    boundaries = conn.execute(
        "SELECT COUNT(*) FROM agent_activity_raw a JOIN session s"
        " ON s.id = a.session_row_id WHERE a.kind = ? AND s.harness = ?",
        (COMPACT_BOUNDARY_KIND, harness),
    ).fetchone()[0]

    observations = qualifying_observations(conn, harness, since=since)
    weekly = weekly_floor(observations, by_cwd=by_cwd)

    grouped: dict = {}
    for row in weekly:
        grouped.setdefault(row["cwd"], []).append(row)

    series = []
    for cwd, buckets in sorted(grouped.items(), key=lambda kv: kv[0] or ""):
        buckets = sorted(buckets, key=lambda r: r["bucket"])
        reported = [b for b in buckets if b.get("floor") is not None]
        current = reported[-1] if reported else None
        series.append(
            {
                "cwd": cwd,
                "buckets": buckets,
                "current_floor": current["floor"] if current else None,
                "current_bucket": current["bucket"] if current else None,
                "current_n": current["n"] if current else 0,
                "history": detect_changepoints(buckets),
            }
        )

    # Top-level convenience fields describe the pooled series only. Under
    # --by-cwd there is no single current floor to name, and picking one
    # would put a directory-specific number under a heading that does not
    # say which directory.
    pooled = series[0] if series and not by_cwd else None

    return {
        "harness": harness,
        "estimator": "turn-1 cache_read_tokens",
        "quantile": FLOOR_QUANTILE,
        "n": len(observations),
        "series": series,
        "buckets": weekly,
        "current_floor": pooled["current_floor"] if pooled else None,
        "current_bucket": pooled["current_bucket"] if pooled else None,
        "current_n": pooled["current_n"] if pooled else 0,
        "history": pooled["history"] if pooled else [],
        "compaction_filtered": compaction_filtered,
        "compaction_boundaries": boundaries,
        "thresholds": limits,
        "grouped_by_cwd": by_cwd,
    }


def _fmt(value) -> str:
    """Thousands-separated, or an em dash when there is nothing to report.

    A blank cell and a zero are different claims. Nothing in this surface
    renders a missing floor as 0 — a week too thin to estimate has to look
    thin, not free.
    """
    if value is None:
        return "—"
    return f"{value:,}"


def _fmt_delta(value) -> str:
    if value is None:
        return "—"
    return f"{value:+,}"


def render_baseline_table(payload: dict) -> str:
    """Headline floor, the changes that cleared threshold, and the caveats.

    The caveats are not a footnote. This is an estimator over a filtered
    population with a detection floor, and a reader who takes the headline
    number without them will over-trust it — so what was measured, how many
    sessions it came from, and what the surface cannot see all render every
    time.

    No `~` marker anywhere: unlike an inferred context window, every figure
    here is a value a session actually reported. Marking it would spend the
    convention on something measured and weaken it where it is real.
    """
    limits = payload["thresholds"]
    quantile_label = f"p{int(payload['quantile'] * 100)}"
    # The headline carries its own provenance because the two counts in this
    # block mean different things: the floor comes from one week's sessions,
    # the estimator line below reports the whole qualifying population. Naming
    # only "n" next to the floor invites reading the larger number as its
    # support.
    lines = []
    for entry in payload["series"]:
        label = f"   {entry['cwd']}" if payload["grouped_by_cwd"] else ""
        where = (
            f"{quantile_label} of {entry['current_n']} sessions"
            f" in week of {entry['current_bucket']}"
            if entry["current_floor"] is not None
            else "no week had enough sessions to estimate"
        )
        headline = (
            f"{_fmt(entry['current_floor'])} tokens"
            if entry["current_floor"] is not None
            else _fmt(None)
        )
        lines.append(f"floor  {headline}   [{payload['harness']}]{label}   {where}")

        history = entry["history"]
        if not history:
            lines.append("last change  none above threshold")
            lines.append("")
            continue

        last = history[-1]
        pct = 100.0 * last["delta"] / last["previous"] if last["previous"] else 0.0
        lines.append(
            f"last change  {last['previous_bucket']} -> {last['date']}"
            f"   {_fmt(last['previous'])} -> {_fmt(last['floor'])}"
            f"   {_fmt_delta(last['delta'])}  ({pct:+.1f}%)"
        )
        lines.append("")
        lines.append("history")
        lines.append(f"  {'from':<12}{'to':<12}{'floor':>9}{'delta':>10}{'n':>5}")
        for row in history:
            # Buckets exist only for weeks with observations, so two adjacent
            # rows can be months apart. Saying so is the difference between a
            # dated fact and a date the reader supplies themselves.
            gap = "" if row["adjacent"] else "   (weeks skipped in between)"
            lines.append(
                f"  {str(row['previous_bucket']):<12}{row['date']:<12}"
                f"{_fmt(row['floor']):>9}{_fmt_delta(row['delta']):>10}{row['n']:>5}{gap}"
            )
        lines.append("")

    lines.append(
        f"estimator: turn-1 cache_read_tokens at {quantile_label};"
        f" {payload['n']} qualifying sessions"
    )
    if not payload["compaction_filtered"]:
        lines.append(
            f"compaction filtering: unsupported for {payload['harness']} —"
            " resumed sessions cannot be excluded, so this population is noisier"
        )
    elif payload["compaction_boundaries"] == 0:
        # Capability is not coverage. A store harvested before the collector
        # recorded these events has the capability and no rows, and "applied"
        # over zero rows claims a filter that matched nothing.
        lines.append(
            "compaction filtering: supported, but this store holds no boundary"
            " events — harvest with --rescan if it predates their capture"
        )
    else:
        lines.append(
            f"compaction filtering: applied ({payload['compaction_boundaries']} boundaries)"
        )
    lines.append(
        f"detects moves of at least {int(limits['min_pct'] * 100)}% and"
        f" {int(limits['min_abs']):,} tokens; smaller drift is not visible here"
    )
    if payload["grouped_by_cwd"]:
        lines.append("grouped by cwd — buckets thin out quickly when split this way")
    else:
        # The pooled floor is the leanest project's prefix, so a week that
        # adds sessions from a lighter directory lowers it without any
        # configuration having changed. Same failure mode p25 had, one level
        # up, and it cannot be filtered away — only disclosed.
        lines.append(
            "pooled across projects — a shift in which directories you worked"
            " in can move this without any configuration changing"
        )
    lines.append("measured on this machine only")

    return "\n".join(lines)


EMPTY_POPULATION_NOTE = (
    "no qualifying sessions: a session contributes only its first recorded"
    " turn, seen from the start of its transcript, with a cache hit and no"
    " preceding compaction"
)


def baseline_command(
    days: int = DEFAULT_WINDOW_DAYS,
    show_all: bool = False,
    harness: str | None = None,
    by_cwd: bool = False,
    as_json: bool = False,
) -> int:
    """CLI entry point for `flow cost baseline`.

    The window flags exist for parity with the other cost surfaces, but the
    useful invocation is `--all`: a changepoint log needs more than one
    bucket to have anything to compare, and a seven-day window holds one.
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    since = None if show_all else _cutoff(days)
    targets = (harness,) if harness else HARNESSES

    conn = sqlite3.connect(store)
    conn.row_factory = sqlite3.Row
    try:
        rows = [baseline_rows(conn, name, since=since, by_cwd=by_cwd) for name in targets]
        freshness = telemetry_freshness.usage_freshness(conn)
    finally:
        conn.close()

    if as_json:
        print(render_json({"rows": rows, "freshness": freshness}))
        return 0

    rendered = [
        f"floor  —   [{row['harness']}]\n{EMPTY_POPULATION_NOTE}"
        if row["n"] == 0
        else render_baseline_table(row)
        for row in rows
    ]
    notes = telemetry_freshness.freshness_notes(freshness, read_only=True)
    print("\n\n".join(rendered) + ("\n\n" + "\n".join(notes) if notes else ""))
    return 0
