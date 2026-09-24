# Review: chunk 1a, Chartered v8 Delivery Recovery

- **Reviewers:**
  - `review-acceptance` (quality-reviewer): requirement and technical fit.
  - `review-proof` (test-engineer): validation fit.
- **Brief:** `briefs/review.md`. Both reviews were read-only and ran concurrently over `e43c109..0b47695`.
- **Intent read:**
  - `acceptance-criteria.md`, `validation-plan.md`, and ADR 0016;
  - the implementation and tests;
  - `validation-results.md` and `research/implement-review.md`.
- **Checked against source:** the orchestrator confirmed the code paths behind findings I1 and I3 (`cli/delivery_gateway.py:638`, `:652-678`, `:801-804`).
- **Advisory expertise:** request `43a8e81a-…` delivered one entry to the test-engineer ("Define a test oracle with a concrete example"). Its disposition is `applied/trigger_satisfied`, and the post-receipt is recorded.

## Review Summary

### Verdict
- **Needs refinement.**
- The slice is right, with no drift into 1b or chunk 2. v5 to v7 behavior is unchanged apart from the intended reason codes.
- There are no critical defects.
- One important finding is a code defect against a stated invariant (I1). A second is a code-level issue in how the refusal reason is chosen (I3). Two AC proofs fall short of their criterion text (I2, I4).
- Do not run `accept-review` until the important findings are fixed or waived by the engineer.

### Findings
- **Critical:** none.
- **Important:**
  - **I1. Seal mode can re-run the targeted test.** Code path confirmed at `cli/delivery_gateway.py:652-653`, `:673-678`, `:801-804`.
    - Scenario: the runtime outcome is recorded with `failure=""` and no bound verifier input, then the process dies. Seal mode then gets `recorded_failure=False`, so it passes `run_test=True`. There is no `test_digest`, so the test runs again.
    - If the rerun or the re-verification raises after the claim, the attempt stays `started` at a higher generation. Every later recovery then claims again and reruns the test.
    - This breaks the ADR 0016 rule "exactly once", and the implement-review fix #2 claim "seal mode never reruns the test".
    - Fix: `run_test=(mode != "seal")`. Add a seal-mode test for a failure-free outcome with no verifier input that asserts `test_calls` does not increase.
    - Whether the runtime can record `failure=""` with no verifier input is inferred, not verified.
  - **I2. The AC12 mutation never reached the named assertion.** Found by both reviewers; see `validation-results.md:87-93` and `tests/test_chartered_delivery_recovery.py:471-472`.
    - The mutated run failed on the status assertion, line 471. The `test_calls == 1` zero-calls assertion that AC12 names, line 472, never ran.
    - Fix: assert `test_calls` first, or in its own `subTest`. Then re-run the mutation and record the zero-calls failure.
  - **I3. A live attempt mid-send is refused with the wrong reason.** See `cli/delivery_gateway.py:638` and `cli/delivery_projection.py:57`.
    - The first `_recovery_gates` runs before the lock is probed. A live run with an action `started` is therefore refused with `reconciliation_required`, not `attempt_running`.
    - Inspection has the same problem: it shows a `resolve-execution` blocker or `recoverable: true` between sends.
    - This breaks AC2's "a live attempt yields `attempt_running`". Once chunk 2 enables resolution, it invites resolving a send that is still in flight.
    - Fix: probe or take `recovery_lock` before the first gates; in inspection, report `attempt_running` while the lock is held. Add a test that holds the lock with an action `started`.
    - This comes from reading the code and is not tested.
  - **I4. AC2 "no automatic resume path" is proven only by code review.** See `validation-results.md:42`.
    - Nothing in CI fails if a timer, expiry, or exit path later calls `_resume_chartered` or `claim_chartered_recovery`.
    - The reviewer observed that today only `cli/flow.py:980` and `:990` call in.
    - Fix: add a call-site or import-graph assertion, or downgrade the proof-map wording from "proven" to "checked".
- **Suggestions:**
  - **S1.** Removing the recovery block from a seal-mode receipt passes receipt-only validation (`cli/execution_contracts.py:365-367`). This is accepted under R2. Note the limit in AC10's proof map, or add a seal-mode subtest showing that inspection reports it as inconsistent.
  - **S2.** Record in the ADR residuals the crash window between `decide` granting an action and `bind_magentic_checkpoint` (`cli/delivery_gateway.py:1267-1298`). It leads to a permanent `no_restorable_checkpoint`.
  - **S3.** Inspection's `recoverable` flag skips the drift and envelope checks, so it can say "recoverable" when the command will refuse. Relabel it as ledger-eligible, or run the read-only drift check.
  - **S4.** The "exact ordered sends" assertions in the boundary tests record worker calls only. Fold manager sends into the list, or state the limit in the proof map.
  - **S5.** Six of the eight tamper subtests in `tests/test_chartered_delivery_gateway.py:699-714` use a bare `assertRaises`. Pin the reasons with `assertRaisesRegex` before chunk 2 reuses the pattern. AC10's in-scope checks are separately pinned in `tests/test_chartered_delivery_recovery.py:565-572`.

### Requirement Fit

| AC | Status | What decides it |
|---|---|---|
| AC1 | Met | `_assert_refused_without_mutation` (file hashes plus the full snapshot), through both entry points; the v8 refusal in `resolve-execution` |
| AC2 | Partial | Lock exclusion, the CAS claim, and re-invoke without mutation are proven. The live mid-send reason is wrong (I3), and "no automatic path" is checked only by code review (I4) |
| AC3 | Met | Boundary (b) orders claim, then regrant, then adapter; the manager reissue test shows the same order |
| AC4 (b, d, f, g, h, i, transport) | Met | Kill-matrix tests; the MAF-gated pending test recomputes the action identity independently |
| AC6 | Met, weak proof | Zero reruns after `valid_pass`, and one run at (d). The seal-mode rerun (I1) sits next to this criterion |
| AC7 | Met | `worktree_drift` refuses before the claim; generation 1; the grant stays `allowed` |
| AC8 | Met | Limit test at paid=1, retry denial, and boundary (g) |
| AC9 clause 1 | Met | Inactive-lead refusal |
| AC10 (generation, marker) | Met, R2 caveat | Real recovered-receipt tamper checks with pinned reasons (S1) |
| AC11 | Met | `CharteredRecoveryInspectionTests` (caveats I3, S3) |
| AC12 (test-runner half) | Partial | The guard is load-bearing, but the named assertion was not shown to fail (I2) |

Both reviewers found no chunk mismapping.

### Validation Fit
- **What exists:**
  - The refusal tests and the kill matrix have hard oracles: full file-hash and snapshot comparison, zero-call counts, exact worker send order, and the sealed-digest match.
  - The MAF pending-mode test is strong.
  - The full suite ran 1420 tests with 0 skipped, and the MAF-gated tests ran 11 with 0 skipped. These results come from `validation-results.md`; the reviewers had no shell and ran nothing.
- **Gaps:**
  - The AC12 mutation evidence does not meet the AC's own wording (I2).
  - AC2's negative claim has no proof artifact CI can run (I4).
  - No test covers a live attempt mid-send (I3), or seal mode without a recorded failure and without a verifier input (I1).

### Residual Risks
- **If I1 is left in:** seal mode can loop — every recovery claims again and reruns the test, so the attempt is never sealed.
- **If I3 is left in:** once chunk 2 ships resolution, an operator can resolve a send that is still in flight.
- **Already accepted:** R2 (seal-mode block removal is visible only to inspection), R8, and the trailing-denial window. S2 would add a second crash window to the no-checkpoint class.
- **Carried over:** `send_lock` still lacks `O_NOFOLLOW`, and the read-only URI is still built from the raw path. CI has no MAF job.

## Next action
- **Fix-up:** fix I1 to I4 on branch `codex/chartered-delivery-recovery-1a`, re-run the AC12 mutation and the full suite, and update `validation-results.md`.
- **Suggestions:** apply S1 to S5 or record a disposition for each.
- **Re-review:** after that, run a targeted re-review of the fix commit, then `accept-review`.

## Re-review (`review-recheck`, quality-reviewer, brief `briefs/review-recheck.md`)

- **Verdict: ready to accept.** I1–I4 and S1–S5 are fixed in `f01ea35` and `c39d7fa`, with no regressions. The reviewer confirmed:
  - AC1 refusals still write only the excluded lock file;
  - the lock is released on every refusal path;
  - the lock order is intact;
  - no seal case needs a fresh test run: a completed receipt needs a `valid_pass`, which is always bound to a `test_digest`.
- **New suggestions and their dispositions:**
  - **N1, fixed:** the I1 test now asserts that its runtime outcome is failure-free.
  - **N2, fixed:** each command entry may be loaded only once inside `cli/flow.py:main`. An `atexit.register(recover_delivery)` mutation there fails the test. The alias, `getattr`, and outside-tree limits are stated in the proof map.
  - **N3, fixed:** the AC2 proof-map wording now says the test catches any load.
  - **N4, accepted and recorded in `HANDOFF.md`:** a stale lock label can give the reason `recovery_in_progress` instead of `attempt_running` for a moment while a live run takes the lock. It predates 1a, still refuses, and mutates nothing.
  - **N5, recorded as a chunk-2 requirement in `HANDOFF.md`:** the v8 `resolve-execution` must take `recovery_lock`.
  - **S5 note, accepted:** two subtests share the message "generation chain". Both mutations target the same chain check.

## Final disposition

**Ready to accept.** All in-scope ACs are met: AC1–AC4 (b, d, f, g, h, i, and transport), AC6–AC8, AC9 clause 1, AC10 (generation and marker), AC11, and AC12 (test-runner half). The residual risks are as listed above and in `HANDOFF.md`.
