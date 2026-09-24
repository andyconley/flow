# Implementation Review: chunk 1a (quality and security)

- **Reviewers:**
  - `implement-review-quality` (quality-reviewer)
  - `implement-review-security` (security-reviewer)
- **Brief:** `briefs/implement-review.md`.
- **Mode:** both reviews were read-only and ran concurrently over `e43c109..7de46ee`. The orchestrator recorded their findings.
- **Fixes:** landed in `3a69f3f`.
- **Verdicts:**
  - Quality: request changes (0 blockers, 2 majors).
  - Security: no blockers; no path to resend a call, issue a duplicate live grant, or bypass the guard or fence.

## Findings and dispositions

| # | Source | Severity | Finding | Disposition |
|---|---|---|---|---|
| 1 | both | major | Eligibility was decided on a snapshot taken before `recovery_lock`, and never re-checked. A live run dying in that window let a claim act on stale facts: it converted a `started` row, released a now-bound grant, and quarantined a now-bound checkpoint. | **Fixed.** The gates re-run under `recovery_lock` (`_recovery_gates`). The claim also compares the event high-water mark the gates saw, and refuses `started`/`unknown` rows with `reconciliation_required` instead of fencing them. Test: `test_recovery_claim_refuses_moved_facts_and_uncertain_sends_without_mutation`. |
| 2 | quality | major | Seal mode after a recorded test failure reran the test. A plain `ContractError` bypassed the fallback, so the attempt could never seal. | **Fixed.** A recorded failure is sealed without rerunning the test, and either error type falls back to sealing without evidence. Test: `test_seal_mode_after_a_failed_test_seals_failed_without_rerunning_it`. |
| 3 | security | major | The released-grant rule demanded equality with the actions' current reason. Grant expiry or a denied regrant later overwrites that reason, so validation failed and sealing was blocked forever. | **Fixed.** Every action still marked as released must be listed, and every listed id must be an action in the receipt. The tamper subtest "released grant removed" still fails, as intended. |
| 4 | quality | minor | Drift was detected only after the claim, which bumped the generation, released grants, and quarantined files. The next interruption cause was then misstated. | **Fixed.** `_check_chartered_evidence` verifies the worktree before the claim without writing (`_verify_chartered_edit(record=False)`). The drift test now asserts no recovery row, generation 1, and the grant still `allowed`. |
| 5 | quality | minor | The stub supervisor never called `on_manager`, so the reissue hook and manager-send ordering were not exercised at gateway level. | **Fixed.** `test_never_sent_manager_grant_is_reissued_on_replay_and_sent_once` kills between the manager grant and its send, recovers, and asserts exactly one manager send. The claim, then the reissue, precede the send. |
| 6 | quality | minor | The tamper test on the real recovered receipt did not pin the reason for each mutation. | **Fixed.** It now uses `assertRaisesRegex`, matching "generation chain" or "lacks its recovery block". |
| 7 | quality | minor | Boundary (h) had only one subcase. | **Fixed.** A `valid_pass` terminal subcase was added. |
| 8 | quality | minor | `after-receipt-draft` fires before the write, so on disk it is identical to `after-runtime-outcome`. | **Accepted as designed.** The plan defines this point as "validated but not written". The on-disk-draft case is `before-finish-attempt`, which asserts `replaced_draft_sha256`. |
| 9 | quality | minor | A trailing denied action followed by a crash before the runtime outcome fails with `no_restorable_checkpoint`. | **Accepted, under the R1 fail-closed rule.** Restoring from an earlier checkpoint would re-propose the action under a new identity. Recorded as a residual in ADR 0016; the remedy is supersede and a successor (1b). |
| 10 | security | minor | Refusals after the peek ran DDL, because the writable ledger was opened before the lock. | **Fixed.** The lock is taken through a read-only ledger instance, and the writable ledger opens only after the gates pass again under the lock. The docstring notes that the lock file may be created. |
| 11 | both | minor | The lock-holder read could return empty and misreport a live run. | **Fixed.** The name is no longer truncated on release, and an unnamed holder reads as `attempt_running`. Exclusion was never affected. |
| 12 | security | minor | The quarantine target followed symlinks. | **Fixed.** A symlinked or non-directory `checkpoints-quarantine` is refused before and after `mkdir`. |
| 13 | security | minor | The regrant hook was not limited to recovery-released grants. | **Fixed.** Only actions the ledger marks `recovery_unconsumed_grant` can be re-granted. This deliberately includes a grant released by an earlier recovery that crashed before its regrant, which an "ids from this claim only" rule would strand. |
| 14 | security | nit | `reissue_recovered_manager_grant` did not check that the attempt is started and v8. | **Fixed.** It now also requires no unresolved row. |
| 15 | quality | nit | `_lead_active` duplicated `lead_claim_active`, and `_peek_snapshot` did not catch `sqlite3.Error`. | **Fixed.** |
| 16 | quality | nit | `_unbound_checkpoints` hashes files of unbounded size. | **Declined.** The checkpoint directory is owner-only and attempt-local, the runner writes at most one checkpoint per superstep, and hashing only reads. |
| 17 | security | nit | The read-only URI is built from the raw path, and `send_lock` lacks `O_NOFOLLOW`. | **Declined for 1a.** Both predate this diff, and the default paths are unaffected. Recorded as follow-up. |
| 18 | quality | note | v6/v7 refusals now raise `RecoveryRefused`, which is a `ContractError`, with new text. | **Intended.** These are the P3 and AC1 reason codes, and v5 is unchanged. |

## Invariants after the fixes

1. **Holds.** No uncertain call is resent, and uncertain rows are refused before any claim, including under the lock.
2. **Holds.** Refusals before the claim read the ledger read-only. A recovery lock file beside the ledger is the only artifact.
3. **Invariants 3 to 8 hold**, as both reviewers stated.
