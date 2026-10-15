# Focused review reliability follow-up

Implemented under Andy's focused approval, after the completed R2 comparison.
Release remains on hold. No additional live-model comparison, commit, release or
deployment occurred. The installed runtime was not changed. All prior live observations and exclusions
remain in place; this follow-up does not turn their failed targets into passes.

## Changes

The production SDK execution boundary now classifies missing, unchanged, unusable,
ambiguous or disposition-only `review.md` as `incomplete_review` and returns a
nonzero CLI status. Chat-only ACCEPT cannot supply an artifact or receipt. The
host records each attempt before SDK dispatch, preserving interrupted attempts,
and retains separate outcome evidence per review ID.

The existing `workflow repair` command reserves `--check-id review-output` for a
targeted output repair. It uses the existing journal-backed `repair_attempts`,
two-allocation limit and block/escalation behavior. Allocation does not approve
work, change criteria or reopen approved implementation artifacts. New sessions
and resume do not refund the limit. Waiting-for-confirmation continuation reuses
the same attempt and deadline. A shared 1800-second deadline persists from first
review dispatch. A small review-only wrapper uses the pinned SDK's `arun()` and
`interrupt()` at the remaining deadline; output arriving late cannot be accepted.

Independent review can run while implementing to assess an equivalent test repair
before handback. It does not advance lifecycle. Its output separates
`Verdict: ACCEPT|REJECT` (implementation correctness) from
`Test equivalence: EQUIVALENT|MATERIAL|UNCERTAIN` (evaluation-input repair).
Fixing an import while retaining assertions can be equivalent; correcting addition
logic fulfills the addition criterion rather than changing it. An equivalent test
repair may accompany an implementation REJECT. The existing receipt command
requires a separate host action and binds the actual independent session,
artifact, approved inputs and workspace. Missing, stale, altered or mismatched
outputs cannot supply that receipt. Material or uncertain dispositions cannot
approve criterion changes.

Incomplete reviews block handback. Rejected or incomplete executed reviews block
final acceptance through both workflow approval and direct lifecycle transition.
No approval is synthesized. Existing manual/operator receipt workflows remain
available under their original trust model; people sharing the same OS user are
not authenticated by hashes.

## Deterministic production CLI coverage

Eleven focused tests use the shipped CLI argument parser, dispatch and workflow
handlers, with only SDK conversations/readiness mocked. Saved responses retain
source trial IDs and source-result hashes. There are zero live model dispatches.

- Saved missing-artifact, repetitive-output and chat-only ACCEPT responses fail
  without a receipt. Repetitive artifacts, labels without rationale and conflicting
  verdicts also fail.
- A bounded output repair produces a usable review while leaving host approval
  separate; complete REJECT cannot bypass final approval through direct transition.
- Confirmation resume preserves attempt ID/deadline; two repairs persist across
  pause/resume/new sessions, and a fresh CLI process blocks a third allocation.
- Independent import-only repair produces a valid receipt. Same-producer,
  mismatched-session, altered-artifact and stale-workspace receipts are rejected.
- Changed assertions with MATERIAL disposition cannot mint an equivalent receipt
  or pass handback. This tests enforcement of the disposition, not automatic
  semantic discovery of every weakened assertion.
- A mocked stalled SDK is interrupted at the shared deadline; late output and
  subsequent repair/dispatch remain ineligible.
- A full host CLI lifecycle covers init, definition/plan approvals, failed check,
  targeted repair, passing check, independent equivalent review, receipt, handback
  and final approval. Integrity verification then calls `runstate.verify` directly.

Author focused run: 11 tests passed in 5.924 seconds. Independent final run: 11
passed in 5.866 seconds, no actionable issues. The reviewer initially found three
issues (confirmation resume, direct-transition bypass and exit status); all were
fixed and re-reviewed before final sign-off. See `independent-review.json`.

Final relevant aggregate: **87 tests passed in45.712 seconds**, covering the review
contract, verification, workflow, usage, SDK construction/specialists, generated
help, staging inventory and runtime smoke. Results are recorded in `validation.json`
and compressed logs.
Generated CLI help and whitespace checks pass.

An expanded command ran 825 tests: 20 failures, one loader error and five skips.
Nineteen failures were SDK provisioning failures in disposable homes under network
restrictions; no actual installed Flow runtime was changed. The remaining failure
was the explicit staging inventory lacking the new module; adding it retained the
exact-set and every-module-removal assertions, and the staging test now passes.
The loader error was an erroneous reference to nonexistent `tests.test_runstate`
in the test command, not a production import error. The failed run is retained;
the broader suite is not represented as fully green. No dependency download or
installation was retried to clear these environment failures.

## What is and is not established

Established: deterministic Flow execution/approval/receipt contract behavior for
these cases, persistent retry accounting and deadline dispatch/interrupt wiring.
This is production CLI validation with a mocked SDK boundary, not a new live-model
comparison or an actual native/provider execution benchmark. SDK/provider orphan
compute and external process cancellation guarantees are not established.

Not established: semantic review accuracy, actual model compliance with the new
instructions, better legitimate-repair completion rates, rework reduction or cost
savings. The R2 25% rework target remains unmet; authoritative whole-team tokens
and actual bills remain unknown. Nonempty rationale and exact hashes cannot prove
semantic equivalence. Separate user approval is still needed for material changes.

User configuration and frozen evaluation criteria hashes match their prior
receipts. Source hashes for this follow-up are in `revision.json`. No further live
runs are scheduled. Return this result to Andy before any commit/release/deployment
or installation decision.
