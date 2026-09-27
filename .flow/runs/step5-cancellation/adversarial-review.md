# Adversarial review: step5-cancellation

Reviewer: architect (adversarial). Date: 2026-09-27. Scope: `requirements.md`, `acceptance-criteria.md`, `intake.md`, `research/*.md`, checked against the current code. Paths are relative to `/Users/andyconley/src/flow`.

Verdict: **not approvable as written.** The ledger half (R4 to R8) is sound once it is tightened. The live-cancel half (R1 to R3) rests on two wrong assumptions:

- that the handler can do the work inside the signal handler;
- that `cancel-delivery` can take the run fences while a provider call is in flight.

Both have to be redesigned before planning.

---

## F1. A SIGTERM handler cannot seal from signal context. A flag-only handler cannot interrupt the waits. (blocking)

**Evidence.**
- Every blocking wait retries automatically on EINTR (PEP 475) if the Python handler returns normally:
  - `select.select` in `cli/maf_supervisor.py:61`, `:93`;
  - `selector.select` and `process.wait(timeout=)` in `cli/claude_edit_worker.py:136`, `:166` (the same shape is in `cli/codex_worker.py:149` and `cli/claude_worker.py:204`);
  - the urllib socket read in `cli/local_worker.py:84`, `:87`, with a timeout of up to 60 s;
  - blocking `flock` in `cli/execution_ledger.py:253` and `cli/delivery_control.py:32`.
- So a handler that only sets a flag does nothing until the wait's own deadline, which can be up to 600 s. That is far past R2's 30 s shutdown deadline.
- A handler that *seals* runs between bytecodes in the main thread, often while that thread is inside `with authority_guard(), ledger.send_lock():` (`cli/delivery_gateway.py:1455`, `:1558`).
  - Re-taking `run_lock` or `send_lock` opens a new fd. `flock` locks belong to the open file description, so the new lock conflicts with the process's own held lock and **self-deadlocks**.
  - Re-entering SQLite from inside an open `BEGIN IMMEDIATE` on another connection hits the 10 s busy timeout (`cli/execution_ledger.py:239`).

**Disposition: requirement changed (R2).** Specify the mechanism:
1. The handler sets `cancel_requested`, then raises a one-shot `DeliveryCancelled`. It raises only while an "interruptible" flag is set, and it never raises twice.
2. The interruptible flag is set only around the MAF read/write waits, the provider subprocess waits, and the Ollama request. Everywhere else the handler just sets the flag, and the loop checks it at the next boundary before any `decide*` call.
3. The seal happens in normal code after the stack unwinds, keyed on the flag rather than on the exception type:
   - the unwind passes through `except Exception` sites, such as `cli/delivery_gateway.py:1472`, `:1598`, `:1631` and `suppress(Exception)` at `:1573`;
   - `DeliveryCancelled` must therefore subclass `Exception`, so that `mark_unknown` and `mark_manager_unknown` still run;
   - but the branch that runs after `:1631` has to check the flag *before* the v8 `record_interruption` branch at `:1645`.
4. Lock acquisition on the cancel path uses `LOCK_NB` polling against the shutdown deadline. Otherwise "bounded by a stated deadline" cannot be enforced.

The unverified assumption "a handler can interrupt a blocking provider wait" is **rejected as stated** and replaced by the rule above.

## F2. `cancel-delivery` must be lock-free. The parent holds `run_lock` and `send_lock` for the whole provider call. (blocking)

**Evidence.**
- `on_action` sends inside `with authority_guard(), ledger.send_lock():` (`cli/delivery_gateway.py:1558-1601`). `authority_guard` is `run_lock` (`cli/delivery_control.py:40-42`). `on_manager` does the same (`:1455`). The test runner also runs inside that block (`:1593`).
- So during a Claude or Codex call, which can last up to 600 s, both `run_lock` and `send_lock` are held by the parent.
- If `cancel-delivery` checks `--expected-generation` under `run_lock`, it blocks until the provider returns. Cancel then never reaches the process it is meant to stop.
- If it holds `run_lock` while it waits for the seal, the parent's cancel seal needs `run_lock`. That deadlocks until the 45 s cancel timeout. The parent's 30 s deadline expires first, so the attempt is left `started`.
- The documented order is `recovery_lock` → `run_lock` → `send_lock` → SQLite (`cli/execution_ledger.py:265`).

**Disposition: requirement changed (R3).**
- `cancel-delivery` takes no lock, apart from a non-blocking `recovery_lock` probe that it releases at once. It reads the generation from a read-only snapshot and never holds any fence across the signal and the wait.
- The generation check in `cancel-delivery` is advisory. The authoritative check is repeated by the parent under the fences at seal time, using the value from the cancel request (F4). A mismatch there makes the parent record an interruption instead of a seal.
- Add an AC: cancel while a stub provider is blocked *inside* the send section completes within the deadline.

## F3. The cancel seal cannot use `delivery_authority_guard`, because `attention` and `release` are not fenced against a live run. (blocking)

**Evidence.**
- `attention` skips `_fence_and_seal_attempts` entirely (`cli/delivery_control.py:240-243`, `:261`).
- `release` fences only attempts with open expansions (`:297-300`, `cli/execution_ledger.py:714-727`).
- So a live run's lead can become `attention_required` or `released` at any time.
- `delivery_authority_guard` raises unless `owner_status == "active"` (`cli/delivery_control.py:50`).
- The existing `_seal_attempt` path wraps every write in that guard (`cli/delivery_gateway.py:1689`, `:1698`). A cancel after `attention` would therefore always fail and leave the attempt `started`.

**Disposition: requirement changed (R2).**
- The cancelled seal uses the same fences as abandon: `run_lock`, `send_lock`, `BEGIN IMMEDIATE`, and a check against the ledger owner generation. It works for `active`, `attention_required` and `released`, the same as R4.
- Add the matching cases to AC1.

## F4. SIGTERM carries no actor or explanation, and a stray SIGTERM would make an attempt terminal. (important)

**Evidence.**
- R5 requires the actor, explanation and cause in the receipt, but a signal carries no payload.
- Today a SIGTERM from logout, shutdown, `kill` or a supervisor kills the parent. The attempt then stays `started` and is recoverable, as with the 600 s cap: `record_interruption`, `cli/delivery_gateway.py:1645-1655`.
- Under R2 any SIGTERM seals a terminal `cancelled`. That forces a successor attempt and spends the lineage caps (ADR 0016's rejected "successor-only recovery discards spend" concern, `docs/adr/0016-chartered-v8-recovery.md:170-171`).

**Disposition: requirement changed (R2, R3).**
- `cancel-delivery` first writes a cancel request atomically into the attempt directory, then signals. The request holds the attempt id, the expected generation, the actor, the explanation and a nonce.
- On SIGTERM the parent seals `cancelled` only if a valid request for this attempt and generation exists.
- Otherwise it takes the existing interruption path: the attempt stays `started` and recoverable.
- Add an AC: a bare SIGTERM leaves the attempt `started` with an interruption and no receipt.

## F5. "`--expected-generation`" is ambiguous: ledger owner generation or lead generation? (important)

**Evidence.**
- `resolve-execution` and `decide-expansion` compare against the **ledger attempt** `owner_generation` (`cli/execution_ledger.py:1756`, `:767-768`; `cli/flow.py:596-597`, "ledger owner generation shown by inspect-delivery").
- A chartered recovery claim bumps the ledger generation (`cli/delivery_gateway.py:740-746`), and a supersede bumps it again (`cli/execution_ledger.py:694-696`).
- R3 and R4's refusal code `stale_delivery_owner_generation` and R8's argument refer to the **lead** generation in `run.json`.
- These two numbers diverge after any recovery.

**Disposition: requirement changed (R3, R4, R8).**
- For cancel and abandon, `--expected-generation` means the ledger attempt owner generation. The refusal code is `owner_generation_stale`, reusing the existing constant.
- For `delivery-lead` it means the lead generation, with its own code.
- The receipt records both generations.

## F6. A receipt-backed `abandoned` seal is infeasible in the very states abandon exists for. (important)

**Evidence.**
- `_build_receipt` reads `baseline.json` without a guard (`cli/delivery_gateway.py:1252`).
- It raises `ContractError` when the Claude debug or event trace is over its limit (`:1313`, `:1321`). Traces are truncated only in the worker's `finally` (`cli/claude_edit_worker.py:183-188`). If the parent is SIGKILLed during a traced Claude edit, the untruncated trace makes every later receipt build fail. **Abandon would be permanently refused.**
- `validate_receipt` requires valid baseline evidence (`cli/execution_contracts.py:1188-1193`).
- A draft `receipt.json` may already exist from a seal that died before `finish_attempt`. `_build_receipt` handles that only when recoveries exist (`:1299-1305`).
- Abandon has no in-memory edit or test evidence. Rebuilding it would run `verify_edit` or tests, which is unacceptable for a last-resort seal.

**Disposition: requirement changed (R4, R5).**
- The `abandoned` (and `cancelled`) receipt is built from the ledger snapshot and the ledger envelope. Evidence fields may be null, and an explicit `evidence_damage` list covers:
  - a missing or unreadable baseline;
  - an oversized trace, recorded by digest and size;
  - a replaced draft receipt digest.
- No test is run, and nothing is written to the worktree.
- Abandon refuses only when:
  - the ledger is unreadable (`lead_guard_ledger_unreadable`);
  - the attempt directory is a symlink;
  - the attempt directory is absent and cannot be created safely.
- Add AC3 variants: missing baseline, oversized trace, stale draft receipt.

## F7. The abandon and cancel seals must also release grants, close expansions and bump the generation. The requirements are silent on this. (important)

**Evidence.**
- The precedent `seal_superseded_attempts` does all three:
  - turns `allowed` grants into `not_dispatched/superseded_unconsumed_grant`;
  - closes expansions;
  - bumps `owner_generation` to fence late writers (`cli/execution_ledger.py:683-696`).
- A cancel can also land after `decide`/`decide_manager_call` returned allowed but before the consume step (`cli/delivery_gateway.py:1430-1458`, `:1541-1557`). That leaves an `allowed` row.

**Disposition: requirement changed (R4, R5).**
- The seal releases `allowed` grants as `not_dispatched` with reason `cancelled_unconsumed_grant` or `abandoned_unconsumed_grant`.
- It closes expansions with cause `cancelled` or `abandoned`.
- It bumps the attempt's `owner_generation`.
- These are asserted in AC3 and AC5.

## F8. The blocker scope is stated three different ways, and "started only" silently unblocks v5–v7 `unknown` attempts. (important)

**Evidence.**
- R6 says to *exclude* `cancelled` and `abandoned`.
- R10 says uncertainty blocks "only in `started` attempts".
- `abandon-seal.md` §Implications item 3 suggests "scope to `started`".
- ADR 0016 blocks on uncertainty "in any attempt of the run, v7 included" (`docs/adr/0016-chartered-v8-recovery.md:75-76`). v5–v7 may be sealed terminal `unknown` (`cli/execution_ledger.py:2140-2147`), and a started-only scope would lift that block without any decision to do so.
- Both sites must change together: `lead_change_blocker` (`:635-646`) and the seal check (`:673`).

**Disposition: requirement changed (R6, R10).**
- Use an exclusion list of exactly `{cancelled, abandoned}` at both sites.
- Add to AC8: a v7 attempt sealed `unknown` still refuses a lead change.

## F9. Resend and double count through the new scoping: no path found. (assumption confirmed, minor residuals)

**Evidence.**
- Action and call ids hash in `attempt_id` (`runtime/maf_runner/delivery_lead.py:207-211`, `:356-361`). A successor can never replay a predecessor row through `decide`'s `WHERE action_id=?` (`cli/execution_ledger.py:1085`).
- The per-attempt unresolved checks look only at the current attempt (`:1101`, `:1229`, `:1274`).
- Predecessor paid sends are counted once each, as `started|completed|failed|unknown` (`:380-383`). Verifier sends are counted through `_verifier_consumed` (`:384`).
- `resolve-execution` already refuses non-`started` attempts (`:1754-1755`). AC6 therefore holds with no change, which is consistent with the "resolve-execution unchanged" non-goal.

**Disposition: assumption confirmed.** Residual: `resolve-execution` on a cancelled row with a stored observation cannot reclassify it, so late evidence has no route. Record this as an accepted consequence in ADR 0019.

## F10. The process-identity mechanics are unsafe as proposed on macOS. (important)

**Evidence and reasoning.**
- `ps -o lstart=` prints *local* time at 1 s resolution, and its output depends on locale. A timezone or DST change between record and check produces a false `process_identity_mismatch`.
- `socket.gethostname()` on macOS follows the network (DHCP or Bonjour names). That produces a false `foreign_host` on a laptop that changes network during a run. After that false refusal, abandon also refuses (the lock is held → `attempt_running`), so the operator is stuck until the 600 s cap.
- The window between verifying the pid and calling `os.kill` allows the pid to be reused.
- Research §Implications already proposed persisting the pid. No platform check was done.

**Disposition: AC changed, plus an open question for planning.**
- Read the start time with `TZ=UTC LC_ALL=C ps -o lstart= -p PID`, or with sysctl/libproc on macOS and `/proc/PID/stat` field 22 plus `/proc/sys/kernel/random/boot_id` on Linux. Store it canonically.
- Replace the host name with a stable machine id: `IOPlatformUUID` on macOS, `/etc/machine-id` on Linux. Keep the host name for display only.
- Re-verify the start time immediately before signalling, and use `os.pidfd_open` on Linux where it is available.
- Add a test that the start time is stable across a `TZ` change.

## F11. Process groups whose leader has exited: R4's "never signal unverifiable" leaves exactly the orphan case unreaped. The MAF child is killed by pid, not by group. (important)

**Evidence.**
- Provider CLIs are group leaders (`start_new_session=True`, `cli/claude_edit_worker.py:118-120`).
- After the parent is SIGKILLed, the leader may exit while its descendants (node, shells) survive. The leader's start time is then unreadable, so R4 would report the group and never kill it.
- Linux and XNU do not hand out a pid that is still in use as a live pgid or sid. A group with live members but no leader is therefore still the recorded group. **This must be verified by a planning spike, not assumed.**
- `run_maf_delivery` cleans up with `process.kill()`, which signals the pid only (`cli/maf_supervisor.py:518-520`). R2 says "kill the MAF child group".

**Disposition: requirement changed (R2, R4); the kernel-guarantee spike is an open question.**
- If the leader is alive, reap the group only when its start time matches.
- If the leader is gone, reap members with the matching pgid, the same uid, and a start time at or after the recorded one. Report anything else.
- Change the supervisor cleanup to `os.killpg`.

## F12. Some processes are neither recorded nor killed. The success criterion overclaims. (important)

**Evidence.**
- The chartered targeted test runs with `subprocess.run(... timeout=...)` inside the send section (`cli/delivery_gateway.py:635-637`, `:1593`), in the parent's own group. On an exception, `subprocess.run` kills only the pid, so the test's grandchildren survive.
- The Ollama call is plain HTTP with no process (`cli/local_worker.py:78-87`). Whether the server stops generating when the client disconnects is untestable hermetically.

**Disposition: requirement changed (R1).** Run the targeted test with `start_new_session=True` and record its group. Rewrite the success criterion as "no surviving process from any *recorded* group". Make Ollama server-side generation a non-goal: the client socket is closed, and nothing further is claimed.

## F13. Recovery runs and in-flight recovery claims are not covered. (important)

**Evidence.**
- A chartered recovery is also a live parent calling providers. It holds `recovery_lock(holder="recovery")` (`cli/delivery_gateway.py:713`), not `live`, and runs `_execute_prepared_delivery` with `recovery` set, which skips the `live` lock (`:1356`, `:775`, `:805`).
- `decide-expansion` holds `holder="decide"` (`:1086`).
- The lock probe maps both of those holders to `recovery_in_progress` (`cli/execution_ledger.py:288`).
- The refusal lists in R3 and R4 only name `attempt_running`.

**Disposition: requirement changed (R1, R3, R4).**
- The control record and handler cover every parent that dispatches: live runs and recovery runs in restart, pending and answer modes.
- The control record is written per owner generation and never overwritten, so abandon reaps groups from every epoch.
- Add `recovery_in_progress` to the refusal lists and to AC4.

## F14. Cancel races the normal seal, and the handler has install windows. (important)

**Evidence.**
- Once the run has committed to sealing (`record_runtime_outcome`, `cli/delivery_gateway.py:1657-1660`), a raise between `write_atomic` and `finish_attempt` (`:1700-1702`) leaves a draft receipt behind.
- A SIGTERM before the handler is installed, or after it is restored, hits the default disposition. The control record could still point at a live CLI process that has moved on to other work.

**Disposition: requirement changed (R2, R3).**
- Disarm raising once the runtime outcome is recorded, and let the normal seal finish.
- `cancel-delivery` then reports a stable `attempt_finished` result with the real receipt.
- Order of events: install the handler, then write the control record; mark the record closed, then restore the handler.
- Add an AC: cancel issued after `record_runtime_outcome` yields `completed` or `failed`, never `cancelled`.

## F15. This is two slices with very different risk. (important)

**Reasoning.**
- The dead end both live runs hit (unknown send → release → dead work id) is fixed by R4–R8 alone. The ledger, contracts and CLI work there has no OS or signal risk.
- R1–R3 (control record, handler, `cancel-delivery`) carry every blocking finding in this review (F1–F4, F10–F14).
- Abandon's reaping step works fine with no control record: nothing is recorded, so nothing is reaped.

**Disposition: open question for the engineer (reopens decision 1a).** Suggested split:
- **5a:** R4–R10 minus reaping. This closes `delivery-lead-claim-cli` and the dead end.
- **5b:** R1–R3 plus reaping in abandon.

If 1a stands, planning should sequence 5a first, as its own reviewed checkpoint.

## F16. Expansion-paused attempts and attempts with open requests have no explicit AC. (minor)

**Evidence.** A paused attempt's parent has already exited (`cli/delivery_gateway.py:1623-1630`), so cancel returns `attempt_not_live` and abandon is the only route. Abandon must cancel the pending request through `_close_expansions_locked` (`cli/execution_ledger.py:702-711`). A concurrent `decide-expansion` holds the `decide` lock (F13).

**Disposition: AC changed.** Add to AC3: abandon an `expansion_paused` attempt with a pending request; the request is `cancelled` and the successor inherits consumed grants only (ADR 0017:79-80). Add to AC4: abandon during a `decide` refuses with `recovery_in_progress`.

## F17. AC5 asks `validate_receipt` to compare against the ledger, which it cannot do. R5's `lineage_usage` rule conflicts with the current convention. (important)

**Evidence.**
- `validate_receipt(envelope, receipt)` is pure (`cli/execution_contracts.py:842`).
- The ledger comparison is at seal time in `finish_attempt`, and covers only `lineage_usage`, `expansion` and `manager_progress` (`cli/execution_ledger.py:2151-2156`). Action and manager rows are compared nowhere.
- `lineage_usage` is present only when predecessors exist (`cli/delivery_gateway.py:1289-1290`), and `_assert_receipt_lineage` expects it to be absent otherwise (`cli/execution_ledger.py:535`). R5 says "each receipt carries `lineage_usage`".

**Disposition: AC changed (AC5) and requirement changed (R5).**
- The new seal method compares the listed action and manager rows, including status, against the ledger inside the seal transaction.
- AC5 splits into validator cases and seal cases.
- `lineage_usage` follows the existing rule: present only with predecessors.

## F18. Two AC12 mutation claims will not hold. (minor)

**Evidence.**
- A successor is prepared through `_v8_lineage_locked`, not `lead_change_blocker` (`cli/execution_ledger.py:338-342`). "Scope the blocker back to all attempts → AC7 fails" is true only if AC7 includes a lead change, and the post-AC1 successor has none.

**Disposition: AC changed.**
- Either add a `resume` step to AC7's abandon branch, or drop AC7 from that mutation.
- Add a mutation for F4: "seal `cancelled` without a cancel request → the bare-SIGTERM AC fails".

## F19. AC1 is not hermetic or deterministic as written. (important)

**Evidence.**
- The `execute-delivery-lead` CLI (`cli/flow.py:555`, `:976`) cannot take stub adapters.
- A stub `worker_adapter` bypasses the group recording, which R1 implies lives in the workers (`cli/claude_edit_worker.py:118`, `cli/codex_worker.py:108`).
- The real MAF child needs `FLOW_MAF_PYTHON`.

**Disposition: AC changed.**
- Add a process-group registrar callback as an explicit seam passed to the adapters. The test's stub adapter spawns a real `start_new_session` subprocess through that registrar.
- Run the parent from a harness subprocess that imports the gateway with stubs.
- The stub signals "blocked" through a file or FIFO before `cancel-delivery` runs, so the test needs no sleeps.
- Also add one test that uses a fake `claude` executable on `PATH`, so the real worker's registration is exercised.

## F20. Stable reason codes and naming. (minor)

**Evidence.**
- `change_lead_claim` returns free-text messages, for example "stale delivery owner generation" and "only an active Delivery Lead can require attention" (`cli/delivery_control.py:224-259`). R8 promises stable codes, so a mapping is needed.
- `cancelled` is already an expansion-request status (`cli/execution_contracts.py:392`, `cli/execution_ledger.py:706`). Diagnostics must label which one they mean.
- `inspect-delivery` consistency (`cli/delivery_projection.py:85-87`) is fine for receipt-backed statuses, but still misreports `superseded` (research §1).

**Disposition: requirement changed (R8, R9).**
- Add a reason-code table.
- In R9, qualify "attempt status" versus "expansion status".
- Optionally fix the `superseded` consistency display, since it is adjacent.

## F21. SIGINT, stopped processes and threads. (minor)

**Evidence.**
- Ctrl-C raises `KeyboardInterrupt`, which bypasses `except Exception` (`cli/delivery_gateway.py:1631`). The attempt is left `started` with no interruption recorded. That is unchanged, but it is inconsistent with the new cancel path.
- A SIGSTOPped or suspended parent never runs its handler, so the result is `cancel_timeout`. That is correct, but it is not documented.
- `signal.signal` works only in the main thread. Future MCP ingress (slice 4) may call from a thread.

**Disposition: non-goal plus a documentation note.**
- SIGINT behaviour stays unchanged; state this explicitly.
- If the handler cannot be installed, the control record says `cancel_supported: false`, and `cancel-delivery` refuses with `cancel_unsupported`.

---

## Summary of dispositions

| Finding | Severity | Disposition |
|---|---|---|
| F1 | blocking | R2 changed; "handler interrupts waits" assumption rejected as stated |
| F2 | blocking | R3 changed (lock-free cancel) |
| F3 | blocking | R2 changed (seal without authority guard) |
| F4 | important | R2 and R3 changed (cancel request file; bare SIGTERM leads to an interruption) |
| F5 | important | R3, R4 and R8 changed (which generation) |
| F6 | important | R4 and R5 changed (ledger-derived receipt, `evidence_damage`) |
| F7 | important | R4 and R5 changed (grants, expansions, generation bump) |
| F8 | important | R6 and R10 changed (exclusion list, v7 case) |
| F9 | minor | assumption confirmed |
| F10 | important | AC changed; planning spike |
| F11 | important | R2 and R4 changed; kernel pgid-reuse spike is an open question |
| F12 | important | R1 changed; Ollama server side is a non-goal |
| F13 | important | R1, R3 and R4 changed |
| F14 | important | R2 and R3 changed |
| F15 | important | open question (split into 5a and 5b) |
| F16 | minor | AC3 and AC4 changed |
| F17 | important | AC5 and R5 changed |
| F18 | minor | AC12 and AC7 changed |
| F19 | important | AC1 changed (registrar seam, harness, fake binary) |
| F20 | minor | R8 and R9 changed |
| F21 | minor | non-goal and documentation |
