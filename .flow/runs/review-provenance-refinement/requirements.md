# Requirements: Review Provenance Refinement

## Problem

Flow correctly rejects acceptance when a sealed orchestration manifest has incomplete producer provenance, but a run already in review has no supported way to approve a constrained correction without overwriting historical authority. This blocks `maf-runtime-readiness-2` even though the defect is known and bounded.

The planning guidance also says bug-shaped work can remain in `flow-plan`, while the lifecycle requires an approved definition or solution before `start-plan`. This run will follow the enforced prerequisite and correct the misleading guidance; it will not weaken delivery authority.

## Required outcome

1. Add one explicit review-only approval event for a constrained orchestration amendment.
2. Preserve the original manifest bytes, path, approved digest, and Delivery authority.
3. Approve a separate content-addressed replacement manifest and acceptance-disposition artifact with digest-chained lineage.
4. Permit only verification corrections and appended read-only review assignments with run-local outputs.
5. Bind explicit AC2 and AC13 dispositions for `maf-runtime-readiness-2` to its original acceptance-criteria digest.
6. Make dispatch, verification, and acceptance resolve and validate the approved effective review manifest while Delivery evidence remains bound to the original.
7. Correct the bounded MAF ADR/support-evidence discrepancies and planning guidance identified in review.
8. Use the capability to complete fresh independent review and, only if all gates pass, accept and archive `maf-runtime-readiness-2`.

## Constraints

- Amendment is legal only from protocol-revision-2 `reviewing` state.
- Original approved artifacts are never rewritten or repointed.
- Invalid, stale, conflicting, repeated, out-of-state, unsafe, or tampered amendments fail without lifecycle writes.
- No general post-approval requirements editor, multi-generation amendment framework, macOS baseline repair, or broader MAF redesign.

