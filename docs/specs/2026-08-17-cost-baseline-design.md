# `flow cost baseline` — design

**Date:** 2026-08-17
**Repo:** `andyconley/flow`
**Status:** implemented

## Why

Every `flow cost` surface measures what a session *spent*. None measures what it
*started at*.

That opening cost is real and it is growing. On the machine this was built against it
measures roughly 21,000 tokens — system prompt, tool definitions, MCP server
instructions, agent and skill descriptions, `CLAUDE.md`, memory files — re-sent on every
request of every session. Roughly three-quarters of it came from installed plugins and
connected MCP servers, many of which had never been invoked once across 817 transcripts.

The defect is not any particular plugin. It is that enabling one is frictionless and its
cost is never shown, so the floor rises by accretion and nobody notices. A number that
nobody can see is a number nobody manages.

## The estimator

On a session's first turn there is no conversation yet, so `cache_read_tokens` is the
cached static prefix and nothing else. The opening user message and any SessionStart hook
output land in `fresh_input_tokens`, so they are excluded for free.

Two independent methods agree on the result, which is the main reason to trust it:

| Method | Result |
|---|---|
| Byte-count of the installed config on disk | ~21,000 tokens |
| `cache_read_tokens` on turn 1, 204 sessions | p10 20,568 · p25 21,094 · p50 22,379 |

The alternative estimator, `fresh + cache_read + cache_write`, qualifies more sessions but
includes the opening message and reads high (min 25,268, p10 30,016). It is not used.

**`cache_read_tokens = 0` means cache miss, not new conversation.** Anthropic's prompt
cache is keyed by prefix hash across the account rather than per session, so a genuinely
new session started soon after another with the same prefix reads the entire prefix from
cache. An earlier draft treated cache-cold sessions as the clean population and got this
exactly backwards; cache-warm first turns are the ones carrying a reading.

## Why p10 and not p25

The approved plan specified p25. Measurement against the real corpus overturned it.

Prefix readings are not a distribution. They are a small number of exact, repeated
plateaus, because the cache returns an identical value for every session sharing a
prefix — one week had all 13 of its sessions read exactly 22,489, another had all 41 read
exactly 21,830.

A mid-range quantile over plateaus tracks the *mix* between configurations, not the
floor, and moves discontinuously when the mix shifts. Measured:

| Week | n | min | p10 | p25 |
|---|---:|---:|---:|---:|
| 2026-07-27 | 13 | 22,489 | 22,489 | 22,489 |
| 2026-08-03 | 22 | 22,595 | 22,595 | **30,382** |
| 2026-08-10 | 41 | 21,830 | 21,830 | 21,830 |

p25 invents a +35% spike and a −28% return across weeks in which no configuration
changed. p10 is flat there, and is identical to the minimum in every measured week —
the plateaus repeat, so nothing sits below the lowest one. p10 rather than a bare
minimum only to absorb a single freak low reading.

It is also the semantically correct statistic. The floor is the leanest prefix a session
actually started from, not a typical one.

## Population rules

Four, each removing a distinct way a turn can look like a first turn without being one:

1. **minimum `turn_seq` among non-subagent turns.** `turn_seq` is the transcript line
   number — `claude_collector.py` passes the same value for `turn_seq` and
   `source_line_no` — so it orders correctly but does not start at 1, and a subagent turn
   can precede the main thread's first turn in the file.
2. **`source_line_no` at or below `line_threshold`.** A larger value means the collector
   first attached partway through the file, so its earliest row is mid-conversation and
   its `cache_read` is conversation, not prefix.
3. **no `compact_boundary` at or before the turn.** A compacted session resumes with a
   summary already in context. Applied only where the harness can report the event.
4. **`cache_read_tokens > 0`.** Zero is a cache miss carrying no reading, not a session
   whose prefix is empty.

Rule 2 is not cosmetic: applying it moved the qualifying population from 204 sessions to
166, and shifted one week's estimate by 7,000 tokens. A threshold calibrated without it
was calibrated against the wrong population.

## Changepoint detection

The floor is a step function in principle. In practice the estimate wanders, so a naive
detector fires on noise, and a detector that cries wolf is worse than none.

A move registers only when it clears **both** 15% and 2,500 tokens. Either bound alone
misfires at one end of the range — a percentage on a small floor, an absolute on a large
one.

Calibrated against 166 sessions over 8 reporting weeks. The p10 series ran 14,632 /
20,131 / 21,094 / 20,568 / 22,489 / 22,595 / 21,830 / 21,830. Its first move (+5,499,
+37.6%) is real — the floor growing as plugins accumulated. Every later move is wander:
+4.8%, −2.5%, +9.3%, +0.5%, −3.4%, 0.0%, a largest absolute move of 1,921 tokens. The
thresholds sit between the two.

**The consequence is a limitation and the surface says so.** A change below threshold is
undetectable. One plugin quietly returning at ~500 tokens will not appear. This detects
deliberate reconfiguration, not gradual creep.

Parameters live in `data/baseline_thresholds.json`, matching the `token_weights.json`
precedent: calibration is a data question, not a per-invocation one.

## Grouping

Pooled across projects by default; `--by-cwd` available.

Grouping was the plan's default and the data disagreed. 166 observations spread over 24
directories left only three with 20 or more and 20 with fewer than five, so grouping
blanks most of the table. It is also unnecessary: the three directories with enough
observations agreed to within 6% (20,568 / 20,737 / 21,830), because the floor's dominant
contributors — plugins, MCP definitions, agent and skill descriptions, the global
`CLAUDE.md` — are the same everywhere. Per-project `CLAUDE.md` is a rounding error.

## Structure

Read-time only. No schema change, no `normalize.py` change, no `NORM_VERSION` bump, no
re-harvest. Every input already existed in `turn_norm`, `turn_raw.source_line_no`, and
`agent_activity_raw`.

`cli/baseline.py` is a new module importing from `cost.py` in one direction only.
**`cost.py` is not modified by this work at all**, which is what keeps the change off the
live `verdict` and `warn` hook paths — nothing here can regress them. `_percentile` is
defined locally rather than by generalizing `cost._median` (50th percentile only) for the
same reason: widening a function those hooks reach would move this feature's risk onto
their path for no behavioural gain.

`data/harness_capabilities.json` gains `compact_boundary` (claude 1, codex 0). Codex
records no equivalent event, so its population cannot be filtered for compaction and the
render says so rather than implying a filter that never ran.

No `~` markers anywhere. Unlike an inferred context window, every figure here is a value
some session actually reported; spending the convention on measured output would weaken
it where it carries real meaning.

## Testing

Twenty-three tests. Each population rule is proved independently, including the two
easiest to get backwards: compaction excludes only at or before the turn rather than
anywhere in the session, and the rule is skipped entirely on a harness that cannot report
the event rather than silently filtering nothing.

The load-bearing test is negative. The measured week-to-week series, with its one genuine
move removed, must produce zero changepoints.

One gap found by mutation testing and closed: `thresholds()` resolves through
`SOURCE_DIR`, which points at the install rather than the checkout, so in every test
environment it falls back to the in-code defaults and the shipped JSON is never read.
Loosening the data file would have left the suite green. A separate test now reads
`data/baseline_thresholds.json` from the repo directly and asserts both bounds stay above
the measured wander.

## Out of scope

- **Composition attribution** — which plugin or MCP contributes how many tokens. There is
  no local tokenizer, so a per-source count cannot be computed, only guessed from
  character counts, and it would render beside measured values. If it ships later it
  belongs on a `flow doctor`-adjacent surface, never as a column here.
- **Multi-host capture** — inherited unchanged from the 2026-08-15 capture spec. This
  measures one machine and says so.
- **Sub-threshold drift detection** — excluded by construction, not by omission.
