# Handoff: producer-turn-contract

## What changed

- **`cli/delivery_gateway.py`:**
  - The manager's Flow-verified facts block is now built by a pure `_execution_facts(envelope, job, source_commit)`.
  - For chartered protocols (6, 7, 8) the block adds a line: the approved editors get one call in total, Flow refuses a second editor call, that call must make the complete edit, and an inspect-only or "do not edit yet" editor step fails the attempt. This addresses D7.
  - Protocol 5 text is unchanged.
- **`_verify_chartered_edit`** now separates the no-edit outcomes (D6):
  - an empty worktree status gives "editor made no edit to the worktree";
  - the scope message is unchanged;
  - "the allowed paths still match the pinned baseline" covers a declared-regression baseline where the editor did nothing.
- **`docs/maf-adoption-design.md`:** one sentence on the one-call contract.
- **Tests:** 9 new tests in `tests/test_chartered_delivery_gateway.py`.

## Commits

- `29c9c6a` refactor(delivery): extract the execution facts builder
- `91e567b` fix(delivery): report a chartered no-edit outcome distinctly
- `fdb112b` fix(delivery): tell the manager the editor gets one call
- `46dbe23` test(delivery): pin the complete-edit phrase in the one-call fact

## Proof

- Full suite: 1,571 OK, 0 skipped.
- Mutations M1–M4 were each caught by the intended tests.
- AC7 scan passed.

Details are in `validation-results.md`. Review dispositions are in `implementation-review.md`.

## Risks and next actions

- The rule is guidance only, per decision 2a. The manager may still spend the editor call on inspection. The fail-closed check remains, and now reports it clearly as "no edit". `v8-live-validation-3`, with a new work id, measures whether the guidance works.
- Resuming the archived `v8-live-validation` protocol-8 attempt would be refused because of the `prompt_digest` change. This is accepted.
- Nothing is pushed. Branch `codex/producer-turn-contract` is based on main as of 0.37.0. PR #43 (`v8-live-validation-2`) is separate and still open.
