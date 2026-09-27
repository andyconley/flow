# Acceptance Criteria: producer-turn-contract

- **AC1.** The facts text is built by a pure helper, `_execution_facts(envelope, job, source_commit)`, and appended to the manager task exactly as before. For every chartered protocol (6, 7, 8), a parameterized test asserts it has a line saying:
  - the approved editors get one call in total, and Flow refuses any second editor call;
  - that call must read what it needs and make the complete edit in the same turn;
  - an inspect-only or "do not edit yet" delegation to an editor fails the attempt.

  The whole chartered facts block stays at or under 1,500 bytes; a test asserts this.
- **AC2.** For protocol 5 (not chartered), the facts text is byte-identical to today's, checked in the same parameterized test.
- **AC2b.** Through `_execute_prepared_delivery`, a fake supervisor receives a task that contains the new line. This follows the pattern of `test_no_actions_yields_linked_failed_receipt`.
- **AC3.** `_verify_chartered_edit` reports distinct reasons:
  - **(a)** no changed paths: "editor made no edit to the worktree";
  - **(b)** any path outside `write_paths`, or a status other than ` M`, `M ` or `??`: "editor changed files outside the approved job scope". This keeps the old text;
  - **(c)** changed paths, all of which still hash to the baseline: "editor made no edit: the allowed paths still match the pinned baseline". This covers a declared-regression baseline where the editor did nothing, and a mode-only change.

  Each case has its own test:
  - (a) a clean baseline;
  - (b) an out-of-scope path, and a deleted allowed path;
  - (c) a `declared_regression` baseline with no editor change.
- **AC4.** Through `_execute_prepared_delivery`, a chartered attempt whose producer returns without editing fails with reason (a), not the scope text. The implementer first pins the field it lands in (the result reason or the receipt failure) and asserts on that field.
- **AC5.** A doc sentence records the editor's one-call contract and states that Flow tells the manager.
- **AC6.** Proof:
  - the full suite is OK with 0 skipped, run with `FLOW_MAF_PYTHON`;
  - mutation checks: removing the new facts line fails AC1 and AC2b; routing the empty case back to the scope message fails AC3(a) and AC4; restoring the old (c) message fails AC3(c).
- **AC7.** Before merge, no attempt in `.flow/runs/*/execution` is `expansion_paused` or interrupted. The result is recorded in `validation-results.md`.
