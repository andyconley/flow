# Brief: acceptance review, chunk 2

Run `chartered-delivery-recovery-2`, lane `review`. Read-only; do not edit files. Return findings inline; the orchestrator records them in `review.md`.

## Task

Review chunk 2's implementation against `plan.md` (P1–P4, contracts) and `acceptance-criteria.md` (AC1–AC12; AC4 removed).

- **Diff:** `git diff 87bb715..HEAD -- cli tests docs`, in `/Users/andyconley/.codex/worktrees/delivery-recovery/flow` on branch `codex/chartered-delivery-recovery-2`.
- **Commits:** 4331765, 9155c4d, 08b35bf, c4a613d, abede3d, a7f43e6, f6b5ea9, 7e94e84, 3d6cec2, 3561c8e, ef60915, df6808b, af223c0, c90d58c, a54925d, 32ab015.

Invariants to challenge:

1. **Evidence.** Only Flow's stored observation resolves an action, re-validated inside the resolving transaction. No operator-supplied content reaches the ledger.
2. **No mutation on refusal.** Every refusal (route, ledger, binding, guards) mutates nothing. Lock files are the one exception.
3. **Fencing.**
   - Lock order: `recovery_lock`, then `run_lock` (via `delivery_authority_guard`), then `send_lock`, then SQLite.
   - A live run is refused.
   - The stale-generation and event high-water checks close every window between the route's checks and the write.
4. **No generation bump.** A resolution at the current generation keeps the recovery chain continuous. A resolved verifier is evaluated once with no resend.
5. **Binding.** `unbound_resolutions` accepts only one resolution for the action, in this attempt, at a chain generation. Look for a bypass, and for a false refusal of an honest recovery.
6. **Unchanged behavior.**
   - v5–v7 resolution is unchanged apart from the text of the missing-`--evidence-file` error.
   - `_append_resolution_locked` keeps `resolve_unknown`'s behavior byte-identical.
7. **Guards.** Check the worktree guard's path logic (symlinks, `..`, case), the v8 no-dispatch guard, `send_lock` `O_NOFOLLOW`, and the MAF interpreter coming only from the environment.

## Evidence inventory

- **Intent:** `.flow/runs/chartered-delivery-recovery-2/requirements.md` (C1–C3, amendments), `acceptance-criteria.md`, `solution.md`, `plan.md`, `validation-plan.md`, and `research/plan-architecture.md` / `research/solution-verify.md`.
- **Code:**
  - `cli/execution_ledger.py`: `resolve_observed_v8`, `_append_resolution_locked`, `regrant_not_dispatched`, `send_lock`
  - `cli/delivery_gateway.py`: `resolve_execution`, `_resolve_chartered`, `_refuse_project_flow_in_worktree`, the `_recovery_gates` refusal pointer
  - `cli/delivery_recovery.py`: `recovery_chain`, `unbound_resolutions`, `EVIDENCE_NEEDED`, eligibility routes
  - `cli/delivery_projection.py`, `cli/flow.py` (parser and dispatch)
  - `docs/adr/0016-chartered-v8-recovery.md` (the chunk 2 amendment)
- **Tests:**
  - `tests/test_chartered_delivery_recovery.py`: `ObservedReconcileHarness`, `ObservedReconcileLedgerTests`, `V8ResolveRouteTests`, `BoundaryReconcileTests`, the new tests in `LeadChangeFenceTests` and `CharteredRecoveryRefusalTests`, and `CharteredRecoveryEntryTests`
  - `tests/test_chartered_delivery_gateway.py` (the prepare worktree guard)
  - `tests/test_structured_verifier_ledger.py` (`send_lock`)
  - `tests/maf_env.py`, `tests/test_maf_env.py`
- **Evidence:**
  - `validation/full-suite.log`: 1461 OK, 0 skipped.
  - `validation/maf-gated.log`: 11 OK.
  - `validation/mutations.log`: M1, M3, and M4 each fail. M2 is recorded as not constructible as a single mutation (three independent guards block a resend). Assess that claim.

## Output

Findings ranked blocker, major, minor, or nit, each with `file:line`, a concrete scenario, and a claim status (observed, inferred, or unverified). Then a verdict. Keep it under ~700 words.

## Acceptance focus (this is the acceptance lane, not a repeat of implementation review)

- Judge each AC1–AC12 against `acceptance-criteria.md`: met, partially met, or not met, with the deciding test.
- `research/implement-review.md` holds the implementation review and its dispositions. Do not re-raise a disposition unless its fix is wrong or incomplete; check the fixes in `c90d58c`.
- Two engineer decisions are open. Give your recommendation on each, but don't treat them as defects:
  - **(1)** M2 (AC11) is recorded as a deviation.
  - **(2)** `resolve_unknown` still accepts v8 at the ledger level.
