# ADR 0021: Automatic review handoff

## Status

Accepted

## Context

A successful Delivery execution currently stops at `handback_ready`. An operator must issue a second `start-review` transition even when Flow already holds a completed protocol-v8 receipt, a bound `valid_pass`, and current Delivery Lead authority. The split is useful for audit and recovery, but the manual coordination step is not.

Handback validation also historically treated every assignment output as a standalone file. That creates placeholder reports when a sealed execution receipt is the canonical evidence.

## Decision

Flow exposes `flow run handoff-to-review` as a Flow-owned, recoverable two-step operation:

1. Verify the explicitly named completed v8 attempt, its offline receipt checks, the active Delivery Lead generation, and sealed `handoff_to_review` charter authority.
2. Project immutable implementation evidence, handback, and review-input inventory under the run.
3. Apply the existing `mark-handback-ready` transition.
4. Apply the existing `start-review` transition.

`handback_ready` remains a durable checkpoint. A retry from that state performs only review entry; a retry from `reviewing` is a no-op success. Both existing lifecycle events remain in history. The operation never creates a review verdict or invokes `accept-review`.

Lifecycle authority is an explicit, versioned Shaper Contract and Delivery Charter field. Older contracts remain readable but do not authorize automatic handoff.

Orchestration outputs may declare `kind: receipt-backed`. Such an output is satisfied only by the latest sealed, offline-verified, completed v8 receipt; ordinary outputs retain file-existence checks.

## Consequences

- Delivery can route successful work into independent review without another operator command.
- Partial failure after handback is visible and safely resumable.
- Review acceptance and archive remain separate gates.
- New automatic handoffs require a version-5 charter with explicit authority.
- Receipt-backed output declarations avoid synthetic manager or verifier files while retaining fail-closed verification.
