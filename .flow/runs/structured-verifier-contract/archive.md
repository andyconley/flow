## Archive Summary

### Work Closed

- `structured-verifier-contract` was accepted on 2026-09-23. The source is `review.md`, "Acceptance Review (after refinement)". The branch is `codex/structured-verifier-contract` at `6177c16`, not yet published or merged.
- Protocol v8 adds a verifier result that Flow evaluates itself. The verifier's input now includes a versioned JSON output format, and Flow classifies each response as `valid_pass`, `valid_fail`, or `unusable`. Each evaluation is bound, by digest, to the exact verifier input, raw output, diff, and test evidence.
- Flow records the provider response before judging it. A malformed or empty response counts as a completed but `unusable` call; only an uncertain send stays `unknown`.
- The Delivery Charter seals a verifier call cap of 1 or 2 (default 2). A cap of 2 allows one retry after a fail or unusable result. Flow denies an excess call before send, even when the global budgets still have room.
- A completed verifier call with no evaluation is re-evaluated when replayed, with no resend. Receipts recompute every evaluation, bind it to the evidence, and report the cap and the calls consumed.
- v1 contracts and v6 and v7 receipts keep their original meaning. ADR 0015 records the ownership boundary.
- The first review requested refinement: 1 Critical, 4 Important, and 7 suggestions. All were resolved, and so were three findings from a second review round.
- Acceptance review found one more Critical: a regression on v6 and v7 receipts (AC8). It was fixed in `cab521a` and re-verified by the reviewer, with no open findings.

### Validation

- **Automated:**
  - The full suite (`python3.12 -m unittest discover -s tests`) passes 1370 tests, with 0 skipped.
  - `git diff --check` is clean.
  - Six mutation checks each failed their intended test: the original evaluator check plus five refinement checks.
  - The AC8 regression test failed before its fix and passes after it.
- **Manual:**
  - Independent read-only quality and test reviews ran in three rounds. They are recorded in `review.md` and in `research/acceptance-quality.md` and `research/acceptance-test.md`.
  - The orchestration acceptance gate passed.
- **Runtime/deploy:** not run. No live Ollama call was made; the approved plan and AC10 don't require one.

### Residual Risks

- Real Ollama output against the strict contract is unproven. Strict parsing may yield many `unusable` results.
- A v8 attempt that crashes cannot be resumed; only v5 can. A crash between completion and evaluation leaves the attempt `started`, and it needs operator reconciliation.
- The stale-evidence gate and replay re-evaluation guard future resume support. The stale-evidence gate has no direct test.

### Follow-up Work

- Run one controlled live Ollama verifier job before relying on the contract.
- Add v8 resume and recovery, reusing the recorded test evidence rather than rerunning a test whose output varies.
- Have the Codex and Claude adapters pass `provider_task` before either is approved as a verifier.
- Deferred tests:
  - the stale-evidence gate;
  - attempt inspection of a stored v7 receipt;
  - the `num_predict` change, the `rowid` tiebreak, and the supervisor message;
  - AC5 cap denial with the global budgets explicitly unused.
- Record when retained output over 64 KiB is cut.
- Publish and merge the branch when the engineer asks.

### Capability Gaps Observed

- **Missing lifecycle transition:** there is no transition from `reviewing` back to implementation. The refinement ran inside `reviewing`, with its handback recorded by hand as addenda.
- **Reviewer roles lack command execution:** the read-only quality-reviewer and test-engineer roles have no shell. When the brief asked the test reviewer to run suites, it couldn't. The coordinator ran every suite by hand.
- **Late orchestration check:** handback does not require the orchestration manifest to declare producer and evidence-collector assignments. The gap surfaced only at the acceptance gate, and the entries were added by hand.
- **Undeclared test command:** there is no project-level declaration of the canonical test command and interpreter. Each lane had to rediscover a working interpreter after the default one failed.
- **Ledger:**
  - `review-rework-transition` (reuse);
  - `reviewer-role-command-execution` (new);
  - `handback-orchestration-producer-inventory` (new);
  - `project-test-command-declaration` (new).
- **Repeats:** `review-rework-transition` has now been seen 9 times. It is already promoted.
