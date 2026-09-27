# Validation Plan: step5-cancellation

## Acceptance criteria mapped to tests

| AC | Test location | Kind |
|---|---|---|
| AC1, AC1b, AC1c | `tests/test_delivery_cancel.py` | Harness subprocess, real process groups, SIGTERM, FIFO synchronization. AC1c uses a fake `claude` on `PATH` driven through the real `call_claude_edit`. |
| AC2, AC2b, AC2c | `tests/test_delivery_cancel.py` (refusals); `tests/test_process_identity.py` (the TZ stability check) | Real processes; a pid reused with a different start time is simulated by editing the record's start time. |
| AC3 (a)–(e) | `tests/test_delivery_termination.py` | Ledger and gateway fixtures. (b) goes through the runtime-cap path using a stub that raises `MafTransportError`. |
| AC4 | `tests/test_delivery_termination.py` | Real sleeper groups: a live leader, a leader that has exited, and a start-time mismatch. |
| AC5 | `tests/test_delivery_termination.py` | Validator cases, plus seal cases where the rows differ from the ledger. |
| AC6 | `tests/test_delivery_termination.py` | Recover, resolve, decide and resume each refuse. |
| AC7 | `tests/test_delivery_termination.py`, `tests/test_delivery_cancel.py` | A successor runs with stubs after a cancel and after abandons (a), (b) and (d). |
| AC8 | `tests/test_delivery_termination.py` | `delivery-lead resume`: succeeds with terminal-uncertain predecessors; refuses on a started attempt and on a v7 `unknown` attempt. |
| AC9 | `tests/test_delivery_termination.py` | CLI entry through `flow.main` with argv. |
| AC10 | `tests/test_delivery_termination.py` | `inspect-delivery` output; `stuck` over a fixture project with four attempts. |
| AC11 | Manual check | ADR 0019, `maf-adoption-design.md`, and the help regenerated with no diff remaining. |
| AC12 | Full suite plus mutations | See below. |

## Tests added by the plan-review amendments

| Amendment | Test |
|---|---|
| A1 | Seal with an `allowed` row and a `pending` expansion; the receipt shows `not_dispatched` and a cancelled expansion. |
| A2 | Bare SIGTERM with nothing in flight, blocked on the child read: `interrupted` with cause `cancel_signal`, and no receipt. |
| A3 | Cancel while blocked in a manager call. |
| A6 | Set the flag, then enter `interruptible()`: it raises at once, and only once. |
| A7 | A `recovery` or `decide` lock held in a child process: `recovery_in_progress`. |
| A8 | A probe interleaved with a live acquisition does not fail the live run; the probe creates no lock file. |
| A10 | Recover a cancelled or abandoned attempt that has recoveries: `ATTEMPT_TERMINAL`. |
| A11 | Real `run_maf_delivery` with a fake `FLOW_MAF_PYTHON` child (AC1b), and the real runtime-cap deadline (AC3(b)). |

## Mutation checks (AC12)

Each is applied from a file backup, run against the focused test files, and restored with `git status` confirmed clean. Before running the tests, grep to confirm the mutation actually applied.

| Mutation | Tests that must fail |
|---|---|
| M1: allow uncertain rows only for `abandoned` | AC1, AC5 |
| M2: blocker excludes all terminal statuses | AC8, the v7 case |
| M3: skip the start-time check | AC2, AC4 |
| M4: seal `cancelled` without a cancel request | AC2b |
| M5: allow resume on `abandoned` | AC6 |
| M6: keep raising after the outcome is recorded | AC2c |

## Full suite

Run with `FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python`, expecting OK with 0 skipped. Rerun it at the final commit before handback, and record the commit in `validation-results.md`.

## Per-check verdicts to record

- Process identity on macOS: validated.
- The Linux `/proc` reader: parser-tested only; not validated on Linux, since CI runs no delivery tests.
- Real Codex, Claude or Ollama: not exercised; that is covered by `v8-live-validation-3`.

## Out of this plan

No live or paid calls. `v8-live-validation-3` follows this slice.
