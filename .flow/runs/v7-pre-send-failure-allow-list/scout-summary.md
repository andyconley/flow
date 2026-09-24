# Scout Summary: v7 pre-send failure allow-list

## Scope
- **Defect:** `ExecutionLedger.close_pre_send_failure` accepted protocols 3–6 and 8, but not 7.
  - A v7 chartered attempt can fail before dispatch, when the checkpoint bind or the grant consume raises (`cli/delivery_gateway.py`).
  - The gateway's release call then raised "action is not an unconsumed mixed grant".
  - That hid the original error and left the grant reserved as `allowed`.
- **Fix:** added `7` to the allow-list (`cli/execution_ledger.py`).
- **Test:** `test_pre_send_failure_releases_an_unconsumed_grant_on_every_chartered_protocol` (`tests/test_structured_verifier_ledger.py`) checks protocols 6, 7, and 8.
- **Commit:** `661a9d9 fix(ledger): release unconsumed v7 grants on pre-send failure`.

## Validation
- **Before the fix:** only the v7 subtest failed, with the defect's error.
- **After the fix:** the full suite ran 1371 tests with python3.12: OK, 0 skipped. The `main` baseline was 1370.
- **MAF delivery-lead tests:** 10 ran, OK.
- **Merge check:** the branch merges cleanly with `codex/chartered-delivery-recovery-1a`.

## Handback
- The fix is ready to merge.
- It stayed within scout size: one line, one test, and no new abstractions.
- No escalation was needed. There are no capability gaps and no memory updates.
