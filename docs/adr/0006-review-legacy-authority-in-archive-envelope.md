# Reviewed legacy authority inside the archive envelope

Status: accepted, 2026-09-07. Solution and three-chunk plan accepted by Andy.

## Context

R27/S6.1–S6.4 require reviewed legacy import without invented canonical closure.
Andy permits same-person review and local/external evidence, and requires
withdrawal. ADR0005 already selects one current envelope per qualified run.

## Decision

Use schema2 reviewed-legacy envelopes with independently versioned review controls
and immutable complete prior review revisions. Validate current authority
separately from generated prose. Keep canonical schema1 and lifecycle writer
unchanged. Use distinct eligibility adapters above common source extraction.

Reviewers retain evidence of final outcome and closure plus interpretation;
external evidence is locally captured with URL and time. Flow verifies local
bytes, not remote truth. Reviewer identity is declared and may be the author.
Closure date remains unknown when the evidence cannot establish it.

Withdrawal is a new durable review revision. Exact action retries use the full
validated chain and report latest state without restoring the old action.
Derived observation may invalidate approved evidence but never writes a review.
Index/coverage/prose failure cannot undo a committed withdrawal. Ambiguous
post-replace durability has an explicit uncertain outcome and readback.

## Alternatives

A per-run append-only review journal offers straightforward event reconstruction
but adds another durable authority source and reconciliation with the envelope.
There is no demonstrated ownership or volume need to change ADR0005. Retained
review IDs/digests allow a later governed split if evidence supports it.

## Consequences

Envelope validators and history handling gain complexity; complete history and
evidence inspection add I/O. Pure reducers, expected-base checks and staged fault
tests make behavior testable. Captures can preserve false or outdated external
claims; reviewer interpretation remains explicit and future remote refresh is
outside this delivery. No global store, network dependency or lifecycle rewrite.

Generated-only failures use explicit per-run import rescan with current consent.
Rescan preserves review/history and cannot grant approval. Canonical backfill stays
canonical-only. See [operator contract](../archive-legacy-import.md).
