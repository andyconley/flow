# Archive Summary

## Work Closed

- **Run:** `v8-live-validation-2`, the second live v8 chartered job on real providers. The review was accepted on 2026-09-26 as **validation found defects (R7)**.
- **Code:** none changed in this run. It produced run records, evidence, and the job worktree's test commit `d6d771f2`.
- **Found by this run and fixed in their own runs:**
  - D3: gemma4's thinking used up the verifier's output budget (v0.36.2);
  - D4: one malformed manager progress reply failed the attempt (v0.37.0, ADR 0018);
  - D5: recovery failed after a charter-headroom grant (v0.37.0).
- **Still open:**
  - D6: the edit check reports "outside scope" when nothing changed;
  - D7, a design gap: the manager isn't told that each producer gets exactly one turn.
- **Attempt 1** (`22ab86c3…`): the edit completed and the test passed, then it failed on D4.
- **Attempt 2** (`0fa56024…`):
  - an escalation, with nothing sent while paused;
  - Andy approved it;
  - a resume replayed the same proposal under a single-use grant;
  - a real edit call was sent once;
  - then it failed on D7, because the task said "Do not edit any files yet".
- **Proven live for the first time:** the escalation, the decision, the resume, lineage accounting, and sealed receipts carrying expansion evidence.

## Validation

- **Automated:** not applicable, because no code changed.
- **Manual and live:**
  - real Claude manager and producer turns, with ledger per-call timings;
  - both receipts validate, and their digests are recorded;
  - AC12 (the D1 fix) held on both edits.
- **Acceptance criteria:**
  - **Met:** AC1, AC2, AC5, AC7, AC10, AC12;
  - **Partly met:** AC3, AC6;
  - **Met with gaps:** AC9;
  - **Not reached:** AC4;
  - **Not met:** AC8 (both attempts ended in Flow defects);
  - **Not applicable:** AC11.
- **Runtime:** v0.36.2 for attempt 1, v0.37.0 for attempt 2.

## Residual Risks

- Until D7 is fixed, any v8 job whose manager splits "inspect" from "edit" fails.
- The automatic grant, manager-call replay, the verifier and a completed job are still unproven live.

## Follow-up Work

1. **A fix run:**
   - D6 (the message);
   - D7 (Flow-supplied manager guidance on the one-turn producer contract, or a charter rule; decide in `flow-plan`);
   - optionally, a decision-gate warning for inspect-only rationales.
2. **`v8-live-validation-3`,** with a new work id, after the fix release.

## Capability Gaps Observed

| Gap | Ledger key | Seen |
|---|---|---|
| The manager isn't told the one-turn producer contract | `manager-producer-contract-guidance` | 1 (new) |
| Inspection lacks per-call timings, so a script was written | `delivery-per-call-timings` | 1 (new) |
| No built-in realistic verifier preflight | `local-verifier-realistic-load-check` | 2 (reuse) |
| The handback gate demands outputs for assignments that were never reached | `handback-unreached-assignment-outputs` | 2 (reuse) |
| Live evidence was captured by hand | `runtime-evidence-completion-manifest` | 10 (reuse, already promoted) |
| Nothing strips a provider CLI's absolute symlink from evidence | `run-evidence-symlink-hygiene` | 1 (new) |

**Repeats:** `local-verifier-realistic-load-check` (2), `handback-unreached-assignment-outputs` (2) and `runtime-evidence-completion-manifest` (10, already promoted).

## Memory Updates

- **STATE:** the run is closed, and the D6/D7 fix run and `v8-live-validation-3` are next.
- **Runtime memory:** `project_flow_delegated_expansion.md` now records the run-2 outcome and D6/D7.
