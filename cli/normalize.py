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
Bumping it *down* is not handled — rows stamped with a newer version are
never revisited by a `<` comparison, so a rollback leaves two conventions
mixed in the table with nothing flagging it. Not expected to happen in
practice; noted so it isn't mistaken for an oversight if it ever does.

Only stale rows are touched — a row with no `turn_norm` counterpart yet, or
one whose `norm_version` predates the current code. At today's volume (tens
of thousands of rows) a full rebuild would also be cheap, but selecting only
what actually changed is the shape that stays cheap as this grows, and it is
no more code to maintain once written.

One malformed row does not stop the pass, matching `codex_collector.py`'s own
per-file isolation ("one file's hard stop does not affect any other file") —
the same property, one level down, since a value this collector never
anticipated in a payload leaf is exactly as real a risk as a line it never
anticipated in a file.

No module-level path or connection resolution, matching `codex_collector.py`
and `usage_store.py` — everything is passed in explicitly.
"""

import json
import sqlite3

import usage_store
from paths import HOME, SOURCE_DIR

NORM_VERSION = 2


def _num(value) -> int | float | None:
    """A leaf value if it's actually numeric, else None.

    Payload leaves are trusted less than payload containers: a container
    shape (`info`, `rate_limits`, `last_token_usage`) that isn't a dict
    degrades cleanly via `isinstance` checks throughout this module, but a
    leaf that survives the container check could still be a string, a dict,
    or anything else valid JSON allows. Passing that straight to a numeric
    SQLite column raises `sqlite3.InterfaceError` — this function is what
    turns "unexpected leaf shape" into "None," the same category as "field
    absent," rather than into a crash.
    """
    return value if isinstance(value, (int, float)) else None


def _normalize_codex_row(payload: dict) -> dict | None:
    """Extract turn_norm's token/capacity columns from one Codex turn_raw payload.

    `payload` is the full JSONL record as parsed JSON (what `codex_collector`
    stored verbatim), not just its `payload` sub-object — mirroring how the
    collector itself reads it.

    Returns `None` if this record isn't a `token_count` event — dispatch is
    by harness, not record type, so nothing structurally prevents a future
    record type from reaching here. `normalize_all` counts a `None` as
    skipped rather than treating it as a row to normalize.

    `info` and `rate_limits` are both nullable in real data (`info` is null in
    about 0.1% of rows on the corpus this was built against). Every field
    degrades to `None` rather than raising — absence is a real, expected
    outcome here, not a shape violation the way it would be for a required
    identity field during harvest.
    """
    record_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    if record_payload.get("type") != "token_count":
        return None
    info = record_payload.get("info") if isinstance(record_payload.get("info"), dict) else None
    rate_limits = (
        record_payload.get("rate_limits") if isinstance(record_payload.get("rate_limits"), dict) else None
    )

    usage = info.get("last_token_usage") if info and isinstance(info.get("last_token_usage"), dict) else None
    input_tokens = _num(usage.get("input_tokens")) if usage else None
    cached_tokens = _num(usage.get("cached_input_tokens")) if usage else None
    fresh_input_tokens = _compute_fresh_input_tokens(input_tokens, cached_tokens)

    primary = rate_limits.get("primary") if rate_limits and isinstance(rate_limits.get("primary"), dict) else None
    secondary = (
        rate_limits.get("secondary") if rate_limits and isinstance(rate_limits.get("secondary"), dict) else None
    )

    return {
        "fresh_input_tokens": fresh_input_tokens,
        # cache_read_tokens reflects what Codex actually reported, even in the
        # (unobserved on the real corpus, but real data has overturned two
        # other assumptions in this feature already) case where
        # fresh_input_tokens couldn't be computed — the two are independent
        # measurements, not one derived from the other.
        "cache_read_tokens": cached_tokens,
        "cache_write_tokens": _num(usage.get("cache_write_input_tokens")) if usage else None,
        # Codex reports no cache-TTL split at all — `harness_capability` has
        # said `cache_ttl_split: 0` for this harness since v1. NULL, not 0:
        # "this harness cannot report it" and "it reported nothing cached"
        # are different facts and turn_norm keeps them apart everywhere else.
        "cache_write_1h_tokens": None,
        "cache_write_5m_tokens": None,
        "output_tokens": _num(usage.get("output_tokens")) if usage else None,
        "reasoning_tokens": _num(usage.get("reasoning_output_tokens")) if usage else None,
        "context_window": _num(info.get("model_context_window")) if info else None,
        "capacity_primary_used_pct": _num(primary.get("used_percent")) if primary else None,
        "capacity_primary_window_minutes": _num(primary.get("window_minutes")) if primary else None,
        "capacity_primary_resets_at": _num(primary.get("resets_at")) if primary else None,
        "capacity_secondary_used_pct": _num(secondary.get("used_percent")) if secondary else None,
        "capacity_secondary_window_minutes": _num(secondary.get("window_minutes")) if secondary else None,
        "capacity_secondary_resets_at": _num(secondary.get("resets_at")) if secondary else None,
    }


def _compute_fresh_input_tokens(
    input_tokens: int | float | None, cached_tokens: int | float | None
) -> int | float | None:
    """`input_tokens - cached_tokens`, handling both ways the inputs can be incomplete.

    `input_tokens` missing: genuinely uncomputable — `None`. A total with no
    reported total is not "zero fresh tokens," it's "no measurement."

    `cached_tokens` missing while `input_tokens` is present: treated as `0`,
    not `None`. Checked against the real 16,260-row corpus this was built
    against — this combination never occurs there, `cached_input_tokens`
    is always present whenever `input_tokens` is — but the repo's own test
    fixture (`_token_count()` in tests/test_flow.py) omits it, meaning every
    test using that fixture exercised this exact gap with nothing asserting
    on the result. Treating an omitted cache field as "nothing was cached"
    matches how JSON serializers commonly drop zero/default fields, and it is
    the interpretation that keeps `input_tokens` from disappearing from the
    normalized layer entirely — `turn_norm` has no column to hold it
    separately, so `None` here would be a silent undercount with nothing
    downstream able to tell the difference from "no data."

    A negative result — `cached_tokens > input_tokens` — is treated as
    uncomputable (`None`) rather than stored. Codex's subset semantics say
    this should never happen (confirmed: zero occurrences in the real
    corpus), but this feature has already been wrong twice about what real
    Codex data does; storing a value that corrupts every downstream SUM is
    a worse failure than reporting "no measurement" for one row.
    """
    if input_tokens is None:
        return None
    fresh = input_tokens - (cached_tokens if cached_tokens is not None else 0)
    return fresh if fresh >= 0 else None


def _normalize_claude_row(payload: dict) -> dict | None:
    """Extract turn_norm's token columns from one Claude turn_raw payload.

    Unlike Codex's payload (a wrapper record whose actual content sits one
    level down under its own `payload` key), Claude's `turn_raw.payload` is
    the JSONL line itself — the `usage` block lives at `message.usage`
    directly, verified against real transcripts including this session's own.

    Returns `None` for anything but `type: "assistant"` — `claude_collector.py`
    only ever writes `turn_raw` rows for assistant entries with a `usage`
    block today, but nothing structurally prevents that from changing, so
    this checks rather than assumes, the same way the Codex extractor does.

    Claude's fields are already disjoint (unlike Codex's, where
    `cached_input_tokens` is a subset of `input_tokens`), so this is direct
    mapping, no subtraction — `fresh_input_tokens = input_tokens` as
    reported. `reasoning_tokens`, `context_window`, and both `capacity_*`
    groups stay `NULL`: Claude transcripts do not carry them, matching
    `data/harness_capabilities.json`'s existing claims for this harness.

    `usage.cache_creation` splits the cache write by TTL —
    `ephemeral_1h_input_tokens` and `ephemeral_5m_input_tokens` — and the two
    sum to `cache_creation_input_tokens` exactly, verified across 20,587 real
    turns with no rounding. Both are extracted as of NORM_VERSION 2, and this
    is exactly the recompute-without-re-harvest case the module docstring
    promises: the fields were in the raw payload from the first harvest, just
    unread. `cache_write_tokens` stays the total rather than being replaced,
    because it is what Codex reports and what existing callers read.
    Extracted independently rather than deriving one from the other and the
    total — if a future release ever adds a third TTL bucket, two independent
    reads degrade into an under-report that the sum check catches, while a
    subtraction would silently attribute the new bucket to an existing one.
    `cache_creation` absent (older transcripts, before the field existed)
    leaves both NULL, distinct from a reported zero.

    Real data carries more still (`server_tool_use`, `service_tier`,
    `inference_geo`, `iterations`, `speed`) — none of it extracted here. The
    raw payload holds it verbatim regardless, so it can be picked up in a
    later recompute the same way these two were.
    """
    if payload.get("type") != "assistant":
        return None
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    usage = message.get("usage") if isinstance(message.get("usage"), dict) else None
    cache_creation = (
        usage.get("cache_creation")
        if usage and isinstance(usage.get("cache_creation"), dict)
        else None
    )

    return {
        "fresh_input_tokens": _num(usage.get("input_tokens")) if usage else None,
        "cache_read_tokens": _num(usage.get("cache_read_input_tokens")) if usage else None,
        "cache_write_tokens": _num(usage.get("cache_creation_input_tokens")) if usage else None,
        "cache_write_1h_tokens": (
            _num(cache_creation.get("ephemeral_1h_input_tokens")) if cache_creation else None
        ),
        "cache_write_5m_tokens": (
            _num(cache_creation.get("ephemeral_5m_input_tokens")) if cache_creation else None
        ),
        "output_tokens": _num(usage.get("output_tokens")) if usage else None,
        "reasoning_tokens": None,
        "context_window": None,
        "capacity_primary_used_pct": None,
        "capacity_primary_window_minutes": None,
        "capacity_primary_resets_at": None,
        "capacity_secondary_used_pct": None,
        "capacity_secondary_window_minutes": None,
        "capacity_secondary_resets_at": None,
    }


_EXTRACTORS = {
    "codex": _normalize_codex_row,
    "claude": _normalize_claude_row,
}


def normalize_all(conn: sqlite3.Connection) -> dict:
    """(Re)compute turn_norm for every stale turn_raw row.

    Returns `{"normalized": n, "skipped": n, "failures": [{"turn_raw_id", "reason"}, ...]}`.

    Stale means: no turn_norm row yet, or one stamped with an older
    NORM_VERSION than this code's. `norm_version` is `NOT NULL` on every write
    path, so `tn.norm_version < ?` can't actually see a NULL today — but
    `COALESCE(tn.norm_version, -1)` costs nothing and the failure mode if that
    ever changed would be silent permanent staleness with no error, so it's
    guarded anyway.

    The query is restricted to harnesses `_EXTRACTORS` actually knows —
    `s.harness IN (...)`, not a post-hoc `continue`. A harness with no
    extractor yet (Claude, until that collector exists) would otherwise never
    get a `turn_norm` row and so would match `tn.turn_raw_id IS NULL` on
    every single call forever, re-selecting and re-parsing its full payload
    text every run for no result — exactly the growing-cost failure this
    module's own docstring claims not to have.

    `ON CONFLICT DO UPDATE` rather than `INSERT OR REPLACE`: REPLACE deletes
    the existing row before inserting, which is invisible today (nothing
    references `turn_norm`) but would silently cascade-delete a future
    table's rows on every re-normalize if one ever gets a
    `REFERENCES turn_norm(turn_raw_id) ON DELETE CASCADE`. `DO UPDATE`
    updates in place and never deletes anything.

    A row that fails to extract or insert (an unrecognized leaf shape, a
    constraint violation) is reported and skipped rather than aborting the
    whole pass — matching `codex_collector.harvest_all`'s per-file isolation.
    Committed per-row rather than in one transaction for the whole pass, so a
    failure partway through does not roll back rows that already succeeded.
    """
    extractors_placeholder = ",".join("?" for _ in _EXTRACTORS)
    rows = conn.execute(
        "SELECT tr.id, tr.payload, tr.ts, tr.model, tr.is_subagent, s.harness"
        " FROM turn_raw tr"
        " JOIN session s ON s.id = tr.session_row_id"
        " LEFT JOIN turn_norm tn ON tn.turn_raw_id = tr.id"
        " WHERE s.harness IN (" + extractors_placeholder + ")"
        " AND (tn.turn_raw_id IS NULL OR COALESCE(tn.norm_version, -1) < ?)",
        (*_EXTRACTORS.keys(), NORM_VERSION),
    ).fetchall()

    normalized = 0
    skipped = 0
    failures: list[dict] = []

    for turn_raw_id, payload_text, ts, model, is_subagent, harness in rows:
        try:
            extractor = _EXTRACTORS[harness]
            record = json.loads(payload_text)
            fields = extractor(record)
            if fields is None:
                # The extractor itself decides what counts as a normalizable
                # record for its harness — dispatch is by harness only, not
                # record type, so nothing structurally prevents turn_raw from
                # ever holding a row an extractor doesn't recognize. Counted
                # as skipped rather than silently becoming an all-NULL row
                # indistinguishable from a legitimate absence-of-data case.
                skipped += 1
                continue
            with conn:
                conn.execute(
                    "INSERT INTO turn_norm"
                    " (turn_raw_id, ts, model, is_subagent, fresh_input_tokens, cache_read_tokens,"
                    "  cache_write_tokens, cache_write_1h_tokens, cache_write_5m_tokens,"
                    "  output_tokens, reasoning_tokens, context_window,"
                    "  capacity_primary_used_pct, capacity_primary_window_minutes, capacity_primary_resets_at,"
                    "  capacity_secondary_used_pct, capacity_secondary_window_minutes, capacity_secondary_resets_at,"
                    "  norm_version)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(turn_raw_id) DO UPDATE SET"
                    "   ts = excluded.ts,"
                    "   model = excluded.model,"
                    "   is_subagent = excluded.is_subagent,"
                    "   fresh_input_tokens = excluded.fresh_input_tokens,"
                    "   cache_read_tokens = excluded.cache_read_tokens,"
                    "   cache_write_tokens = excluded.cache_write_tokens,"
                    "   cache_write_1h_tokens = excluded.cache_write_1h_tokens,"
                    "   cache_write_5m_tokens = excluded.cache_write_5m_tokens,"
                    "   output_tokens = excluded.output_tokens,"
                    "   reasoning_tokens = excluded.reasoning_tokens,"
                    "   context_window = excluded.context_window,"
                    "   capacity_primary_used_pct = excluded.capacity_primary_used_pct,"
                    "   capacity_primary_window_minutes = excluded.capacity_primary_window_minutes,"
                    "   capacity_primary_resets_at = excluded.capacity_primary_resets_at,"
                    "   capacity_secondary_used_pct = excluded.capacity_secondary_used_pct,"
                    "   capacity_secondary_window_minutes = excluded.capacity_secondary_window_minutes,"
                    "   capacity_secondary_resets_at = excluded.capacity_secondary_resets_at,"
                    "   norm_version = excluded.norm_version",
                    (
                        turn_raw_id,
                        ts,
                        model,
                        is_subagent,
                        fields["fresh_input_tokens"],
                        fields["cache_read_tokens"],
                        fields["cache_write_tokens"],
                        fields["cache_write_1h_tokens"],
                        fields["cache_write_5m_tokens"],
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
        except (sqlite3.Error, TypeError, ValueError, json.JSONDecodeError) as exc:
            failures.append({"turn_raw_id": turn_raw_id, "reason": str(exc)})

    return {"normalized": normalized, "skipped": skipped, "failures": failures}


def normalize_command() -> int:
    """CLI entry point: ensure the store, then normalize whatever is stale.

    Thin by design, same as harvest.py — a fourth module for this one
    function isn't justified at this size; if a second harness's dispatch
    grows complex enough to need its own wrapper, split then.

    Returns 0 if every row normalized cleanly, 1 if any row failed. Rows that
    succeeded still have their turn_norm counterpart committed either way.
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
    if result["skipped"]:
        print(f"  skipped {result['skipped']} rows with no normalizable record type")
    for failure in result["failures"]:
        print(f"  failed: turn_raw id {failure['turn_raw_id']} — {failure['reason']}")

    return 1 if result["failures"] else 0
