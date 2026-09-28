# Plan: Review Provenance Refinement

## Desired outcome

Enable a provenance-blocked reviewing run to approve one constrained, auditable orchestration correction and explicit acceptance dispositions without rewriting original Delivery authority, then use it to complete the MAF review.

## Slice 1: Lifecycle and artifact contract

- Add `approve-review-amendment` as a same-state `reviewing -> reviewing` transition.
- Define content-addressed replacement-manifest, disposition, and amendment-record schemas.
- Preserve canonical original artifact pointers and approved digests.
- Add atomic validation, idempotent replay, stale/conflict refusal, and append-only event evidence.

## Slice 2: Effective review orchestration

- Add an effective-manifest resolver used only by review dispatch, review verification, and acceptance.
- Restrict replacement deltas to verification corrections and appended read-only reviewers.
- Keep all Delivery authority and historical execution evidence bound to the original manifest.
- Extend `verify`, status diagnostics, and acceptance events with amendment identity checks.

## Slice 3: Proof and compatibility

- Add lifecycle/CLI tests for every legal and illegal state.
- Add tamper, unsafe-path, symlink, digest-chain, replay, conflict, and atomic-failure tests.
- Prove no-amendment revision-2, revision-1, and legacy compatibility.
- Prove dispatch and acceptance use the effective manifest while Delivery evidence remains unchanged.

## Slice 4: Apply to the blocked MAF review

- Prepare the constrained replacement with complete producer provenance and fresh read-only reviewer assignments.
- Record AC2 and AC13 dispositions against the original acceptance-criteria digest.
- Correct ADR 0020, installation-time wording, unsupported-host activation status, and planning guidance.
- Dispatch fresh quality, test, security, and SRE reviewers against final HEAD and amended criteria.
- Re-run acceptance validation; accept and archive only when every gate passes.

## Boundaries

- Do not add general artifact amendment, multiple amendment generations, or non-review amendment states.
- Do not repair the unrelated macOS process/cancellation baseline.
- Do not redesign the v0.38 bridge or broaden MAF behavior.
- Do not add a direct `<new> -> planning` shortcut. Record `start-bug-plan` as a follow-up design opportunity.

