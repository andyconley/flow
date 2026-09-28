# Archive: v8-live-validation-3

## Archive Summary

### Work Closed
- **Run:** `v8-live-validation-3`, the third live chartered v8 job. The review was accepted on 2026-09-27 (`review.md`).
- **Outcome:** the first completed live v8 job. Attempt `def92b2b…` sealed `completed` on v0.38.0, with receipt sha256 `0ec8bf30…`; `validate_receipt` passes. No Flow code changed.
- **Chain proven live:**
  - sealed authority: charter `756f6503…`, with `paid_worker_calls` headroom 1, Andy's definition decision;
  - a Claude manager (6 calls) and a Claude `tech-writer` edit (47 s, four files);
  - an **automatic `charter_headroom` grant** at manager call 5;
  - an escalation at call 6, approved by Andy, followed by an answer-mode resume with 0 sends while paused;
  - a **D4 progress-reply repair**;
  - a **D5 recover after a grant**;
  - a local `gemma4:26b` verifier `valid_pass` in 7 s;
  - a sealed receipt.
- **Delivered:** the `flow run decide-expansion` documentation, merged as PR #47 after being carried onto current `main` and tightened.

### Validation
- **Automated:**
  - the targeted job test passed 3/3;
  - `regenerate-flow-help.py --check` is clean;
  - `tests/test_flow.py` passed 730 OK, in the worktree and on the PR branch;
  - PR #47 CI is green.
- **Manual:**
  - quality and test acceptance reviews, with no Critical findings;
  - the receipt checker was hardened against vacuous passes, and the evidence re-recorded;
  - all AC verdicts rest on file-recorded assertions, apart from two pre-recover checks that ran but weren't saved.
- **Runtime/deploy:** the live run on v0.38.0 with real Claude and Ollama. The preflight verifier gate passed in 4.95 s. Ledger timings are in `evidence/attempt-1-timings.txt`. AC1–AC12 are met, D7 through the checkpoint substitute. D6 was not exercised, and AC13 is not applicable.

### Residual Risks
- D6 (the no-edit reason) and the stuck, abandon and successor path are still unproven live.
- A single attempt is one sample of model behaviour, so the manager may still split inspect from edit on another job. D7 is guidance only.
- Manager guidance can be checked only through checkpoints.
- Codex, replan expansion and multi-attempt lineage are untested live.

### Follow-up Work
- The remaining step 5 slices: trace correlation, receipt verification, MCP handback, and the token cap.
- Optionally, a live run that exercises a successor (abandon or failed, then a successor), so that AC13 and lineage headroom get proven live.
- The backlog "Delivery Termination Follow-Ups".
- The new gaps: `manager-prompt-text-inspection`, `recovery-actor-provenance`, `inspect-delivery-project-root`.

### Capability Gaps Observed
- Per-call timings are still not shown by inspection.
- Live evidence and receipt checks were scripted by hand, and the ad hoc checker had vacuous-pass shapes.
- Read-only reviewers couldn't run git or shell checks.
- The realistic verifier preflight is still a run script.
- The job charter is outside the sealed digests.
- A provider CLI symlink had to be removed by hand.
- Manager request text is stored only as digests.
- The hard-coded recovery actor gives misleading provenance.
- Delivery inspection has no project-root option.
- **Ledger:**
  - reused `delivery-per-call-timings`, `runtime-evidence-completion-manifest`, `reviewer-role-command-execution`, `local-verifier-realistic-load-check`, `job-charter-sealed-digest`, `run-evidence-symlink-hygiene`;
  - new `manager-prompt-text-inspection`, `recovery-actor-provenance`, `inspect-delivery-project-root`.
- **Repeats:**
  - already promoted: `runtime-evidence-completion-manifest` 11, `reviewer-role-command-execution` 8, `local-verifier-realistic-load-check` 3;
  - open, can be promoted: `delivery-per-call-timings` 2, `job-charter-sealed-digest` 2, `run-evidence-symlink-hygiene` 2.

### Memory Updates
- **STATE:** `v8-live-validation-3` moves to recently completed. The v8 live validation goal is met, and the next step is the remaining step 5 slices.
- **Runtime memory entries written:** `project-flow-delegated-expansion` is updated with the run-3 outcome.
