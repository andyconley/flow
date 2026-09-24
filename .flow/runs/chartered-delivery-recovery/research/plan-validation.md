# Validation plan: chartered v8 delivery recovery

Role: test-engineer. Date: 2026-09-23. Chunk 1 detailed, chunk 2 outlined, per `plan-test.md`.

Claim tags: **O** = observed (in current code/tests), **I** = inferred, **R** = recommended, **U** = unverified (needs the planning spike or implementation to confirm).

Target test file for all new chunk-1 tests: `tests/test_chartered_delivery_gateway.py`, as new methods on the existing `CharteredPreparationTests` class (**R**). That class already owns `setUp`, `_proposal`, `_result`, and `_run_v8` (O, `test_chartered_delivery_gateway.py:29,279,309,514`), and the brief requires reusing `_run_v8`. A new file would have to duplicate that fixture; reuse is cheaper and keeps one hermetic worktree-per-test fixture. If the recovery surface grows past ~15 tests, split to `tests/test_chartered_delivery_recovery.py` importing a shared fixture mixin extracted from `CharteredPreparationTests` (**R**, not required for chunk 1).

## 1. Chunk-1 acceptance-criterion to test map

Each test drives one v8 attempt with `_run_v8` (or a boundary-specific variant, see section 2), kills it at the named boundary, then calls the not-yet-implemented `resume_delivery`/`recover_delivery` chartered v8 path (or, before that lands, `_resume_chartered`/equivalent — name per `solution.md` design item 1) directly against the same `ledger`/`attempt_dir`. All assertions are stated in terms of what the current v7/v8 receipt schema already exposes (`status`, `actions[].status`, `verifier_evaluations`, `verifier_inputs`, `evidence.tests`) (O) plus the new `recovery` block from `solution.md` design item 7 (**U** until implemented).

### AC1 — scope refusals, no mutation

1. **`test_recovery_refuses_a_v6_attempt_without_mutation`**
   - File/target: `test_chartered_delivery_gateway.py`, new method on `CharteredPreparationTests`.
   - Fixture: prepare a v6 attempt (same pattern as `test_v7_projects_ownership_and_requires_auditable_provider_choice` but pinned `execution_protocol_version = 6`), leave it `started`, snapshot the ledger row and any receipt file before the call.
   - Assertions: the recovery call raises `ContractError` with a stable, asserted reason string (e.g. `assertRaisesRegex`); ledger `snapshot(attempt_id)` is byte-identical before/after (`assertEqual` on the full snapshot dict); no receipt file was created or modified (mtime/hash unchanged); zero calls to `worker_adapter`/`manager_adapter`/`test_runner` (pass counting stubs, assert call count 0).
2. **`test_recovery_refuses_a_v7_attempt_without_mutation`** — same shape, `execution_protocol_version = 7`.
3. **`test_recovery_refuses_a_terminal_v8_attempt_without_mutation`**
   - Fixture: run `_run_v8([self.PASS])` to `completed`, capture the sealed receipt's sha256 and the ledger snapshot.
   - Assertions: recovery raises `ContractError` (reason: terminal attempt, e.g. `"chartered attempt is already terminal"`); receipt file bytes unchanged (`hashlib.sha256` before/after); ledger snapshot unchanged; zero provider/test-runner calls.
4. **`test_recovery_leaves_v5_resume_and_recover_unaffected`** (regression half of AC1, see section 4) — run the existing v5 `resume_delivery`/`recover_delivery` tests in `tests/test_maf_recovery.py` unmodified; no new test needed here, only inclusion in the regression ledger (section 4).

### AC2 — explicit, exclusive invocation

5. **`test_recovery_never_fires_from_elapsed_time_grant_expiry_or_process_exit`**
   - Fixture: an interrupted v8 attempt (boundary (b), see AC4). Advance a fake clock / let a grant's TTL lapse, and simulate process exit (no explicit call at all — just let `setUp`/`tearDown` run without invoking recovery).
   - Assertion: after the fixture teardown, the ledger snapshot's status is still `started` with the interruption record present and no `attempt_recoveries` row exists — i.e., nothing except the explicit recovery entry point ever calls `claim_recovery`. This is best proved by asserting the mock `worker_adapter`/`manager_adapter` were never invoked outside the explicit test call, and by grepping (at plan level, not runtime) that no timer/`atexit` hook calls the chartered recovery path (**R**: a static check, not a unit test — record as a code-review note, not an automated assertion).
6. **`test_two_concurrent_recoveries_yield_exactly_one_success`**
   - Fixture: interrupted boundary (b) attempt. Two threads (or two sequential calls with the second issued after the first has claimed the generation but before it releases, using a `threading.Event` inserted via a patched `claim_recovery` that blocks on the event) both call the chartered recovery entry point.
   - Assertions: exactly one call returns a completed/continuing result; the other raises `ContractError` with reason `recovery_in_progress` (per `solution.md` design item 3); ledger shows exactly one generation bump for this claim; `worker_adapter` call count reflects only the winning path's expected sends (no duplicate sends from the loser).
7. **`test_reinvoking_after_completed_recovery_returns_current_state_without_mutation`**
   - Fixture: run boundary (b) recovery to `completed`. Capture receipt sha256 and ledger snapshot.
   - Assertions: a second call to the same recovery entry point with the same `attempt_id` returns the current terminal state (status `completed`, same receipt path) and raises no error; receipt bytes and ledger snapshot are unchanged after the second call; zero additional provider/test-runner calls.

### AC3 — ledger first, zero calls until grant

8. **`test_recovery_makes_no_provider_send_for_a_queued_call_without_a_grant`**
   - Fixture: an interrupted attempt where the ledger holds a queued (not yet granted) call — reachable via boundary (b)'s "unconsumed grant" shape, but before the re-grant step, patch `ledger.decide`/the grant path to inspect state mid-flight (or assert on the intermediate snapshot inside `_resume_chartered` via a test-only hook if one exists; otherwise, assert on the final call counts as a proxy).
   - Assertions: `worker_adapter` call count is 0 and `manager_adapter` call count is 0 at the point the ledger has not yet authorized a call; once the ledger authorizes (grant recorded), exactly one call follows. Practically: assert the *ordered* call list has the grant-authorization ledger event before the first adapter call timestamp/sequence (compare ledger event `seq` for `decide`/grant vs. the adapter call's recorded order using a counting wrapper that also records ledger `event count so far`).

### AC4 — kill-boundary matrix (chunk 1 boundaries)

Each boundary test below follows one shape: **kill** (drive `_run_v8` to the boundary, then force the fixture-specific interruption), **recover** (call the chartered recovery entry point), **assert** (terminal state, ordered provider sends across both kill and recovery phases combined, and the receipt). All boundary tests assert:
- `result["status"]` (terminal state) after recovery;
- the full ordered `sends` list (editor/verifier/etc., in order, across kill+recovery, e.g. `["editor"]` then recovery adds `["verifier"]`, checked as one concatenated list `self.assertEqual(sends, [...])`);
- receipt fields: `receipt["status"]`, `receipt["actions"][i]["status"]`, `receipt["verifier_evaluations"]`, `receipt["evidence"]["tests"]`, and (once implemented) `receipt["recovery"]` containing the interruption cause and the recovery generation;
- adapter/runner call counts: `worker_adapter` call count, `manager_adapter` call count, and (for AC6-relevant boundaries) `test_runner` call count, each asserted as an exact integer, not just "at least".

9. **`test_boundary_b_unconsumed_producer_grant_is_regranted_and_counted_once`**
   - Kill: interrupt after `decide` grants the editor action but before any dispatch event is recorded (patch the dispatch call to raise before it fires, or use the planned `seal_hook`/an earlier seam if one exists for pre-dispatch — see section 2 for the exact mechanism).
   - Assert: recovered terminal state `completed`; ordered sends `["editor", "verifier"]` (grant consumed exactly once, not twice); receipt evidence shows one editor action row with reason `recovery_unconsumed_grant` in its history (**U**, field name from `solution.md`); `worker_adapter` called exactly 2 times total (editor + verifier), `manager_adapter` 0 times (stub supervisor), limits counted once (assert `receipt["...limits or usage..."]` — likely `verifier_usage`/an analogous producer counter — reflects one consumed slot, not two).
10. **`test_boundary_d_producer_completed_verification_incomplete_reuses_edit_runs_test_once`**
    - Kill via `seal_hook("after-runtime-outcome")` immediately after the producer's result is recorded but before `verify_edit`/`test_runner` run (or, before the seam exists, by raising inside a patched `_verify_chartered_edit`/`_run_chartered_test` on the first call only, mirroring `test_v8_completed_verifier_without_evaluation_is_reevaluated_on_replay_without_resend`'s `crash_once` pattern at `test_chartered_delivery_gateway.py:560-567`).
    - Assert: terminal `completed`; sends `["editor", "verifier"]`; `test_runner` called **exactly once** across kill+recovery (AC6's "before any verifier input exists, invoked exactly once" clause) — use a counting wrapper, `self.assertEqual(test_calls, 1)`; receipt `evidence.tests.status == "passed"`.
11. **`test_boundary_f_verifier_completed_not_evaluated_replays_from_binding`**
    - Kill by patching `ExecutionLedger.record_verifier_evaluation` to raise on first call, exactly as `crash_once` in the existing test at line 559-576, but interrupted (no automatic retry sequence — the recovery call is the explicit second attempt, not an in-band `repeat`).
    - Assert: terminal `completed`; sends `["editor", "verifier"]` with no second verifier send; receipt `verifier_evaluations == ["valid_pass"]` (or `valid_fail` variant); `worker_adapter` called exactly 2 times (no re-send of the verifier).
12. **`test_boundary_g_retry_eligible_evaluation_recovers_to_denied_or_retry_send`**
    - Kill after the first verifier evaluation lands as `valid_fail` (retry-eligible) but before the retry decision commits — use `_run_v8([self.FAIL], plan=("editor","verifier"))`, then force interruption before the second `on_action` call would be issued.
    - Assert: recovery reaches the same non-terminal `started`→continue path as a live retry would: `sends` ends in a second `verifier` call (or, if allowance is exhausted, a denial with `denied` count incremented — mirror `test_v8_two_nonpasses_are_terminal_and_third_proposal_is_denied`'s assertions at line 441-472); receipt `verifier_usage` fields exactly match the expected reserved/consumed/denied counts.
13. **`test_boundary_h_terminal_evaluation_recovers_by_reusing_evidence_and_sealing`**
    - Kill immediately after a `valid_pass` (or two-strike terminal `valid_fail`) evaluation is recorded but before `finish_attempt`/receipt draft is written — via `seal_hook("after-receipt-draft")` (see section 2) or, pre-seam, via a patched `finish_attempt`/write step raising once.
    - Assert: terminal state matches the pre-interruption evaluation outcome (`completed` or `failed`); **zero** additional provider sends during recovery (`sends` unchanged from the kill phase); `test_runner` called 0 additional times; receipt is sealed exactly once (assert only one `receipt.json` write — check mtime count or a write-counting patch on `_write_snapshot`).
14. **`test_boundary_i_interrupted_receipt_sealing_uses_runtime_outcome_recorded_marker`**
    - Kill via the new `seal_hook("before-finish-attempt")` seam (this is the seam `solution.md` names explicitly for boundary (i)) — raise inside the hook after `runtime_outcome_recorded` is written but before `finish_attempt` commits.
    - Assert: recovery detects the `runtime_outcome_recorded` event, skips MAF entirely (assert `supervisor`/MAF restore path is never invoked on recovery — 0 calls), and seals exactly one receipt; receipt content matches what would have been sealed pre-interruption byte-for-byte except for the added `recovery` block (compare all fields except `recovery`).
15. **`test_clean_transport_loss_with_no_uncertain_sends_recovers_like_boundary_b_through_h`**
    - Kill via `MafTransportError` raised by the supervisor **after** a clean commit point (mirroring `test_v7_transport_loss_after_producer_seals_nonresumable_receipt` at line 725-756, but for v8 continuing instead of sealing non-resumable).
    - Assert: interruption record has `cause=transport`; terminal state after recovery matches the underlying boundary reached (e.g. `completed`); ordered sends have no duplicate/uncertain entries; receipt `recovery.interruptions[0].cause == "transport"` (**U**, exact field name pending implementation).

### AC6 — test evidence reuse

16. **`test_ac6_killed_after_valid_pass_recovery_never_invokes_injected_test_runner`**
    - Fixture: `test_runner` stub that returns a **new** `output_sha256` on every call (per brief's non-determinism note) via a counter, e.g. `output_sha256=hashlib.sha256(str(next(counter)).encode()).hexdigest()`. Run `_run_v8([self.PASS])` to the point the verifier returns `valid_pass`, then kill before sealing (`seal_hook("after-receipt-draft")` or equivalent).
    - Assert: after recovery reaches `completed`, `test_runner_calls == 1` (the one call made before interruption; **never invoked again** during recovery — brief's exact wording, so assert the counter's value is unchanged across the recovery call, e.g. `self.assertEqual(test_runner_calls, pre_recovery_count)`); receipt `evidence.tests.output_sha256` equals the digest recorded in `verifier_inputs[-1]["diff_digest"]`-adjacent `verifier_inputs.test_digest` binding (assert the final evaluation's bound `test_digest` field, not a freshly computed one).
17. **`test_ac6_boundary_d_before_any_verifier_input_invokes_test_runner_exactly_once`**
    - Same fixture/counter as above but killed at boundary (d), before any verifier input exists.
    - Assert: `test_runner_calls == 1` total across kill+recovery (not 0, not 2) — this is the explicit contrast case the brief calls out against test 16's "zero on recovery."

### AC7 — worktree drift

18. **`test_worktree_drift_fails_closed_before_any_send_or_completion`**
    - Fixture: interrupted boundary (b) or (d) attempt; before calling recovery, mutate the worktree (e.g. `git commit --amend` or write an extra tracked change) so the recomputed diff no longer matches the binding's `diff_digest`.
    - Assert: recovery raises `ContractError` with reason `worktree_drift` (assertRaisesRegex); zero `worker_adapter`/`manager_adapter`/`test_runner` calls; no action row transitions to `completed`; ledger snapshot's action statuses unchanged from before the call.

### AC8 — limits and allowance

19. **`test_regranted_unconsumed_action_counts_once_against_chartered_limits`**
    - Fixture: boundary (b) attempt with `max_edit_calls`/analogous limit set to exactly 1 in the charter.
    - Assert: after recovery's re-grant and completion, the receipt's producer usage/limit counters show exactly 1 consumed (not 2); a hypothetical second grant attempt would be denied (assert via the counter, not by trying a second real attempt unless cheap to add).
20. **`test_recovered_verifier_retry_granted_only_when_latest_evaluation_is_fail_or_unusable_and_allowance_remains`**
    - Fixture: boundary (g)/(h)-style kill after a `valid_pass` evaluation with allowance remaining.
    - Assert: recovery does **not** grant a retry (no additional verifier send) because the latest evaluation is `valid_pass`, not `valid_fail`/`unusable`; contrast subtest with latest evaluation `valid_fail` and allowance remaining, asserting a retry **is** granted (one additional verifier send); contrast subtest with allowance exhausted, asserting denial before any adapter call (`worker_adapter` call count 0 for that step).

### AC9 — lead authority

21. **`test_recovery_refuses_once_lead_claim_generation_is_no_longer_active`**
    - Fixture: interrupted v8 attempt; supersede/resume the lead claim (bump `run.json` generation) before calling recovery.
    - Assert: `ContractError` with a stable reason (e.g. `stale_lead_generation`); zero mutation (same pattern as AC1 tests).
22. **`test_lead_resume_or_supersede_seals_the_old_attempt_as_superseded`**
    - Fixture: an active v8 attempt with `unknown` actions all resolved (so the guard should pass — see test 23 for the negative case). Call the lead resume/supersede path.
    - Assert: old attempt's ledger `finish_attempt`-equivalent status becomes `superseded`; the successor's envelope carries `predecessors == [{attempt_id, terminal_status: "superseded", receipt_sha256, lead_generation}]` (**U**, exact predecessor schema per `solution.md` design item 9).
23. **`test_lead_resume_or_supersede_is_refused_while_any_action_is_unknown`**
    - Fixture: an attempt with at least one action `unknown` (unresolved).
    - Assert: the lead-change function-seam call raises/refuses with a stable reason; the attempt is untouched (still `started`/`unknown`, not `superseded`).
24. **`test_abandonment_succeeds_while_actions_are_unknown`**
    - Same fixture as 23 but calling the abandonment path instead.
    - Assert: abandonment succeeds (no exception, or a success result); this is the explicit contrast the AC calls out against test 23.

### AC10 — truthful receipt (generation and marker subtests only; added/removed-resolution subtests are chunk 2)

25. **`test_receipt_records_recovery_owner_generation_and_relied_resolutions`**
    - Fixture: any boundary-(b)-through-(i) recovered attempt.
    - Assert: `receipt["recovery"]` contains the interruption(s), the recovery generation (matches `ledger.claim_recovery`'s returned generation), and the resolutions relied on (empty list for chunk-1 boundaries, since chunk 1 has no operator resolutions — assert `[]` explicitly to pin the chunk boundary).
26. **`test_receipt_validation_rejects_a_changed_recovery_generation`** (subTest style, matching `test_v8_receipt_rejects_each_tampered_verifier_binding`'s `mutations` dict pattern at line 612-623)
    - Mutations table with two entries for chunk 1: `"generation changed"` (mutate `receipt["recovery"]["generation"]`) and `"recovery marker removed"` (delete the `recovery` block or its marker field entirely).
    - Assert: `validate_receipt` raises `ExecutionContractError` for each, via `subTest(label=...)`.
27. **`test_completed_v7_receipt_still_validates_unchanged`** — no new test; reuse the existing `test_completed_v7_receipt_keeps_its_original_validation_semantics` (line 631-652) unmodified as the regression proof that adding the `recovery` block to the v8 validator does not touch v7 validation. Include it by name in the regression ledger (section 4), not as a new test.

### AC11 — inspection

28. **`test_inspect_delivery_reports_recoverable_v8_attempt_with_blocking_actions_and_needed_evidence`**
    - Fixture: an interrupted boundary-(c)-shaped attempt is not available in chunk 1 (that is chunk 2), so use a chunk-1-only blocker: e.g. boundary (b) before recovery is called, or a worktree-drift-blocked case.
    - Assert: `inspect-delivery`'s output (CLI or library function — name to be confirmed against the implemented signature) reports `recoverable: false` with the drift blocker, or `recoverable: true` with the pending re-grant listed as a blocking action, its reason string, and the evidence needed (e.g. "worktree diff must match binding"). Because this is a pure projection over a ledger snapshot (`solution.md` domain-boundaries note), test it directly against a hand-built or fixture-produced ledger snapshot rather than a full CLI invocation — unit level, not integration.

### AC12 — test-runner mutation check (chunk-1 half)

29. **`test_mutation_test_runner_zero_calls_guard_fails_when_removed`**
    - This is not a new production test but a **guard-removal exercise** documented as a manual/CI step, not a permanent unittest (mutation checks are typically run once and recorded, not kept as a standing test — see section 3 for the exact mechanism).

## 2. Kill-boundary harness design

All harness mechanisms are deterministic, in-process, and use no sleeps and no real providers (constraint honored throughout):

- **Reuse `_run_v8`.** For boundaries reachable by controlling the `plan`/`verifier_outputs`/`repeat` arguments already supported (boundaries (f), (g), (h), and the "clean transport loss" case), call `_run_v8` with a `plan`/`on_reply` shaped to stop short of completion, or call `execute_chartered_delivery` directly (bypassing `_run_v8`'s full-completion assumption) when a boundary needs to leave the attempt genuinely non-terminal. **Recommendation (R):** extend `_run_v8` with an optional `kill_at: str | None` keyword that, when set, raises a sentinel `RuntimeError`/`MafTransportError` from inside the supervisor or worker at the named point, and returns the partial `sends`/`captured` state instead of a completed result. This keeps one helper for both the "run to completion" and "run to a boundary" cases and matches the brief's instruction to reuse `_run_v8`.
- **`delivery_control.failure_point` precedent (O, `cli/delivery_control.py:120,171,180,193,196,203`).** That function takes a keyword-only `failure_point: str | None` and raises at named checkpoints (`before-staging`, `after-staging`, `before-run-replace`, `after-run-replace`, `after-event-append`). The chartered recovery harness follows the identical shape: a keyword-only string parameter, string-named points, and a raise immediately after the point is reached — no sleeps, no threads except for the AC2 concurrency test (which uses a blocking `Event`, not a sleep).
- **The planned `seal_hook(point)` seam** (design item 13 in `solution.md`, **U** until implemented) on `_execute_prepared_delivery`, with points `after-runtime-outcome`, `after-receipt-draft`, and `before-finish-attempt`. Tests pass `seal_hook=lambda point: (_ for _ in ()).throw(RuntimeError(f"kill at {point}")) if point == target else None` (or a small named test double `class _KillAt` for readability), assert the raise happened at the intended point (via a captured point list), then call the chartered recovery entry point with no `seal_hook` (or a no-op one) and assert exactly one sealed receipt results. Boundaries (i) and (h) map directly to `before-finish-attempt` and `after-receipt-draft`; boundary (d) and the AC6 "kill after valid_pass" case map to `after-runtime-outcome`.
- **No sleeps, no real providers, confirmed:** every boundary is reached by a synchronous raise from a stub `supervisor`/`worker_adapter`/`test_runner`/`seal_hook`, never by timing. The AC2 concurrency test uses a `threading.Event`/lock handoff, not `time.sleep`, to force ordering deterministically.

## 3. Mutation checks (AC12)

- **Chunk 1 — test-runner-zero-calls guard.**
  - Guard to remove: the conditional in the recovery evidence-reuse path that skips invoking `test_runner` once a verifier input already exists (the `solution.md` "Evidence reuse rule" — the `if a verifier input exists, do not call test_runner` branch, analogous in shape to the existing `if any(... completed for editor): edit_evidence = verify_edit(...); test_evidence = test_runner(...)` gate at `cli/delivery_gateway.py:779-782`, but for the recovery path specifically).
  - Assertion that must fail when the guard is removed: `test_ac6_killed_after_valid_pass_recovery_never_invokes_injected_test_runner`'s `self.assertEqual(test_runner_calls, pre_recovery_count)` (test 16 above). With the guard removed, `test_runner` is called again during recovery, so the counter increments and the assertion fails — proving the guard is load-bearing.
  - Mechanism: a one-time manual or CI-scripted mutation exercise: comment out / invert the guard, run only this test, confirm failure, then restore the guard. Record the result as a line in the run's evidence, not as a permanent repository file (mutation testing tools like `mutmut`/`cosmic-ray` are not currently in the dependency set — **R**: keep this manual to stay dependency-free, consistent with `project_flow_c_lite_run_protocol.md`'s dependency-free stance).
- **Chunk 2 — worker-adapter-zero-calls guard (outline only).**
  - Guard to remove: the branch in boundary (c)/(e) resolution-continuation that skips calling `worker_adapter` when a `manager_call_resolutions`/`resolve_unknown` record already supplies the completed response (i.e., the "replay from resolution, do not resend" branch analogous to `resume_delivery`'s existing replay-without-resend logic at `cli/delivery_gateway.py:607-621`, `620-621` reply-matches-ledger check).
  - Assertion that must fail when removed: a chunk-2 test asserting `worker_adapter_calls == 0` after boundaries (c) and (e) are recovered via a bound resolution (this is the exact wording of AC12's second bullet). Name to reserve: `test_ac4_boundaries_c_and_e_recover_with_zero_worker_adapter_calls`.
  - Same manual mutation mechanism as chunk 1.

## 4. Regression proof (v5, v6, v7 unchanged)

- **Suites to run unmodified, by name:**
  - `tests/test_maf_recovery.py` — the v5 resume and recover tests (O, per brief's evidence inventory). Zero changes expected; any diff in behavior here is a regression.
  - `tests/test_execution_recovery.py`.
  - `tests/test_delivery_control.py`.
  - `tests/test_maf_continuation_supervisor.py`.
  - `tests/test_maf_post_resolution_continuation.py`.
  - `tests/test_structured_verifier_ledger.py` — proves the v8 ledger/verifier contract itself is untouched by the recovery additions.
  - Within `tests/test_chartered_delivery_gateway.py`: every existing `test_v7_*` method (10 methods, e.g. lines 144-862) and the existing `test_v8_*` methods that predate this chunk (lines 402-652) must pass unmodified — these are the v6/v7/v8-pre-recovery regression anchors.
- **Before/after ledger snapshot comparison for AC1.**
  - **`test_ac1_refusal_ledger_snapshot_is_byte_identical_before_and_after`** (folds into tests 1-3 above, or stands alone as one parametrized test over the three refusal cases: v6, v7, terminal-v8).
  - Method: capture `ledger.snapshot(attempt_id)` as a deep-copied dict immediately before the refused call, and again immediately after; assert `self.assertEqual(before, after)` on the full structure (not a subset), plus a receipt-file-level check (`assertEqual` on read bytes, or "file does not exist" both before and after for attempts with no receipt). This is stronger than asserting individual fields because it also catches an accidental new row, event, or resolution the design didn't anticipate.
  - Extend the same snapshot-diff helper to the AC2 "re-invoke after completion" test (test 7) and the worktree-drift test (test 18), since both are also no-mutation claims — reuse one `_assert_ledger_unchanged(before, after)` helper (**R**) rather than duplicating the comparison in each test.

## 5. Ordered validation commands

Run in this order; each gates the next:

1. `python3.12 -m pyflakes cli/delivery_gateway.py cli/execution_ledger.py cli/delivery_control.py cli/execution_contracts.py` (or the project's existing lint entry point, if different — **R**, confirm the actual lint command used elsewhere in CI before relying on this exact invocation; not observed in the evidence inventory).
2. `python3.12 -m unittest tests.test_chartered_delivery_gateway -v` — fast inner loop on the new and existing chartered tests first, so a regression here is caught before the full suite runs.
3. `python3.12 -m unittest tests.test_maf_recovery tests.test_execution_recovery tests.test_delivery_control tests.test_maf_continuation_supervisor tests.test_maf_post_resolution_continuation tests.test_structured_verifier_ledger -v` — the named v5/v6/v7 regression suites from section 4.
4. `python3.12 -m unittest discover -s tests` — the full repository suite (brief's explicit requirement); expect 1370 + the new chunk-1 test count, all passing, hermetically (no network, no live Ollama/Claude/Codex).
5. `git diff --check` — whitespace/conflict-marker check on the diff (brief's explicit requirement), run after tests pass so a whitespace-only failure doesn't block earlier signal.
6. The two mutation-check exercises from section 3 (chunk-1 test-runner guard now; chunk-2 worker-adapter guard once chunk 2 lands), run manually against a temporarily mutated checkout, each followed by restoring the guard and re-running step 2 to confirm green again.

## Open items for the engineer / lead-developer

- The exact production function names for the chartered recovery entry point, `seal_hook`, and the `recovery` receipt block field names are **U** (unverified) — this plan names them per `solution.md`'s design vocabulary; test names above should be treated as intent, not final, until those signatures land.
- R1 (no bound checkpoint) is owned by lead-developer; if the spike concludes `no_restorable_checkpoint` is the only safe outcome, add one more chunk-1 test: `test_recovery_fails_closed_with_no_restorable_checkpoint_when_none_is_bound`, asserting `ContractError` and zero mutation, same shape as the AC1 refusal tests.
