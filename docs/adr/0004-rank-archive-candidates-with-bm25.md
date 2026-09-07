# ADR 0004: Rank archive candidates with query-time BM25

- Status: accepted
- Date: 2026-09-06
- Decision owner: repository owner
- Related work: archive-retrieval, stages 1–5
- Scope: ranker, storage boundary and FTS5 availability posture; remaining solution contracts are not approved by this ADR

## Context

Flow needs bounded retrieval of prior decisions for define and solution. Current
and ancestor project overlays are searched by default. The indexes are derived
and project-owned; run artifacts remain authoritative. Selecting a lexical
ranker must not quietly turn those indexes into one shared persistent corpus.

FTS5 was originally shorthand for dependency-free lexical retrieval. The initial
choice preceded ancestor-by-default search and did not evaluate a Flow-owned
ranker. BM25 and TF-IDF both depend on corpus statistics; scores independently
computed within overlay indexes cannot be treated as globally comparable.

A bounded experiment compared weighted unique-term coverage, Python TF-IDF and
FTS5 BM25. SQLite storage was held fixed. TF-IDF computed document frequency over
all merged post-filter eligible documents, not per-index or only matching hits.
BM25 used one temporary table containing that same eligible corpus.

The three-way extension used 52 abstracts and 27 queries, 21 involving ancestor
or cross-overlay behavior. Most were synthetic; four abstracts were adapted
from archived Flow artifacts. The initial two-ranker run had already been seen.
A stopping rule was frozen before the three-way extension was scored, and
independent review checked the method and selection arithmetic.

## Decision

Use FTS5 BM25 behind the query/filter/cap interface. Retain ordinary SQLite
projection storage per project overlay. Filter the selected sources first, then
assemble their eligible records into a transient query-time FTS table with one
set of corpus statistics. Never combine per-index BM25 scores. Never persist
an aggregate ancestor corpus into a child projection.

**The per-overlay storage boundary held through the ranker reversal.** The
shared statistics exist only for the query; they do not change data ownership,
canonical artifacts or projection-rebuild boundaries. SQLite is the store;
FTS5 BM25 is the chosen scorer, not the storage format.

Keep the ranker swappable. Coverage and merged-post-filter TF-IDF remain in the
comparison harness for a future evidence-based revisit, including if a real
environment makes FTS5 impractical. They are not runtime fallbacks.

### Why BM25 won

Of 45 expected query-target occurrences, five had no shared query vocabulary
and were missed by every ranker. For the remaining 40:

| Experimental budget | Coverage | TF-IDF | BM25 |
| --- | ---: | ---: | ---: |
| Top 5, 8192 UTF-8 bytes for the full response | 37/40 | 37/40 | 40/40 |
| Top 3, 4096 UTF-8 bytes for the full response | 35/40 | 37/40 | 37/40 |

The winning margin is **three synthetic cases at positions four and five**:
child overlay scope, broad mixed search vocabulary after component filtering,
and an unknown-conditions abstract competing with recent archive wording.
This is thin evidence. It is not proof of general relevance or precision.

The frozen rule first compared plausible false-positive cases withholding
required targets, then expected targets lost under the generous primary cap,
then losses under the tighter cap. Exact ties favored coverage, then TF-IDF,
then BM25 for maintenance and portability. Observed tuples were (0,3,5),
(0,3,3), and (0,0,3), respectively. Rule 7 required stopping after the fixed
extension and review even when the margin was small. BM25 was selected per
that rule, rather than extending the comparison until a preference won.

The 8192/4096-byte ceilings were experimental controls, not approved production
token defaults. Changing tokenization or materially changing corpus/filter
behavior requires rerunning the comparison before claiming that this result
transfers.

### Availability is explicit

FTS5 unavailable is a hard failure for retrieval, not for Flow. Probe using the
actual selected interpreter during install/update and in `flow doctor`. Do not
defer normal capability discovery until lane execution. The diagnostic names
the missing FTS5 capability, interpreter/SQLite build and the supported
FTS5-enabled Python build/package to install or select.

Flow installation, archive closure, define and solution remain usable without
automatic retrieval. Doctor reports retrieval unavailable while retaining its
advisory Flow-wide exit behavior for this condition. A direct retrieval command
returns an unavailable result with a nonzero status; it must not return empty
success or switch to a Python ranker. Machine-dependent ranking would make
results and debugging less trustworthy.

Existing installations without current preflight evidence are directed to
`flow doctor` before automatic retrieval. Queries still fail safely if an
interpreter or environment changes after preflight; that defensive check does
not replace install/doctor detection. The environment matrix must identify
supported interpreter/build combinations, verification evidence and which need
an FTS5-enabled build installed or selected. Unknown cells stay unverified.

### Applicability and tokenization remain Flow responsibilities

BM25 returned labelled plausible-but-inapplicable precedent in eight cases,
compared with seven for TF-IDF and five for coverage at the primary budget.
None displaced an expected matching target in those cases, but extra precedent
is real review burden. Visible conflict and inapplicability disposition is
therefore essential. Stage 5 must inject a plausible current hit that does not
apply and assert the lane rejects it with source evidence rather than deferring
to it. Returning the right target alongside the wrong precedent is insufficient.

The five shared misses remain source, query or tokenizer problems. Route them
to stage 1 abstract-quality evaluation and the explicit tokenization decision.
Preserve source-supported terminology without inventing aliases. Identifier
confusion and vocabulary drift belong there too. The prototype split AE-743
into ae and 743, permitting AE-744 to rank above it under coverage and BM25.
Selection of BM25 does not accept that behavior as a finished tokenization
contract, nor does it resolve a no-overlap semantic paraphrase.

## Alternatives considered

- Weighted term coverage: smallest owned scorer and no optional extension;
  lost three rankable targets at the primary budget. Kept in the harness.
- Python TF-IDF with query-time post-filter DF: globally comparable without an
  FTS table; improved tight-cap results over coverage, but retained the same
  three primary-budget misses. Kept in the harness.
- Independently scored overlay results: rejected because local corpus statistics
  are not one ranking space.
- A persisted child-owned aggregate index: rejected because it duplicates
  ancestor data and introduces descendant invalidation and ownership problems.
- Automatic fallback: rejected because the same query must not silently change
  scoring semantics according to machine capabilities.

## Consequences and owned follow-up

- Flow maintainer owns install/doctor detection, a concrete remedy matrix and
  containment of retrieval failure. Only one macOS/Homebrew FTS5 environment
  was exercised by the experiment; broader certification remains work.
- Implementation lead owns transient corpus assembly and source freshness.
  Reference timing at about 9400 eligible replicated records was approximately
  75 ms for BM25, including in-memory SQLite selection/loading and assembly.
  That excludes disk/freshness checks and is not a production latency promise.
- Solution architect owns the explicit tokenization decision and comparison
  rerun when semantics change. Source-quality improvements cannot fabricate
  facts just to recover missed query targets.
- Test engineer and lane owners own the stage 5 false-positive and genuine
  conflict cases in both runtime adapters. The comparison did not test live
  lane judgment or transcript behavior.

## Evidence

The run retains the executable harness, original and corrected fixtures,
prewritten extension stopping rule, input hashes, complete results, repeat run,
selection calculation and independent review under
`.flow/runs/archive-retrieval/research/ranker-comparison/`. Those run-local files
may not be distributed with the repository; this ADR retains the method,
counts, limits and decision rationale needed to understand the choice.
