# Adversarial Review: chartered delivery recovery

Round 1, 2026-09-23. The draft requirements were challenged by four read-only role reviewers:

- `adversarial-product` (product-manager)
- `adversarial-requirements` (business-analyst)
- `adversarial-architecture` (solution-architect)
- `adversarial-test` (test-engineer)

Each finding and its disposition is recorded below. Code references are to the v8 worktree.

## Product

- **P1. Why now.** Recovery comes before Shaper approval because of this run's own reasoning: a pause that cannot resume stalls. The design doc does not mandate that order. **Disposition:** requirement changed. The rationale is now labelled as this run's reasoning.
- **P2. Operator-resolved continuation.** Continuing after an operator resolves an `unknown` is essential: without it, boundaries (a), (c), and (e) dead-end. But it overrode the discovery non-goal without sign-off. **Disposition:** open question, gating. The engineer decides at approval.
- **P3. Splitting the work.** A smaller first slice could cover only the local boundaries (b), (d), (f), (g), (h), and (i), which need no operator evidence and unblock pause and resume. Operator-resolved continuation would follow as a second slice. **Disposition:** next lane refined. `flow-solution` chunks the work this way unless the engineer decides otherwise.
- **P4. Non-goal wording.** The non-goals should distinguish "no automatic evidence discovery" from "operator-resolved continuation is in scope" in the list itself. **Disposition:** non-goal clarified.

## Requirements

- **R1. Concurrent recovery.** Two explicit recovery commands racing on one attempt are unaddressed. **Disposition:** requirement changed. Recovery is mutually exclusive: the second caller fails closed.
- **R2. Terminal attempts.** Recovery on an attempt that is already terminal has no stated refusal. **Disposition:** requirement changed. It is refused, and no second receipt is sealed.
- **R3. Worktree drift.** A worktree edited by hand after the crash is not addressed. **Disposition:** acceptance criterion added. Recovery fails closed with a stated reason.
- **R4. Verifier resolved as completed.** A verifier `unknown` resolved as completed appeared to have no response to evaluate. **Disposition:** assumption confirmed by the coordinator. `resolve_unknown` already refuses `resolved_completed` without a durable observed response (`execution_ledger.py:917-919`). The requirement now states that the recorded response is evaluated.
- **R5 and R6. Resolution binding.** A resolution could be recorded against the wrong attempt or action. **Disposition:** requirement changed. It must be bound to the blocking action id, the attempt id, and the fencing generation.
- **R7. Repeated recovery.** Re-invoking recovery after a prior recovery has already advanced the attempt is not covered. **Disposition:** requirement changed. It returns the current state and makes no second reconciliation pass.

## Architecture

- **A1. Req 5 answered too early.** Req 5 settled the terminal-marker shape, which is an open solution question. It also dropped the v5 precondition of at least one completed action. **Disposition:** requirement changed. It is reworded as an outcome ("recoverable without operator evidence") and the mechanism is left to `flow-solution`.
- **A2. Lead resume becomes supersede.** Under Req 10, an ADR 0014 lead "resume" behaves like supersede. **Disposition:** requirement changed. The choice is now stated explicitly: an ADR 0014 amendment is required, and the old attempt must receive a terminal superseded record. This is subject to engineer decision D2.
- **A3. The Shaper-approval pause.** A long approval wait can trip `attention_required` (`delivery_control.py:245`), and under Req 10 that forces a new attempt. **Disposition:** non-goal added. Ownership that survives a pause is deferred to adoption step 5, and this increment must not preclude it. Open question D2.
- **A4. No exit from an unresolvable `unknown`.** **Disposition:** acceptance criterion added. Abandoning the run stays available while actions are `unknown`, as ADR 0014 Consequences allows.
- **A5. The test-evidence record exists.** A durable test record already exists for v8 (`verifier_inputs.test_digest`, written before the send). **Disposition:** assumption rejected, since "no record exists" was wrong. Req 6 is narrowed:
  - reuse the input bound to the *final* evaluation;
  - capture the test fresh at boundary (d), when no verifier input exists yet.
- **A6. Second attempt under a successor lead.** It is unverified whether a second attempt can be created for the same logical delivery. **Disposition:** open question for `flow-solution`.
- **A7. The rest of the draft.** Reqs 3, 4, 8, 9, and 11 are consistent with ADRs 0012 and 0015, and the checkpoint-restore assumption holds. **Disposition:** assumption confirmed.

## Test

- **T1. Existing seams.** AC4 boundaries (a) through (h) are provable with the existing ledger and adapter injection seams. **Disposition:** assumption confirmed.
- **T2. Receipt sealing.** AC4(i), interrupted receipt sealing, needs a new pre-seal seam. **Disposition:** acceptance criterion changed. The new test seam is required.
- **T3. New gate logic.** The v5-only gate is new logic that needs its own refusal-and-no-mutation test, checked by comparing ledger snapshots. **Disposition:** acceptance criterion changed.
- **T4. The lead-change guard.** `change_lead_claim` has no CLI caller, so the lead-change guard is testable only at the function seam. **Disposition:** open question D3.
- **T5. The mutation check.** AC12's mutation check was a review practice, not a test oracle. **Disposition:** acceptance criterion changed. It now names call-count assertions.
- **T6. Proving test reuse.** AC6 is proven directly with a test runner that returns a new digest on each call and is asserted never to be invoked on recovery. **Disposition:** acceptance criterion changed.

## Engineer decisions carried to approval

- **D1.** One increment chunked into two slices, or two separate definitions.
- **D2.** Lead resume and supersede fence the old attempt and require a new attempt, with ADR 0014 amended; or add a lead-adoption record now.
- **D3.** Whether to add a CLI command for a Delivery Lead resume or supersede in this increment.
- **D4.** The v7 `close_pre_send_failure` defect: fix it here, or open a separate scout.
