# Structured Verifier Contract Requirements

## Problem or opportunity

The accepted Magentic route treats a completed verifier provider call as sufficient ordering evidence even when the returned prose is repetitive, unsupported, malformed, or does not express a usable verdict. Flow needs an explicit acceptance signal without reopening provider feasibility or producer routing.

## Audience

- Shapers and operators who approve a charter and inspect its handback.
- Flow maintainers who own policy, evidence, receipts, and compatibility.
- The Magentic Delivery Lead, which needs an unambiguous result from an approved verifier action.

## Desired outcome

Flow accepts a chartered job only after a distinct approved verifier returns a bounded structured verdict that Flow validates and binds to the exact Flow-observed producer diff and targeted-test evidence. Flow independently limits verifier calls.

## Requirements

1. Flow owns a closed, versioned verifier verdict and evaluation contract. The provider supplies candidate output; Magentic does not decide whether it is valid.
2. The minimal verdict contains a schema version, `pass` or `fail` decision, bounded summary, and bounded findings. A pass cannot contain blocking findings; a fail requires at least one finding.
3. Flow binds its evaluation to the verifier action, verifier input, raw output, observed diff, and targeted-test evidence using durable digests. The verifier is never represented as having inspected files it could not access.
4. A valid pass is necessary, but not sufficient by itself, for successful handback; all existing producer, ordering, scope, test, authority, and receipt checks still apply.
5. A valid fail makes the attempt terminal failed and preserves the findings. Missing, malformed, oversized, contradictory, replay-conflicting, or otherwise unusable verdict output makes the attempt terminal failed with a distinct stable reason.
6. A received provider response is observed and recorded before verdict evaluation. Unusable content remains a known completed provider call. Only transport uncertainty remains `unknown`.
7. Shaper intent and the Delivery Charter carry an independent, configurable `max_verifier_calls` allowance. The default is two total calls: one initial verdict and at most one retry. Flow projects it into the execution envelope and atomically denies excess verifier calls before provider send, even when the global delegation budget remains.
8. The verifier allowance is shared across approved verifier identities and remains separately observable from global delegation and paid-call counters in the receipt.
9. Existing protocol-v7 receipts remain readable with their historical meaning. New completion semantics use an explicit new or negotiated contract version chosen during `flow-solution`; they do not silently redefine v7.
10. The contract remains provider-neutral even though Ollama is the accepted first verifier provider.

## Success criteria

- Successful handback can be traced to one valid pass verdict over the exact supplied evidence.
- Negative and unusable verifier outcomes stop safely with truthful provider and attempt states.
- A second verifier proposal is denied before send when the sealed cap is one.
- Existing producer behavior and legacy receipt inspection remain compatible.

## Non-goals

- Re-proving Ollama availability or general quality.
- Semantic truth scoring, automated prompt tuning, retries, repair loops, quorum, or multi-verifier voting.
- Changes to producer selection, provider authentication, recovery of historical attempts, or nested subagents.
- General receipt redesign or a new scheduler.

## Constraints and assumptions

- Flow-observed diff and test evidence remain authoritative.
- Verifier work is read-only and limited to evidence supplied by Flow.
- At most one automatic verifier retry may occur after a valid fail or unusable verdict, subject to the sealed total-call cap. The second outcome is terminal.
- The solution should reuse existing charter, envelope, ledger, action, and receipt boundaries.

## Evidence

- The predecessor archive explicitly identifies structured verifier output and a verifier-specific call cap as the next follow-up.
- The live route proved Ollama dispatch but showed repetitive output and unsupported inspection claims, so the requirement is enforceability and evidence quality rather than provider feasibility.
- Archive retrieval selection `a5fb1606146fb0abb0ce9ec8a42d96cd26a59832b289421bc9be64e14d5d96a1` was unavailable; the accepted predecessor was manually inspected instead.

## Open decision

- `flow-solution` must choose the compatible versioning mechanism and exact placement of the Flow-owned evaluation record.

## Approval status

- Approved by the engineer on 2026-09-23.
