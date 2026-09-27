# Plan: producer-turn-contract

Fixes D7 (the manager isn't told the editor's one-call contract) and D6 (a no-edit outcome is misreported), found by `v8-live-validation-2`. Requirements are in `requirements.md`; AC1–AC6 are in `acceptance-criteria.md`.

## Current state (verified 2026-09-26)

- `cli/delivery_gateway.py`, `_execute_prepared_delivery`, appends "Flow-verified execution facts:" to `task`. The chartered branch covers protocols 6, 7 and 8 (`chartered = ... in {6, 7, 8}`).
  - Its editor line reads: "The approved editor may edit only the charter's allowed paths. Flow verifies the diff and runs the targeted test after that edit; the full suite is an acceptance check."
  - Nothing says the editor gets one call.
- `cli/execution_ledger.py` refuses any producer call after a completed one: `producer_already_completed`, a hard limit that no expansion can lift. After a producer completes, the gateway's next manager turn runs `verify_edit`, which is `_verify_chartered_edit` when the job is chartered.
- `_verify_chartered_edit`: `if not changed or any(<bad status or out of scope>)` raises "editor changed files outside the approved job scope". The next check raises "editor produced no observed change". An empty worktree therefore gets the scope text.
- The read-only analyst and verifier specialists can't read files. So the editor's turn is the only place code can be inspected.
- The charter task is sealed in `job_contract.task`, and the facts are appended afterwards. So envelope and charter digests don't change. Each manager call's recorded `prompt_digest` does cover the task text, though, so an attempt paused before this change can't be resumed after it (AC7 checks for any).
- A `declared_regression` baseline already has the allowed files at ` M`. An editor that does nothing there reaches the "no observed change" branch, not the empty branch (review F1).

## Changes

1. **Extract the facts helper.** Move the facts construction into a pure `_execution_facts(envelope, job, source_commit) -> str`. It returns the text starting with "\n\nFlow-verified execution facts:\n". `_execute_prepared_delivery` does `task += _execution_facts(...)`. The output for protocol 5 stays byte-identical.
2. **The D7 facts line.** In the chartered branch only, directly after the editor line, add:

   > - The approved editors get one call in total; Flow refuses any second editor call. That call must read what it needs and make the complete edit in the same turn. Never delegate an inspect-only or "do not edit yet" step to an editor: Flow checks the worktree right after it, and no edit fails the attempt.

   That's about 300 bytes (review F4 and F6).
3. **The D6 split** in `_verify_chartered_edit`:
   - `if not changed: raise ContractError("editor made no edit to the worktree")`;
   - then the existing `any(...)` scope check, keeping its message;
   - then the hash check, with its message changed to "editor made no edit: the allowed paths still match the pinned baseline".

   The source-commit check stays first. Recovery callers (`record=False`) inherit the new text inside their `WORKTREE_DRIFT` detail; no other change is needed (review F5).
4. **Docs.** In `docs/maf-adoption-design.md`, in the paragraph beginning "The current chartered path is v8", add one sentence. It says the approved editors get a single call per attempt, which must read and edit together, and that Flow states this in the manager's execution facts (review F7).

## Tests (in `tests/test_chartered_delivery_gateway.py` unless an existing helper fits better)

- **AC1 and AC2.** Call `_execution_facts` directly with minimal envelopes for protocols 5, 6, 7 and 8, using `subTest`.
  - For 6, 7 and 8, assert "one call in total", "refuses any second editor call" and "do not edit yet", and that the block is at most 1,500 bytes.
  - For 5, assert equality with a literal copy of today's text.
- **AC2b.** Use a fake supervisor that captures `task`, following `test_no_actions_yields_linked_failed_receipt`, and assert that the new line is present. (The manager adapter is the wrong seam: it runs only inside the MAF manager round trip.)
- **AC3.** Call `_verify_chartered_edit` directly on a temporary git worktree in four cases:
  - (a) clean: "made no edit";
  - (b1) an edit to a file outside `write_paths`: the scope text;
  - (b2) an allowed file deleted: the scope text;
  - (c) a `declared_regression` baseline with the allowed file already modified, and no further editor change: "the allowed paths still match the pinned baseline".

  Use `assertRaisesRegex` on each message.
- **AC4.** Through `_execute_prepared_delivery`, a fake supervisor sends the editor proposal to a worker that returns without writing, following the existing pattern around `test_chartered_delivery_gateway.py:410-417`. First pin where the failure text lands (the result reason or the receipt failure), then assert "editor made no edit to the worktree" there.
- Existing tests stay green.

## Validation

- Run the targeted test modules, then the full suite via `scratchpad/suite-main.sh`, which fails closed on skips and sets `FLOW_MAF_PYTHON`.
- **Mutation checks,** restoring from file backups and never with `git checkout`:
  - **M1:** delete the new facts line. Expect AC1 and AC2b to fail.
  - **M2:** revert the empty-case split. Expect AC3(a) and AC4 to fail.
  - **M3:** restore the old (c) message. Expect AC3(c) to fail.
  - **M4:** drop the "do not edit yet" clause. Expect AC1 to fail.
- **AC7:** scan `.flow/runs/*/execution` ledgers for `expansion_paused` or interrupted attempts before merging.
- Make no live or paid calls.

## Sequencing and commits

1. `refactor(delivery): extract the execution facts builder` (behavior unchanged; its test pins the protocol 5 and 8 text).
2. `fix(delivery): report a chartered no-edit outcome distinctly` (D6 and its tests).
3. `fix(delivery): tell the manager the editor gets one call` (D7, its tests and the doc).

## Risks

The manager may still delegate inspect-only work. The existing fail-closed check stays the backstop, and `v8-live-validation-3` measures this live.
