"""Normalize turn_raw into turn_norm: one shared token convention across harnesses.

Reads each harness's raw payload in its own semantics and projects it into
`turn_norm`'s disjoint-token convention, so nothing above this layer needs to
know that Codex's `cached_input_tokens` is a *subset* of `input_tokens` while
Claude's cache buckets are disjoint and additive.

Recomputable by design: `turn_norm` is disposable. A wrong extraction rule
costs a re-run of `normalize_all`, never a re-harvest — the raw payload is
kept verbatim in `turn_raw` specifically so this correction is always
possible. `NORM_VERSION` is the mechanism: bump it when a rule changes, and
every row stamped with an older version becomes stale and gets reprocessed.

Only stale rows are touched — a row with no `turn_norm` counterpart yet, or
one whose `norm_version` predates the current code. At today's volume (tens
of thousands of rows) a full rebuild would also be cheap, but selecting only
what actually changed is the shape that stays cheap as this grows, and it is
no more code to maintain once written.

No module-level path or connection resolution, matching `codex_collector.py`
and `usage_store.py` — everything is passed in explicitly.
"""

import json
import sqlite3

import usage_store
from paths import HOME, SOURCE_DIR

NORM_VERSION = 1


def _normalize_codex_row(payload: dict) -> dict:
    """Extract turn_norm's token/capacity columns from one Codex turn_raw payload.

    `payload` is the full JSONL record as parsed JSON (what `codex_collector`
    stored verbatim), not just its `payload` sub-object — mirroring how the
    collector itself reads it.

    `info` and `rate_limits` are both nullable in real data (`info` is null in
    about 0.1% of rows on the corpus this was built against). Every field
    degrades to `None` rather than raising — absence is a real, expected
    outcome here, not a shape violation the way it would be for a required
    identity field during harvest.
    """
    record_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    info = record_payload.get("info") if isinstance(record_payload.get("info"), dict) else None
    rate_limits = (
        record_payload.get("rate_limits") if isinstance(record_payload.get("rate_limits"), dict) else None
    )

    usage = info.get("last_token_usage") if info and isinstance(info.get("last_token_usage"), dict) else None
    input_tokens = usage.get("input_tokens") if usage else None
    cached_tokens = usage.get("cached_input_tokens") if usage else None
    # Codex reports cached_input_tokens as a SUBSET of input_tokens — the
    # store's disjoint convention requires subtracting it out. Both must be
    # present as numbers; either missing means "cannot compute," not zero.
    fresh_input_tokens = (
        input_tokens - cached_tokens
        if isinstance(input_tokens, (int, float)) and isinstance(cached_tokens, (int, float))
        else None
    )

    primary = rate_limits.get("primary") if rate_limits and isinstance(rate_limits.get("primary"), dict) else None
    secondary = (
        rate_limits.get("secondary") if rate_limits and isinstance(rate_limits.get("secondary"), dict) else None
    )

    return {
        "fresh_input_tokens": fresh_input_tokens,
        "cache_read_tokens": cached_tokens,
        "cache_write_tokens": usage.get("cache_write_input_tokens") if usage else None,
        "output_tokens": usage.get("output_tokens") if usage else None,
        "reasoning_tokens": usage.get("reasoning_output_tokens") if usage else None,
        "context_window": info.get("model_context_window") if info else None,
        "capacity_primary_used_pct": primary.get("used_percent") if primary else None,
        "capacity_primary_window_minutes": primary.get("window_minutes") if primary else None,
        "capacity_primary_resets_at": primary.get("resets_at") if primary else None,
        "capacity_secondary_used_pct": secondary.get("used_percent") if secondary else None,
        "capacity_secondary_window_minutes": secondary.get("window_minutes") if secondary else None,
        "capacity_secondary_resets_at": secondary.get("resets_at") if secondary else None,
    }


_EXTRACTORS = {
    "codex": _normalize_codex_row,
}


def normalize_all(conn: sqlite3.Connection) -> dict:
    """(Re)compute turn_norm for every stale turn_raw row. Returns `{"normalized": n}`.

    Stale means: no turn_norm row yet, or one stamped with an older
    NORM_VERSION than this code's. `INSERT OR REPLACE`, keyed on turn_norm's
    PRIMARY KEY (turn_raw_id), handles "new" and "needs overwriting"
    identically — there is no meaningful difference between them from this
    function's point of view.

    A row whose harness has no extractor yet (Claude, until that collector
    exists) is left alone rather than raising — this is the seam chunk 5
    fills in without needing to change anything here.
    """
    rows = conn.execute(
        "SELECT tr.id, tr.payload, tr.ts, tr.model, tr.is_subagent, s.harness"
        " FROM turn_raw tr"
        " JOIN session s ON s.id = tr.session_row_id"
        " LEFT JOIN turn_norm tn ON tn.turn_raw_id = tr.id"
        " WHERE tn.turn_raw_id IS NULL OR tn.norm_version < ?",
        (NORM_VERSION,),
    ).fetchall()

    normalized = 0
    with conn:
        for turn_raw_id, payload_text, ts, model, is_subagent, harness in rows:
            extractor = _EXTRACTORS.get(harness)
            if extractor is None:
                continue
            fields = extractor(json.loads(payload_text))
            conn.execute(
                "INSERT OR REPLACE INTO turn_norm"
                " (turn_raw_id, ts, model, is_subagent, fresh_input_tokens, cache_read_tokens,"
                "  cache_write_tokens, output_tokens, reasoning_tokens, context_window,"
                "  capacity_primary_used_pct, capacity_primary_window_minutes, capacity_primary_resets_at,"
                "  capacity_secondary_used_pct, capacity_secondary_window_minutes, capacity_secondary_resets_at,"
                "  norm_version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    turn_raw_id,
                    ts,
                    model,
                    is_subagent,
                    fields["fresh_input_tokens"],
                    fields["cache_read_tokens"],
                    fields["cache_write_tokens"],
                    fields["output_tokens"],
                    fields["reasoning_tokens"],
                    fields["context_window"],
                    fields["capacity_primary_used_pct"],
                    fields["capacity_primary_window_minutes"],
                    fields["capacity_primary_resets_at"],
                    fields["capacity_secondary_used_pct"],
                    fields["capacity_secondary_window_minutes"],
                    fields["capacity_secondary_resets_at"],
                    NORM_VERSION,
                ),
            )
            normalized += 1

    return {"normalized": normalized}


def normalize_command() -> int:
    """CLI entry point: ensure the store, then normalize whatever is stale.

    Thin by design, same as harvest.py — a fourth module for this one
    function isn't justified at this size; if a second harness's dispatch
    grows complex enough to need its own wrapper, split then.
    """
    store = usage_store.default_store_path(HOME)
    capabilities = usage_store.default_capabilities_path(SOURCE_DIR)
    usage_store.ensure_store(store, capabilities)

    conn = sqlite3.connect(store)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        result = normalize_all(conn)
    finally:
        conn.close()

    print(f"normalize: {result['normalized']} rows")
    return 0
