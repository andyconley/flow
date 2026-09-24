# Validation Results: Chartered v8 Delivery Recovery, chunk 1a

- **Branch:** `codex/chartered-delivery-recovery-1a` in `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`.
- **Commits:** 15 commits on top of the plan commit `e43c109`:
  - 12 implementation commits;
  - 1 implement-review fix commit (`3a69f3f`);
  - 2 acceptance-review fix commits (`f01ea35`, `c39d7fa`);
  - evidence commits. The base is `main` at `6015e9b` (v0.33.0).
- **Interpreter:** `python3.12`.
- **MAF interpreter:** `/private/tmp/flow-maf-runtime-spike-20260919/bin/python`, the default when `FLOW_MAF_PYTHON` is unset.
- **Everything here ran against the change itself.** No surrogate environment and no live provider were used.

## Commands (validation-plan.md order)

| # | Command | Result | Log |
|---|---|---|---|
| 1 | Focused suites: `tests.test_chartered_delivery_gateway`, `tests.test_chartered_delivery_recovery`, `tests.test_delivery_recovery`, `tests.test_structured_verifier_ledger`, `tests.test_maf_delivery_lead` | 108 tests, OK | `validation/focused.log` |
| 2 | Regression suites: `tests.test_maf_recovery`, `tests.test_execution_recovery`, `tests.test_maf_continuation_supervisor`, `tests.test_maf_post_resolution_continuation`, `tests.test_delivery_projection`, `tests.test_delivery_control` | 70 tests, OK | `validation/regression.log` |
| 3 | Full suite: `python3.12 -m unittest discover -s tests` | 1425 tests, OK, **0 skipped** (baseline 1370) | `validation/full-suite.tail.log` |
| 4 | `git diff --check e43c109..HEAD` | clean | — |
| 5 | AC12 mutation (below) | the guard is load-bearing | — |

The full suite also ran after every commit, and each commit was gated on its exit code. There is one exception. Commit 7's first run failed the `test_release_staging_requires_every_real_cli_sibling` guard: the new module was not yet listed or reachable. That commit was amended before any later work, and the amended commit passes.

## MAF-gated tests (R9 merge gate)

`python3.12 -m unittest -v tests.test_maf_delivery_lead`: all 11 tests ran and **none skipped** (`validation/maf-gated.log`). They include the new `test_unanswered_action_restores_in_pending_mode_with_its_original_identity`. That test drives the pinned MAF runtime through a real kill before Flow answers, then a `pending` restore. It asserts:

- the re-emitted proposal keeps its original `action_id`, `checkpoint_id`, and sequence;
- a pending restore carrying a `result` is refused;
- the workflow finishes after Flow answers.

CI has no MAF job, so this local log is the evidence the gate requires.

## Acceptance criteria to proof (chunk 1a)

All test names below are in `tests/test_chartered_delivery_recovery.py` unless another file is named.

- **AC1: no mutation on refusal.**
  - The refusal tests cover v6, v7, terminal v8, `no_restorable_checkpoint`, `reconciliation_required`, `lead_generation_inactive`, `continuation_epochs_v5_only`, and `v8_resolution_requires_chunk_2`.
  - Each test compares every execution file's sha256 (including `ledger.sqlite`) and the full snapshot before and after the call. Each asserts zero adapter, supervisor, and test calls, through both `resume` and `recover`.
- **AC2: explicit and exclusive.**
  - `test_recovery_is_exclusive_and_refuses_a_live_attempt` covers `recovery_in_progress` and `attempt_running`.
  - The ledger test for the compare-and-swap claim confirms a stale claim is refused.
  - `test_reinvoking_after_a_completed_recovery_returns_state_without_mutation` confirms a re-invoke changes nothing.
  - `test_a_live_attempt_mid_send_refuses_as_attempt_running_not_reconciliation`: an action `started` under a held live fence refuses as `attempt_running` through both entry points, with the snapshot unchanged. Once the fence is free, the same attempt refuses as `reconciliation_required`.
  - No time-, expiry-, or exit-triggered path exists. This is proven by `CharteredRecoveryEntryTests`, an AST test over `cli/` and `runtime/`: every reference to `resume_delivery`, `recover_delivery`, `_resume_chartered`, or `claim_chartered_recovery` is a call site or a callable handed to a timer. That test pins the reference set to the two operator subcommands in `cli/flow.py`. Adding a `threading.Timer(..., recover_delivery)` fails it (mutation below).
- **AC3: the ledger decides first.** In the boundary (b) producer test, the `recovery_claimed` event and then the call's `policy_allowed`/`recovery_regranted` event both come before the ledger high-water mark recorded at the adapter call. The adapter count is zero before the regrant.
- **AC4: boundaries b, d, f, g, h, and i, plus transport loss.** Each is killed with `KillPoint(BaseException)` and then recovered explicitly:
  - `test_boundary_b_unconsumed_producer_grant_is_regranted_and_counted_once`, `test_boundary_b_unconsumed_verifier_grant_captures_the_test_once`;
  - `test_boundary_d_…`, `test_boundary_f_…`, `test_boundary_g_…`, `test_boundary_h_…`;
  - `test_boundary_i_…`, with subtests `after-receipt-draft` and `before-finish-attempt`; the second asserts `replaced_draft_sha256`;
  - `test_clean_transport_loss_recovers_from_the_committed_producer`.

  Each test asserts the terminal status, the exact ordered **worker** sends, the receipt `recovery` block, and the sealed-digest match.

  **Limit:** the stub supervisors never call the manager, so manager-send ordering is covered only by `test_never_sent_manager_grant_is_reissued_on_replay_and_sent_once`.
- **AC6: test evidence is reused.**
  - `test_ac6_killed_after_valid_pass_recovery_never_invokes_the_test_runner`: the runner returns a new digest on each call. Recovery calls it 0 more times in both `answer` mode (killed after the pass is recorded) and `seal` mode (killed after the runtime outcome). The final evaluation is bound to the reused `test_digest`. The zero-rerun assertion runs before the status assertion.
  - `test_seal_mode_without_a_recorded_failure_or_verifier_input_never_runs_the_test`: seal mode never runs the test, and seals `failed` with no test evidence.
  - At boundary (d), the runner is called exactly once.
- **AC7: worktree drift.** `test_worktree_drift_fails_closed_before_any_send_or_completion` refuses with `worktree_drift` before the claim. There are no sends, no restore, and no recovery row, the generation stays at 1, and nothing completes.
- **AC8: limits.**
  - `test_ac8_regranted_unconsumed_action_counts_once_against_chartered_limits` runs with `max_paid_worker_calls=1` and `max_delegations=2`. Double counting would deny.
  - `test_ac8_verifier_retry_after_a_pass_is_denied_before_any_adapter_call` confirms that retry is denied before any adapter call.
  - Boundary (g) grants a retry after `valid_fail`.
  - Ledger tests cover the regrant retry rule and the refreshed grant clock.
- **AC9, clause 1: an inactive lead is refused.** Covered by `test_recovery_refuses_once_lead_claim_generation_is_no_longer_active`. Clauses 2 to 4 belong to 1b.
- **AC10: generation and marker.**
  - `test_recovered_receipt_rejects_a_changed_generation_and_a_removed_marker` runs on a real recovered receipt.
  - In `tests/test_chartered_delivery_gateway.py`, `test_v8_receipt_recovery_block_is_required_and_bound_to_its_evidence` runs 8 tamper subtests plus a marker-only check.
  - `test_completed_v7_receipt_keeps_its_original_validation_semantics` still passes, unchanged.
  - The 8 tamper subtests each pin the reason for their own guard.
  - **R2 limit:** `test_seal_mode_receipt_without_its_block_is_caught_only_by_the_sealed_digest`. A seal-mode receipt without its block still validates on its own; inspection's sealed digest reports it as inconsistent.
- **AC11: inspection.**
  - `CharteredRecoveryInspectionTests` checks blockers and the evidence each needs, the recoverable mode, the sealed-digest match, and a removed block detected as inconsistent.
  - A recovered started attempt shows as executable under its active lead.
  - Inspection's recovery verdict is labelled `decided_from: ledger`. It names the checks only the command runs: the live-run fence, worktree drift, and the envelope file.
- **Additional proof:**
  - R1 fail-closed (U0–U5) is covered in `tests/test_delivery_recovery.py`.
  - The quarantine test checks that a stale unbound checkpoint is moved, its digest recorded, and the attempt completes rather than sealing as failed.
  - Manager-grant reissue is covered by a ledger test.
  - Old-ledger migration is covered in `tests/test_structured_verifier_ledger.py`.
  - A live-run fence test and the flipped transport test are in `tests/test_chartered_delivery_gateway.py`.

## Review-driven additions (`research/implement-review.md`)

- `test_recovery_claim_refuses_moved_facts_and_uncertain_sends_without_mutation`: the claim's check of the event high-water mark, and its refusal of uncertain rows.
- `test_seal_mode_after_a_failed_test_seals_failed_without_rerunning_it`.
- `test_never_sent_manager_grant_is_reissued_on_replay_and_sent_once`: AC3 for manager calls at gateway level.
- A boundary (h) `valid_pass` subcase.
- Pinned reasons in the AC10 tamper checks on a real recovered receipt.

## Acceptance-review additions (`review.md`)

- **I1**, fixed in `f01ea35`: seal mode never runs the test.
- **I3**, fixed in `f01ea35`: the fence is taken before the gates run.
- **I2** and **I4**, fixed in `f01ea35`: the AC6 test has an answer-mode case and its zero-rerun assertion comes first; the AST entry-point test is new.
- **S1**, **S2** and **S5**, in `c39d7fa`: the seal-mode R2 test, the ADR residual, and the pinned tamper reasons.
- **S3**, in `f01ea35`: the inspection label.
- **S4**: this proof map now states the worker-only limit.

## Mutation checks

**Method:** the source was mutated in place, the covering test was run, and the source was restored byte for byte (`cmp` against a saved copy). The code was that of `f01ea35`.

| Guard broken | Covering test | Result |
|---|---|---|
| **AC12 (test-runner half):** the evidence-reuse branch of `_rebuild_chartered_evidence` (`if plan["test_digest"] is not None:` changed to `if False and ...`) | AC6 test | **FAIL** in `mode='answer'`: `AssertionError: 2 != 1 : recovery must reuse the bound test evidence` |
| Seal mode runs the test again (`run_test=not recorded_failure`, the pre-fix code) | `test_seal_mode_without_a_recorded_failure_or_verifier_input_never_runs_the_test` | **FAIL**: `2 != 1` |
| Gates run before the recovery lock (the pre-fix order) | `test_a_live_attempt_mid_send_refuses_as_attempt_running_not_reconciliation` | **FAIL**: `'reconciliation_required' != 'attempt_running'` |
| A `threading.Timer(60, recover_delivery, ...)` watchdog added to `cli/delivery_gateway.py` | `CharteredRecoveryEntryTests` | **FAIL**: an unexpected reference, `cli/delivery_gateway.py:_watchdog` |

Notes on the AC12 row:
- The first AC12 run, before `f01ea35`, failed on the status assertion. The acceptance review found that this did not show the named assertion failing (`review.md` I2). The AC6 test now asserts the zero-rerun count first, and has an answer-mode case.
- In answer mode, evidence reuse is the only guard.
- The seal-mode case fails differently, with `'failed' != 'completed'`. Since `f01ea35`, seal mode never runs the test, so the mutation there leaves test evidence absent instead of rerunning it.

The chunk-2 worker-adapter mutation is out of scope for 1a.

## Not run

- **Live providers:** none were needed, and none was run without the engineer's approval.
