# Acceptance Quality Review

The coordinator recorded this report from the `acceptance-quality` assignment (quality-reviewer, read-only, no shell) on 2026-09-23.

## First pass: refine

- AC1 through AC7 and AC10 were met.
- **AC8 was not met.** In `cli/execution_contracts.py`, the final-evidence check on completed receipts was outside the v8 guard. It read `receipt["verifier_evaluations"]` on every chartered receipt, so every completed v6 or v7 receipt raised `KeyError`. Attempt inspection catches only `ValueError` and `OSError`, so that `KeyError` would have escaped to users. The suite missed it because the "v7"-named gateway tests now produce v8 receipts.
- **AC9 was partly met**, because no test validated a completed v6 or v7 receipt.
- The reviewer confirmed from source that v8 attempts run fresh only, that resume and recover accept v5 only, and that the ledger denies a second producer turn.
- Suggestions:
  - Replay re-evaluation is reachable only when the same process re-proposes the action.
  - The stale-evidence gate has no direct test.
  - `validate_evaluation` should require an integer `schema_version`.
  - Output over 64 KiB is cut silently.

## Re-check after the fix: accept

- Both checks now sit under `has_structured_verifier_evaluations(...)`, so v6 and v7 completed receipts go straight to `_validate_chartered_completion`, as before the branch. This closes AC8.
- The regression test `test_completed_v7_receipt_keeps_its_original_validation_semantics` is a faithful enough stand-in for a real v7 receipt, with three minor gaps:
  - It is derived from a v8 run, so the verifier output is JSON and the checkpoint names are v8. Neither affects v7 validation.
  - It has no manager calls.
  - It calls `validate_receipt` directly rather than going through attempt inspection. That function is the shared cause of the crash.
