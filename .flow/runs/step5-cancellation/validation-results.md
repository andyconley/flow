# Validation Results: step5-cancellation

Branch `codex/step5-cancellation`. Implementation commits, on top of the plan commit `62a4d5f`:

- `5bf826b` C1: ledger seal
- `0973be1` C2: process identity
- `1632044` C3: abandon, the lead CLI, and stuck
- `1050db2` C4: cooperative cancel
- `ac3aa4c` C5: ADR 0019 and docs
- `b066309`: review fixes

## Full suite

The full suite (`scratchpad/suite-main.sh`, with `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python`) ran green after every commit, with 0 skipped:

| Commit | Result |
|---|---|
| C1 `5bf826b` | 1,581 tests OK |
| C2 `0973be1` | 1,598 tests OK |
| C3 `1632044` | 1,614 tests OK |
| C4 (`1050db2`, before the comment-only amend) | 1,630 tests OK |
| Review fixes `b066309` | 1,638 tests OK |

## Acceptance criteria to tests

| AC | Test (file :: class.test) | Oracle |
|---|---|---|
| AC1 | `test_delivery_cancel` :: `LiveCancelTests.test_cancel_during_a_blocked_provider_call` | Harness parent blocked in a real provider session; `cancel-delivery` returns `cancelled` in under 45 s. The receipt has the actor, explanation and `cancel_request`; the in-flight action is `unknown`; `sends == ["editor"]`; the owner generation is 2; no recorded group is alive; the parent exits 0. |
| AC1 (lead states) | `LiveCancelTests.test_cancel_on_the_real_maf_child_under_each_lead_status` | The same outcome with the lead `active`, `attention_required` and `released`, with the lead changed while the parent waits on the child. During a guarded send the parent holds the run lock, so the lead cannot change then. |
| AC1b | Same test | The real `run_maf_delivery` with a fake `FLOW_MAF_PYTHON` child: a `maf` group is recorded, killed, and the record shows `cancel_supported: true` and closed. |
| AC1c | `LiveCancelTests.test_cancel_during_the_real_claude_edit_worker` | A fake `claude` on `PATH` runs through the real `call_claude_edit`; its `provider` group is recorded and killed; the result is `cancelled`. |
| A3 | `LiveCancelTests.test_cancel_while_blocked_in_a_manager_call` | The manager call is `unknown` in a `cancelled` receipt. |
| AC2 | `CancelRefusalTests.test_each_refusal`, `test_a_terminal_attempt_refuses`; `test_process_identity` :: `StartTimeTests.test_the_start_time_does_not_depend_on_the_timezone` | Each refusal code (`attempt_not_live`, `process_identity_mismatch`, `foreign_machine`, `cancel_unsupported`, `owner_generation_stale`, `attempt_not_started`, and a closed record) leaves the ledger unchanged, writes no request, and leaves the recorded "parent" sleeper alive. The start time reads the same under three timezones. |
| AC2b / A2 | `SignalWithoutRequestTests.test_a_bare_sigterm_leaves_the_attempt_started_with_an_interruption` | A bare SIGTERM while waiting on the child: `interrupted` / `cancel_signal`, the attempt still `started`, no receipt, no sealed digest. |
| AC2c | `SignalWithoutRequestTests.test_a_cancel_after_the_runtime_outcome_reports_the_real_receipt`, `test_a_request_for_another_generation_is_not_a_cancel` | A cancel after the outcome returns `attempt_finished` / `completed` with the parent's own receipt. A request for another generation records an interruption and the attempt stays `started`. |
| AC3(a) | `test_delivery_termination` :: `AbandonTests.test_the_dead_end_is_abandoned_under_every_lead_status_without_touching_the_claim` | For `active`, `attention_required` and `released`: sealed `abandoned`; the unknown send is kept; the generation goes up by 1; `run.json` is byte-identical; the worktree is unchanged; no test runs. |
| AC3(b) / A11 | `AbandonTests.test_a_runtime_cap_interruption_is_abandoned_and_its_successor_completes` | The real launcher with a silent fake child and `runtime_seconds=2` gives a `transport` interruption. Abandon reports the `maf` group gone, seals with cause `transport`, and a successor completes. |
| AC3(c) | `AbandonTests.test_an_interrupted_recovery_is_abandoned_with_its_recovery_block` | The receipt's recovery block lists generation 2, and the termination owner generation is 2. |
| AC3(d) / A12 | `PausedAbandonTests.test_a_paused_attempt_is_abandoned_its_request_cancelled_and_a_successor_completes` | Cause `expansion_paused`; the request is `cancelled`, with an `expansion_cancelled` event whose cause is `abandoned`; `stuck` is empty afterwards; a successor completes. |
| AC3(e) | `TerminalSealTests.test_damaged_evidence_is_recorded_rather_than_refused`, `AbandonTests.test_damaged_evidence_does_not_stop_an_abandon` | `baseline_missing`, `trace_oversized` (with digest and size) and `draft_receipt_replaced` are recorded, with null fields. |
| AC4 / A7 | `AbandonRefusalTests` (4 tests); `test_process_identity` :: `ReapTests` | `attempt_running` while a live lock is held; `recovery_in_progress` for a `recovery` or `decide` lock held in a child process; a stale generation; `attempt_dir_unsafe`; `attempt_not_started`; `lead_guard_ledger_unreadable`. None of them mutates anything or signals anything. The reap covers generations 5 and 6: a live group killed, an orphaned member killed, a mismatch reported and left alive. |
| AC5 / A1 | `TerminalSealTests` (validator, row-mismatch, grant-release/expansion-close tests) | The validator accepts `cancelled` and `abandoned`, and rejects failed-with-unknown, v8 `unknown`, termination outside those statuses, a wrong cause, a missing termination, a stale lead generation, and bad damage. The seal refuses changed or dropped rows with no mutation. The receipt shows `not_dispatched`/`cancelled_unconsumed_grant` and a `cancelled` request. |
| AC6 / A10 | `TerminalityTests` (2 tests) | Claim, resolve, decide and resume all refuse `attempt_terminal` for `cancelled` and `abandoned`, with no change, including an attempt that had a recovery. |
| AC7 | `SuccessorTests`, `AbandonTests` (a, b), `PausedAbandonTests` (d), `LiveCancelTests.test_a_successor_completes_after_a_cancel`, `ConsumedGrantInheritanceTests` | Successors complete, list the predecessor with its sealed digest, and count its unknown paid send (`predecessor_paid_calls: 1`). Only the consumed grant raises the successor's paid limit; the cancelled request does not. |
| AC8 | `UncertaintyScopingTests` (2 tests) | `resume` succeeds once the only uncertainty is abandoned. It refuses `reconciliation_required` for a v7 attempt sealed `unknown`. |
| AC9 | `LeadCliTests` (2 tests) | All four lead actions through `flow.main`, with exact outputs. Refusals exit 2 with a stable code: `lead_status_invalid`, `owner_required`, `lead_generation_stale`, `reconciliation_required`, and `owner_generation_stale` from `abandon-delivery`. |
| AC10 | `DiagnosticsTests` (2 tests) | `inspect` shows the attempt status apart from the expansion status, the stopper and cause, damage, the control verdicts, uncertain rows and the next command. `stuck` over four runs lists exactly the three started attempts, each with the right command (`cancel`, `decide-expansion`, `abandon`); it is byte-for-byte read-only and exits 0. |
| AC11 | Manual | ADR 0019 is written; ADR 0016 has an amendment note; `docs/maf-adoption-design.md` step 5 is updated; `scripts/regenerate-flow-help.py --check` reports up to date. |
| A6 | `test_delivery_cancel` :: `ControllerTests` (5 tests) | The flag only; one raise inside a wait; a pending cancel breaks a wait on entry, once; disarm; restore. |
| A8 | `ProbeTests.test_the_probe_is_read_only_and_a_live_run_outlasts_it` | `absent` without creating the file, then `held`, then `free`. A live acquisition succeeds while a probe briefly holds the lock. |
| F13 | `test_delivery_cancel` :: `RecoveryCancelTests`, `test_process_identity` :: `RecoveryControlRecordTests` | A recovery writes its own generation-2 record. A cancel during the recovery's targeted test seals `cancelled` (owner generation 3), sends nothing, and restores the handler. |

## Mutation checks (AC12)

Run in a throwaway git worktree at `ac3aa4c`, so the reviewers' files were never touched. Each mutation was applied from a file backup, confirmed applied by a grep, run against the named tests, then restored from the backup and compared byte for byte with a reference copy. Every file was restored identical.

| Mutation | Edit | Named tests | Result |
|---|---|---|---|
| M1: uncertain rows only for `abandoned` | `_validate_termination` condition | AC5 validator test, AC1 provider cancel | Failed (2 errors) |
| M2: the blocker excludes all terminal statuses | `_blocking_attempts` selects `status='started'` | AC8 v7-sealed-unknown | Failed (1) |
| M3: skip the start-time check | `parent_live`, the reap mismatch check, and the pre-signal recheck | AC2 `test_each_refusal`; AC4 abandon reap; the reap reuse test | All three failed |
| M4: seal `cancelled` without a cancel request | `stop_on_cancel` invents a request | AC2b bare SIGTERM | Failed (1) |
| M5: allow resume on `abandoned` | `_recovery_gates` replays `abandoned` | AC6 `TerminalityTests` | Failed (2) |
| M6: keep raising after the outcome is recorded | `disarm()` does nothing | AC2c after-outcome | Failed (1 error) |

M3 note: mutating `parent_live` alone still failed the AC4 reap test, but not AC2. The second start-time check, immediately before signalling, still refused with `process_identity_mismatch`. That is the defense in depth R3 asks for. With every start-time check skipped, AC2 and AC4 both fail.

## Per-check verdicts

- **Process identity on macOS** (sysctl start time, `IOPlatformUUID`, reaping): validated against the change itself, with real processes, groups and signals.
- **The Linux `/proc` reader:** parser-tested only, against sample text. Not validated on Linux, because CI runs no delivery tests.
- **pidfd signalling (Linux):** not exercised; the macOS path uses `os.kill` after the start-time recheck.
- **Real Codex, Claude or Ollama:** not exercised; fake executables and stubs only. Covered by `v8-live-validation-3`, which is paid and needs Andy's go.
- **Real project smoke test (read-only):** `flow run stuck` and `inspect-delivery` against this checkout listed the real stuck `v8-live-validation` attempt, with next command `abandon-delivery`. It was not abandoned: no destructive action was taken on real runs.

## Review fixes

`b066309` addresses the quality and security findings (see `implementation-review.md`). It adds 8 tests:

- a lost attempt directory is recreated and abandoned, and a successor completes;
- abandon refuses at once behind a held run lock;
- a refused seal leaves the draft untouched;
- an unknown verifier send is abandoned with a valid receipt;
- a FIFO at the lock path never hangs the probe;
- a record naming Flow itself is never signalled;
- a failed cancel leaves no request behind;
- a group older than its recording parent is never signalled.

The liveness verdicts now also cover Flow's own process and init.

## Final run

- **Full suite at `b066309`:** 1,638 tests OK, 0 skipped, with `FLOW_MAF_PYTHON` set.
- **Mutations re-run at `b066309`**, in a throwaway worktree with byte-identical restores:
  - M1, M2, M4, M5 and M6 each failed their named tests.
  - M3, with every start-time check skipped (`parent_live`, reap, and the pre-signal recheck), failed AC2 `test_each_refusal` (`process_identity_mismatch`, and cascades) and the AC4 abandon reap test.
  - Skipping any single check alone is still caught by the other, which is the intended defense in depth.
