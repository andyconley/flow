# Solution: Chartered v8 Delivery Recovery

The engineer accepted this solution on 2026-09-23. It follows the approved `requirements.md` and `acceptance-criteria.md`, decisions D1 to D4, and the five engagement answers in `solution-brief.md`.

## Problem

An interrupted protocol-v8 chartered attempt cannot continue. The operator needs an explicit recovery through the existing `resume-delivery-lead` and `recover-delivery-lead` commands. Recovery must do all of the following:

- reconcile the ledger first;
- never resend an uncertain call;
- reuse the test evidence the verifier judged;
- seal **one** receipt that records the recovery.

An attempt may remain "interrupted, recoverable" with no receipt. After a lead resume or supersede, the successor starts fresh from the charter baseline. It is aware of its fenced predecessors, and it counts their spend against the same budget.

## Applicable rules

- **ADR 0012 (Decision, Consequences).** The ledger is read before a Magentic checkpoint is restored, and a checkpoint grants nothing. Resolution is append-only, and a lost response may stay blocked.
- **ADR 0013.** The v5 continuation epochs stay v5-only. This solution does not reuse them.
- **ADR 0014 (Compatibility and recovery).** Generations are fenced, and ownership changes only through an explicit resume or supersede. The new ADR 0016 amends the meaning of "resume".
- **ADR 0015 (Recovery).** Evaluations are idempotent, changed bindings are rejected, and unknown sends consume the verifier allowance.
- **`scaffolds/default/standards/architecture.md`:**
  - "Domain and integration boundaries" and "Domain rules": recovery eligibility is a pure, deterministic function over a ledger snapshot.
  - "Layering": the CLI routes into the gateway, and operator evidence is normalized at the boundary.
  - "Core principles, prefer reversible decisions": every change is additive and v8-only.
  - "ADR convention": this changes data ownership and ADR 0014's semantics, so it needs ADR 0016.

## Options

### Option A: same-attempt resume with an interruption record (chosen)

**Shape:**

- An interrupted v8 attempt stays `started` in the ledger.
- It carries an append-only `attempt_interruptions` record (cause: transport, reconciliation required, or unmarked process exit) and has no receipt.
- Recovery claims a new ledger fence exclusively, reconciles the ledger, and rebuilds evidence from durable records.
- It restores the latest bound checkpoint and continues in place.
- `finish_attempt` seals one receipt with a `recovery` block.

**Pros:**

- It follows the v5 same-attempt path.
- The v5 epochs are untouched.
- Limits are still counted from one source, the action rows.
- There is one commit point for sealing.

**Cons:**

- Inspection must explain a new non-terminal state.
- Chunk 2 needs a new resolution path for manager calls.

**Reversibility:** high.

### Option B: widen the v5 continuation epochs to v8 (rejected)

**Shape:** each recovery is a continuation epoch with its own fence and grants, and the final receipt lists the epochs.

**Rejected because:**

- Epochs assume the original receipt is already sealed and terminal (ADR 0013), which conflicts with engagement answers 1 and 2.
- Epochs are limited to one per action.
- The epoch grants sit outside the rows that v8 limits and the verifier allowance are counted from, so limits would have two sources.
- It would change shared v5 schema.

**Reversibility:** low to medium.

### Option C: mirror v5 exactly (rejected)

**Shape:** a same-attempt resume, then an epoch with a linked receipt after an `unknown` call.

**Rejected because:** it seals two receipts, which violates engagement answer 1.

## Decision and design

1. **Routing.**
   - `resume_delivery` and `recover_delivery` route v8 attempts to a chartered path that never calls the v5 fixtures.
   - v6, v7, and terminal attempts are refused with stable reasons and no mutation.
2. **Interruption.**
   - For v8, a transport loss or an uncertain send records an interruption and does not call `finish_attempt`.
   - For v8, a terminal `unknown` receipt is never sealed.
   - v5 to v7 are unchanged.
3. **Exclusive claim.**
   - A non-blocking per-attempt recovery lock, plus an `expected_generation` compare-and-swap on the recovery claim.
   - A second caller receives `recovery_in_progress`. A repeat after completion returns the current state.
   - Lock order is `run_lock`, then `send_lock`.
4. **Reconcile first.** Ledger reconciliation comes before any checkpoint restore or grant. If no checkpoint is bound, recovery fails closed with `no_restorable_checkpoint` unless the planning spike (risk R1) proves a safe replay.
5. **Evidence reuse.**
   - Recovery re-verifies the diff against the binding's `diff_digest`. A mismatch fails closed with `worktree_drift`.
   - Once a verifier input exists, test evidence is `{command: envelope job.test.argv, status: passed, output_sha256: the final evaluation's verifier_inputs.test_digest}`, and the test is not re-run.
   - Before a verifier input exists, the test is run exactly once.
6. **Boundaries.** How each boundary recovers is tabled in `research/solution-options.md`:
   - (b) An unconsumed grant becomes `not_dispatched` with reason `recovery_unconsumed_grant`, then is re-granted on the same row and counted once.
   - (f) The existing replay path evaluates the verifier from the stored response.
   - (i) A `runtime_outcome_recorded` event is written before the receipt is built. When it is present, recovery skips Magentic and seals.
7. **Receipt.**
   - The receipt has one `recovery` block: the interruptions, each recovery generation, the resolutions relied on, and the digest of any replaced draft.
   - The ledger stores `sealed_receipt_sha256`. Validation cross-checks the recovery block against action reasons.
8. **Lead change (ADR 0014 amendment).**
   - A lead resume or supersede first seals the in-flight attempt as `superseded` in the ledger, then bumps the `run.json` claim.
   - The lead guard reads real ledger `started` and `unknown` state, replacing the unwritten field.
   - Abandonment stays available.
9. **Successor lineage (engineer: yes).**
   - The new attempt's v8 envelope carries a `predecessors` list of `{attempt_id, terminal_status, receipt_sha256, lead_generation}`.
   - `create_attempt` checks that each predecessor is terminal and that its digest matches. The link is tamper-evident because the receipt binds the envelope digest.
   - The predecessors' outcomes appear in the Delivery Lead task facts and in `inspect-delivery`. Their evidence is not reused.
   - `prepare_chartered_delivery` refuses to start while a sibling attempt is not terminal.
10. **Limits across a lineage (engineer: yes).** `decide` counts the predecessors' paid calls and verifier sends against the same charter limits, so superseding the lead cannot reset the budget.
11. **Chunk 2 resolutions.**
    - A new `manager_call_resolutions` record, bound to the call, the attempt, and the generation.
    - Operator-supplied response evidence for actions and manager calls, validated with the same checks as `observe_*` (the v5 precedent is `recover_delivery`).
    - Resolutions are checked against those bindings when continuing.
12. **Inspection.** A pure eligibility projection reports whether the attempt is recoverable, lists the blocking actions with reasons, names the evidence each needs, and shows the predecessors.
13. **Test seam.** A keyword-only `seal_hook(point)` on `_execute_prepared_delivery`, at `after-runtime-outcome`, `after-receipt-draft`, and `before-finish-attempt`. It is modelled on `delivery_control.failure_point` and is not exposed on the CLI.

## Proposed chunks

Each chunk is independently mergeable.

1. **Chunk 1: evidence-free recovery.**
   - Scope:
     - the version gate and refusals;
     - interruption records;
     - the exclusive claim;
     - release and re-grant of unconsumed grants;
     - evidence reuse and the drift check;
     - the `runtime_outcome_recorded` event and the seal seam;
     - the receipt `recovery` block, its validator, and the sealed digest;
     - the ledger-backed lead guard;
     - the `superseded` seal;
     - `predecessors` and counting limits across the lineage;
     - inspection;
     - ADR 0016.
   - Covers AC1, AC2, AC3, AC4 (b, d, f, g, h, i, and transport loss), AC6, AC7, AC8, AC9, AC10 (generation and marker), AC11, and the AC12 test-runner mutation check.
   - Until chunk 2 lands, v8 uncertain sends stay interrupted, blocked, and visible, and abandonment remains possible.
2. **Chunk 2: continuation after operator resolution.**
   - Scope: manager-call resolutions, operator response import, resolution-binding checks, and the resolution list in the receipt.
   - Covers AC4 (a, c, e), AC5, the AC8 no-dispatch re-grant, AC10 (added and removed resolutions), and the AC12 worker-adapter mutation check.

## Owned risks

- **R1: restoring when no checkpoint is bound.** Owner: lead-developer. Mitigation: a planning spike. If it can't prove a safe replay, fail closed with `no_restorable_checkpoint`.
- **R2: validating from the receipt alone cannot detect a removed resolution.** Owner: test-engineer. Mitigation: cross-check against action reasons, and compare against the ledger's `sealed_receipt_sha256` in inspection.
- **R3: a truly lost response has no observation.** Owner: engineer. Mitigation: chunk 2 accepts operator-supplied responses that pass the `observe_*` checks. Otherwise the call stays blocked, and abandonment remains available.
- **R4: a successor resetting its limits.** Owner: engineer. Resolved: limits are counted across the lineage (design item 10).
- **R5: `resolve-execution` may not support v8.** Owner: lead-developer. Mitigation: verify it in chunk 2, and add a v8 route if it is missing.
- **R6: the lead guard depends on a readable ledger.** Owner: sre. Mitigation: open the ledger read-only, and fail closed if it cannot be read.
- **R7: implementation base.** Owner: engineer. Mitigation: planning and implementation start after `codex/structured-verifier-contract` (v8) merges to `main`.

## Design artifacts

- **ADR 0016: chartered v8 recovery.**
  - It records the decision: the non-terminal interrupted state, same-attempt resume, one receipt, and that uncertain calls are never resent and v8 never seals a terminal `unknown` receipt.
  - It records the ADR 0014 amendment: the `superseded` seal, a successor started from the baseline with a `predecessors` link, and ledger uncertainty blocking a lead change while abandonment stays available.
  - It records the consequences: ADR 0013 stays v5-only, v6 and v7 are unchanged, and limits are counted across the lineage.
  - It records the rejected alternatives B and C.
- **A recovery sequence diagram** in the plan: interrupt, recovery claim, reconcile, evidence rebuild, restore, continue, seal.
- **A planning spike for R1.**

## Research

- `research/solution-options.md`: the options, the table of how each boundary is handled, and the five architecture dimensions.
- `research/solution-data.md`: the ledger state design. Where it disagreed with the options note, this solution chooses the digest-bound envelope `predecessors` over a separate lineage table, and keeps the attempt status as `started` for interruptions.
- The coordinator resolved one open data question from code. The test command is pinned in the envelope (`job_contract.test.argv`, `delivery_gateway.py:380`), and chartered test evidence has exactly the fields `command`, `status`, and `output_sha256` (`:564`). So no new column is needed.
- Archive retrieval was unavailable (exit 4). The v5 precedent was inspected manually.

## Session model advice

- **Coordinator recommendation:** the judgment profile, which resolves to `claude-opus-4-8` at high effort. The reason is that this decision sets durable recovery and ownership semantics.
- **Active parent:** unknown. No verified session identity was supplied.
- **Effective delegated assignments:** solution-architect and data-engineer, per the Flow routing table.
- **Switch performed:** no.

## Next lane

`flow-plan`, once v8 merges. The approach is chosen, the chunks are defined, and one spike (R1) is named for planning.
