# Archive: shaper-expansion-approval

## Archive Summary

### Work Closed
- **Run:** `shaper-expansion-approval`, MAF adoption step 5, slice 1. The review was accepted on 2026-09-26 (`review.md`).
- **Outcome:** chartered protocol v8 gains delegated expansion (ADR 0017).
  - **Headroom.** The Shaper may seal expansion headroom for delegations, paid worker calls, verifier calls, manager calls and manager rounds. It is sealed in the v3 Shaper Contract and Delivery Charter and bounded by the runner ceilings, which live in one module.
  - **Automatic grants.** A v8 limit hit within the lineage's remaining headroom is granted in the same ledger transaction.
  - **Pause.** An escalated request pauses the attempt with nothing sent, and status, list and inspect show the pending decision.
  - **Decide.** `flow run decide-expansion` approves or denies. It is fenced and generation-checked, and follows the ADR 0016 lock order.
  - **Resume.** `recover-delivery-lead` replays the paused proposal under a single-use grant. A worker pause resumes in `pending` mode; an approved manager pause in `answer` mode, or `restart` when there are no actions; a denied manager call seals the attempt failed.
  - **Lifecycle.** Supersede, release and sealing close open requests and grants.
  - **Receipts.** An `expansion` block is added, recomputed by validation and compared with the ledger at seal time.
- **Commits:** `2b9e045`–`1d5ec46` on `codex/step5-shaper-approval-design`, plus run-artifact commits.

### Validation
- **Automated:**
  - The full suite passed 1,538 tests with 0 skipped, with `FLOW_MAF_PYTHON` set. It was run through a fail-closed runner after every commit and after both rounds of review fixes.
  - Five MAF-gated end-to-end cases ran against the real pinned stock Magentic runner, pinning replay identity (spike S1–S3).
  - Mutation checks M1–M10 were each caught and restored.
  - The acceptance-criteria-to-test mapping is in `validation-results.md`.
- **Manual (review):**
  - plan review by the architect and test-engineer (`plan-review.md`);
  - implementation review by the quality and security reviewers (`implementation-review.md`);
  - acceptance review by the quality reviewer and test-engineer (`review.md`).
  - Engineer decisions: E5a, E6a, and I1, I2 and A10, all accepted.
- **Runtime/deploy:** no live provider or live v8 run, which was a non-goal of this slice. Nothing has been released yet.

### Residual Risks
- **Replay identity depends on the pinned MAF version.** `tests/test_maf_expansion.py` must pass on every pin change.
- **New recovery surface.** The `restart` mode and the wider checkpoint binding (which now also binds denied proposals) are proven hermetically only.
- **Seal failure after the close.** If a seal fails after the pre-seal close, a lapsed grant is left on a started attempt. A supersede recovers it.
- **Queued decisions.** A decide can queue up to 10 seconds behind another decide.

### Follow-up Work
- Push and open one PR, then merge and release.
- Real-world validation runs of v8 chartered delivery with expansion.
- **The rest of step 5:**
  - cancellation;
  - stuck-run recovery beyond reconcile;
  - trace correlation;
  - an MCP handback;
  - a token cap.
- **Deferred:** replan expansion (E1) and the optional specialist pool (E2).

### Capability Gaps Observed
- **Sealed artifacts can't be amended.** There is no lifecycle path to amend approved acceptance criteria after delivery authority is sealed, so the approved amendments live in `plan.md`.
- **Sealed manifest can't take new assignments.** Plan and implement reviewer dispatches can't be added to the orchestration manifest once it is sealed.
- **The fail-closed full-suite command** had to be hand-scripted again.
- **Reviewer roles can't run tests or mutation checks**, so they verify proof by reading only.
- **No command runs declared mutation checks and records the results.** The mutation script was hand-written.
- **Ledger:**
  - `solution-amends-approved-definition`: reused.
  - `orchestration-manifest-assignment-command`: reused.
  - `project-test-command-declaration`: reused (already promoted).
  - `reviewer-role-command-execution`: reused.
  - `mutation-check-harness`: new.
- **Repeats:**
  - `project-test-command-declaration`: 6 (promoted).
  - `reviewer-role-command-execution`: 5 (open).
  - `orchestration-manifest-assignment-command`: 3 (open).
  - `solution-amends-approved-definition`: 2 (open).

### Memory Updates
- **STATE (`.flow/memory/STATE.md`):** added this run to Recently completed, with next steps (real-world validation, then the rest of step 5).
- **Runtime memory entries written:** `project_flow_delegated_expansion.md`, covering how v8 delegated expansion pauses, decides and resumes, with its gotchas; indexed in `MEMORY.md`.
- **Parent-overlay implications:** none.
