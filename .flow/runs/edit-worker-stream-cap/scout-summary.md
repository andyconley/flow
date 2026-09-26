# Scout Summary: edit-worker-stream-cap

- **Branch:** `codex/edit-worker-stream-cap`, from `origin/main` at `a941eb6` (v0.36.0).
- **Planned in:** `flow-plan` on 2026-09-26. Engineer answers 1b, 2a, 3a, 4a, scout.
- **Fixes:** D1 and D2 from `v8-live-validation`.

## Scope

- **D1** (`ab00060` `fix(cli)`, in `cli/claude_edit_worker.py`):
  - `MAX_EVENT_BYTES` rises from 1 MiB to 16 MiB. That cap still limits both the stream-json read and the saved event log, and output past it still raises `ClaudeEditError`, so the outcome stays unknown and the path fails closed.
  - `--include-partial-messages` is dropped. `--verbose` stays, because stream-json needs it.
  - An oversized debug trace no longer aborts the turn; it is truncated to `MAX_TRACE_BYTES` at the end. The 1 s select poll, which existed only for that check, now waits until the deadline.
- **D2** (`3e44cf1` `fix(scripts)`, in `scripts/regenerate-flow-help.py`):
  - `escape_cell` writes `|` as `\|` in both columns of every generated table.
  - `README.md` and `flow-help.md` are regenerated; one row changes, for `flow runtime smoke`.
- **Backlog** (`cdeb3d7` `docs(backlog)`): three gaps promoted through Flow's own `gaps.promote`, pointed at this checkout:
  - `maf-runtime-interpreter-preflight` (4);
  - `reviewer-role-command-execution` (5);
  - `orchestration-manifest-assignment-command` (3).

  The ledger records each as promoted.

## Validation

- **Targeted tests.** `tests/test_claude_edit_worker.py` passed 10 of 10, including four new or rewritten tests:
  - a 3 MiB stream completes and is logged whole;
  - output over the cap raises `ClaudeEditError` and the log is clamped to the cap;
  - the command has no partial-messages flag;
  - a 2 MiB trace leaves the turn successful, with the trace truncated to 1 MiB at mode 0600.

  The new `tests/test_regenerate_flow_help.py` passed 2 of 2 (escaping, and every real row has exactly two cells), and `--check` is clean.
- **Mutation checks: 4 of 4 caught.**
  - Restoring the 1 MiB cap fails the 3 MiB test.
  - Restoring the partial-messages flag fails the argv test.
  - Restoring the trace abort fails the trace test.
  - Removing the escaping fails both generator tests.
- **Full suite:** 1,543 tests OK, 0 skipped, with `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python`.
- **Quality review** (quality-reviewer): approved, with no critical or important findings.
- **Live proof** is deferred to `v8-live-validation-2`, after release.

## Handback

- **Outcome:** D1 and D2 are fixed and ready for a PR. The next release (v0.36.1) unblocks `v8-live-validation-2`.
- **Caveats** (review suggestions, accepted and not acted on):
  - the debug trace can grow on disk until the timeout, and it's only truncated afterwards;
  - truncation keeps the start of the trace, not the end;
  - `flow help` in a terminal shows a literal `\|`;
  - the trace cleanup's `finally` can skip the event-log chmod if the trace file disappears. That behaviour predates this change.
- **Scope note:** two primary files plus a backlog commit is more than the usual one-file scout size. The engineer approved this in plan, with three logical commits.
- **Capability gap:** on a release install, `flow gaps promote` only prints paste blocks, so promoting into a dev checkout needed a direct Python call.
