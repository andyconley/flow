"""`flow cost`: the first read surface over `turn_norm`.

Every other module in `cli/` writes to the usage store. This one only reads
it. `summary_rows`, `sessions_rows`, and `capacity_gauge` are pure query
functions — a connection and an optional cutoff in, a list of dicts (or, for
the gauge, a single dict or `None`) out. Nothing here decides how a caller
displays the result; `render_table` and `render_json` are two independent
renderers over the same shape, matching the convention `kubectl`/`docker`/
`gh` use: one canonical structured result, one default human-readable
rendering, one `--json` for the same data machine-readable.

Codex's capacity percentages are handled separately from the token-total
rows, on purpose. `capacity_primary_used_pct` and its siblings are a
snapshot of the most recent reading in the window, not a quantity that sums
meaningfully across turns the way token counts do — blending a "percent
full right now" figure into a table of summed totals would misrepresent
both. `cost_summary_command` prints it as an adjacent line (table mode) or
an adjacent key (JSON mode) instead, and omits it entirely — not as a zero
or a blank — when no Codex row with capacity data falls inside the window.

No module-level path or connection resolution, matching every other command
module in `cli/`: a directly-imported unit test must never be able to touch
the real `~/.flow/usage.db`.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import usage_store
from paths import HOME, SOURCE_DIR

DEFAULT_WINDOW_DAYS = 7


def _cutoff(days: int) -> str:
    """UTC ISO8601 cutoff string for "the last `days` days," exclusive of tz math surprises.

    Compared lexicographically against `turn_norm.ts`, which is safe because
    ISO8601 sorts correctly as text — the same convention already used
    everywhere else in this schema (`harvest.harvested_at`, `turn_raw.ts`).
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
        ORDER BY last_ts DESC
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
    """
    where = "AND tn.ts >= ?" if since is not None else ""
    params = (since,) if since is not None else ()
    row = conn.execute(
        f"""
        SELECT capacity_primary_used_pct, capacity_primary_window_minutes, capacity_primary_resets_at,
               capacity_secondary_used_pct, capacity_secondary_window_minutes, capacity_secondary_resets_at
        FROM turn_norm tn
        JOIN turn_raw tr ON tr.id = tn.turn_raw_id
        JOIN session s ON s.id = tr.session_row_id
        WHERE s.harness = 'codex' AND tn.capacity_primary_used_pct IS NOT NULL {where}
        ORDER BY tn.ts DESC
        LIMIT 1
        """,
        params,
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


def render_json(rows) -> str:
    """The same structured result, serialized instead of aligned."""
    return json.dumps(rows, indent=2)


def _render_gauge_line(gauge: dict) -> str:
    parts = [f"primary {gauge['capacity_primary_used_pct']:.1f}%"]
    if gauge.get("capacity_secondary_used_pct") is not None:
        parts.append(f"secondary {gauge['capacity_secondary_used_pct']:.1f}%")
    return "codex capacity: " + ", ".join(parts)


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
        print(json.dumps(payload, indent=2))
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

    print(render_json(rows) if as_json else render_table(rows))
    return 0
