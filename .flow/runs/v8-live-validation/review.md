# Review: v8-live-validation

- **Lane:** `flow-review`, 2026-09-26.
- **Reviewers:** quality-reviewer (the diagnosis and the verdicts) and test-engineer (evidence sufficiency; expertise lookup `no_match`). Both are independent of the operator.

## Review Summary

### Verdict
- **Ready to accept and archive, as "validation found defects" (R7).** Both reviewers' refinements were changes to the records only, and they are applied. Nothing needed re-running.

### Findings
- **Critical:** none.
- **Important** (all fixed in the records):
  - **AC9 claimed more than the evidence showed.** It is now "Partly met". The commands and the go decision are recorded verbatim (`evidence/commands.txt`), and a post-release inspect and manager-call token usage were added. Per-call timings weren't captured; that is noted for validation-2.
  - **The D1 fix scope was too narrow.** It now splits the read cap from the log cap, parses the stream line by line with a memory ceiling, covers the debug-trace abort too, reviews `--include-partial-messages`, and adds a test with a stream over 1 MiB.
  - **D2 was stated too strongly.** It is now a latent generator defect together with the producer departing from the stated contract. It is backed by an observed test run against the partial diff (`evidence/d2-sync-check.txt`). Validation-2 must redo the job test and baseline once D2 is fixed.
  - **D1's evidence was only prose.** It is now in `evidence/d1-event-cap.txt`: the events file is exactly 1,048,576 bytes, the cap constant and the abort line are cited, and the stream breakdown is recorded.
  - **AC1's citation was loose.** It now cites the sealed charter and contract fields directly.
- **Suggestions** (applied):
  - AC3 is recorded as not met, with the partial evidence noted.
  - AC8 records exactly one outcome, the Flow defect.
  - The edit is recorded as complete apart from escaping.
  - Release instead of supersede is recorded as a departure from the plan.
  - "No second attempt" is recorded as ADR 0016 working as designed.
  - The fix-run commit types are given (`fix(cli)` for D1, `fix(scripts)` for D2).

### Requirement Fit
- **R7 and AC8** explicitly allow ending with a documented Flow defect. The outcome is recorded with its evidence.
- **Rules:** none were violated. There were no Flow code changes and nothing was staged, the paid calls came only after Andy's go, and the lifecycle events are well ordered.
- **Met live:** AC1, AC2 and AC10.
- **Not reached:** AC4–AC7, because the run stopped at manager call 3.

### Validation Fit
- The evidence supports each verdict, in `validation-results.md` and `evidence/`.
- The D1 diagnosis was checked against the code: `claude_edit_worker.py:149-160`, and the gateway marking the send unknown when `response_completed` is false.
- The no-second-attempt reasoning was confirmed: release is the only route that is never blocked, supersede is blocked by `lead_change_blocker`, and a started sibling blocks `create_attempt`.

### Residual Risks
- This work id can no longer execute: the lead is released and the attempt stays `started` permanently. Validation-2 needs a new run.
- The events log lost its tail, so exactly when the abort fired within the turn can't be proven.
- The expansion chain (automatic grant, escalation, replay) is still unproven live.
