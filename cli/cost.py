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
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import usage_store
from claude_collector import HARNESS as CLAUDE_HARNESS
from claude_collector import default_sessions_root as claude_sessions_root
from claude_collector import harvest_all as claude_harvest_all
from codex_collector import HARNESS as CODEX_HARNESS
from normalize import normalize_all
from paths import HOME, SOURCE_DIR

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


def capacity_gauge(conn: sqlite3.Connection, since: str | None) -> dict | None:
    """The single most recent Codex capacity reading in the window, or `None`.

    A snapshot, not a sum — see the module docstring for why this is kept
    out of `summary_rows` entirely rather than joined in as extra columns.
    `ts` is included specifically so a renderer can show how stale the
    reading is, since "most recent in the window" can still be days old.
    """
    where = "AND tn.ts >= ?" if since is not None else ""
    params = (since,) if since is not None else ()
    row = conn.execute(
        f"""
        SELECT tn.ts AS ts,
               capacity_primary_used_pct, capacity_primary_window_minutes, capacity_primary_resets_at,
               capacity_secondary_used_pct, capacity_secondary_window_minutes, capacity_secondary_resets_at
        FROM turn_norm tn
        JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        JOIN session s ON s.id = tr.session_row_id
        WHERE s.harness = ? AND tn.capacity_primary_used_pct IS NOT NULL {where}
        ORDER BY tn.ts DESC
        LIMIT 1
        """,
        (CODEX_HARNESS, *params),
    ).fetchone()
    return dict(row) if row is not None else None


def _parse_ts(value: str) -> datetime | None:
    """An aware datetime from a stored ISO8601 string, or None.

    Both `Z` and `+00:00` suffixes occur (collectors write `Z`; `_cutoff`
    writes `+00:00`); `fromisoformat` handles `Z` only from 3.11 — normalize
    rather than assume the interpreter.
    """
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# Where the statusline records each session's exact context window
# (`claude-window-<session_id>`). Module-level so tests can point it at a
# tmpdir instead of coupling to the host's real /tmp — the one place a
# stray real file could otherwise flip a test's expected window.
STATUSLINE_DIR = Path("/tmp")


def _infer_window(session_id: str, ctx: int) -> tuple[int, bool]:
    """(window_tokens, exact) for a session's context window.

    The window isn't recorded in transcripts, so two sources, in order:

    1. `STATUSLINE_DIR/claude-window-<session_id>` — the statusline writes
       the exact window it derived from its own payload. That derivation
       divides by an integer percentage, so it carries a few percent of
       rounding error — snap to the nearest real window, but only when the
       recorded value is within 15% of one: a corrupt or truncated file
       snapping confidently to the wrong window would be worse than the
       honest `~` inference, so anything further off falls through. This is
       the one signal that can correctly identify a 1M-window session still
       under 190K context.
    2. Inference: context observed above LONG_THRESHOLD must be the
       long-context variant; anything below is assumed standard, which
       overstates percentages for an unidentified 1M session — the `exact`
       flag is False so a renderer can mark the number as inferred.
    """
    try:
        raw = (STATUSLINE_DIR / f"claude-window-{session_id}").read_text().strip()
        recorded = int(raw)
        nearest = min((STD_WINDOW, LONG_WINDOW), key=lambda w: abs(w - recorded))
        if abs(recorded - nearest) <= nearest * 0.15:
            return nearest, True
    except (OSError, ValueError):
        pass
    return (LONG_WINDOW if ctx > LONG_THRESHOLD else STD_WINDOW), False


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

        window, exact = _infer_window(raw["session_id"], ctx)
        last = _parse_ts(raw["last_ts"])
        # None (not 0) when the timestamp is unparseable: 0 would render as
        # "0s" — the most attention-grabbing state — for a session of
        # genuinely unknown age.
        idle_sec = max(0, int((now - last).total_seconds())) if last else None
        action = "clear" if gap >= TOPIC_GAP_SEC else "compact"
        carry_pct = carry / window * 100

        result.append(
            {
                "id": raw["session_id"][:8],
                "label": _session_label(raw["title"], raw["cwd"], raw["session_id"]),
                "ctx_pct": round(ctx / window * 100, 1),
                "carry_pct": round(carry_pct, 1),
                "window_exact": exact,
                "idle_sec": idle_sec,
                "recommend": _recommendation(carry_pct, action),
                "session_id": raw["session_id"],
            }
        )
    result.sort(key=lambda r: (-r["carry_pct"], r["session_id"]))
    return result


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


def _render_gauge_line(gauge: dict) -> str:
    parts = [_render_gauge_field(gauge["capacity_primary_used_pct"], gauge.get("capacity_primary_window_minutes"))]
    if gauge.get("capacity_secondary_used_pct") is not None:
        parts.append(
            _render_gauge_field(gauge["capacity_secondary_used_pct"], gauge.get("capacity_secondary_window_minutes"))
        )
    return f"codex capacity (as of {gauge['ts']}): " + ", ".join(parts)


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
    finally:
        conn.close()

    if as_json:
        payload = {"rows": rows}
        if gauge is not None:
            payload["capacity"] = gauge
        print(render_json(payload))
    else:
        print(render_table(rows))
        if gauge is not None:
            print()
            print(_render_gauge_line(gauge))

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
    finally:
        conn.close()

    # Same envelope as `cost summary`'s --json — {"rows": [...]}, so a caller
    # never needs to know which subcommand produced a payload before reading
    # payload["rows"] out of it.
    print(render_json({"rows": rows}) if as_json else render_table(rows))
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
        display.append(
            {
                "id": r["id"],
                "session": r["label"][:39] + "…" if len(r["label"]) > 40 else r["label"],
                "ctx": f"{marker}{r['ctx_pct']:.0f}%",
                "carry": f"{r['carry_pct']:.0f}%",
                "idle": _fmt_idle(r["idle_sec"]),
                "recommend": r["recommend"],
            }
        )
    out = render_table(display)
    if any(not r["window_exact"] for r in rows):
        out += (
            "\n\n~ = context window inferred, not measured: a session under"
            f" {LONG_THRESHOLD // 1000}K context is assumed to be on the"
            f" {STD_WINDOW // 1000}K window, which overstates percentages if"
            " it is actually running the 1M variant."
        )
    return out


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
        norm_result = normalize_all(conn)
        for failure in norm_result["failures"]:
            print(f"note: could not normalize turn_raw id {failure['turn_raw_id']} — {failure['reason']}")
        rows = active_rows(conn, within)
    finally:
        conn.close()

    print(render_json({"rows": rows}) if as_json else _render_active_table(rows))
    return 0
