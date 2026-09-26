# Handoff: v8-live-validation-2

- **Status:** ready for review.
- **Outcome:** validation found defects (R7). Both attempts are used and neither completed.

## What happened

- **Found and fixed live:** D3 (verifier thinking budget, v0.36.2), D4 (malformed manager progress) and D5 (recovery after a headroom grant), both in v0.37.0.
- **Proven live for the first time** (attempt 2):
  - an expansion escalation, with nothing sent while paused;
  - the engineer decision;
  - a resume that replayed the same proposal under a single-use grant;
  - lineage accounting across attempts;
  - a sealed, valid receipt with its expansion block.
- **Why attempt 2 failed:** the manager delegated an inspect-only turn, and v8 allows one producer call per attempt, so no edit was made.

## Evidence

`validation-results.md`, `evidence/`, `execution/`.

## Next actions

1. **A fix run.**
   - **D6:** report "produced no observed change" when the editor changed nothing, not "outside the approved job scope".
   - **Tell the manager the producer contract.** It should know that each producer gets exactly one turn, which must make the complete edit. This is either Flow-supplied manager guidance in the envelope or task, or a charter-authoring rule. Decide which in `flow-plan`.
2. **`v8-live-validation-3`,** with a new work id. It still needs to prove live the automatic grant (AC4), manager-call replay, the verifier, and a completed receipt.
3. **Cleanup.**
   - Merge this branch's run records.
   - The first run's worktree is removed, and its commit is kept as tag `archive/v8-live-validation-job` (plan step 16, done; the SHA in the plan was mistyped and was resolved from the worktree).
