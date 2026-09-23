# Chartered Delivery Recovery Requirements

Status: **approved by the engineer on 2026-09-23.**

## Problem or opportunity

Only protocol v5 delivery attempts can resume or recover. `resume_delivery` and `recover_delivery` reject every other version, and chartered attempts are never marked `interrupted`. So a crash, transport loss, or `unknown` provider outcome leaves a v8 attempt stuck in `started` or `unknown`, and the Delivery Lead cannot continue it.

Three defects compound the gap:

- Every resume re-runs the targeted test, whose output includes timing. A resumed v8 pass is therefore always rejected as bound to stale evidence.
- The safeguard meant to stop a lead change while an action is `unknown` reads a field that nothing writes.
- Nothing in the CLI invokes an explicit Delivery Lead resume or supersede.

**Why now (this run's reasoning, not a design-doc mandate):** delegated Shaper expansion approval, adoption step 5 in `docs/maf-adoption-design.md`, needs a mid-run pause. A pause that cannot resume safely becomes a stall. Unattended delivery needs the same property.

## Audience

- The engineer (operator), who decides whether to resume, reconcile, or abandon an attempt.
- The Delivery Lead, meaning the fenced lead-claim generation that owns execution.
- Flow maintainers, who own ledger, evidence, and receipt semantics.
- A future consumer: Shaper delegated approval.

## Desired outcome

An interrupted v8 chartered attempt can be continued explicitly by the operator, and any provider call with an uncertain outcome is never resent. Continuation reuses Flow's recorded evidence and seals a truthful receipt that shows the recovery, under the same Flow authority chain.

## Delivery order (engineer decision D1)

This is one definition, delivered in two chunks, which `flow-solution` orders.

- **Chunk 1: boundaries that need no operator evidence.** Unconsumed grants, interrupted verification, an unevaluated verifier, after an evaluation, interrupted receipt sealing, and a clean transport loss. This chunk alone enables pause and resume.
- **Chunk 2: continuation after operator resolution.** Continue after an operator records an evidence-backed resolution of an `unknown` manager, producer, or verifier call.

## Requirements

1. **Version scope and eligibility.**
   - Recovery applies only to protocol-v8 chartered attempts that are not terminal.
   - v6 stays inspection-only (ADR 0014). v7 is refused with a clear reason. Neither is mutated, and v5 recovery behavior is unchanged.
   - Recovery on a terminal attempt is refused and never seals a second receipt.
2. **Explicit, exclusive invocation.**
   - Only an explicit operator command starts recovery. Elapsed time, grant expiry, and process death never start it.
   - Concurrent recovery commands on one attempt are mutually exclusive: the second fails closed.
   - Re-invoking recovery after a completed recovery returns the current state and makes no second reconciliation pass.
3. **Ledger first.** Flow reconciles the ledger before any Magentic checkpoint restore or new grant (ADR 0012). A checkpoint never authorizes a provider call.
4. **No resend of uncertain calls (chunk 2).**
   - A manager call or action whose send was claimed without a durable response stays `unknown`. It blocks continuation until the operator records an evidence-backed resolution through the existing append-only resolution. Flow never resends it.
   - The resolution must be bound to the blocking action id, the attempt id, and the fencing generation.
   - `resolved_completed` requires a durable observed response; this is already enforced. A verifier resolved as completed is evaluated from that recorded response, under the v8 contract.
   - `resolved_not_dispatched` makes the action eligible for a re-grant (Req 8).
5. **Clean transport loss.** When a chartered attempt loses transport with no uncertain sends, it is recoverable without operator evidence. `flow-solution` chooses the terminal-marker mechanism.
6. **Evidence reuse.**
   - On recovery, Flow re-verifies the current worktree edit against the recorded diff, a deterministic check. If the worktree no longer matches, recovery fails closed with a stated reason.
   - Once a verifier input exists, Flow reuses the test evidence bound to the verifier input of the **final** evaluation (`verifier_inputs.test_digest`, written before the send) and does not capture it again.
   - Before any verifier input exists (producer completed, verification incomplete), the targeted test is captured fresh.
   - Completion still requires the final `valid_pass` bound to that exact evidence.
7. **Resuming the evidence-free boundaries (chunk 1).** Each of these resumes without operator evidence, with the same outcome and receipt content an uninterrupted run would have produced, apart from the recorded recovery facts:
   - an unconsumed grant;
   - producer completed with verification incomplete;
   - verifier completed but not evaluated;
   - after an evaluation;
   - interrupted receipt sealing.
8. **Unsent grants.** An action whose grant was unconsumed or proven not dispatched may be re-granted under the chartered delegation, paid-call, and verifier limits, and it is counted once, not as a second send.
9. **Verifier allowance.**
   - Recovery preserves the v8 verifier cap.
   - A verifier send that is `unknown`, or resolved as completed, consumes allowance. Only proven no-dispatch releases it.
   - A recovered retry is allowed only when the latest evaluation is `valid_fail` or `unusable` and allowance remains.
10. **Lead authority (engineer decisions D2 and D3).**
    - Recovery continues an attempt only while its envelope's lead-claim generation is the active claim.
    - An explicit Delivery Lead resume or supersede fences the in-flight attempt, which receives a terminal superseded record. The successor starts a new attempt. This amends ADR 0014's meaning of "resume" and must be recorded in an ADR.
    - Ledger `unknown` actions block a lead resume or supersede until they are resolved. This is enforced at the existing function; no new CLI command is part of this increment.
    - Abandoning the run stays available while actions are `unknown`.
11. **Truthful receipt.**
    - A recovered attempt's receipt, or a receipt linked to it, records that recovery occurred, the recovering owner generation, and every operator resolution relied on.
    - Receipt validation rejects tampering with those facts.
    - v7 and earlier receipt validation is unchanged.
12. **Operator visibility.** `flow run inspect-delivery` shows, for a v8 attempt, whether it is recoverable, which actions block recovery and why, and what evidence would unblock each one.

## Success criteria

- One kill test per boundary, each followed by an explicit recovery. Each reaches the correct terminal state with zero extra provider sends.
- A v8 attempt killed after its verifier returned `valid_pass` completes on recovery. The targeted test is never re-run.
- The v5, v6, and v7 regressions still pass, including validation of a completed v7 receipt.
- Chunk 1 alone lets a paused or crashed attempt resume, with no operator evidence, from every evidence-free boundary.

## Non-goals

- Automatic or background resume.
- Recovery for v6 or v7 execution.
- Automatic discovery of per-provider send evidence, and provider-side exactly-once guarantees. Continuing after an **operator-recorded** resolution *is* in scope (chunk 2).
- Adopting an existing attempt under a successor lead generation, and ownership that survives a long pause. Both are deferred to the Shaper-approval increment. This increment must not preclude them.
- A CLI command for Delivery Lead resume or supersede; this goes to the operator-controls increment.
- Cancellation, stuck-run diagnostics, and trace correlation.
- Delegated Shaper expansion approval, MCP ingress changes, token or dollar caps, and a live Ollama proof run.
- The v7 `close_pre_send_failure` allow-list defect. It gets a separate `flow-scout` (engineer decision D4).

## Constraints

- ADR 0012: the ledger is read before restore, a checkpoint grants nothing, and resolution is append-only.
- ADR 0014: v6 is not resumable, a stale generation is fenced at every dispatch, and ownership changes only by explicit resume or supersede. An amendment is needed for Req 10.
- ADR 0015: evaluations are idempotent, changed bindings are rejected, and unknown sends consume the verifier allowance.
- Envelopes are immutable. Recovery facts are additive records.
- The standard-library CLI keeps working without MAF installed.
- Implementation starts only after `codex/structured-verifier-contract` (v8) merges to `main`.

## Assumptions

- **Observed:**
  - Pinned MAF checkpoint restore already accepts v5 through v8 (ledger `:1103` and `:1146`; `maf_supervisor.py:450,467`).
  - `resolve_unknown` is protocol-agnostic, validates the v8 verifier shape, and refuses `resolved_completed` without a durable observed response.
  - The chartered diff re-check is deterministic.
  - v8 durably records the verifier's test digest before the send.
- **Test seams:** the existing seams prove every boundary except interrupted receipt sealing, which needs a new pre-seal test seam. This comes from the test review.

## Evidence

- `research/recovery-boundary.md`: architecture.
- `research/failure-scenarios.md`: business analysis.
- `research/increment-scope.md`: product.
- `reconciliation.md`: how conflicts between the discovery notes were resolved.
- `adversarial-review.md`: 24 findings with dispositions.
- Archive retrieval was unavailable (exit 4, preflight required). The predecessor archives `maf-restart-reconciliation` and `maf-post-resolution-continuation` were inspected manually, outside the retrieval selection.

## Open questions for `flow-solution`

- The recovery shape: same-attempt resume, a continuation epoch with a linked receipt after `unknown` resolution, or both, mirroring v5.
- Whether a second attempt can be created for the same logical delivery under a successor lead, and against which baseline.
- The interruption terminal marker for a clean chartered transport loss.
- The design of the pre-seal test seam.

## Approval status

- Approved by the engineer on 2026-09-23, with decisions D1 to D4 recorded in `adversarial-review.md`.
