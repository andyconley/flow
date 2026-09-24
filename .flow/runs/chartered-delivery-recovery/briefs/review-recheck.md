# Brief: targeted re-review of the acceptance fixes, chunk 1a

Run `chartered-delivery-recovery`, lane `review`. The review is read-only; return findings inline.

## Task

The first acceptance pass (`review.md`) returned **needs refinement**, with important findings I1 to I4 and suggestions S1 to S5. The fixes are commits `f01ea35` and `c39d7fa`; the diff is `git diff 0b47695..c39d7fa`. For each finding, judge whether it is fixed, partly fixed, or not fixed, and whether the fix introduced a regression. Don't re-review untouched code.

## Evidence inventory (exists now)

- **The findings:** `.flow/runs/chartered-delivery-recovery/review.md`
- **The fixes:**
  - `cli/delivery_gateway.py`, in `_resume_chartered`: the fence is taken before `_recovery_gates`, and `run_test=mode != "seal"`
  - `cli/delivery_projection.py`: `COMMAND_ONLY_RECOVERY_CHECKS`, `decided_from`, and `checked_by_command`
  - `cli/flow.py`: the inspect text lines
  - `docs/adr/0016-chartered-v8-recovery.md`: the grant-to-bind residual
- **New and changed tests:**
  - In `tests/test_chartered_delivery_recovery.py`:
    - `test_seal_mode_without_a_recorded_failure_or_verifier_input_never_runs_the_test`
    - `test_a_live_attempt_mid_send_refuses_as_attempt_running_not_reconciliation`
    - `test_ac6_killed_after_valid_pass_recovery_never_invokes_the_test_runner`, now with answer and seal subtests
    - `CharteredRecoveryEntryTests`, an AST test pinning the entry-point references
    - `test_seal_mode_receipt_without_its_block_is_caught_only_by_the_sealed_digest`
    - the inspection label assertion
  - In `tests/test_chartered_delivery_gateway.py`: pinned tamper reasons
- **Proof:**
  - `validation-results.md`, which has a new mutation-checks table and an acceptance-review additions section
  - `HANDOFF.md`
  - Results: the full suite ran 1425 tests, OK, 0 skipped; the MAF-gated tests ran 11, 0 skipped.

## Points to challenge

1. Taking `recovery_lock` before the gates. Does any AC1 refusal now mutate anything beyond the allowed lock file? Is the lock released on every refusal path? Does the ordering break the lock order `recovery_lock`, then `run_lock`, then `send_lock`, then SQLite?
2. Seal mode with `run_test=False`. Does any seal case need a fresh test run to seal truthfully? Is the `failed` / tests-null receipt accurate for a failure-free outcome with no verifier?
3. The AST entry test. Is it strong enough to catch a timer, signal, or atexit path? Is it brittle?
4. Is the AC12 evidence now what the AC text asks for?

## Output

Give a verdict: ready to accept, or needs refinement. Then give each of I1 to I4 and S1 to S5 its status, and list any new findings with `file:line` and a claim status.
