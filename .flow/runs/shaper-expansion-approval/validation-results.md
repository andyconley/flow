# Validation Results: shaper-expansion-approval

- **Date:** 2026-09-25
- **Branch:** `codex/step5-shaper-approval-design`, commits `2b9e045`–`9ab48c5` (C1–C7), plus the review fixes in `31ac27b`, on top of `b8cae87` and `a33454d`.
- **Environment:**
  - `python3.12 -m unittest discover -s tests`, with `FLOW_MAF_PYTHON` set to the scratch MAF venv (agent-framework-core 1.19.0, agent-framework-orchestrations 1.2.0).
  - Run through the fail-closed runner, which exits non-zero on any failure or skip.
  - All checks ran against the change itself; there is no surrogate environment.

## Full suite

| Point | Tests | Result |
|---|---|---|
| Baseline before C1 | 1473 | Contaminated: it overlapped C1 edits in flight. Its one failure was the release-staging module list, fixed in C1. |
| After C1 | 1483 | OK, 0 skipped |
| After C2 | 1492 | OK, 0 skipped |
| After C3 | 1496 | OK, 0 skipped |
| After C4 | 1508 | OK, 0 skipped |
| After C5 | 1516 | OK, 0 skipped |
| After C6 | 1528 | OK, 0 skipped |
| After C7 | 1533 | OK, 0 skipped |
| After review fixes (`31ac27b`) | 1537 | OK, 0 skipped |

## Acceptance criteria to tests

AC6, AC7 and AC8 are the versions amended in `plan.md`, "Amendments from plan review (binding)".

| AC | Tests |
|---|---|
| AC1 | `test_shaper_delivery_contracts`: `test_expansion_headroom_is_sealed_and_bounded_by_runner_ceilings`, `test_expansion_headroom_refusals` (negative, bool, replans, concurrency, verifier > 2, manager calls > 12, rounds > 6, actions > 6, paid outgrows delegations), `test_delegated_expansion_must_match_sealed_headroom`, `test_sealed_headroom_mutation_is_refused`, the omitted-headroom-seals-zeros assertions; `test_runner_limits` (envelope projection and ceilings, v8 only, one ceilings source). |
| AC2 | `test_expansion_ledger.test_each_expandable_limit_records_one_unit_request_keyed_on_the_denied_row`, `test_manager_call_and_round_caps_record_requests_and_grant_within_headroom`; `test_expansion_gateway.test_escalated_worker_request_pauses_before_any_send_and_is_visible` (no send, started, generation unchanged, no interruption, checkpoint bound, status, list, inspect, escaped text); `test_escalated_manager_call_pauses_without_sending_it`. |
| AC3 | `test_expansion_ledger.test_hard_denials_never_create_requests_even_when_a_cap_also_fails` (verifier retry plus cap, concurrency masked by delegation cap, replan plus manager cap, producer completed); `test_a_limit_at_its_runner_ceiling_stays_a_terminal_denial`. |
| AC4 | `test_request_within_headroom_is_granted_inline_and_draws_headroom`, `test_exhausted_headroom_escalates_to_a_pending_request`, `test_replaying_a_recorded_row_returns_the_same_request_and_decision`, `test_a_crash_before_commit_leaves_nothing_and_a_rerun_draws_headroom_once`; `test_expansion_gateway.AutomaticExpansionTests`; `test_maf_expansion.AutomaticExpansionMafTests`. |
| AC5 | `test_expansion_decide`: approve (engineer grant, no headroom draw), deny, stale generation, unknown or already decided, not truly paused (fence held, unknown row), inactive lead, ceiling exceeded, each asserting nothing changed. |
| AC6 | `test_expansion_recovery.test_approval_replays_the_paused_proposal_once_under_its_grant` (same identity, denial kept in events, `expansion_granted`, effective = base + grant, no resend), `test_a_consumed_grant_cannot_allow_the_proposal_again`; `test_maf_expansion.WorkerEscalationMafTests`; the manager restart and answer cases. |
| AC7 | Worker: `test_denial_is_reported_to_the_manager_and_a_new_proposal_escalates_again`, `test_denial_then_the_attempt_seals_within_the_charter`. Manager (E5a): `test_denied_manager_call_seals_the_attempt_failed` (hermetic and MAF). |
| AC8 | `test_successor_inherits_lineage_grants_and_remaining_headroom_only`; `test_expansion_decide`: supersede lapses an unused grant, supersede cancels pending, release cancels pending. |
| AC9 | `test_expansion_receipts`: listing; removed grant or block; automatic beyond headroom; wrong authority; amount above one; foreign lineage; foreign generation; altered headroom; granted without a consumed grant; the verifier grant raises the receipted maximum; the seal refuses added, removed or altered blocks. |
| AC10 | `test_two_concurrent_decisions_leave_exactly_one_winner` (`Barrier(2)`), `test_decide_racing_supersede_has_exactly_one_outcome` (`Barrier(2)`, 10 of 10 repeated runs stable), crash atomicity (AC4), and the manager-supplied amount and rationale ignored (AC2 gateway test). |
| AC11 | `test_protocols_before_v8_keep_terminal_denials` (v6 paid cap; v7 delegation and paid caps keep the legacy shape and create no requests); the whole existing suite passes. |
| AC12 | The full suite as above, plus the mutations below. |

## MAF-gated end to end (`tests/test_maf_expansion.py`, real pinned runner, stub providers)

1. **Automatic grant within headroom:** the attempt completes with three sends.
2. **Worker escalation approved:** the runner re-emits the paused proposal with the same `action_id` (S1), and the attempt completes.
3. **Manager escalation approved:** answer-mode restore from the verifier checkpoint. The post-checkpoint call replays under an identical `call_id` (S2), and the denied call is sent once and completed.
4. **Manager escalation denied:** the attempt is sealed `failed` with reason `manager_call_cap`, and no manager text is sent.
5. **Restart before any checkpoint:** calls 1 and 2 are reissued with identical ids and answered from the ledger (S3). Call 3 runs under the grant, and call 4 escalates again. That puts four calls in one process, past base + 1, under the v8 ceiling guard (A1).

## Mutation checks

Each mutation was applied, the named test ran and failed, the code was restored, and the test passed again. The script is `scratchpad/mutate.py`; afterwards the tree was clean.

| # | Mutation | Test | Broken | Restored |
|---|---|---|---|---|
| M1 | Headroom bound removed (always auto-grant) | `test_exhausted_headroom_escalates_to_a_pending_request` | FAILED | OK |
| M2 | Worker pause skipped (denied reply instead) | `WorkerExpansionPauseTests` | FAILED | OK |
| M3 | Generation fence removed in `decide_expansion` | `test_stale_generation_is_refused` | FAILED | OK |
| M4a | Truly-paused guard (unresolved rows) removed | `test_an_attempt_that_is_not_truly_paused_is_refused` | FAILED | OK |
| M4b | Truly-paused guard (recovery fence) removed | same | FAILED | OK |
| M5 | Single-use grant check removed | `test_a_consumed_grant_cannot_allow_the_proposal_again` | FAILED (the double use surfaces as a receipt-integrity error) | OK |
| M6 | Receipt headroom recomputation removed | `test_receipt_rejects_auto_beyond_headroom` | FAILED | OK |
| M7 | Expansion recovery mode dropped | `test_approval_replays_the_paused_proposal_once_under_its_grant` | FAILED (`checkpoint_position_unrecoverable`) | OK |
| M8 | v8 supervisor guard back to base + 1 (A1) | `RestartMafTests` | FAILED | OK |
| M9 | A hard denial no longer binds its position (review Q1) | `test_manager_pause_after_a_hard_worker_denial_resumes_in_answer_mode` | FAILED (`no_restorable_checkpoint`) | OK |
| M10 | The seal no longer closes open expansions (review Q2) | `test_a_failed_resume_seals_and_lapses_the_unused_grant` | FAILED | OK |

M1–M10 were all rerun after the review fixes, and all were caught and restored.

## Deviations from plan, recorded

- **A ceiling-bound unit is a hard denial.** A limit whose next unit would pass the runner ceiling (for example a third verifier call when the ceiling is 2) creates no request, because it could never be granted. Found by three existing tests during C3.
- **The pause marker is the pending request row** (A6), not a separate pause table.
- **Only open expansions are fenced on `release`.** A release fences and closes only attempts with open expansions. It is never blocked by uncertain work, because release is the documented abandon route.
- **Decide holders queue briefly.** A `decide` holder briefly waits on another `decide` holder, up to 10 s, so the loser of a concurrent decision sees `expansion_already_decided` (AC10). A `live` or `recovery` holder is still refused at once.

## Review

The review fixes are in `implementation-review.md`: quality Q1–Q7 and security S1–S5, dispositioned.

## Not run

- No live provider or live v8 run, which is a non-goal of this slice.
