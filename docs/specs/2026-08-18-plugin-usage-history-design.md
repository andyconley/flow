# Plugin and skill usage history — design

**Date:** 2026-08-18
**Repo:** `andyconley/flow`
**Status:** implemented

## Why

Every flow surface measures what a session cost. None measured whether the
configuration that cost it was being used.

The immediate cause was a configuration prune decided on a number that was
accurate and misleading at once. A plugin was cut for "0 invocations" when its
counter actually read 3,552. Those were Stop-hook firings: the harness
increments a plugin's counter once per hook firing, so the number measured how
many hook events the plugin declared, not anything a person did. The decision
held on its merits and the reasoning behind it was wrong.

That is the governing requirement. This surface does not exist to report the
counters — it exists to make sure a hook firing is never read as a use.

It also clears a bar that `flow cost baseline` could not. Composition
attribution was cut from that work because a per-source token count could only
be guessed from character counts. These are values the harness measured itself.

## What the data actually is

Five properties, all verified on a real machine during planning, and nearly
every decision below follows from one of them.

| Property | Measured | Consequence |
|---|---|---|
| Counters increment per **hook firing** | one plugin declaring 5 hook entries moved +8 where a single-Stop-hook plugin moved +3 | the number is a property of plugin architecture, not intent |
| Opposite zero-semantics | `pluginUsage` 31 of 53 at zero (seeded at install); `skillUsage` 0 of 73 at zero (written on first use) | an unused plugin is a row; an unused skill is an absence |
| Doubled keys | `security-guidance@claude-plugins-official` 16,373 **and** `security-guidance@inline` 4,800 | one plugin, two counters, no verified relationship between them |
| Key drift | 40 of 73 skill keys resolve to no installed skill; 8 recoverable by name, 32 not | the map is history across naming regimes, not a registry |
| `lastUsedAt` is epoch **milliseconds** | every real entry | a reader assuming ISO text reads `None` and fails nothing |

The drift is not algorithmically recoverable. `humanize` is dead at 62 uses while
`humanizer` resolves at 39 — a rename, not a namespace change, and no string
rule recovers it. Some of the other 32 are genuinely uninstalled and *should* be
dead. Nothing in the data separates those two cases, which is why the surface
reports unresolved keys as their own fact rather than folding them into either
answer.

## The schema, and what is deliberately absent

One table of observations, one scan watermark, one index. Migration 6, additive.

**The UNIQUE key is over observed state**, `(harness, host_id, kind, name,
usage_count, source_mtime)`, not over observation time. Two writers watch this
file — a SessionStart hook and the harvest backstop — and nothing coordinates
them. Keying on when-observed makes every double-observation a duplicate row,
and worse, makes whichever writer arrives second compute its delta against the
row the first just wrote. Keying on content makes identity independent of
arrival order: same revision, same row, `INSERT OR IGNORE`, no-op.

**No `delta` column.** Delta is derived and only means anything once a series is
ordered by `source_mtime` — the harness's revision clock — rather than
`observed_at`, which is only when flow happened to look. Computed with `LAG` at
read time.

**No `enabled` column.** Enablement lives in `settings.json`: a different file,
a different writer, and on some machines a symlink into a dotfiles repo that
changes via `git pull` with the harness never involved. A row here means "the
harness reported this counter at this revision"; adding `enabled` would make
every row silently also claim something it cannot verify.

**`plugin_usage_scan` carries a `scope`.** Because `skillUsage` holds no zeros,
"which skills are unused" depends on enumerating installed skills, and that
enumeration is directory-dependent once project-local skills count. Without the
scope, a later read cannot separate "absent because never invoked" from "absent
because this scan never looked there".

## What the rendering must never do

- **Never put hook firings in the invocation column.** They live in their own
  block, the heading carries the caveat, and the word is "firings".
- **Never sum namespace variants.** Whether the two counters double-count or
  count disjoint invocations is unverified. The namespace is printed only where
  a base name has more than one variant, because a namespace truncated to fit a
  column disambiguates nothing — which is its only job.
- **Never drop unresolved keys.** Losing 55% of the evidence silently leaves
  output that looks clean.
- **Never report a thin history as a mature one.** The never-invoked plugin
  rollup is withheld until five snapshots span at least a week: a plugin at zero
  after two days is evidence of a short window. Elapsed time is part of the gate
  because the hook fires every session start, so five snapshots can land inside
  an hour and a count-only gate would call that mature.
- **Never classify a plugin that cannot be classified.** Hook status comes from
  the install directory, so a counter that outlived its plugin gets its own
  block rather than the benefit of the doubt in either lane.
- **Never claim a skill is unused without marking it inferred.** That figure
  comes from a directory walk, not from anything the harness reported, so it
  carries `~`.

## Two bugs this found in itself

Recorded because both are the same shape — a wrong answer that failed nothing.

**`lastUsedAt` read as `None` for all 127 entries.** The reader assumed an ISO
string; the harness writes epoch milliseconds. Every test passed. Mutation
testing was what caught that no test covered it, after the bug had already been
fixed by hand.

**An unmigrated store told every existing user "no usage counters exist to
sample."** The capability gate ran before the table check, and an *absent*
capability row was indistinguishable from one saying "unsupported". That
statement is false about Claude, and it sat on the first path every upgrading
user would hit. Found by running against the real v5 store rather than a
fixture. Absent and unsupported are now different answers.

## Found in review

Three of these are the same defect wearing different clothes: a plugin whose
provenance could not be established was quietly given the most favourable
reading available.

**Hook detection failed open.** Hook status was read from the plugin's install
directory, and a plugin with no such directory returned zero hooks — which
routed it into the deliberate-invocation column. Uninstalling a plugin is
exactly what removes that directory, so an uninstalled `ralph-loop` would have
rendered 3,552 hook firings as calls, uncaveated, at the moment someone
re-checked a prune. The tool would have reproduced its own originating error.
Hook status is now tri-state: `None` means "no install found, cannot tell", and
those plugins go to their own block rather than into either lane.

**Counter keys outlive their plugin, and only skills accounted for it.** The
unresolved-key bucket existed for `skillUsage` and not for `pluginUsage`, so a
departed plugin's last counter rendered forever as a live row with a stale date
— on the machine this was built against, roughly half the keys. The design's own
rule, implemented on one of two maps.

**A reset landed in the prune list.** A counter reset to zero satisfies
`usage_count == 0`, so it printed beside genuinely never-used plugins in the
list a person prunes from — while the reset caveat printed separately at the
bottom, attached to nothing. An earlier version of the test suite asserted this
behaviour, which is the more useful half of the finding: the test encoded the
bug.

Four smaller ones, all real: the plugin block truncated to five with no "and N
more" counterpart, in the one block a prune decision reads; the maturity gate
counted snapshots without elapsed time, and the hook fires every session, so
five could land in an hour; the inventory-scope footer selected an arbitrary row
from the scan table rather than the scope the number was computed from; and the
capability probe sat outside the `OperationalError` guard, so a store with no
`harness_capability` table escaped into doctor's catch-all as "unavailable" —
the absent-versus-unsupported collapse again, in different costume.

The security review found no secret reaching the store, the output, or any error
path, and confirmed the `turn_raw` verbatim-payload pattern was deliberately not
repeated. It did find that `observe_usage` parsed the config *before* comparing
the watermark, so the guard suppressed the insert but not the 150 KB parse — the
whole cost the design existed to avoid, with every row-count assertion still
passing. It also asked for two things now done: control characters stripped from
displayed names, since a cloned repo can ship a project-local skill whose name
repositions the cursor in output someone is reading to make a decision, and the
inventory scope rendered home-relative, since doctor output gets pasted into
issues.

## Structure

```
claude_config.py   pure stdlib readers, every path a parameter
      ↑
plugin_usage.py    snapshot, read model, renderer
      ↑
diagnostics.py · harvest.py · flow.py
```

One-way imports. Nothing in `cost.py`'s tree imports this or is imported by it —
`harness_supports` is duplicated rather than imported from `baseline.py`,
because six lines is cheaper than putting this module on the live
`verdict`/`warn` hook paths.

`flow doctor` renders the section but never writes, matching its existing
contract that a diagnosis must not repair the condition it reports. The write
path is `flow plugin-usage snapshot`.

## Testing

60 tests across two classes, built against a real fake home on disk rather than
mocks: most of what this can get wrong is a disagreement between two files
written by two processes, and a mock of either side cannot disagree with the
other the way real files do.

Twenty mutations, each caught, none surviving: disabling the mtime guard; ordering
the `LAG` by `observed_at`; dropping the reset guard; skipping the capability
gate; dropping the hook label; treating an absent skill as never-installed;
collapsing namespace variants; dropping the unresolved-key bucket; rejecting the
epoch-ms timestamp; accepting a boolean counter.

## Out of scope

- **Token attribution per plugin** — no local tokenizer; ruled out for
  `flow cost baseline` on the same reasoning and unchanged here.
- **Changepoint detection on usage** — no data exists yet to calibrate a
  threshold against. `baseline`'s thresholds took a real corpus to derive.
- **Backfill** — the harness keeps no history. Absolute counts inherited at
  first snapshot are archaeology; only deltas flow observed itself are sound.
- **Multi-host** — inherited deferral from the 2026-08-15 capture spec.
