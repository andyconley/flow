# Review: chunk 1b, Chartered v8 Delivery Recovery

- **Reviewers:**
  - `review-acceptance` (quality-reviewer): requirement and technical fit.
  - `review-proof` (test-engineer): validation fit.
- **Brief:** `briefs/review.md`. Both reviews were read-only and ran concurrently over `79cbffb..2760098`.
- **Intent read:** `requirements.md` (1–7, E1–E5), `acceptance-criteria.md`, `plan.md`, `validation-plan.md`, ADR 0016, and both implement reviews with their disposition table.
- **Orchestrator checks:**
  - `python3.12 -m unittest tests.test_chartered_delivery_recovery tests.test_chartered_delivery_gateway tests.test_structured_verifier_ledger` → 106 OK at `2760098`.
  - Confirmed at source: I1 (`cli/execution_contracts.py:356-381`, `:973-975`), I2 (`tests/test_chartered_delivery_recovery.py:239`), I3 (`validation/mutations.log:16` against the test at `:260`, renamed in `e16e8bd`), and S2 (`tests/…recovery.py:397` against `execution_contracts.py:351`).
  - `git diff --check main...HEAD` flags trailing whitespace at `validation/mutations.log:27`.
- **Advisory expertise:** the test-engineer request `0d2cf173-…` returned `no_match`. No entries were delivered, so there is no disposition to record.

## Review Summary

### Verdict
- **Needs refinement (small).**
- Both reviewers found the implementation correct. There are no critical defects, no drift into chunk 2, and no path lets a superseded or sibling attempt spend.
- The problems are in the proof. Two AC clauses are stated more broadly than the tests establish (I1, I2), and one mutation record is stale (I3). All three are cheap to fix. Following the 1a precedent, where the AC text is not proved, don't run `accept-review` until the engineer fixes or waives them.

### Findings
- **Critical:** none.
- **Important:**
  - **I1. AC5 "tampering with `lineage_usage` fails receipt validation" holds only for inflation.** Status: observed in the code, not tested.
    - `_validate_lineage_usage` checks shape and a cap upper bound. `retry_eligible` catches a change only when it flips eligibility.
    - Scenario: understate `predecessor_paid_calls` from 1 to 0, or understate `predecessor_verifier_sends` on a `valid_pass` successor. `validate_receipt` still passes.
    - Spend is still safe, because `decide` counts from the ledger (L2). The real defence against a rewritten receipt is the sealed digest, but no 1b test exercises `lineage_usage` through it.
    - Fix, as an engineer choice: either (a) have the seal compare the receipt's `lineage_usage` against the ledger's `_lineage_usage` and add an understatement test, or (b) narrow the AC5 text and the S-M1 disposition to "inflation, or any change that alters retry eligibility", and add a test that understatement is caught by the sealed digest.
  - **I2. AC1 "a `started` v7 attempt … is left unchanged" is only proved for `status`.** Status: observed.
    - `tests/test_chartered_delivery_recovery.py:239` compares only `snapshot(v7_id)["status"]`.
    - Scenario: a regression that appends an event to the v7 row or bumps its `owner_generation` would still pass.
    - Fix: snapshot the v7 row before the lead change and compare the whole row after.
  - **I3. The M1a mutation evidence predates the final test.** Status: observed.
    - `validation/mutations.log:16` names `test_an_unknown_v7_send_blocks_…`. At HEAD the test is `test_an_uncertain_v7_send_blocks_…` (`:260`), with `started` and `unknown` subtests.
    - This is AC6 evidence, and the guard pre-check is the behavior M1a covers.
    - Fix: re-run M1a against the final test and replace the log entry.
- **Suggestions:**
  - **S1. The regrant path's lineage count is untested (in scope for 1b).** Status: observed.
    - `_v8_limit_reason` gains the lineage count at `cli/execution_ledger.py:568` and feeds `regrant_recovered_action`. A successor's recovery can reach this path now, so it is not a chunk 2 item.
    - M2 mutates only `decide`, so no test fails if this count is dropped.
    - Fix: add one test, or keep it as a stated residual with a higher priority.
  - **S2. The "altered generation" link case never reaches the ledger comparison.** Status: observed.
    - `:397` uses `lead_generation: 2` on a generation-1 envelope, and the envelope validator (`execution_contracts.py:351`) refuses it first.
    - Fix: add a case at generation 2 whose link claims 2 where the ledger records 1.
  - **S3. A failure after the seal leaves the ledger mutated.** Status: inferred.
    - `_write_lead_claim` (`cli/delivery_control.py:331`) can raise after the seal has committed (`:305-308`), for example on an immutable claim-file conflict. The attempts are then `superseded` under an unchanged claim, and the exception escapes the return shape.
    - This is safe for spend, and a same-lead successor still works.
    - Fix: check for the claim-file conflict before sealing, or record this as a known residual.
  - **S4. A crash mid-prepare can block lead changes permanently.** Status: inferred.
    - A crash between the `envelope.json` write (`delivery_gateway.py:428`) and the ledger creation (`:430`) makes every later lead change refuse with `lead_guard_ledger_unreadable`.
    - This fails closed and the window is narrow. Fix: document the manual cleanup.
  - **S5. The accepted residual "no `unknown` manager-call trigger test" is still accepted.** The guard is one `_unresolved_action` query over both tables. Chunk 2 should add the test alongside v8 resolution.
  - **S6. Trailing whitespace at `validation/mutations.log:27`.** `validation-results.md` reports "`git diff --check`: clean", but that was checked at `e16e8bd`, before this log was committed.

### Requirement Fit
- Requirements 1–7 and decisions E1–E5 are implemented as specified.
- **Seal (req 1, E3):** v8 only, with the lead generation at or below the outgoing generation. It runs under `send_lock` and `BEGIN IMMEDIATE`, re-checks the guard, refuses any attempt that was not probed, releases grants, and bumps `owner_generation`.
- **Guard (req 2, 3, E5):** it fails closed on an unreadable, symlinked, or lost ledger, and refuses `attempt_running` through non-blocking probes. Refusals return before any ledger write.
- **Abandonment (req 4):** stays unguarded.
- **Lineage (req 5, 6, E4):** `create_attempt` requires the exact lineage inside its write transaction and runs under `delivery_authority_guard`. `decide`, `_v8_limit_reason`, `_verifier_usage`, and the receipt recompute all count through `_lineage_usage`. The retry rule and `max_manager_calls` stay per attempt.
- **Task facts (req 7):** present.
- **Unchanged behavior:** v5–v7 paths are unchanged apart from the intended v7 `unknown` guard. That comes from reading the code; the envelopes were not diffed byte for byte (unverified). The first attempt has no `predecessors` key.
- **Scope:** no drift. The CLI command and v8 resolution stay out.

| AC | Status | Deciding proof |
|---|---|---|
| AC1 superseded record | Partially met (I2) | `_assert_seals` (`tests:222-240`); the v7 row is checked for status only |
| AC2 lead guard | Met | `:248`, `:260`, `:293`, `:308`, `:321`, each with a full byte and snapshot no-mutation comparison |
| AC3 abandonment | Met | `test_abandonment_succeeds_while_actions_are_unknown` (`:330`) |
| AC4 lineage link | Met (S2 weakens one subtest) | `:358`, `:366`, `:376-409` |
| AC5 lineage limits | Met, except the tamper clause (I1) | `:411` (denied before any adapter call), `:438`, `:472` |
| AC6 suite and mutations | Partially met (I3) | `full-suite.log` 1442 OK, 0 skipped; `maf-gated.log` 11 OK; M1b, M2, M3, and M4 each fail on the named assertion; M1a is stale |

### Validation Fit
- The full suite passed with 1442 tests and 0 skipped, the 11 MAF-gated tests ran locally, and the focused suites re-ran at HEAD (106 OK).
- Mutations M1b, M2, M3, and M4 each fail on the assertion the AC names. The 1a defect, where a mutation was caught by an earlier incidental assertion, does not recur.
- Every AC2 refusal kind compares the full state before and after, not just the return value.
- Gaps: I1, I2, and I3 above, plus S1 and S2.

### Residual Risks
- L1: an `unknown` v8 send blocks lead changes until chunk 2. This is accepted, and abandonment stays open.
- L2: `lineage_usage` is self-reported and the ledger is authoritative (see I1).
- S3 and S4 can each leave the run needing manual attention, but neither is a spend risk.
- Chunk 2 must add the lineage count to `regrant_not_dispatched` and to any v8 resolution regrant, and must test an `unknown` manager call as the guard trigger.
- CI has no MAF job, so the PR body must carry `validation/maf-gated.log` (merge gate R9).

## Refinement round (engineer chose option (a) for I1, 2026-09-24)

| Finding | Disposition |
|---|---|
| I1 | **Fixed.** `finish_attempt` now calls `_assert_receipt_lineage` inside the v8 sealing transaction. The written receipt's `lineage_usage` must equal the ledger's `_lineage_usage`, or be absent when there are no predecessors; otherwise the seal refuses with "receipt lineage usage differs from the ledger". `test_the_seal_refuses_understated_lineage_usage_that_receipt_validation_accepts` understates both counts on a `valid_pass` successor. It shows that `validate_receipt` accepts the receipt, the seal refuses, and the attempt stays `started` with no sealed digest. Mutation M5 fails it. ADR 0016 records the comparison. |
| I2 | **Fixed.** `_assert_seals` snapshots the v7 row before the lead change and compares the whole row after it. |
| I3 | **Fixed.** M1a was re-run against the final `test_an_uncertain_v7_send_blocks_…`, and both the `started` and `unknown` subtests fail. The old entry is annotated as superseded in `validation/mutations.log`. |
| S1 | **Fixed, as a direct rule check.** Predecessors are immutable, so an honest regrant always sees the same lineage its `decide` saw, and no end-to-end scenario makes the regrant count decisive. The lineage-limit test now calls `_v8_limit_reason` on each denied successor action and expects `verifier_call_cap` and `paid_call_cap`. Mutation M6 fails it with `'allowed' != 'verifier_call_cap'`. |
| S2 | **Fixed.** The "altered generation" case now uses a generation-2 candidate whose link claims generation 2 where the ledger records 1. The altered cases (status, generation, digest) must now be refused by the ledger (`RecoveryRefused` `predecessor_link_invalid`). |
| S3, S4 | **Accepted residuals.** Both fail closed with no spend risk. S3 leaves an unchanged claim over superseded attempts. S4 needs manual cleanup of an envelope that has no ledger. |
| S5 | Carried to chunk 2. |
| S6 | **Fixed.** Trailing whitespace stripped. |

## Recheck (`review-recheck`, quality-reviewer, independent of the fix author)

- **Verdict: ready to accept.** I1, I2, I3, S1, S2, and S6 are closed, with no regression found.
- **I1 cannot refuse an honest receipt.** The check is v8 only and runs inside the sealing transaction. A first attempt expects an absent field, and a successor's value comes from the same `_lineage_usage`. Predecessor counts are fixed once the successor exists. Both the normal and the recovery `seal` paths go through `_seal_attempt`.
- **Suggestions, both taken:**
  - The paid-cap half of the S1 check had no mutation evidence. **M6b** now removes only the paid lineage term, and the test fails at the paid check (`'allowed' != 'paid_call_cap'`).
  - ADR 0016 is rewrapped.
- **Unverified, low risk:** whether `resume_local`'s draft repair (`cli/execution_gateway.py:786`) can reach a v8 attempt. If it can, an honest draft still matches and a mismatch fails closed.

## Final disposition

**Ready to accept.** AC1–AC6 are met. On the working tree, the full suite passed 1443 tests (0 skipped) and the MAF-gated tests passed 11. Mutations M1a, M1b, M2, M3, M4, M5, M6, and M6b each fail on the assertion they target. The residuals are S3 and S4 (fail-closed) and the carried chunk 2 items.
