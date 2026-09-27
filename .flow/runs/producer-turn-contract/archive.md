## Archive Summary

### Work Closed
- **Run:** `producer-turn-contract` (fix run for D6 and D7, found live by `v8-live-validation-2`). Review accepted: `review.md`.
- **D7:** the manager's Flow-verified facts, now built by a pure `_execution_facts` in `cli/delivery_gateway.py`, state for chartered protocols 6–8 that:
  - the approved editors get one call in total, and Flow refuses a second;
  - that call must make the complete edit;
  - an inspect-only or "do not edit yet" editor step fails the attempt.

  This is guidance only; enforcement is unchanged. Protocol 5 text is byte-identical.
- **D6:** `_verify_chartered_edit` now names the no-edit outcomes:
  - "editor made no edit to the worktree";
  - "editor made no edit: the allowed paths still match the pinned baseline" (a declared-regression baseline);
  - the scope message is unchanged for real scope violations.
- **Docs:** one sentence in `docs/maf-adoption-design.md`.
- **Tests:** 9 new tests.
- **Commits:** `29c9c6a`, `91e567b`, `fdb112b`, `46dbe23`.

### Validation
- **Automated:**
  - Full suite 1,571 OK, 0 skipped, with `FLOW_MAF_PYTHON`, rerun at HEAD code `46dbe23`.
  - Mutations M1–M4 were each caught by the intended tests (`validation-results.md`).
- **Manual:**
  - The protocol-5 text was diffed against `fd4954b`.
  - Each claim in the new facts line was checked against the ledger's enforcement (`execution_ledger.py:487-507`, `:1128-1161`).
  - The AC7 attempt scan passed.
- **Runtime/deploy:** none, by design. No paid or live calls were made.

### Residual Risks
- The manager may still ignore the guidance. The fail-closed edit check remains and now reports the outcome accurately.
- The archived `v8-live-validation` protocol-8 attempt can't be resumed, because the manager `prompt_digest` changed. This is accepted, since there is no back-compat requirement.
- A recovery `WORKTREE_DRIFT` refusal can carry "editor made no edit…" text when a recorded edit was lost. This is accepted.

### Follow-up Work
- Push and open a PR for `codex/producer-turn-contract`, release, and reinstall. PR #43 (`v8-live-validation-2`) is open separately, and its STATE.md entry may conflict.
- `v8-live-validation-3` with a new work id, to measure whether the manager follows the one-call guidance live. Reset `~/src/flow-v8-live-job-2` to `d6d771f2`.
- Optional review suggestions, not scheduled:
  - check the byte cap with a `declared_regression` baseline kind;
  - add a mode-only branch (c) test.

### Capability Gaps Observed
- **Mutation checks were applied and restored by hand.** One mutation's edit silently failed to apply, and the tests ran against unmutated code before this was noticed.
- **Recorded suite results are not bound to the commit they ran on.** A reviewer caught a one-commit staleness.
- **Ledger:**
  - `mutation-check-harness`: reuse, now seen 3 times, already promoted;
  - `validation-evidence-commit-binding`: new.
- **Repeats:** `mutation-check-harness` (3, already promoted).

### Memory Updates
- **STATE (`.flow/memory/STATE.md`):** added a `producer-turn-contract` entry with its next steps. Marked `manager-progress-retry` as merged in PR #42 and released in v0.37.0.
- **Runtime memory entries written:** updated `project_flow_delegated_expansion.md` (D6/D7 fixed and the `prompt_digest` resume note) and its MEMORY.md index line.
