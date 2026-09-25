# ADR 0017: Delegated expansion under sealed headroom

- Status: accepted
- Date: 2026-09-25
- Supersedes: the rule that delegated expansion stays disabled. That rule
  came from the `shaper-delivery-runtime-contracts` run and was enforced in
  `validate_shaper_intent`. ADR 0014's ownership model is unchanged.

## Context

A chartered protocol v8 Delivery Lead that reaches a charter limit is denied
outright, and the run fails. The Shaper can't pre-approve growth, and the
engineer has no way to approve one more call without re-sealing the charter.
MAF adoption step 5 needs bounded, auditable growth that leaves Flow's
authority chain (ADR 0011, 0012, 0014) intact.

## Decision

A v8 limit can grow one unit at a time. Each unit is backed by a ledger grant.
A grant is authorised in one of two ways: by headroom the Shaper sealed into
the charter, or by an explicit engineer decision. The charter and envelope
never change.

- **Expandable limits.** Only these five: `delegations`, `paid_worker_calls`,
  `verifier_calls`, `manager_calls` and `manager_rounds`.
  - Replans and concurrency are never expandable.
  - Hard denials never create a request:
    - provider, specialist, write scope or prohibited capability;
    - verifier retry;
    - producer already completed;
    - replan refusal.
- **Sealed headroom.**
  - Shaper intent may carry `expansion_headroom`. The Shaper Contract and
    Delivery Charter (both v3) seal it, and omitting it seals zeros.
  - `delegation_matrix.delegated_expansion` is derived. It is true exactly
    when some headroom is non-zero.
  - Sealing refuses any base + headroom above a runner ceiling, and any paid
    headroom that would outgrow delegations.
  - The ceilings live in `runtime/maf_runner/limits.py`. The runner, the
    supervisor guards, envelope validation and contract validation all read
    them from there.
- **Envelope projection.** Prepare copies the charter's non-zero headroom
  into a top-level v8 envelope key, `expansion_headroom`. When no headroom is
  sealed the key is omitted, so the envelope stays byte-identical to before.
- **Requests.**
  - Flow computes a request from the denying ledger row. The amount is
    exactly one unit for each failing expandable limit.
  - The request is keyed by `(attempt, kind, denied row)`, and recording it is
    idempotent.
  - Manager text is shown for display only, and never parsed for amounts or
    limits.
- **Automatic approval** happens inside the denial transaction. A request
  within the lineage's remaining headroom is granted and consumed at once,
  under `charter_headroom` authority, and the attempt carries on.
- **Escalation.**
  - If headroom can't cover the request, the attempt pauses. The pending
    request row is the pause marker.
  - The claim stays active at the same generation.
  - `flow run decide-expansion` approves or denies. It holds the ADR 0016
    lock order, needs the expected generation, and refuses unless the attempt
    is truly paused.
  - A manual grant never draws headroom.
- **Resume by replay.** `recover-delivery-lead` restores the paused position:
  - **Worker pause:** `pending` mode on the denied proposal's bound
    checkpoint.
  - **Manager pause:** `answer` or `pending` mode from the latest worker
    checkpoint, or the new `restart` mode when the attempt has no action rows.

  The denied proposal comes back under its original identity, and one unused
  approved grant allows it once. The row changes from `denied` to `allowed`
  with reason `expansion_granted`. The denial stays recorded in events and in
  the request row.
- **Denial outcomes.**
  - A denied worker request is reported to the manager, and the attempt
    continues within the charter.
  - A denied manager request seals the attempt `failed` with the limit as the
    reason. Flow never writes manager text (ADR 0012).
- **Scope.**
  - Headroom is one pool across the lineage (the v8 attempt chain), and it is
    never refilled by a supersede.
  - A consumed grant raises only the counter it applies to:
    - across the lineage, for paid and verifier calls;
    - for its own attempt, for delegations, manager calls and rounds.
  - Supersede or release marks pending requests `cancelled` and unused grants
    `lapsed`.
- **Evidence.** Receipts list every request and grant. Validation recomputes
  effective limits and headroom in ledger order, and rejects a grant that was
  added, removed or altered, automatic spending beyond headroom, the wrong
  authority, an amount above one, and a foreign lineage or generation.

## State

```text
started ──expandable denial──▶ auto-grant within headroom ──▶ started (continues)
   │
   └──escalated──▶ expansion_paused (request pending, claim active)
                        │ decide-expansion (approve | deny)
                        ▼
                    decided ──recover-delivery-lead──▶ started
                        │                               (replay under grant, or
                        │                                worker denial reported)
                        └── manager deny ──▶ failed (reason = limit)
   supersede/release while pending ──▶ request cancelled, unused grants lapsed
```

## Consequences

- Replay identity depends on the pinned MAF version. A MAF-gated regression
  test asserts identical `call_id`s across a restore and a fresh restart, and
  must pass on every MAF pin change.
- A checkpoint bound at a denial is usable only under a decided request. It
  never counts as an allowed action.
- The protocols before v8 are unchanged, and their denials stay terminal.

## Alternatives rejected

- **Holding the child process while waiting.** A crash would lose the wait,
  and it keeps locks and a process alive indefinitely.
- **A successor attempt with raised limits.** The envelope changes, so no
  `call_id` replays and work is sent again. It is re-sealing by another name.
