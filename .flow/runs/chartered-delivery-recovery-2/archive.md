## Archive Summary

### Work Closed

- `chartered-delivery-recovery-2` was accepted on 2026-09-25 (`review.md`, "Final disposition"; `accept-review` succeeded) on branch `codex/chartered-delivery-recovery-2` at `8bf46c8`. It is stacked on 1b (PR #29, open) and not yet pushed. This closes v8 chartered delivery recovery: chunk 1a is PR #26, chunk 1b is PR #29, and this is chunk 2.
- **Operator reconcile.** An interrupted v8 attempt whose producer or verifier response Flow had already stored is now completed without a resend:
  1. `inspect-delivery` shows each blocker's route and the owner generation.
  2. `resolve-execution … --disposition resolved_completed --expected-generation N` records the resolution.
  3. `recover-delivery-lead` continues.
- **The route.** It refuses `--evidence-file`, requires `--expected-generation`, and accepts only `resolved_completed`. It holds `recovery_lock`, then `run_lock`, then `send_lock`, then SQLite. `resolve_observed_v8` re-validates the stored observation and its recorded send inside the resolving transaction, and appends the resolution at the current generation with no bump.
- **Binding.** Recovery accepts a resolved action only when exactly one resolution matches the action, the attempt, and a recovery-chain generation.
- **Abandon-only rows.** Manager calls and actions without a stored observation are reported "unresolvable; abandon only". `resolve_unknown` refuses v8, so operator-supplied evidence never reaches a v8 ledger (C1).
- **Guards:**
  - a v8 worktree that is, contains, or sits inside the project `.flow` is refused, compared by device and inode;
  - the v8 no-dispatch regrant is refused;
  - `send_lock` refuses a symlink or a hard link;
  - the MAF tests read only `FLOW_MAF_PYTHON`.
- ADR 0016 has the chunk 2 amendment, with its assumptions and residuals.
- **Scope decisions along the way:**
  - C1: Flow-owned evidence only.
  - C2: the v8 no-dispatch regrant is guarded, not built.
  - C3: the hardening stays in chunk 2.
  - Option A: operator-confirmed reconcile.
  - P1–P4: the CLI contract.
  - Solution amendments: manager-call resolution and the trace route dropped; the worktree guard added.

### Validation

- **Automated:**
  - The full suite passed 1465 tests with 0 skipped (`validation/full-suite.log`, at `2c1f9eb`). The MAF-gated tests passed 11 (`validation/maf-gated.log`, the R9 merge gate).
  - **Mutations:** M1 (binding), M3 (the no-dispatch guard), and M4 (a bumped generation, caught by binding) each fail their test. M2 (a resend) is an accepted AC11 deviation: every attempt ended in a refusal or denial before any resend, blocked independently by answer-mode restore, the ledger's replay of completed rows, eligibility, worktree drift, and the verifier limits.
- **Manual:**
  - Definition: adversarial review by product, requirements, architecture, and security.
  - Solution: premise verification.
  - Plan: architecture, validation, requirements, and product reviews.
  - Implementation: quality and security reviews.
  - Acceptance: quality and proof reviews.

  Every finding is dispositioned in the run's `adversarial-review.md`, `research/*.md`, and `review.md`.
- **Runtime/deploy:** no live provider run; hermetic tests only, by plan.

### Residual Risks

- A symlink inside the worktree that points into `.flow` relies on the Codex sandbox canonicalizing write paths (unverified).
- A lead that is released or needs attention while an observed action is still uncertain can only be abandoned. This fails closed.
- R3: a resolved producer without a verifier input is checked for scope only, and its diff is then judged by the verifier.
- Manager calls and unobserved actions stay abandon-only by design (ADR 0012).
- Reason-code imprecision in two refusals: the lock label, and a stale lead inside the authority guard.
- The v5–v7 missing-`--evidence-file` error changed form (the exit code is unchanged).

### Follow-up Work

- Push the chunk 2 branch and open its PR, rebased onto `main` once #29 merges (or stacked). The PR body carries `validation/maf-gated.log`.
- Possible later slices:
  - automatic reconcile (it needs an ADR 0016 amendment);
  - trace-backed resolution (it needs an action-bound trace digest);
  - operator-authored import (it needs an ADR 0012 amendment and the security review's provenance record).
- Process: run focused tests per commit and the full suite before each handback or PR, rather than a full run after every commit.

### Capability Gaps Observed

- `review-rework-transition` (reuse, seen 12 times, promoted): the review fixes ran inside `reviewing`.
- `reviewer-role-command-execution` (reuse, seen 4 times): reviewers could not run diffs, tests, or mutations.
- `project-test-command-declaration` (reuse, seen 4 times): the suite command and a fail-closed check were scripted by hand, and a pipe once masked a failing suite.
- `orchestration-manifest-assignment-command` (reuse, seen 2 times): manifest assignments were hand-edited in every lane.
- `solution-amends-approved-definition` (new): no lifecycle step to record or re-approve definition amendments made during solutioning.
