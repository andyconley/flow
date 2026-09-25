## Archive Summary

### Work Closed

- `chartered-delivery-recovery-1b` was accepted on 2026-09-24 (`review.md`, "Final disposition"; `accept-review` succeeded) on branch `codex/chartered-delivery-recovery-1b` at `5124920`. It is not yet pushed or merged. It is a linked follow-on of the archived `chartered-delivery-recovery` (chunk 1a, PR #26).
- **Lead change fences the old attempt.** A Delivery Lead `resume` or `supersede` seals every started v8 attempt at or below the outgoing generation as terminal `superseded`, before the claim changes. The seal releases unconsumed grants and bumps the owner generation. v5–v7 rows are untouched (E3).
- **Ledger-backed lead guard.** A lead change refuses in four cases:
  - `reconciliation_required` on any `started` or `unknown` action or manager call, v7 included;
  - `lead_guard_ledger_unreadable` on an unreadable, symlinked, or lost ledger;
  - `attempt_running` while a live run holds an attempt's `recovery_lock` (E5);
  - `recovery_in_progress` if the attempt set moved between the probe and the seal.
  Refusals mutate nothing, and abandonment (`release`, lifecycle `block`) stays open.
- **Successor lineage.** A new v8 attempt lists every earlier v8 attempt as `predecessors`, and only when there is at least one. `create_attempt` requires the exact ledger lineage inside its transaction and runs under the authority guard. A started sibling refuses with `sibling_attempt_not_terminal`. A predecessor may share the successor's lead generation (E4).
- **Lineage limits.** Predecessor paid worker sends and verifier sends count against the charter caps in `decide` and in the recovery regrant. The retry rule and `max_manager_calls` stay per attempt. The receipt carries `lineage_usage`, and the seal now refuses a receipt whose `lineage_usage` differs from the ledger's count (acceptance-review I1, option (a)).
- ADR 0016's amendment was updated to match.

### Validation

- **Automated:**
  - The full suite passed 1443 tests with 0 skipped (`validation/full-suite.log`).
  - The 11 MAF-gated tests ran locally with none skipped (`validation/maf-gated.log`). This is the R9 merge gate, and the PR body must carry this log.
  - `git diff --check` is clean.
- **Mutation checks:** each of M1a, M1b, M2, M3, M4, M5, M6, and M6b broke one guard, and the covering test failed on the assertion that guard targets (`validation/mutations.log`).
- **Manual:**
  - Implementation reviews (quality and security): `research/implement-review*.md`.
  - Acceptance review (quality and test): "needs refinement" on proof gaps I1–I3.
  - A refinement round.
  - An independent quality recheck: "ready to accept" (`review.md`).
- **Runtime/deploy:** no live provider run; the plan requires hermetic tests only.

### Residual Risks

- **L1.** An `unknown` v8 send blocks lead changes until chunk 2 adds v8 resolution. Abandonment stays available.
- **S3.** If the claim write fails after the seal commits, the attempts stay `superseded` under an unchanged claim. This fails closed, with no spend risk.
- **S4.** A crash between writing `envelope.json` and creating the ledger makes lead changes refuse `lead_guard_ledger_unreadable` until someone cleans up by hand.
- Unverified: whether `resume_local`'s draft repair can reach a v8 attempt. If it can, an honest draft still matches the seal check, and a mismatch fails closed.
- CI has no MAF job. Three MAF test files hardcode `/private/tmp/flow-maf-runtime-spike-20260919/bin/python` and ignore `FLOW_MAF_PYTHON`, so without that path 17 tests skip silently.

### Follow-up Work

- **PR for 1b.** Push `codex/chartered-delivery-recovery-1b` and open the PR with `validation/maf-gated.log` in the body.
- **Chunk 2** (its own linked run):
  - v8 resolution of `unknown` sends and a v8 `resolve-execution` that takes `recovery_lock`;
  - the resolved-unknown case unblocking a lead change (E2);
  - the lineage count in `regrant_not_dispatched` and in any resolution regrant;
  - a test with an `unknown` manager call as the guard trigger.
- Make the three MAF test files read `FLOW_MAF_PYTHON`.
- Carried nit: `send_lock` lacks `O_NOFOLLOW`.

### Capability Gaps Observed

- `review-rework-transition` (reuse, seen 11 times, already promoted): the acceptance-review fixes ran inside `reviewing`.
- `reviewer-role-command-execution` (reuse, seen 3 times): the reviewers could not run suites, mutations, or diff checks.
- `maf-runtime-interpreter-preflight` (reuse, seen 3 times): the pinned gated-test interpreter vanished and was rebuilt by hand.
- `project-test-command-declaration` (reuse, seen 3 times): the test command was restated by hand in every brief.
- `orchestration-manifest-assignment-command` (new): review and recheck assignments were added by hand-editing the manifest JSON.
