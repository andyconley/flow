# Handback: v8-live-validation-3

The third live chartered v8 job. **The first completed one.**

**Branch:** `codex/v8-live-validation-3`. It holds run records and evidence only; there are no Flow code changes. The job's diff is in the worktree `~/src/flow-v8-live-job-2` (uncommitted) and in `evidence/attempt-1-worktree.diff`.

## Result

- **One attempt** (`def92b2b…`) sealed **`completed`** on v0.38.0, with receipt sha256 `0ec8bf30…`. `validate_receipt` passes.
- **Proven live for the first time:**
  - an automatic `charter_headroom` grant (manager call 5);
  - a D4 progress-reply repair;
  - a D5 recover after a grant;
  - a live local-verifier `valid_pass` (7 s);
  - a completed job with the documentation delivered.
- **Proven again:** an escalation (call 6), Andy's decision, and an answer-mode resume with one send per call.
- **AC1–AC12 are met.** D6 was not exercised, and AC13 is not applicable. See `validation-results.md`.

## Residuals

- D6 (the no-edit reason) and the stuck/abandon/successor path (AC13) weren't needed, so they are still unproven live.
- Codex, replan expansion and multi-attempt lineage remain out of scope.
- One ambiguous phrase in the produced `cli-reference.md`: "owner generation" should say "attempt generation". It can be fixed in the docs PR.

## Next

- `/flow-review v8-live-validation-3`.
- The docs PR from `job/decide-expansion-docs-2` (plan decision 6). The branch is based on v0.36.1, so rebase it onto `main` and regenerate the tables.
