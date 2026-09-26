# Handoff: manager-progress-retry

- **Status:** ready for review.

## What changed

- **D4, a malformed manager progress reply** (ADR 0018):
  - one shared parser for the runner and Flow;
  - a repair limited to invalid JSON escapes;
  - up to 2 retries, each a Flow-gated manager call counted against the limits but not as a round;
  - the 3rd unparsable reply aborts with no replan;
  - a v8 receipt carries a recomputed `manager_progress` block, and the ledger records diagnostic events.
- **D5, recovery after a headroom grant:** replaying a completed call that was granted from headroom no longer tries to regrant it.

## Proof

- **Full suite:** 1,562 tests OK, 0 skipped, with `FLOW_MAF_PYTHON`.
- **Mutation checks:** 10 of 10 caught.
- **Acceptance criteria:** AC1–AC9 met (see `validation-results.md`).

## Residual risks

- **T5:** a progress retry that is itself denied at the runner ceiling isn't tested; that path is generic ADR 0017 behaviour.
- **MAF pin:** parity is pinned to `agent_framework_orchestrations==1.2.0`. `tests/test_progress_parse.py` must pass on every MAF pin change.
- **Live proof:** still pending. It comes from `v8-live-validation-2` attempt 2.

## Next actions

1. `/flow-review manager-progress-retry`, then archive.
2. A PR, then a release as v0.37.0, then reinstall.
3. Resume `v8-live-validation-2`:
   - reset its job worktree to the job commit (attempt 1's edit is saved as evidence);
   - re-run the preflight and the verifier gate;
   - launch attempt 2 under the same sealed limits. The producer needs Andy's approval of a paid-worker expansion.
