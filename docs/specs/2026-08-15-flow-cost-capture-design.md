# `flow cost` capture fidelity — design

**Date:** 2026-08-15
**Repo:** `andyconley/flow`, branch `feat/cost-capture-fidelity` off `main` at `1b8408e`
**Status:** design approved, pending implementation plan

## Why

`flow cost` answers "which sessions need attention right now" well. It cannot answer
"is my session hygiene actually working," and three of its inputs are lossy or
inferred in ways the read surfaces do not disclose. A one-week adoption review had
to be done in hand-written SQL against `turn_norm` because no trend surface exists.

Measured against the Anthropic console for `2026-05-21 → 2026-08-14`, same account:

| | On disk | In `usage.db` | Console |
|---|---:|---:|---:|
| Assistant turns with usage | 56,145 | 28,788 | 76,707 requests |
| cache_read tokens | 15.97B | 8.89B | ~18.17B |
| output tokens | 61.4M | 27.2M | 40.7M |

## What the gap actually is

The obvious reading — "the collector drops half the tokens" — is wrong, and the
investigation that produced this spec started there. The real shape:

**One `requestId` is exactly one `message.id`, which is exactly one API call.**
Zero `requestId` groups span more than one `message.id` across 13,286 groups
checked. Multiple assistant lines under one `requestId` are content blocks of a
single streamed response, appended as they arrive:

```
requestId=req_011Cbux7QgYTa5qSx5m2Y2f9   (6 lines, all msg.id=gHL4Quwm5gn3)
  line8   stop=None       blocks=[text]      in=860 cr=21,424 cw=14,692 out=4
  line9   stop=None       blocks=[tool_use]  in=860 cr=21,424 cw=14,692 out=4
  ...
  line17  stop=tool_use   blocks=[tool_use]  in=860 cr=21,424 cw=14,692 out=487
```

Input fields are byte-identical on every line of a group. Only `output_tokens`
grows, reaching its final value on the line carrying `stop_reason`.

So `claude_collector.py`'s dedup rule — `natural_turn_id = requestId` plus
`UNIQUE (session_row_id, natural_turn_id)` and `INSERT OR IGNORE` — is **correct
for inputs and wrong for output only**. It keeps the first line, whose
`output_tokens` is a partial count. Aggregation strategies against the console:

| Strategy | cache_read | vs console | output | vs console |
|---|---:|---:|---:|---:|
| first (current) | 8.90B | 49% | 27.1M | 67% |
| last | 8.90B | 49% | 31.1M | 76% |
| max | 8.90B | 49% | 31.1M | 76% |
| sum | 15.97B | 88% | 61.4M | 151% |

Summing inputs triple-counts one request, which is why `sum` overshoots output by
51%. The correct rule is: **inputs from any line, output from the maximum.**

The residual — local sees 28,710 `requestId`s against 76,707 console requests, and
49% of console cache_read after the fix — is **not a collector defect.** It is
traffic that never touched this machine: Claude Code on the Web, the dev box, any
other host. That is the deferred milestone below, not this one.

## Scope

Staged. This spec covers items 1-5. Item 6 is recorded for shape only.

| # | Change | Surface | Re-harvest |
|---|---|---|---|
| 1 | Output upsert, highest wins | `claude_collector.py` | Yes, via watermark reset |
| 2 | 1h/5m cache-write split | `normalize.py`, `usage_store.py` | **No** |
| 3 | `flow cost trend` | `cost.py`, `flow.py` | No |
| 4 | Subagent dimension on trend and `active` | `cost.py` | No |
| 5 | Context-window resolution at read time | `cost.py`, `data/` | No |
| 6 | Multi-host capture | deferred | — |

## 1. Output upsert

`claude_collector.py` currently issues `INSERT OR IGNORE INTO turn_raw (...)`.
Replace with an upsert whose guard is the output count:

```sql
INSERT INTO turn_raw (session_row_id, natural_turn_id, turn_seq, is_subagent, ts,
                      model, payload, source_path, source_line_no, collector_version)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (session_row_id, natural_turn_id) DO UPDATE SET
  payload           = excluded.payload,
  source_line_no    = excluded.source_line_no,
  collector_version = excluded.collector_version
WHERE COALESCE(json_extract(excluded.payload, '$.message.usage.output_tokens'), -1)
    > COALESCE(json_extract(turn_raw.payload, '$.message.usage.output_tokens'), -1)
```

Design decisions:

- **`max`, not `last`.** The two differ by 2 tokens across the whole corpus, but
  `max` is order-independent and idempotent: replaying a file cannot corrupt a row,
  which is what makes the backfill below safe to run repeatedly.
- **`ts` and `turn_seq` are not updated.** They keep the first line's values — when
  the turn started. Stable under re-harvest, and it keeps a turn from migrating
  across a day boundary in the trend view because a response finished after
  midnight.
- **`COALESCE(..., -1)`** so a row with absent usage is beaten by any row with a
  real count, and two absent-usage rows do not update each other.
- SQLite's `json_extract` is used rather than parsing in Python because the
  comparison must happen against the *stored* row, which the collector does not
  hold. Available since SQLite 3.38; the environment reports 3.53.4.

`COLLECTOR_VERSION` goes 2 → 3.

**Backfill.** Reuse the mechanism the title-capture work established: zero the
`harvest` watermark (`last_offset`, `last_line_no`) for every Claude row, then run
`harvest_all` normally. Previously replay was a free no-op under `INSERT OR
IGNORE`; under the upsert it becomes a correction pass. `last_size` is not reset —
`harvest_file` recomputes it from `path.stat()`.

The existing flag is `flow harvest claude --backfill-titles`, whose name no longer
describes what it does. Add `--rescan` as the general name and keep
`--backfill-titles` as a hidden alias so any existing muscle memory or script keeps
working.

## 2. 1h/5m cache-write split

Claude's `usage.cache_creation` carries `ephemeral_1h_input_tokens` and
`ephemeral_5m_input_tokens`, which sum exactly to `cache_creation_input_tokens`
(verified across 20,587 turns, exact match). `normalize.py:169` already records
that these exist and are unextracted, and that the raw payload retains them — so
this is a normalization recompute with **no re-harvest**.

This matters because the two bill differently: 1h writes at 2.0× base input, 5m at
1.25×. Collapsing them into one column makes any cost estimate off by up to 60% on
the write component, and writes are a quarter of the bill.

- Schema `_V5`: add `cache_write_1h_tokens`, `cache_write_5m_tokens` to `turn_norm`,
  both nullable INTEGER.
- `cache_write_tokens` stays as the total. It is not redundant — it is what Codex
  reports, and it is what existing callers read. No consumer changes.
- Codex leaves both new columns NULL; update `data/harness_capabilities.json` to
  declare the split unsupported for that harness.
- `NORM_VERSION` goes 1 → 2, which makes every existing row stale and triggers the
  recompute automatically. This also picks up the corrected payloads from item 1
  without a second mechanism.

## 3. `flow cost trend`

```
flow cost trend [--days N] [--bucket day|week] [--harness claude|codex] [--json]
```

One row per bucket:

| Column | Definition |
|---|---|
| `turns` | main-agent turns |
| `sessions` | distinct sessions active in the bucket |
| `ctx/turn` | mean `fresh + cache_read + cache_write` per main-agent turn |
| `in:out` | total input over total output |
| `wt/1k out` | weighted tokens per 1,000 output tokens |
| `cuts/1k` | context cuts per 1,000 turns |
| `sub%` | subagent share of weighted tokens |

**Weighted tokens** collapse the input classes by billing multiplier: uncached 1.0,
cache read 0.1, 5m write 1.25, 1h write 2.0. These live in
`data/token_weights.json` so a pricing change is a data edit, not a code change.
Until item 2 lands there is no 1h/5m split to weight, so `trend` depends on item 2.

**Context cuts** are the compaction signal: a turn whose context is below 60% of the
previous turn in the same session, from a base above 100K. This is a heuristic for
`/compact` or a mid-session `/clear`, and the column header must say so.

`wt/1k out` is the headline efficiency number because it divides out how busy the
period was. Raw daily burn conflates working less with working leaner.

## 4. Subagent dimension

`turn_norm.is_subagent` is already populated (5,291 rows) and no read surface
exposes it. Subagent share of weighted tokens moved 4.8% → 12.9% over a window in
which main-agent context fell 41% — so part of any apparent improvement is work
relocating rather than disappearing.

- `trend` gains the `sub%` column above.
- `active` gains subagent burn attributable to each live session. Subagent turns
  share the parent's `sessionId` (per `claude_collector.py`'s own finding), so
  attribution needs no new identity work.

Rationale: `carry` measures the main session's window only. A metric that improves
when work is moved rather than eliminated will eventually be optimized the wrong
way, and the fix is to show both numbers side by side.

## 5. Context-window resolution

`turn_norm.context_window` is NULL for 100% of Claude turns (29,187 of 29,187);
Codex populates it 99.9% of the time from `info.model_context_window`. Claude
transcripts simply do not carry the field. Every Claude ctx% today therefore rests
on assuming a 200K window, and the `~`-prefix convention that the session-hygiene
guidance describes as an occasional caveat is in fact the only case that ever
occurs for this harness.

**Decision: do not write inferred windows into `turn_norm.context_window`.** That
column means "the harness reported this." Filling it with a lookup would destroy
the measured-versus-inferred distinction that the `~` marker depends on, and would
silently change the meaning of historical rows.

Instead: add `data/model_context_windows.json` mapping model id to window, resolve
at read time in `cost.py`, and keep `~` for every value that came from the table
rather than the transcript. Unknown models report the window as unknown and suppress
the percentage rather than guessing — an honest blank beats a confident wrong number
in a tool whose whole purpose is measurement.

## 6. Multi-host capture (deferred)

`harvest.host_id` exists, is plumbed through both collectors as a parameter, and is
`""` on all 867 rows because no call site passes anything. Populating it is a small
change; the real work is a sync path that brings other machines' transcripts into
one store, plus deciding whether Claude Code on the Web is reachable at all.

Until then, `flow cost` measures this machine. Any surface that reports absolute
totals should say so rather than implying completeness.

## Testing

The repo's fixtures do not currently exercise a multi-line `requestId` group, which
is exactly why the partial-output bug survived. Add:

- A Claude fixture with a 3-line `requestId` group, `output_tokens` 4 → 4 → 487,
  identical inputs. Assert the stored row has 487 and the inputs are counted once.
- The same fixture split across two harvest calls at the group boundary, asserting
  the upsert corrects the row on the second pass.
- Replay of the same file twice, asserting idempotence.
- A normalize test asserting `cache_write_1h + cache_write_5m == cache_write_tokens`
  on real-shaped input, and that both are NULL for Codex.
- A `trend` test over a fixture with a known context cut, asserting `cuts/1k`.

## Out of scope

- Changing `carry` or the 25%/45% bands. Personalized thresholds are a plausible
  follow-up but need a trend baseline to exist first, which is item 3.
- Model-routing advice. The largest single cost lever observed was model mix, and
  nothing in `flow cost` addresses it — worth a separate design, not this one.
- Dollar figures. Weighted tokens are the anchor here; converting to currency needs
  plan and rate data that the local store has no access to.
