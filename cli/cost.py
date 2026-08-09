"""`flow cost`: the first read surface over `turn_norm`.

Every other module in `cli/` writes usage data to the store; this one reads
it back out. It still calls `usage_store.ensure_store` before querying, the
same convenience every other command module gives itself (see
`harvest.py`'s own docstring) — a fresh machine gets a working `flow cost
summary` rather than an error pointing at `flow setup machine`. What it
never does is touch `turn_raw`, `turn_norm`, or `session`: schema creation
and migration are the only writes this module can cause.

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

import usage_store
from codex_collector import HARNESS as CODEX_HARNESS
from paths import HOME, SOURCE_DIR

DEFAULT_WINDOW_DAYS = 7


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


def sessions_rows(conn: sqlite3.Connection, since: str | None) -> list[dict]:
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
    """
    where = "WHERE tn.ts >= ?" if since is not None else ""
    params = (since,) if since is not None else ()
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


def cost_sessions_command(days: int = DEFAULT_WINDOW_DAYS, show_all: bool = False, as_json: bool = False) -> int:
    """CLI entry point for `flow cost sessions`."""
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    since = None if show_all else _cutoff(days)

    conn = sqlite3.connect(store)
    conn.row_factory = sqlite3.Row
    try:
        rows = sessions_rows(conn, since)
    finally:
        conn.close()

    # Same envelope as `cost summary`'s --json — {"rows": [...]}, so a caller
    # never needs to know which subcommand produced a payload before reading
    # payload["rows"] out of it.
    print(render_json({"rows": rows}) if as_json else render_table(rows))
    return 0
