# Validation Results: producer-turn-contract

Validated against the change itself, in the `~/src/flow` checkout on branch `codex/producer-turn-contract`. No surrogate was used. No paid or live calls were made.

## Automated

- **Full suite:** `python3.12 -m unittest discover -s tests` with `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python` (`scratchpad/suite-main.sh`, which fails on any skip). Result: **Ran 1571 tests, OK, 0 skipped**, rc=0. The baseline on main was 1,562, so this adds 9 tests.
  - **Acceptance-lane rerun at `46dbe23` (HEAD code): Ran 1571 tests, OK, 0 skipped**, rc=0. This closes the gap below.
  - The first run was with the code at `fdb112b`. Commit `46dbe23` changed one assertion in a test that already passed, adding a phrase. After it, `tests.test_chartered_delivery_gateway` was rerun: 49 OK.
- **New tests** (`tests/test_chartered_delivery_gateway.py`):

  | AC | Test |
  |---|---|
  | AC1 | `ExecutionFactsTests.test_chartered_facts_state_the_single_editor_call`: v6, v7 and v8 subtests; four phrases; block ≤ 1,500 bytes |
  | AC2 | `ExecutionFactsTests.test_protocol_5_facts_are_unchanged`: literal byte identity, including a predecessor line |
  | AC2b | `CharteredPreparationTests.test_manager_task_carries_the_single_editor_call_fact`: captures `task` from the fake supervisor |
  | AC3(a) | `CharteredEditVerificationTests.test_clean_baseline_without_an_edit_names_no_edit` |
  | AC3(b) | `test_out_of_scope_file_names_scope` and `test_deleted_allowed_file_names_scope` |
  | AC3(c) | `test_declared_regression_without_an_edit_names_the_baseline` |
  | AC3 control | `test_declared_regression_with_an_edit_passes` |
  | AC4 | `CharteredPreparationTests.test_editor_without_an_edit_fails_with_a_no_edit_reason`: pins `result["reason"] == receipt["failure_detail"]`, then asserts it equals "editor made no edit to the worktree" |

## Mutation checks (AC6)

Each mutation was applied to `cli/delivery_gateway.py`, the test file was run, and the file was restored from a copy (`cp gw.bak`), never with `git checkout`. After each restore, `git status` was clean.

| Mutation | Edit | Failed tests |
|---|---|---|
| M1 | Delete the `+ ("- The approved editors get one call ... the attempt.\n" if chartered else "")` term | AC1 v6, v7 and v8, and AC2b: 4 failures |
| M2 | Replace `if not changed: raise ...no edit...` followed by `if any(` with the old `if not changed or any(` | AC3(a) and AC4: 2 failures |
| M3 | `sed` the (c) message back to "editor produced no observed change" | AC3(c): 1 failure |
| M4 | `sed` `\"do not edit yet\" step` to `placeholder step` | AC1 v6, v7 and v8: 3 failures |

The first M4 attempt did not apply, because the replace pattern missed, so the tests ran against unmutated code and passed. It was re-run with a `sed` edit, and a grep confirmed the phrase was gone before the tests ran.

## AC7: resumable attempt scan

- A JSON scan of `.flow/runs/*/execution` found no `expansion_paused` or `interrupted` status.
- A ledger scan (`attempts` table in each `ledger.sqlite`) found two attempts at `started`:
  - `v8-live-validation`: `f628faa9…`, protocol 8. The run is archived.
  - `maf-restart-reconciliation`: pre-chartered schema, with no protocol column. The run is archived.
- `v8-live-validation-2` (branch `codex/v8-live-validation-2`, PR #43) is archived, and its attempts ended terminally.
- **Verdict:** pass. No active run holds a resumable chartered attempt. The one `started` protocol-8 attempt belongs to an archived run and would be refused on resume, because the manager `prompt_digest` now covers the new line. That is accepted, since there is no back-compat requirement.

## Manual

- The doc sentence is in `docs/maf-adoption-design.md` in the paragraph "The current chartered path is v8" (AC5).
- The protocol-5 text was diffed textually from `fd4954b` against the helper. The only difference is a lone `+` continuation line in the layout.

## Runtime

- Not run. Live behaviour (whether the manager follows the guidance) is measured by the planned `v8-live-validation-3`.
