# Plan review: step5-cancellation (architect, adversarial)

Scope: `plan.md`, `implementation-handoff.md` and `validation-plan.md`, checked against `requirements.md` (rev 2), `acceptance-criteria.md`, `research/spikes.md` and the code.

**Verdict:** the plan is buildable after changes. Two findings block it (PR1, PR2), and nine are important.

## Answers to the brief

1. **The C1 `build_receipt` callback.** Holding a flock and a SQLite `BEGIN IMMEDIATE` while writing a file is acceptable, and it does not deadlock by itself. The callback's *reads* are the defect: every public ledger helper opens its own connection, so the callback sees the committed state from before the release. See PR1.

2. **Do provider callbacks run on the main thread?** Yes, confirmed.
   - `flow.py:988/997/1007` calls the gateway directly.
   - `run_maf_delivery` calls `on_manager` and `on_action` synchronously inside its read loop (`maf_supervisor.py:486`, `:499`).
   - The adapters run inline (`delivery_gateway.py:1460`, `:1579`).
   - `cli/` has no `threading` or executor use.
   - The worker waits are `selector.select` plus `process.wait(timeout)` (`codex_worker.py:125,149`; `claude_edit_worker.py:136,166`). PEP 475 retries these after the handler runs, so a raised exception propagates.

   The signal design holds, and the plan's fallback is not needed. There is one gap, the entry race in PR6.

3. **Commit ordering.** It is sound in principle. C2 is not green as written (PR4). C3 names `cancel-delivery` as a next command before C4 adds it, which is tolerable inside one PR.

4. **Recovery entry points.** There are exactly three dispatching parents:
   - `execute-chartered-delivery` (`flow.py:988`);
   - `resume-delivery-lead` (`:997`);
   - `recover-delivery-lead` (`:1007`).

   The last two both go through `_resume_chartered` (`delivery_gateway.py:922`, `:1113`). The plan misses the targeted test that recovery runs **before** `_execute_prepared_delivery` (PR5). It also names "v8 recovery launchers in maf_supervisor", which do not exist.

5. **The `stuck` probe.** Yes, it can make a starting live run fail (PR8).

6. **Harness.** It is feasible, with the adjustments in PR4, PR6, PR11 and PR17.

7. **Coverage and scope.** See PR7, PR9, PR10, PR12–PR16.

---

## PR1 (blocking): the receipt callback reads state from before the release, through separate connections

**Evidence:**
- `ExecutionLedger.snapshot` opens its own `self._db()` (`execution_ledger.py:2516-2517`).
- So do `lineage_usage` (`:543-544`), `manager_progress_receipt` (`:599-600`) and `expansion_receipt` (`:603-604`).
- The gateway's `_build_receipt` uses exactly these public helpers (`delivery_gateway.py:1290-1298`).
- The ledger uses the default rollback journal (no WAL; `_db` at `:238-241`).

A second connection opened while connection A holds RESERVED with uncommitted UPDATEs reads the **last committed** state. The receipt would therefore show:
- `allowed` rows;
- expansion requests still `pending`;
- a `verifier_usage.reserved` count that includes the unreleased grants.

The seal's own step 4 row comparison, and the expansion and `manager_progress` comparisons (the same checks as `:2153-2156`), then refuse. That happens on every attempt with an unconsumed grant or an open expansion, which includes AC3(d) and most AC1 cases. If SQLite spills its cache to disk, connection A escalates to EXCLUSIVE, and the reader waits out the 10 s busy timeout and fails.

There is also a secondary hazard. `send_lock` is a per-file-descriptor `flock` (`:244-253`). A builder that calls any ledger method taking `send_lock` would deadlock against its own process.

**Proposed change to the plan (C1).** Keep the single transaction, and make the callback pure:
- Refactor `snapshot()` into `_snapshot_locked(db, attempt_id)`, with the public method wrapping it. The v5 `continuation_snapshot` call can stay outside the locked variant, since it is v5 only.
- The seal calls `_snapshot_locked(db)`, `_lineage_usage(db, env)`, `_expansion_receipt(db, env)` and `_manager_progress_receipt(db, aid)` on **its own `db`** after steps 2 and 3. It hands the results to `build_receipt(snapshot, blocks) -> bytes`.
- The builder may read attempt files only. No ledger calls, no locks.
- Write the file, then run the comparisons, then update.

If the transaction later refuses, the file left on disk is an ordinary draft. The existing semantics already cover that (`delivery_gateway.py:1299-1305`).

An acceptable alternative mirrors `_seal_attempt`:
1. a committed release-and-close transaction;
2. `snapshot()`, taken while still holding `recovery_lock`, `run_lock` and `send_lock`;
3. a write;
4. a final fenced transaction.

This alternative leaves a visible half state: grants released while the attempt is still `started`. It needs an idempotent phase 1 and an inspect hint.

Either way, add a C1 test: seal an attempt that has one `allowed` row and one `pending` expansion, and assert that the receipt shows `not_dispatched` and `cancelled`.

## PR2 (blocking): a flagged stop without uncertainty seals `failed`, which breaks AC1b, AC2b and the fallback

**Evidence:**
- The v8 interruption branch runs only when `uncertain or (failure and recoverable_transport_failure)` (`delivery_gateway.py:1645`).
- Otherwise it goes to `record_runtime_outcome` and `_seal_attempt`, which seals `failed` (`:1656-1665`).

A `DeliveryCancelled` raised from the MAF child read (AC1b), or a bare SIGTERM between sends (AC2b), leaves no uncertain row and is not a `MafTransportError`. If the plan's check sits "in the post-exception branch, before the v8 `record_interruption` at ~1645", it never runs, and the attempt seals `failed`:
- AC1b gets `failed` instead of `cancelled`;
- AC2b gets a receipt instead of an interruption;
- the R2 fallback when the deadline passes or the generation is stale also seals `failed`.

Two further problems:
- `record_interruption` accepts only `RECOVERY_INTERRUPTION_CAUSES = {transport, reconciliation_required, unmarked_process_exit}` (`execution_contracts.py:335`, `execution_ledger.py:2208`), and the receipt validator enforces the same set (`execution_contracts.py:564`). So a new cause needs a contract change too.
- The `ExpansionPaused` return (`:1623-1630`) exits before any flag check. A cancel landing there reports `cancel_timeout`.

**Proposed change to the plan (C4).** Right after `snapshot = ledger.snapshot(aid)` (`:1634`), for v8 only, and **regardless of whether an exception occurred**:
- If `controller.requested` is set and there is a valid cancel request, reap and seal `cancelled`.
- If it is set and there is no valid request, or on a timeout or generation mismatch, record the interruption with a new cause, `cancel_signal`, added to `RECOVERY_INTERRUPTION_CAUSES`. Return `interrupted`.
- Apply the same check before the `ExpansionPaused` return.
- Do the disarm at `record_runtime_outcome`, as planned.
- Add a C4 test for AC2b with no send in flight, blocked on the child read.

## PR3 (important): manager provider calls are outside the registrar

**Evidence:**
- `on_manager` sends through `manager_adapter` (`delivery_gateway.py:1460`).
- The default adapter spawns `call_claude` or `call_codex` (`:1722-1731`), each in its own session (`claude_worker.py:150`, `codex_worker.py:108-110`).
- C2 threads the registrar only through `_default_worker_adapter`, the test runner and the supervisor.

R1 requires "each provider call". A cancel during a manager call would leave an unrecorded group, and AC1's "no recorded group survives" would pass only vacuously.

**Proposed change:** bind the registrar into `_default_manager_adapter` as well, which passes it to `call_claude` and `call_codex`. Add a harness case that cancels while blocked in a manager call.

## PR4 (important): passing the registrar to injected adapters breaks the suite in C2

**Evidence:**
- Stub workers are declared `def worker(action, *, envelope, workspace)` with no `**kwargs`, for example `tests/test_chartered_delivery_gateway.py:179,432,478…` and `tests/test_expansion_recovery.py:238`.
- Stub managers are `def manager(message, *, envelope, workspace)` (`tests/test_expansion_recovery.py:179`, `tests/test_maf_expansion.py:40`).
- `test_runner` is typed `Callable[[Path], dict]`.
- Stub supervisors do accept `**kwargs`, so supervisors are safe.

**Proposed change:**
- Bind `on_process_group` **only** into the default adapters and the default test runner, via `partial` in `_run_prepared_delivery` (`:1396-1398`).
- Pass it to the supervisor through `runner_kwargs`.
- Harness stubs register by calling `process_identity.register_group(attempt_dir, generation, pgid, "test")` directly, since the harness knows both values.
- State in C2 that no injected adapter signature changes.

## PR5 (important): the recovery control-record window misses the recovery's targeted test, and the plan double-writes the record

**Evidence:**
- `_resume_chartered` claims at `:740-746`, then runs `_rebuild_chartered_evidence` at `:752`. With the default runner that calls `_run_chartered_test` (`:895`), all **before** `_execute_prepared_delivery` (`:775`, `:805`).
- If the record and handler live in `_run_prepared_delivery`, a SIGTERM during that test hits the default handler. The parent dies, and the test, which C2 moves to a new session, is orphaned and never recorded.
- C2 also writes the record in both `_run_prepared_delivery` and "the v8 recovery entry points". With `control-g<N>.json` defined as written once, the second write for the same generation either conflicts or is silently skipped.
- The "v8 recovery launchers in maf_supervisor" do not exist. `run_maf`, `run_maf_multiturn`, `_run_maf_pair` and `run_maf_action3_continuation` are v1–v4 only (`maf_supervisor.py:131-443`, `:525`), and only `run_maf_delivery` uses `start_new_session` (`:462`). Applying `killpg` to the others would target a pgid that is not the child's own.

**Proposed change:**
- One owner: a context manager, for example `delivery_cancel.parent_scope(attempt_dir, generation, cancel_supported)`, that installs the handler, writes the record, closes it, then restores the handler.
- Enter it:
  - in `_execute_prepared_delivery` inside `recovery_lock` for the live run;
  - in `_resume_chartered` immediately after the claim (`:746`) for `restart`, `pending` and `answer` modes, wrapping the evidence rebuild and dispatch.
- `_run_prepared_delivery` only reads `current()`.
- Remove the non-existent launchers from C2 and C4.
- Limit the `killpg` change to `run_maf_delivery`'s `finally` (`:517-520`).
- Seal-mode recovery spawns nothing, so it needs no record.

## PR6 (important): the `interruptible()` entry race makes cancel time out

**Evidence:** the handler raises only while the flag is set (plan C4). The stub worker writes FIFO `blocked` and *then* enters `interruptible()`. The AC1c fake `claude` signals the FIFO from the child, while the parent may still be between `Popen` (`claude_edit_worker.py:118`) and the `select` (`:136`). A SIGTERM in that gap only sets `requested`. The worker then blocks until the provider timeout (up to 300 s, `delivery_gateway.py:1751`), and `cancel-delivery` returns `cancel_timeout`. The test would be flaky by construction.

**Proposed change:** `interruptible()` checks `requested` on entry and raises at once if nothing has been raised yet. The same one-shot applies. Specify this in D3 and C4, and add a unit test that sets the flag and then enters the region.

## PR7 (important): abandon steps 2 and 3 map refusals wrongly and would refuse AC3(c)

**Evidence:**
- `recovery_lock` already distinguishes the holders. `recovery` or `decide` gives `RECOVERY_IN_PROGRESS`; anything else gives `ATTEMPT_RUNNING` (`execution_ledger.py:282-288`). The plan maps every probe failure to `attempt_running`.
- Step 3 refuses on "an open recovery claim or decision row". `attempt_recoveries` rows have no open or closed state (`:2575-2578`), so a crashed recovery leaves its row permanently. Any rule based on rows would either never fire, or refuse every attempt that was ever recovered. The second case is exactly AC3(c).

**Proposed change:** step 2 maps by lock holder: `recovery` or `decide` gives `recovery_in_progress`, and `live` or an unnamed holder gives `attempt_running`. Delete step 3. The lock is the in-flight signal. The AC4 test holds a `recovery` or `decide` lock in a child process.

## PR8 (important): the lock probes in `stuck`, `inspect` and `cancel` can strand a starting live run

**Evidence:**
- A live v8 run acquires `recovery_lock` right after `create_attempt` has made the row `started` (`delivery_gateway.py:594-595`, `:1356-1357`).
- `recovery_lock` never waits, except decide against decide (`execution_ledger.py:275-288`).
- If `stuck` holds the flock at that instant, the live run refuses and leaves a `started` attempt that sent nothing. That attempt then needs abandoning.
- `recovery_lock` also opens with `O_CREAT` (`:271`) and writes its holder (`:289-290`), so a "read-only" scan creates lock files.
- Its valid holders are only `live`, `recovery` and `decide` (`:267`).

**Proposed change:**
- Add `ExecutionLedger.probe_recovery_lock(attempt_id) -> "held" | "free" | "absent"`. It opens without `O_CREAT` (ENOENT means absent), tries `LOCK_EX|LOCK_NB`, never writes, and unlocks at once.
- Make `recovery_lock` retry `BlockingIOError` for a bounded ~250 ms before refusing, so a probe collision costs latency rather than an attempt.
- `stuck` should base liveness on the control record plus the pid and start time, and use the probe only as corroboration.
- Add a unit test that interleaves a probe with a live acquisition.

## PR9 (important): the uncertain-row validator and the new hooks must be v8 only

**Evidence:**
- v5–v7 still seal `unknown` receipts with uncertain rows (`finish_attempt`, `execution_ledger.py:2140-2147`). v5 recovery validates such a receipt (`delivery_gateway.py:1129`).
- The plan says "uncertain rows are allowed only for those two statuses", without scoping it.
- Line `~857` is the v1–v4 validator path, so no change is needed there.
- `_run_prepared_delivery` serves v5–v8 (`:1390-1392`), and the plan does not gate the handler or record on protocol.

**Proposed change:**
- Add the rule to `_validate_magentic_receipt` (`:997`) for v8 only: uncertain rows are allowed iff the status is in `{cancelled, abandoned}`. v5–v7 keep `unknown`.
- Drop the `~857` edit.
- Gate `parent_scope`, the registrar binding and the flag checks on `execution_protocol_version == 8`.
- M1 then remains a valid mutation.

## PR10 (important): `recover-delivery-lead` "replays" a terminal attempt instead of refusing (AC6)

**Evidence:** `_recovery_gates` returns `(snapshot, None)` when the status is not `started` **and** recoveries exist (`delivery_gateway.py:676-678`). `_resume_chartered` then returns a success-shaped `replayed` result (`:718-721`). An attempt abandoned after an interrupted recovery, AC3(c), would "recover" as `abandoned` with exit code 1, not a refusal. The plan's terminality audit lists `claim_chartered_recovery`, which already refuses at `:860-861`. It does not list this branch.

**Proposed change:** in `_recovery_gates`, raise `RecoveryRefused(ATTEMPT_TERMINAL)` when the status is in `TERMINAL_UNCERTAIN`, before the replay branch. The AC6 tests should cover a cancelled or abandoned attempt **that has recoveries**.

## PR11 (important): stub supervisors leave the real MAF wait, `killpg` and registration untested

**Evidence:** AC1b uses "a stub supervisor that blocks", and AC3(b) uses a stub that raises `MafTransportError`. Neither exercises:
- the `interruptible()` around `_read_message` and `_write_bounded` (`maf_supervisor.py:61`, `:93`);
- the moved `killpg` cleanup (`:517-520`);
- MAF group registration.

The real launcher runs `[FLOW_MAF_PYTHON, "-m", "runtime.maf_runner.delivery_lead"]` (`:456-463`).

**Proposed change:**
- For AC1b, set `FLOW_MAF_PYTHON` in the harness to a fake executable that ignores its arguments, writes the FIFO, and blocks. That drives the real `run_maf_delivery`.
- For AC3(b), use the same fake child with a small sealed `max_runtime_seconds`, going silent so the real deadline raises `MafTransportError`. Alternatively, keep the stub and record AC3(b) as a ledger-state test.

## PR12 (minor): AC3(d) says "closed as abandoned", but the ledger records `cancelled` plus a cause

**Evidence:** `_close_expansions_locked` sets `status='cancelled'` and puts the cause only in the event detail (`execution_ledger.py:706-707`). `EXPANSION_REQUEST_STATUSES` has no `abandoned` (`execution_contracts.py:392`).

**Proposed change:** state the assertion as request `status == "cancelled"` plus an `expansion_cancelled` event with `cause: "abandoned"`. Do not add a new status.

## PR13 (minor): pin down the receipt path, recovery block and termination generations

**Evidence:**
- `inspect-delivery` judges consistency from `receipt.json` and the recovery-block rule (`delivery_projection.py:85-87`, `:196-204`).
- The validator requires a non-empty `recoveries` list whenever the block is present (`execution_contracts.py:530-540`).

**Proposed change:**
- The builder writes `receipt.json`.
- It includes `recovery` exactly when `snapshot["recoveries"]` is non-empty, using `build_recovery_block`.
- A replaced draft appears in both `recovery.replaced_draft_sha256`, when a block exists, and `evidence_damage`.
- `termination.owner_generation` is the fenced (pre-bump) value.

## PR14 (minor): regenerating the help is a no-op without `flow.toml` entries

**Evidence:** `scripts/regenerate-flow-help.py:32` reads `scaffolds/default/flow.toml`, and only `inspect-delivery` is listed there (`flow.toml:584`).

**Proposed change:** add `flow.toml` CLI entries for `cancel-delivery`, `abandon-delivery`, `delivery-lead` and `stuck` in the commits that add them, then regenerate.

## PR15 (minor): the cancel fallback under a non-active lead escapes with `DeliveryControlError`

**Evidence:** the fallback `record_interruption` runs under `authority_guard()` (`delivery_gateway.py:1649`), which refuses unless the lead is `active` (`delivery_control.py:49-54`). AC1 runs with the lead `released` and `attention_required`, so a timeout or generation mismatch there records nothing and raises.

**Proposed change:** the flag path, both the seal and the fallback interruption, uses non-blocking `run_lock` plus `send_lock`, and does not use `authority_guard`. This matches R4's "any lead status".

## PR16 (minor): scope reconciliation

- **The targeted-test wait as an interruptible region** goes beyond R2's list, but it is needed: test timeouts reach 3600 s (`delivery_gateway.py:152`), well past the 45 s cancel window. Record it as a disposition.
- **R3 requires a non-blocking probe** in `cancel-delivery`, while the plan says it "takes no locks". Reconcile the two, using PR8's `probe_recovery_lock`.
- **R4 lists `lead_guard_ledger_unreadable`**, and R5 lists "attempt directory absent and cannot be created safely". Neither is mapped in C3; add both.

## PR17 (minor): harness details

- **Provider env is filtered.** Only the `CLAUDE_ENV_KEYS` variables reach the provider, and that list includes `PATH` (`claude_worker.py:24`). So the fake `claude` resolves, but the FIFO path must be baked into the script body rather than passed through the environment.
- **Where the parent is prepared.** The harness subprocess should both prepare and run, through `execute_chartered_delivery`. The live `recovery_lock` is taken inside `_execute_prepared_delivery`, so a prepared attempt can't be handed across a process boundary with its fence.
- **Simulating identity changes.** Simulate PID reuse and a foreign machine by editing the control record in the test. That is fine, but note that it bypasses "written once".
