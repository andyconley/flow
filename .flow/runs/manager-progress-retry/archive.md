# Archive Summary

## Work Closed

- **Run:** `manager-progress-retry`. The review was accepted on 2026-09-26 (`review.md`) as ready to archive. Branch `codex/manager-progress-retry`, 11 commits over `main` at v0.36.2.
- **D4: a malformed manager progress reply no longer fails a v8 attempt on sight** (ADR 0018).
  - **Shared parser:** the runner and Flow use one parser, `runtime/maf_runner/progress_parse.py`, loaded by `cli/runner_progress.py`. It copies MAF 1.2.0's extraction rules, checks the five-item shape and checks the canonical round trip.
  - **Repair:** invalid JSON escapes are repaired.
  - **Retry:** a reply that still won't parse is retried up to twice. Each retry is a Flow-gated manager call that counts against the limits but not as a round.
  - **Abort:** the 3rd unparsable reply raises `PolicyAbort`, with no MAF replan.
  - **Evidence:** a v8 receipt carries a `manager_progress` block recomputed from its manager calls, and the ledger writes diagnostic events in the observation's transaction.
- **D5: recovery after a headroom grant is fixed.** It was found during this run, reproduced on unchanged `main`, and included with the engineer's approval. Replaying a completed call that was granted from headroom keeps its recorded answer instead of trying to regrant it. This is the live validation run's planned resume path.
- **Acceptance-review fix:** a deeply nested reply is now unparsable. Before, it could strand a completed paid call as `unknown`.

## Validation

- **Automated:**
  - **Full suite:** 1,562 tests OK, 0 skipped, with `FLOW_MAF_PYTHON`, after the final commit.
  - **Mutation checks:** 11 of 11 caught.
  - **MAF parity:** passes on 18 corpus cases.
  - **Fixture:** the verbatim live reply that failed attempt 1 is a test fixture, and it's repaired.
- **Manual:** D5 was reproduced on unchanged `main` with the live run's limits. The `RecursionError` was reproduced with a 30 KB reply.
- **Runtime:** none. There were no live provider calls. The live proof is `v8-live-validation-2` attempt 2, after release.
- **Acceptance criteria:** AC1–AC3 and AC5–AC9 met. AC4 is partly met: a retry denied at the runner ceiling isn't tested specifically.

## Residual Risks

- **Untested edges:**
  - a progress retry denied at the runner ceiling;
  - a retry paused for expansion, then recovered.
- **MAF pin:** parser parity is pinned to `agent_framework_orchestrations==1.2.0`, so `tests/test_progress_parse.py` must pass on every pin change.
- **Provider text:** Flow changes it in exactly one bounded way (doubling an invalid backslash). The raw text stays the recorded observation.

## Follow-up Work

1. A PR, then a release as v0.37.0, then reinstall.
2. Resume `v8-live-validation-2`:
   - reset its job worktree to `d6d771f2` (attempt 1's edit is saved as evidence);
   - re-run the preflight and the verifier gate;
   - launch attempt 2 under the same sealed limits. The producer needs Andy's approval of a paid-worker expansion.
3. Optional: tests for the two untested edges above.

## Capability Gaps Observed

- **Planning needs a definition:** bug-shaped work can't enter planning without one, so a compact definition, intent and manifest were hand-built (`plan-entry-without-definition`, reuse, 2).
- **No mutation harness:** ten mutate-test-restore cycles were scripted by hand, and a git restore once discarded uncommitted work (`mutation-check-harness`, reuse, 2).
- **Manifest by hand:** the orchestration manifest was assembled by hand-editing JSON again (`orchestration-manifest-assignment-command`, reuse, 4, already promoted).
- **Reviewers can't run commands:** review roles couldn't run the suite or mutation checks (`reviewer-role-command-execution`, reuse, 6, already promoted).
- **Repeats:** `plan-entry-without-definition` (2) and `mutation-check-harness` (2) are now repeats and still open. The other two are already promoted.

## Memory Updates

- **STATE:** this run is closed, and the release plus `v8-live-validation-2` attempt 2 are next.
- **Runtime memory:** `project_flow_delegated_expansion.md` gained D4, D5 and the ADR 0018 notes.
