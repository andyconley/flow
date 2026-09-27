# Plan: step5-cancellation

**Inputs:**
- Approved `requirements.md` (revision 2, R1–R10);
- `acceptance-criteria.md` (AC1–AC12);
- `definition-dispositions.md`;
- `research/` (three research notes plus `spikes.md`).

**Delivery:** one branch (`codex/step5-cancellation`), one PR, five Conventional Commits in order. Each commit leaves the full suite green.

**Engineer planning decisions (2026-09-27):**
- **1a:** one PR.
- **2a:** spikes run during planning (`research/spikes.md`).
- **3a:** architect review of this plan.
- **4a:** the coordinator implements, with role agents used for review.

## Design decisions fixed by this plan

- **D1. New module `cli/delivery_termination.py`.** It owns:
  - the terminal-uncertain receipt builder;
  - `abandon_delivery`, `cancel_delivery` and `stuck_attempts`.

  This keeps `delivery_gateway.py`, already 1,769 lines, from growing further, beyond the hooks it needs.
- **D2. New module `cli/process_identity.py`.** It owns process start time, machine id, control records, group registration, liveness and reaping. Pure functions plus small file I/O, with no ledger import.
- **D3. New module `cli/delivery_cancel.py`.** It owns the cancel controller: the SIGTERM handler, the `cancel_requested` flag, the `interruptible()` context manager, `DeliveryCancelled(Exception)`, and disarm.
  - `interruptible()` does nothing when no controller is installed.
  - Workers and the supervisor import it directly instead of receiving a parameter. The registrar, by contrast, is an explicit parameter (F19).
- **D4. Start-time format** (S1):
  - `darwin:<sec>.<usec>` from sysctl `KERN_PROC_PID` `p_starttime`;
  - `linux:<boot_id>:<ticks>` from `/proc/<pid>/stat` field 22.

  The Linux reader is parser-tested on fixture text only, and is **not validated on Linux**, because CI runs no delivery tests.

  Machine id comes from `IOPlatformUUID` or `/etc/machine-id`.
- **D5. Control record files:** `execution/<attempt>/control-g<owner_generation>.json`, written once. Groups are appended to `control-g<N>.groups.jsonl`, one line per group: `{pgid, leader_start, kind: maf|provider|test, at}`. Closure writes `control-g<N>.closed`.
  - Cancel request: `execution/<attempt>/cancel-request.json`, written atomically with a temp file and rename, and never a symlink.
- **D6. Lock order is unchanged.**
  - `abandon` mirrors `change_lead_claim`: `run_lock`, then a non-blocking `recovery_lock` probe held until sealing, then the ledger `send_lock` with `BEGIN IMMEDIATE`.
  - The parent's cancelled seal already holds `recovery_lock`. It takes `run_lock` and `send_lock` by non-blocking polling against the 30 s deadline.
  - `cancel-delivery` holds no lock (F2).
- **D7. One ledger seal method for both statuses:** `ExecutionLedger.seal_terminal_uncertain(...)`. `finish_attempt` keeps rejecting uncertainty for its own statuses.

## Commits

### C1 `feat(ledger): seal cancelled and abandoned attempts with their uncertainty`

Covers R5, R6, R7, AC5, AC6 (ledger half), AC7 (lineage) and AC8.

- **`cli/execution_ledger.py`:**
  - Add `TERMINAL_UNCERTAIN = frozenset({"cancelled", "abandoned"})`.
  - Add `seal_terminal_uncertain(attempt_id, status, *, expected_generation, receipt_path, actor, explanation, cause)`. Under `send_lock` and `BEGIN IMMEDIATE` it:
    1. asserts v8, `started`, and the owner generation equals `expected_generation`;
    2. releases `allowed` rows as `not_dispatched` with reason `<status>_unconsumed_grant`;
    3. closes expansions with cause `<status>`, using `_close_expansions_locked`;
    4. reads the receipt bytes and compares its listed actions and manager calls, ids and statuses, against the ledger, refusing on any difference;
    5. runs the existing `_assert_receipt_lineage`, expansion and `manager_progress` checks;
    6. sets the status, reason, receipt path and `sealed_receipt_sha256`, sets `owner_generation+1`, and sets `owner_actor` to the actor;
    7. records the event `attempt_<status>`.

    The receipt is built **after** step 2's grant release is known. To do that, the method takes a `build_receipt(snapshot) -> bytes` callback that runs inside the transaction after steps 2–3, then writes the file and verifies it. That avoids a receipt that predates the grant release.
  - `lead_change_blocker` (~635) and `seal_superseded_attempts` (~673) skip attempts whose status is in `TERMINAL_UNCERTAIN`, and nothing else.
  - `_v8_lineage_locked` (~347), plus the lineage count queries (~371, ~383, ~489–507, ~1606), treat the new statuses as terminal predecessors and keep counting their `unknown` and `started` paid and verifier rows.
  - Terminality: audit every `status='started'` precondition. `claim_chartered_recovery`, the resolve paths and `decide_expansion` must refuse the new statuses with the existing `attempt_not_active` or `attempt terminal` reason.
- **`cli/execution_contracts.py`:**
  - `validate_receipt` (~857, ~997) accepts `status in {cancelled, abandoned}`, and requires `termination: {actor, explanation, cause, owner_generation, lead_generation}` and `evidence_damage: list`.
  - Uncertain rows are allowed only for those two statuses.
  - `PREDECESSOR_TERMINAL_STATUSES` and `_validate_predecessors` accept both, with a required receipt digest.
- **`cli/delivery_termination.py` (new):** `build_terminal_receipt(envelope, attempt_dir, snapshot, *, status, termination)`.
  - Built from the ledger snapshot and envelope: roster, actions, manager calls, checkpoints, `lineage_usage` (only with predecessors), and the expansion and `manager_progress` blocks (from the ledger helpers).
  - `evidence` holds baseline and edit/test data when readable. Otherwise the fields are null, and an `evidence_damage` entry is added (`baseline_missing`, `trace_oversized:{sha256,size}`, `draft_receipt_replaced:{sha256}`).
  - It never runs a test or touches the worktree.
- **Tests:** new `tests/test_delivery_termination.py`, with ledger-level fixtures reusing `CharteredFixture` patterns:
  - validator accept and reject cases;
  - a seal that refuses on row mismatch;
  - grant release, expansion close and generation bump;
  - blocker scoping, including a v7 `unknown` attempt that still blocks;
  - a successor's predecessor digest and lineage counts;
  - terminality refusals.

### C2 `feat(delivery): record process identity for every dispatching parent`

Covers R1, AC2 (identity parts) and the AC4 groundwork.

- **`cli/process_identity.py` (new):**
  - `start_time(pid) -> str | None`, `machine_id() -> str`;
  - `write_control_record(attempt_dir, generation, *, cancel_supported)` and `close_control_record`;
  - `register_group(attempt_dir, generation, pgid, kind)`, which records the leader start time read now;
  - `records(attempt_dir)`;
  - `parent_live(record) -> live | dead | mismatch | foreign`;
  - `reap(attempt_dir) -> report`:
    - leader alive with a matching start time: `killpg`;
    - leader gone: kill members from `ps -A -o pid=,pgid=,uid=` with the same pgid, the same uid, and a start time at or after the leader's;
    - otherwise report;
    - `ProcessLookupError` counts as gone.
- **Registrar seam:** add an optional keyword argument, `on_process_group: Callable[[int, str], None] | None = None`, to:
  - `call_codex` (`cli/codex_worker.py:108`);
  - `call_claude_edit` (`cli/claude_edit_worker.py:118`);
  - `call_claude` (`cli/claude_worker.py:150`);
  - `run_maf_delivery` (`cli/maf_supervisor.py:458`);
  - the v8 recovery launchers in `maf_supervisor` that dispatch for v8;
  - `_run_chartered_test`, which also moves to `start_new_session=True`, with the group killed on timeout.

  Each calls the registrar right after `Popen`.
- **Supervisor cleanup** moves to `os.killpg` (F11).
- **`cli/delivery_gateway.py`:** `_run_prepared_delivery`, and the v8 recovery entry points (restart, pending and answer), write the control record for the current owner generation and pass a bound registrar through `_default_worker_adapter`, the test runner and the supervisor. The record is closed in `finally`.
- **Tests:** new `tests/test_process_identity.py`:
  - the sysctl start time for self and for a child;
  - `None` for a dead pid;
  - stable when `TZ` changes;
  - the Linux parser on fixture text;
  - the liveness verdicts;
  - reaping a leader-alive group, reaping a leader-gone group, and reporting a start-time mismatch without signalling.

  The gateway tests assert that the control record and groups are written for a stub run.

### C3 `feat(delivery): abandon stuck attempts and add the lead CLI and stuck scan`

Covers R4, R8, R9, AC3, AC4, AC7, AC9 and AC10.

- **`delivery_termination.abandon_delivery(work_id, attempt_id, *, actor, explanation, expected_generation, root)`:**
  1. Take `run_lock`.
  2. Probe `recovery_lock` without blocking; on failure refuse `attempt_running`.
  3. Refuse `recovery_in_progress` if a recovery claim or decision row is open.
  4. Refuse on a symlinked or unsafe attempt directory.
  5. Reap across all control records, keeping the report.
  6. Call `seal_terminal_uncertain(..., status="abandoned")` with the receipt builder.
  7. Return `{status, receipt_path, reap_report}`.

  It works for any lead status and never touches the lead claim.
- **`delivery_termination.stuck_attempts(root)`:** read-only. It iterates `.flow/runs/*/execution/ledger.sqlite`, opened read-only, for `started` v8 attempts. Each row carries liveness (recovery-lock probe plus control record), lead status, uncertain counts, any open expansion, and one next command:
  - live: `cancel-delivery`;
  - a pending expansion request: `decide-expansion`;
  - not live and recovery available: `recover-delivery-lead`;
  - otherwise: `abandon-delivery`.
- **`cli/delivery_projection.py` / `inspect-delivery`:**
  - show the attempt status separately from the expansion status;
  - show the termination block and `evidence_damage`;
  - show the control records with group liveness;
  - use the next-command rules above.
- **`cli/flow.py`:** add three parsers and dispatch branches next to `recover-delivery-lead` (~1004):
  - `abandon-delivery <work-id> <attempt-id> --actor --explanation --expected-generation`;
  - `delivery-lead <work-id> {attention,release,resume,supersede} --expected-generation [--owner]`, wrapping `change_lead_claim`;
  - `stuck [--json]`.

  Refusals print `refused: <code>: <detail>` and exit 2.
- **Tests,** added to `tests/test_delivery_termination.py`:
  - AC3 (a) to (e), where (b) goes through the real runtime-cap path using a stub supervisor that raises `MafTransportError` for the cap;
  - AC4, including a real sleeper group whose leader has exited;
  - AC7 successors after (a), (b) and (d);
  - AC9 through the CLI entry;
  - AC10 for `inspect` and `stuck`.

### C4 `feat(delivery): cancel a live attempt cooperatively`

Covers R2, R3, AC1, AC1b, AC1c, AC2, AC2b and AC2c.

- **`cli/delivery_cancel.py`:**
  - `CancelController.install()` saves the old SIGTERM handler, installs the new one, and returns a `supported` flag.
  - The handler sets `requested`. If `interruptible` is set and nothing has been raised yet, it raises `DeliveryCancelled` once.
  - `interruptible()` is a context manager.
  - `disarm()` stops further raises.
  - `restore()` puts the old handler back.
  - A module-level `current()` returns the controller, or `None`.
- **Interruptible regions:**
  - the MAF child read/write waits in `run_maf_delivery` and the v8 recovery launchers (the waits around `maf_supervisor.py:61, :93`);
  - the provider waits in `codex_worker`, `claude_edit_worker` and `claude_worker` (~136, ~166);
  - the Ollama request in `local_worker` (~84);
  - the targeted test wait.

  Every worker `finally: os.killpg` still runs on unwind.
- **`cli/delivery_gateway.py` `_run_prepared_delivery` and the v8 recovery runners:**
  - Order: install the controller, write the control record with `cancel_supported`, run, close the record, restore the controller.
  - The authorization entry points (manager decide and action decide) check `requested` first and raise `DeliveryCancelled` from normal code.
  - `DeliveryCancelled` subclasses `Exception`, so the existing `except Exception` sites (~1472, ~1598, ~1631) still mark rows unknown.
  - In the post-exception branch, **before** the v8 `record_interruption` at ~1645: if `controller.requested` and a valid `cancel-request.json` matches this attempt and owner generation, kill the recorded MAF and provider groups, then call `delivery_termination.seal_cancelled(...)`. That takes `run_lock` and `send_lock` by non-blocking polling up to the 30 s deadline. On a timeout or generation mismatch it falls through to `record_interruption`.
  - Once the runtime outcome is recorded, call `controller.disarm()`, so a late cancel lets the normal seal finish.
- **`delivery_termination.cancel_delivery(...)`:**
  - takes no locks;
  - checks the generation against a read-only snapshot, as advisory only;
  - reads the latest open control record;
  - handles `cancel_supported: false`;
  - verifies liveness and identity (machine id, pid alive, start time);
  - writes the cancel request atomically, then re-reads the start time, then sends SIGTERM (via `pidfd` on Linux where available);
  - polls the ledger read-only for up to 45 s, returning `cancelled` with the receipt, `attempt_finished` with the receipt, or `cancel_timeout`.
- **`cli/flow.py`:** add `cancel-delivery <work-id> <attempt-id> --actor --explanation --expected-generation`.
- **Tests:** new `tests/test_delivery_cancel.py` and a harness `tests/delivery_cancel_harness.py`.
  - The harness runs the parent in a subprocess: it imports the gateway, prepares from the test's fixture root, and runs with a stub supervisor and a stub worker.
  - The stub worker spawns a real `start_new_session` sleeper through the registrar and writes a FIFO line `blocked` before waiting inside `interruptible()`.
  - Cases:
    - AC1 for each lead status;
    - AC1b, blocked on the child read (a stub supervisor that blocks);
    - AC1c, a fake `claude` script on `PATH` that signals the FIFO and then sleeps, driven through the real `call_claude_edit`;
    - AC2, each refusal;
    - AC2b, a bare `os.kill(SIGTERM)`;
    - AC2c, cancel after the outcome is recorded, using a harness hook, plus a seal-time generation mismatch.
  - No sleeps: FIFO reads with timeouts only.

### C5 `docs(delivery): record ADR 0019 and step 5 cancellation`

Covers R10 and AC11.

- `docs/adr/0019-attempt-cancellation-and-abandonment.md`, covering everything R10 lists, with an amendment note added to ADR 0016.
- `docs/maf-adoption-design.md`: the step 5 row and bullets list cancellation and stuck-run recovery as built.
- The CLI help regenerated with `scripts/regenerate-flow-help.py`.
- Release notes come from the commits.

## Risks

- **The handler raises inside an unexpected frame.** Mitigated: raising happens only inside `interruptible()`, which is never around ledger or file I/O, and it happens at most once.
- **Provider callbacks run off the main thread**, where Python signal handlers never run. This is an assumption to verify first in C4. If it's false, the stub harness test fails immediately, and the fallback is for the main thread to set an event that the waits poll.
- **macOS-only validation of process identity.** The Linux path is parser-tested only. This is recorded as a per-check verdict.
- **Gateway size.** The new logic lives in modules; the gateway gets hooks only.

## Amendments from plan review (binding)

Source: `plan-review.md`, findings PR1–PR17. Each amendment overrides the plan text above wherever the two conflict.

- **A1 (PR1). Single transaction, pure builder** (changes C1).
  - Refactor `snapshot()` into `_snapshot_locked(db, attempt_id)`, with the public method wrapping it.
  - After releasing grants and closing expansions, `seal_terminal_uncertain` calls `_snapshot_locked`, `_lineage_usage`, `_expansion_receipt` and `_manager_progress_receipt` on its **own** connection. It passes the results to a pure `build_receipt(snapshot, blocks) -> bytes`, which may read attempt files but makes no ledger or lock calls.
  - The seal then writes `receipt.json`, compares, and updates. A refusal leaves an ordinary draft behind.
  - New C1 test: an attempt with one `allowed` row and one `pending` expansion seals with `not_dispatched` and a cancelled expansion in its receipt.
- **A2 (PR2). Check the flag right after the snapshot** (changes C4).
  - For v8, check `controller.requested` right after `snapshot = ledger.snapshot(aid)` (gateway ~1634), **whether or not an exception occurred**, and also before the `ExpansionPaused` return (~1623).
  - Requested with a valid cancel request: reap and seal `cancelled`.
  - Requested without a valid request, or on a timeout or generation mismatch: `record_interruption` with the new cause `cancel_signal`, which is added to `RECOVERY_INTERRUPTION_CAUSES` (`execution_contracts.py:335`) and to the receipt validator's allowed set (~564). The attempt returns `interrupted`.
  - New C4 test: a bare SIGTERM with nothing in flight, while blocked on the child read.
- **A3 (PR3). The manager adapter is registered too** (changes C2 and C4). `_default_manager_adapter` gets the registrar and passes it to `call_claude` and `call_codex`. New harness case: cancel while blocked in a manager call.
- **A4 (PR4). No injected adapter signature changes** (changes C2).
  - `on_process_group` is bound only into the default worker adapter, the default manager adapter and the default test runner, via `partial` in `_run_prepared_delivery`.
  - The supervisor receives it through `runner_kwargs`.
  - Harness stubs call `process_identity.register_group` directly.
- **A5 (PR5). One owner for the control scope** (changes C2 and C4).
  - `delivery_cancel.parent_scope(attempt_dir, generation, cancel_supported)` installs the handler, writes the record, and then closes the record and restores the handler.
  - It is entered in `_execute_prepared_delivery` inside `recovery_lock` for a live run, and in `_resume_chartered` immediately after the claim (~746) for restart, pending and answer modes. That covers the recovery's evidence rebuild and targeted test.
  - `_run_prepared_delivery` only reads `current()`.
  - The non-existent "v8 recovery launchers" are dropped.
  - `killpg` changes only in `run_maf_delivery`'s `finally` (~517). Seal-mode recovery spawns nothing and gets no scope.
- **A6 (PR6). `interruptible()` raises on entry if a cancel is already pending**, with the same one-shot rule. New unit test: set the flag, then enter the region.
- **A7 (PR7). Abandon maps refusals by lock holder** (changes C3).
  - Refusals come from the `recovery_lock` holder: `recovery` or `decide` → `recovery_in_progress`; anything else → `attempt_running`.
  - The row-based step 3 is deleted.
  - The AC4 test holds a `recovery` or `decide` lock in a child process.
- **A8 (PR8). A non-mutating probe.**
  - Add `ExecutionLedger.probe_recovery_lock(attempt_id) -> held|free|absent`. It opens without `O_CREAT`, tries `LOCK_EX|LOCK_NB`, never writes, and unlocks at once.
  - `recovery_lock` retries `BlockingIOError` for up to 250 ms before refusing.
  - `stuck`, `inspect` and `cancel-delivery` base liveness on the control record plus pid and start time, with the probe as corroboration only.
  - New unit test: a probe interleaved with a live acquisition.
  - This probe is R3's "non-blocking probe" (PR16).
- **A9 (PR9). v8 only.**
  - The rule "uncertain rows iff the status is `cancelled` or `abandoned`" goes in `_validate_magentic_receipt` (~997), for v8 only. v5–v7 keep `unknown`. The ~857 edit is dropped.
  - `parent_scope`, the registrar binding and the flag checks all apply only when `execution_protocol_version == 8`.
- **A10 (PR10). A terminal attempt refuses instead of replaying.** `_recovery_gates` (~676) raises `RecoveryRefused(ATTEMPT_TERMINAL)` for a `TERMINAL_UNCERTAIN` status, before the replay branch. The AC6 tests include terminal attempts **that have recoveries**.
- **A11 (PR11). The real MAF launcher is exercised.**
  - AC1b sets `FLOW_MAF_PYTHON` to a fake executable that writes the FIFO and blocks, driving the real `run_maf_delivery` wait, registration and `killpg`.
  - AC3(b) uses the same fake child with a small sealed `max_runtime_seconds` that goes silent, so the real deadline raises `MafTransportError`.
- **A12 (PR12).** AC3(d) asserts request `status == "cancelled"` plus an `expansion_cancelled` event whose cause is `abandoned`. No new expansion status is added.
- **A13 (PR13).**
  - The builder writes `receipt.json`.
  - It includes the `recovery` block exactly when `snapshot["recoveries"]` is non-empty, via `build_recovery_block`.
  - A replaced draft appears in both `recovery.replaced_draft_sha256` and `evidence_damage`.
  - `termination.owner_generation` is the fenced, pre-bump value.
- **A14 (PR14).** `flow.toml` CLI entries for `cancel-delivery`, `abandon-delivery`, `delivery-lead` and `stuck` are added in the commits that introduce them. The help is regenerated each time.
- **A15 (PR15).** The flag path, both the seal and the fallback interruption, uses non-blocking `run_lock` plus `send_lock` and not `authority_guard`, so it works under any lead status.
- **A16 (PR16).**
  - The targeted-test wait is an interruptible region; it is needed because test timeouts reach 3600 s. Recorded as a scope disposition.
  - C3 maps `lead_guard_ledger_unreadable` and `attempt_dir_unsafe`.
- **A17 (PR17). Harness details.**
  - The fake `claude` bakes the FIFO path into the script body, because the provider environment is filtered.
  - The harness subprocess both prepares and runs, via `execute_chartered_delivery`.
  - PID reuse and a foreign machine are simulated by editing the record in the test.
