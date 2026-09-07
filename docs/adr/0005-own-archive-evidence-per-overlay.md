# Own canonical archive evidence per overlay

Status: accepted by the engineer during archive-retrieval solution approval.

## Context

Archive retrieval must preserve decision authority across overlay moves, partial
writes, derived-index rebuilds and ancestor search. Lexical similarity cannot
establish applicability or supersession. Archive closure must survive enrichment
failures. ADR 0004 records the separate scorer and storage decision.

## Decision

Allocate a durable UUID in each overlay's identity.json during an authorized
setup/archive/backfill write. Qualify run and component identifiers with that
UUID. Moves and clones preserve identity; duplicate logical sources in one
physical context are quarantined. Missing identity with retained qualified
evidence requires restoration, never automatic retargeting.

Keep one current abstract.json envelope per run, with generated content,
declarations, refinement and provenance owned separately. Deterministic offline
extraction selects final source passages and marks absent facts unknown.
Refinements cannot rewrite identity, closure or supersession. Preserve replaced
refinements immutably and reject stale base consent. When generated content
changes, retain old refinement but serve the fresh generated view with an
explicit stale-refinement diagnostic.

Record explicit whole-run supersession through a canonical declaration digest
anchored by the normal lifecycle closure event. A prepared envelope without a
matching closure event cannot establish authority. Same-source and upward edges
apply in the declaring context and descendants. Resolve the full context graph
before candidate filters, including valid controls without searchable prose.
Cycles, missing evidence and changed anchors produce uncertainty rather than
silently suppressing or resurrecting decisions.

Runstate remains the sole lifecycle writer. Publish controls, complete closure,
then attempt generated prose, projection and coverage independently. Coordinate
archive writers per overlay and revalidate source/base digests before publication.
Canonical publication uses contained paths, atomic replacement and durability
checks. Queries observe source fingerprints and never repair ancestor state.

SQLite projections and coverage are disposable observations under .flow/.cache/.
Doctor reads cached coverage without scanning history; its narrow write exception
is a machine capability receipt after its actual FTS5 probe. Retrieval advisories
do not change the Flow-wide doctor exit posture.

Bound the complete serialized response by UTF-8 bytes: define 5 hits/16384 bytes,
solution 8 hits/32768 bytes. These are not measured model-token counts. A future
supported tokenizer contract requires versioned accounting and recalibrated
budgets. Preserve essential conditions and warnings; report no-fit explicitly.

## Alternatives and consequences

Path and Git-remote identities were rejected because they drift or conflate
overlays. Separate control/prose/refinement files remain possible if ownership
pressure warrants them later, but introduce multi-file publication complexity.
Automatic persistent repair on query was rejected because reading child history
must not mutate ancestors. Whole-run supersession is deliberately conservative:
partial reversals keep both records and require a source-backed lane explanation.

Source hashing costs query-time I/O. Explicit repair adds operator work. UUID
restoration, invalid control data, stale refinement and partial search need clear
diagnostics. Tests of storage/ranking do not certify actual Claude/Codex judgment;
the release requires source-linked conflict and inapplicability dispositions on
both lane surfaces, plus verified runtime/build evidence.
