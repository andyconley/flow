# Validation Results: chunk 2

Validated on `codex/chartered-delivery-recovery-2` against the change itself (no surrogate). The code is at `c90d58c`, followed by the doc-only `a54925d`.

## Automated

- **Full suite.** `python3.12 -m unittest discover -s tests` with `FLOW_MAF_PYTHON` set: **1465 tests OK, 0 skipped** (`validation/full-suite.log`). The baseline at 1b was 1443. Every code commit ran the suite through a script that fails on any failure or skip, except commit 8, below.
- **MAF-gated.** `tests.test_maf_delivery_lead`: **11 OK** (`validation/maf-gated.log`). The interpreter was built from `runtime/maf_runner/requirements.txt`. The MAF tests now read only `FLOW_MAF_PYTHON` and skip visibly, naming the variable, when it is unset.
- **`git diff --check`:** clean.
- **Process note.** Commit 8 was first made while the suite had 12 failures, because a pipe hid the exit code. It was fixed and amended before any later commit, and nothing was pushed.

## AC map

| AC | Proof |
|---|---|
| AC1 (c)/(e) | `BoundaryReconcileTests.test_boundaries_c_and_e_recover_after_reconcile_with_zero_resends`: producer and verifier, each `started` and `unknown`. It asserts zero resends first, then the test-capture count, the status, one resolution in the receipt, the interruption cause, the chain `[(1,2,mode)]`, and that the verifier is evaluated once. |
| AC1 (c)/(e), no observation | `ObservedReconcileLedgerTests.test_reconcile_refuses_an_unobserved_action_and_a_terminal_attempt`, `V8ResolveRouteTests.test_an_unobserved_action_is_abandoned_with_release`, and the inspection test. |
| AC1 (a) | `BoundaryReconcileTests.test_boundary_a_an_unresolved_manager_call_is_abandon_only`: the route refuses `unresolvable_abandon_only` with no mutation, inspection says abandon only, and `release` succeeds. |
| AC2 | `test_recovery_refuses_a_resolution_not_bound_to_the_action_attempt_and_chain`: another action, another attempt, and outside the chain, each refused `resolution_unbound` with no mutation. |
| AC3 | `V8ResolveRouteTests` covers every settled refusal with snapshots, including `evidence_invalid` on an intact but invalid observation, the live run, a concurrent resolution, and replay. The ledger tests cover the stale generation, moved events, and a tampered digest. `test_v5_to_v7_resolve_execution_keeps_its_contract` runs against a real v7 row. `CharteredRecoveryEntryTests` checks entry-point reachability. |
| AC5 | Realized by AC1 (c)/(e) through the operator-confirmed route. |
| AC6 | `test_v8_no_dispatch_regrant_is_refused_without_mutation`. |
| AC7 | `test_a_lead_change_succeeds_once_every_uncertain_action_is_resolved` (resume and supersede), and `LeadChangeFenceTests.test_an_unknown_manager_call_alone_blocks_a_lead_change`. |
| AC8 | `test_receipt_validation_rejects_an_added_or_removed_resolution`. |
| AC9 | `test_inspect_delivery_guides_each_blocker_and_refusals_point_to_it`, plus the updated OSError-verifier expectation. |
| AC10 | `test_send_lock_refuses_a_symlinked_lock_path`, `test_send_lock_refuses_a_hard_linked_lock_file`, `test_no_test_file_hardcodes_the_maf_interpreter_path`. |
| AC11 | The suite and the MAF-gated tests above, and the mutations below. |
| AC12 | `test_v8_prepare_refuses_a_worktree_containing_project_flow`, `test_the_worktree_guard_compares_files_not_spellings`, `test_v8_resolve_refuses_an_envelope_worktree_containing_project_flow`. |

## Mutation checks (`validation/mutations.log`)

Each check restored the source from a byte copy and compared its sha256 afterwards.

- **M1**, the binding check skipped: the AC2 binding test **fails**, in all three cases.
- **M3**, the v8 no-dispatch guard removed: the AC6 test **fails**, because the stable refusal is gone.
- **M4**, resolving at generation+1: **caught** by the binding check (`resolution_unbound`) before any seal. The receipt never reads a resolution's generation, so binding is the guard.
- **M2**, a resend after resolution: **not demonstrated. This is an AC11 deviation for the engineer.**
  - Three mutation attempts each ended in a refusal or a denial, never a resend.
  - Five independent guards block a resend: answer-mode restore, the ledger's replay of completed rows, eligibility's refusal of an allowed row that has a recorded send, worktree drift, and the verifier limits.
  - The zero-resend assertion is kept, and runs before the status assertion.

## Review

`research/implement-review.md`: quality and security reviews, both recommending approval, with every finding dispositioned.

## Not run

- Live providers: none, by plan.
- A mutation that produces an actual resend (M2 above).
