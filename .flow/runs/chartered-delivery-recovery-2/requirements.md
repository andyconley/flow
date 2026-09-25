# Requirements: Chartered v8 Delivery Recovery, chunk 2

Status: **approved by the engineer on 2026-09-24** (revised after adversarial review).

- **Parent run:** `chartered-delivery-recovery` (archived). Chunk 1a merged as PR #26. Chunk 1b (`chartered-delivery-recovery-1b`) was archived, and its PR #29 is open. This run carries the parent's requirement 4 ("no resend of uncertain calls") and its chunk 2 criteria. The one exception is operator-authored response import: decision C1 below narrows parent risk R3's mitigation to Flow-owned evidence, as ADR 0012 requires. The parent's `requirements.md`, `solution.md`, and `research/plan-architecture.md` §5 remain the source of truth for everything else.
- **Why a linked run:** there is no lifecycle path from `review_accepted` back to `implementing` (E1, 2026-09-23).
- **Base:** stacked on `codex/chartered-delivery-recovery-1b`, then rebased onto `main` once #29 merges (engineer, 2026-09-24).
- **Adversarial review:** `adversarial-review.md`.

## Problem

- **Who is stuck.** After chunk 1, a v8 attempt with a manager call, producer send, or verifier send left `started` or `unknown` is refused with `reconciliation_required`. It stays blocked until it is abandoned, and it also blocks every lead change (1b L1).
- **Flow may already hold the evidence.** In many of these cases Flow already has the evidence to continue safely, and nothing lets it be used:
  - `resolve-execution` refuses v8 (`cli/execution_gateway.py:911-913`).
  - There is no ledger record for resolving a manager call. `recovery_resolutions.action_id` references `actions` (`cli/execution_ledger.py:101`).
  - `claim_chartered_recovery` refuses any unresolved row (`:495-498`). So the chunk 1 claim cannot fence a resolution, and a v5-style unconditional generation bump would break the v8 recovery chain. It would record a spurious `unmarked_process_exit` (`:508-512`), and the receipt validator would treat the generation as outside the chain (`execution_contracts.py:404-431`).
  - A validated response that is already durable in `response_observations`, but whose completion was interrupted, has no path to completion for v8.
- **Some cases remain blocked after chunk 2.** A claimed send whose response Flow never captured cannot be completed: ADR 0012 accepts that "a physically successful call can remain blocked if its response was lost". It cannot be marked not dispatched either, because a claimed send has crossed the fenced send boundary. Abandonment remains the only remedy (C1, C2).

## Engineer decisions (2026-09-24, after adversarial review)

- **C1. Flow-owned evidence only.** Chunk 2 resolves only from evidence Flow itself captured:
  - durable `response_observations` rows;
  - manager-call observations;
  - Flow-captured provider traces, following the v5 `recover_delivery` precedent.

  Operator-authored response import is out of scope and needs its own decision and an ADR 0012 amendment. There is no ADR 0012 change in chunk 2.
- **C2. The v8 no-dispatch regrant is guarded, not built.** `regrant_not_dispatched` refuses v8 attempts. A v8 action cannot reach `resolved_not_dispatched`: chunk 1 already re-grants unconsumed grants, and a claimed send cannot qualify under ADR 0012. Parent AC8's no-dispatch half, and the 1b carry-over of counting the lineage there, are deferred together with Q1.
- **C3. Carried hardening stays in chunk 2.** This covers `send_lock` O_NOFOLLOW and MAF tests that read `FLOW_MAF_PYTHON`. The engineer kept them here over the product review's suggestion of a separate prerequisite PR.
- **Carried from the intake (2026-09-24):**
  - stack on 1b;
  - own the 1b carry-overs, observation-backed reconcile, the MAF path fix, and `send_lock` O_NOFOLLOW;
  - targeted adversarial review.

## Requirements

1. **v8 resolution route.** `resolve-execution` accepts a non-terminal v8 attempt.
   - **Fence invariant.** Under the delivery authority guard (`run_lock`) and the attempt's `recovery_lock`, a `started` row is provably not live and may be resolved.
   - **Chain continuity.** The route compares against a caller-supplied expected generation. Whether it bumps the owner generation and how it extends the recovery chain are `flow-solution` choices, but the chain must stay continuous and each resolution must carry its generation.
   - **Refusals.** The route refuses with stable reasons, mutating nothing, when:
     - the attempt is terminal;
     - a live run holds the attempt (`attempt_running`);
     - the lead generation is stale;
     - the item is not unresolved;
     - the evidence is insufficient.
   - **Unchanged.** v5–v7 resolution behaves exactly as today.
2. **Resolution from Flow-owned evidence (C1).** An `unknown` or `started` action may be resolved as `resolved_completed` only from a Flow-owned durable response observation, or a Flow-captured provider trace, that validates against the original envelope and action. A verifier response is then evaluated under the v8 contract, bound to the exact evidence.
3. **Manager-call resolution.**
   - A `started` or `unknown` manager call can be resolved as `resolved_completed` from Flow-owned evidence.
   - The resolution goes in a new, append-only record bound to the call id, the attempt id, and the owner generation, with a unique key.
   - Recording the observation and the resolution is atomic, so a crash never leaves a completed call without a resolution.
   - A replay with the same content is idempotent, and a conflicting replay is refused.
4. **Resolution binding at continuation (parent AC5).** Recovery treats an unresolved item as unblocked only when a resolution matches the item kind and id, the attempt, and a generation in the attempt's recovery chain. The recovery chain is the envelope's lead-claim generation plus each `attempt_recoveries.generation` for that attempt, all at or below the current owner generation.
5. **Continuation after resolution.** After `resolved_completed`, recovery continues with zero resends, from the resolved response.
6. **Observation-backed reconcile.**
   - An action whose validated Flow-observed response is durable, but whose completion was interrupted, is reconciled with zero resends.
   - Operator-confirmed reconcile is the default and needs no ADR change. Automatic reconcile would need an ADR 0016 amendment, because eligibility is decided on a read-only snapshot. `flow-solution` chooses.
   - Reconcile never uses anything other than Flow-observed evidence.
7. **Lead changes after resolution (1b E2).** Once every uncertain send is resolved, a lead resume or supersede is no longer blocked by those rows. An `unknown` manager call alone blocks a lead change.
8. **v8 no-dispatch guard (C2).** `regrant_not_dispatched` refuses a v8 attempt with a stable reason. v5 behavior is unchanged.
9. **Truthful receipt (parent AC10).** The receipt's `recovery.resolutions` includes manager-call resolutions. The recovery-block builder and the validator count both action and manager-call resolutions. Receipt validation rejects an added resolution and a removed resolution.
10. **Inspection and operator guidance.**
    - A `reconciliation_required` refusal names the blocking items and points to `inspect-delivery`.
    - For each blocker, `inspect-delivery` names the route that applies and the Flow-owned evidence it needs, or states that the item is unresolvable and can only be abandoned.
    - It lists the resolutions relied on.
11. **Carried hardening (C3).**
    - `send_lock` opens its lock file without following symlinks.
    - Every MAF-gated test resolves its interpreter from `FLOW_MAF_PYTHON`, so the merge gate cannot pass by silently skipping.

## Success criteria

- A v8 attempt blocked only by rows for which Flow holds a durable response can be resolved and continued with `resolve-execution` followed by `recover-delivery-lead`, with zero resends.
- Zero duplicate provider sends across the v5–v8 suite. The mutation checks in AC12 hold.
- An operator can tell from `inspect-delivery` alone, for each blocker, whether it is resolvable and how, or whether abandonment is the only remedy.

## Non-goals

- Operator-authored response import, and any change to ADR 0012 (C1).
- Resolving a claimed send as not dispatched (Q1, kept impossible), and the v8 no-dispatch regrant (C2).
- Authenticating the operator. `actor` is attribution only, and the trust boundary is the local uid.
- Automatic discovery of provider-side send evidence, and provider exactly-once guarantees (parent non-goal).
- A CLI command for Delivery Lead resume or supersede.
- Any change to v5–v7 recovery semantics.
- CI for the MAF-gated tests.

## Constraints

- Dependency-free C-lite run protocol. Ledger migrations are tolerant and additive; there is no table rebuild.
- The lock order stays `recovery_lock`, `run_lock`, `send_lock`, then SQLite.
- ADR 0012 is unchanged. Any ADR 0016 change is recorded as an amendment.
- Hermetic tests only, and the MAF-gated tests run locally with 0 skipped.

## Assumptions

- **A2 (confirmed by architecture review).** Manager calls need only `resolved_completed`.
- **A3 (confirmed, with a caveat).** A unique index on `recovery_resolutions(action_id)` matches the lookup at `:1265`. Existing ledgers must be checked for duplicate rows before migrating.
- **A4 (to verify in `flow-solution`).** Flow-launched workers can neither write to the ledger or the attempt directory nor invoke `resolve-execution`.
- **A5 (unverified).** v8 captures a usable provider trace for producer and manager calls. If it does not, requirement 2's trace route narrows to `response_observations` only.

## Open questions (for `flow-solution`)

- **Q3.** Operator-confirmed or automatic observation-backed reconcile (requirement 6).
- **Q4.** Does the resolve route bump the owner generation? How does it record the step in the recovery chain (requirement 1)?
- **Q5.** Manager-call observation storage, so that observation and resolution are atomic (requirement 3).

## Closed or deferred questions

- **Q1.** Closed: a claimed send is never resolvable as not dispatched in chunk 2 (all four reviews agree). Reopening it needs an ADR 0012 amendment and a new evidence class. It is tracked as a known limitation.
- **Q2.** Moot under C1. If operator import is reopened, the security review's structured provenance record is its starting point (`adversarial-review.md`).

## Evidence

- Archive retrieval (`--lane define`, selection `42924c9e…`, after an index rebuild) returned one hit, the parent's 1a archive, which applies.
- Code anchors were read on `codex/chartered-delivery-recovery-2`, which is 1b at `8c79953`. The architecture review re-verified them.

## Approval status

- Approved by the engineer on 2026-09-24.
