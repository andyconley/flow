## Archive Summary

### Work Closed

- `chartered-delivery-recovery` chunk 1a was accepted on 2026-09-23 (`review.md`, "Final disposition") and merged as PR #26 (`e37d5b1`). This archive closes the 1a cycle only.
- An interrupted protocol v8 chartered attempt is now recovered explicitly, on the same attempt, from its latest Flow-bound Magentic checkpoint (ADR 0016). v8 records an interruption instead of sealing `unknown`.
- `resume-delivery-lead` and `recover-delivery-lead` route v8 to recovery. v6, v7, and terminal attempts refuse with stable reasons and mutate nothing. `resolve-execution` refuses v8 until chunk 2.
- Eligibility is decided read-only, then rechecked under a non-blocking `recovery_lock` that the live run also holds. The claim is a compare-and-swap on the owner generation. It releases unconsumed grants, quarantines unbound checkpoints, and reuses the bound test digest so the test never reruns once a verifier input exists.
- The receipt carries a validated `recovery` block, and the ledger stores the sealed receipt digest. `inspect-delivery` reports eligibility, blockers, interruptions, recoveries, predecessors, and sealed-digest consistency.

### Validation

- **Automated:** the full suite passed 1425 tests with 0 skipped. The 11 MAF-gated tests ran locally with none skipped (`validation/maf-gated.log`, the R9 merge gate, carried in the PR body). The main-plus-#27 merge result passed 1426 tests.
- **Mutation checks:** five guards were broken and each covering test failed: evidence reuse (AC6), seal-mode test rerun, gates before the fence, a timer path, and an `atexit` hook in `main`.
- **Manual:** implementation review (quality and security) and acceptance review (quality and test), plus a targeted re-review, all recorded in `research/implement-review.md` and `review.md`.
- **Runtime/deploy:** no live provider run; the plan requires hermetic tests only.

### Residual Risks

- R2: a receipt-only check cannot see a removed recovery block after seal mode; the ledger digest and inspection are authoritative.
- R8: at boundary (d) with no `repair.diff`, the current worktree becomes the recorded diff, bounded by baseline and scope checks.
- Crashes in the trailing-denial or grant-to-bind windows refuse with `no_restorable_checkpoint`. The remedy is supersede plus a successor (1b).
- A stale lock label can briefly report `recovery_in_progress` instead of `attempt_running`. It still refuses and mutates nothing.
- CI has no MAF job, so the pending-mode runtime test runs only locally.

### Follow-up Work

- **1b** (linked run `chartered-delivery-recovery-1b`): plan commits 12–13 — the superseded seal and ledger-backed lead guard (AC9 clauses 2–4) and successor predecessors with lineage limits (R4). Engineer decisions for 1b (2026-09-23): the superseded seal applies to v8 only; the positive supersede test uses an attempt with no `unknown` actions, and the resolved-unknown case moves to chunk 2.
- **Chunk 2** (its own linked run): operator resolution of `unknown` sends, boundaries (a), (c), (e), AC5, and a v8 `resolve-execution` that takes `recovery_lock`.
- Carried nits: `send_lock` lacks `O_NOFOLLOW`; the read-only URI is built from the raw path.

### Capability Gaps Observed

- `review-rework-transition` (reuse): acceptance-review fixes ran inside `reviewing`.
- `reviewer-role-command-execution` (reuse): reviewers could not run suites or mutations.
- `project-test-command-declaration` (reuse): the suite command was rediscovered again.
- `maf-runtime-interpreter-preflight` (reuse): the MAF merge gate needs a hand-supplied interpreter.
- `multi-cycle-run-lifecycle` (new): no path from `review_accepted` back to `implementing` for a run planned as several cycles.
- `worktree-identity-propagation` (new): new worktrees lack `.flow/identity.json`.
