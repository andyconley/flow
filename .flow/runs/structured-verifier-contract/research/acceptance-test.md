# Acceptance Test Review

The coordinator recorded this report from the `acceptance-test` assignment (test-engineer, read-only, no shell) on 2026-09-23.

## Verdict

AC9 is supported.

Every AC9 class and every item in the refinement plan maps to a proving test with a direct oracle:

- valid pass and valid fail;
- all unusable classes, table-driven;
- cap enforcement;
- truthful observation;
- replay with no resend;
- the ten receipt tamper subtests, including the isolated `rebind_evaluation_only`.

## Gaps

- **Important:** no test validated a pre-v8 (v7) completed receipt. Only the additive ledger migration was proven. **Resolved:** `test_completed_v7_receipt_keeps_its_original_validation_semantics` now covers it.
- **Important:** the stale-evidence branch (`cli/delivery_gateway.py:999-1004`) has no test. It is accepted as documented: the branch cannot be reached in a v8 run today.
- **Suggestion:** no test covers the `num_predict` change for structured calls.
- **Suggestion:** no test covers the `rowid` tiebreak or the supervisor message text.
- **Suggestion:** the AC5 cap-denial tests don't hold the global delegation and paid-call budgets non-exhausted explicitly while asserting the denial.
