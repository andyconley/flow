
# Research: live-child-cancel

Named question: how is a live chartered v8 delivery attempt run today, and what
would it take to cancel it cleanly from another process?

## 1. How the supervised child is launched and supervised

- `cli/delivery_gateway.py:1353-1359` `_execute_prepared_delivery`: for a v8
  envelope with no `recovery` payload, it enters `ledger.recovery_lock(attempt_id,
  holder="live")` (`cli/execution_ledger.py:260-296`) and calls
  `_run_prepared_delivery` inside it. **Observed**: the lock is held by the
  parent Flow CLI process for the whole attempt, not by the child.
- `_run_prepared_delivery` (`cli/delivery_gateway.py:1617-1620`) calls
  `run_maf_delivery(envelope, task, on_manager, on_action, timeout_s=envelope["limits"].get("max_runtime_seconds", 900), ...)`.
  **Observed**.
- `cli/maf_supervisor.py:445-523` `run_maf_delivery` launches the child with
  `subprocess.Popen([executable, "-m", "runtime.maf_runner.delivery_lead"], stdin=PIPE, stdout=PIPE, stderr=DEVNULL, cwd=root, env={"PYTHONPATH": ...}, bufsize=0, start_new_session=True)`
  (`cli/maf_supervisor.py:458-463`). `start_new_session=True` puts the child in
  its **own session and process group**, detached from the parent's process
  group. **Observed**.
- The child is a stdio-only coordinator: "It cannot reach a Flow ledger or a
  provider through this interface" (`cli/maf_supervisor.py:1-6`). Provider
  calls (Codex/Claude/Ollama) happen in the **parent** process inside
  `on_manager`/`on_action` (`cli/delivery_gateway.py:1419-1614`), not in the
  child. **Observed**.
- Process identity: `run_maf_delivery` never records the child's `process.pid`
  anywhere durable. A grep for `pid`/`getpid`/`process_id` across `cli/`
  (`cli/expertise_runtime.py:422`, `cli/claude_worker.py:216`,
  `cli/codex_worker.py:158`, `cli/claude_edit_worker.py:176`) shows `pid` used
  only transiently inside each worker's own `os.killpg(process.pid, ...)`
  cleanup — never written to the ledger, `run.json`, or any attempt file.
  **Observed**: no pid, process group id, or parent pid is persisted anywhere
  another process could read to find the supervised child or the CLI parent.
- Cleanup on normal exceptions inside the same process:
  `run_maf_delivery`'s `finally` (`cli/maf_supervisor.py:517-522`) does
  `process.kill(); process.wait(timeout=5)` if the child is still alive, then
  closes stdin/stdout. This only runs if the parent process itself keeps
  running Python code (e.g. on a caught `MafTransportError`); it cannot run if
  the parent is killed outright. **Observed** (code), **inferred**
  (consequence).

## 2. Detecting "a live run holds this attempt" from a second process

- The only durable liveness signal is the per-attempt `recovery_lock` file
  `recovery-{attempt_id}.lock` (`cli/execution_ledger.py:270`), an `flock(LOCK_EX
  | LOCK_NB)` with a 16-byte holder name (`live`, `recovery`, or `decide`)
  written after the lock is acquired (`cli/execution_ledger.py:271-290`).
  **Observed**.
- A second process taking the same lock non-blocking gets `BlockingIOError`,
  reads the holder name, and raises `RecoveryRefused(ATTEMPT_RUNNING)` if the
  holder is `live` (unnamed/holder in progress also maps to `ATTEMPT_RUNNING`),
  or `RECOVERY_IN_PROGRESS` if the holder is `recovery`/`decide`
  (`cli/execution_ledger.py:280-288`, constants at
  `cli/delivery_recovery.py:19-23`). **Observed**.
- This is used by `_fence_and_seal_attempts`
  (`cli/delivery_control.py:270-323`) for lead-claim `resume`/`supersede`/
  `release`: it enumerates `started_v8_attempts` / `open_expansion_attempts`
  (`cli/execution_ledger.py:648-654`, `:724-...`) and probes each attempt's
  `recovery_lock` without waiting, inside the outer `run_lock` (never releasing
  it until the claim is written), so no concurrent recovery or live run can
  slip past it (`cli/delivery_control.py:275-278` comment). **Observed**.
- **Reliability gap (inferred)**: an `flock` is released by the kernel the
  moment the holding process's last fd on that file closes — including on
  `SIGKILL`/crash of the parent. Because the lock is held by the **parent** CLI
  process and not by the child, a crash of the parent alone is enough to make
  the attempt look "not live" to a second process, even though the detached
  child (`start_new_session=True`) — and any provider subprocess it triggered
  inside the parent's `on_action`/`on_manager` before the crash — can still be
  alive and running. So "live vs dead" as currently implemented is reliable
  only for a parent that exits cleanly (or is killed by a signal the parent's
  own subprocess machinery gets a chance to react to); it is **not** reliable
  after a hard parent crash, because lock-release and child/provider-process
  death are two independent events today. **Inferred** from the code above; no
  code path cross-checks "is anything still holding this attempt's process
  group alive" before declaring it not-live.
- There is no `change_lead_claim` CLI today (`.flow/runs/step5-cancellation/intake.md`
  gap `delivery-lead-claim-cli`), so the only place this detection logic runs
  today is inside the Python API path exercised by tests / other callers, not
  an operator-facing command. **Observed** (from intake; no CLI subcommand
  found under `flow.py` wiring `change_lead_claim`).

## 3. SIGTERM/SIGINT mid-run, and how the 600s runtime cap seals today

- Flow registers no signal handlers anywhere in the CLI: a repo-wide search for
  `SIGTERM`/`SIGINT` inside `cli/flow.py` finds no matches, and the only
  `SIGTERM`/`SIGINT`-adjacent code in the whole tree is the worker modules'
  `signal.SIGKILL` used for killing already-owned child process groups
  (`cli/claude_edit_worker.py`, `cli/codex_worker.py`, `cli/claude_worker.py`).
  **Observed**. Consequence (**inferred**): a `SIGTERM` delivered to the
  parent CLI process while it is anywhere in `_run_prepared_delivery` (waiting
  on the MAF child, waiting on a provider call, or in the ledger) hits Python's
  default disposition — the process terminates immediately without running any
  `except`/`finally` Python cleanup. `SIGINT` raises `KeyboardInterrupt`,
  which is a `BaseException`, not caught by the delivery loop's
  `except Exception as exc` at `cli/delivery_gateway.py:1631`, so it also
  unwinds without going through the sealing path (though `finally`/`with`
  blocks already entered, e.g. `recovery_lock`'s `finally`, do still run for
  `KeyboardInterrupt` since it is a normal Python exception propagating
  through frames — unlike `SIGTERM`'s default disposition, which never enters
  Python at all). **Inferred** from CPython signal semantics plus the observed
  absence of handlers.
- The one **existing** "stop" path is the envelope's own runtime cap: v8/v7
  envelopes validate `1 <= max_runtime_seconds <= 600`
  (`cli/execution_contracts.py:250`, `:258`), and
  `run_maf_delivery(..., timeout_s=envelope["limits"].get("max_runtime_seconds", 900))`
  (`cli/delivery_gateway.py:1617`) is the deadline `_read_message`/
  `_write_bounded` in `cli/maf_supervisor.py` (lines 476-521) race against.
  When the deadline passes with the child not moving, `_read_message` /
  `_write_bounded` raise `MafTransportError` (a `MafProtocolError` subclass)
  (`cli/maf_supervisor.py:60,63,92,95`), and `run_maf_delivery`'s `finally`
  (`cli/maf_supervisor.py:517-522`) kills the still-alive child and its pipes
  **because the parent process is still alive and running Python** — this is
  categorically different from a `SIGKILL`/`SIGTERM` case where the parent
  itself is gone. **Observed**.
- Back in `_run_prepared_delivery`, that exception is caught generically at
  `cli/delivery_gateway.py:1631-1633`: `failure = str(exc)`,
  `recoverable_transport_failure = isinstance(exc, MafTransportError)` → `True`
  here. **Observed**.
- For a **structured_verifier (v8)** attempt (`cli/delivery_gateway.py:1392,
  1645-1655`): if there is an `uncertain` action/manager-call (`status in
  {"started","unknown"}`) or a recoverable transport failure, Flow **never
  seals a receipt**. It calls `ledger.record_interruption(aid, cause, failure,
  generation=generation)` under `authority_guard()`+`send_lock()`
  (`cli/delivery_gateway.py:1649-1650`) with `cause = "reconciliation_required"`
  if uncertain, else `"transport"`, and returns `status: "interrupted"` with
  `resume_available: not uncertain` and a `blocking` list of the
  started/unknown action/call ids (`:1651-1655`). The attempt row itself stays
  `status='started'` in the ledger — nothing is sealed `cancelled` or
  otherwise terminal by this path today. **Observed**. This is exactly the
  intake's "released attempt with uncertain sends stays `started`" gap
  (`run-supersede-transition`) — the 600s cap path produces that same stuck
  state, it just also happens to be recoverable/interrupted rather than truly
  abandoned.
- If instead the v8 run finishes cleanly (no failure, no uncertainty),
  `_seal_attempt` (`cli/delivery_gateway.py:1681-1704`) closes open expansions,
  builds/validates the receipt, `write_atomic`s `receipt.json`, and calls
  `ledger.finish_attempt(aid, terminal, reason, str(receipt_path), generation=generation)`
  (`cli/execution_ledger.py:2127`) under the same owner/send-lock fencing.
  **Observed**. There is today no `terminal` value of `"cancelled"` produced by
  any code path — `_build_receipt`'s terminal statuses are driven by
  `failure`/`uncertain` conditions already covered above, not by an explicit
  cancel signal (grep of `delivery_gateway.py` finds no `"cancelled"` literal
  used as a receipt terminal status). **Observed** (absence).

## 4. Provider-call exposure: would killing the child orphan a provider subprocess?

- The MAF child itself (`runtime.maf_runner.delivery_lead`) makes no provider
  calls — see the coordinator-only docstring in `cli/maf_supervisor.py:1-6`
  and the callback design (`on_manager`, `on_action` run in the parent,
  `cli/delivery_gateway.py:1419,1476`). So **killing only the MAF child**
  (e.g. `os.killpg` its process group) does not touch any Codex/Claude/Ollama
  subprocess, because none is a descendant of the MAF child — the provider
  subprocess is a descendant of the **parent** Flow CLI process, spawned
  synchronously inside `worker_adapter`/`manager_adapter`
  (`cli/delivery_gateway.py:1579`, `:1723-1731`, `:1758-1759`). **Observed**.
- Every provider worker Flow shells out to for chartered delivery
  (`cli/codex_worker.py:108-110` `call_codex`, `cli/claude_edit_worker.py:118-120`
  `call_claude_edit`, and `cli/claude_worker.py:...:216` for the analyst/manager
  path) launches with `start_new_session=True`, i.e. its **own** process
  group, and each function's own `finally` does
  `os.killpg(process.pid, signal.SIGKILL)` if the process is still alive
  (`cli/codex_worker.py:154-161`, `cli/claude_edit_worker.py:174-179`,
  `cli/claude_worker.py:~216`). **Observed**. That cleanup only runs if the
  **parent** Python process is still executing (i.e. survives long enough to
  reach that `finally`); it is not reachable if the parent itself is killed by
  `SIGKILL`, or terminated by an unhandled `SIGTERM` (default disposition,
  bypasses Python entirely).
- Local Ollama calls (`call_local`, referenced at
  `cli/delivery_gateway.py:1758`) are an HTTP call, not a subprocess
  (`cli/local_worker.py` not shown in this pass, but the call site passes
  `assignment`/task/`attempt_id` and returns a dict the same way as
  `call_claude`/`call_codex`, consistent with an HTTP client rather than
  `subprocess.Popen`) — **inferred** from the call-site shape and absence of
  `Popen` in the earlier `Grep` hit list for `cli/local_worker.py` versus the
  worker files that did show `Popen`. If Flow's own process dies mid-request,
  the outstanding HTTP request either completes server-side with nobody to
  read the response (no local process to orphan) or is abandoned by the
  severed TCP connection depending on the HTTP client's keep-alive semantics —
  **this HTTP path was not fully traced in this pass** and is flagged as an
  open question below rather than asserted.
- **Conclusion (inferred)**: cleanly signalling only the supervised MAF child
  (e.g. `SIGTERM` to its process group) is not sufficient to guarantee no
  provider subprocess is left running — the provider subprocess is a sibling,
  not a descendant, of the MAF child, and only dies today via the parent's own
  `finally` cleanup in `codex_worker.py`/`claude_edit_worker.py`/
  `claude_worker.py`, which itself requires the parent to still be alive and
  running Python. A clean external cancel must reach the **parent** CLI
  process (so its per-call `finally: os.killpg(...)` fires), not just the MAF
  child.

## Open questions

- Whether `cli/local_worker.py`'s Ollama HTTP call has its own timeout/cancel
  and what happens to the in-flight request if the parent process dies mid-call
  (not traced in this pass).
- Whether the parent CLI process, if it *does* survive a `SIGTERM`/`SIGINT`
  signal delivered to its own process group only (not SIGKILL), currently has
  any code path that converts that into a clean `record_interruption` +
  child/provider `killpg`, or whether it always requires the 600s deadline or
  process death to unwind.

## Implications for requirements

- A live cancel needs a durable, cross-process-readable target: today neither
  the CLI parent's pid nor the MAF child's pid nor any provider subprocess pid
  is persisted anywhere (`recovery-{attempt_id}.lock` only carries a holder
  *name*, not a pid). A cancel command needs the parent to either persist its
  own pid at attempt start, or expose a control channel (e.g. a FIFO/socket)
  the parent polls, since a second process cannot safely guess or reconstruct
  the parent's pid from the ledger alone.
- "Signal the supervised child" (intake decision 3) must be defined precisely:
  signalling only the MAF child's process group does not reach the provider
  subprocess (Codex/Claude edit worker), which is a sibling spawned inside the
  parent's `on_action`/`on_manager` callback. The requirement should either (a)
  target the parent process (so its own `finally: killpg` fires for whichever
  provider call is in flight) or (b) explicitly define how an orphaned provider
  subprocess gets reaped if only the child is signalled.
- The `recovery_lock`'s "live" holder detection is reliable for graceful exits
  and for the parent's own timeout path (600s cap), but is not reliable after a
  hard crash of the parent alone: the lock releases on process exit regardless
  of whether the child/provider subprocess is still running. A requirement for
  "abandon a stuck attempt... with no live process" needs to define what
  "no live process" means operationally (lock-free is necessary but may not be
  sufficient) or accept that gap explicitly as a known limitation.
- The 600s runtime-cap path already demonstrates the target shape for a live
  cancel's outcome for v8: `record_interruption` with the attempt staying
  `started`, `resume_available` reflecting uncertainty, and a `blocking` list
  of started/unknown ids. But it never seals a receipt as `cancelled` — the
  requirement's "receipt sealed cancelled" (intake decision 3) is new behavior,
  not a reuse of an existing terminal state; the requirement should specify how
  a `cancelled` receipt differs from today's `interrupted` (no receipt) return
  and how it interacts with `_seal_attempt`'s existing close-expansions +
  `finish_attempt` sequence.
- Because `SIGINT`'s `KeyboardInterrupt` does propagate through Python frames
  (unlike `SIGTERM`'s default disposition), an operator-facing cancel signal
  should very likely be delivered as `SIGTERM` to a handler Flow installs
  itself (not relying on default disposition, and not relying on `SIGINT`
  which conflates with terminal Ctrl-C), so the parent can run a bounded,
  intentional shutdown sequence (mark unknown, kill child/provider process
  groups, seal `cancelled`) rather than dying uncontrolled.
- No CLI wires `change_lead_claim` today (gap `delivery-lead-claim-cli` in
  intake); a live-cancel requirement that reuses the lead-claim/recovery
  machinery should account for adding that CLI surface if it doesn't already
  exist elsewhere.
