# ADR 0019: Cancelling and abandoning chartered v8 attempts

- Status: accepted
- Date: 2026-09-27
- Amends: ADR 0016's rule that any uncertain send blocks a Delivery Lead change. ADR 0017's expansion semantics are unchanged.

## Context

An operator could not stop a live v8 attempt or recover a stuck one without dropping into Python. Both live validation runs hit this.

- **The dead end.** An attempt with an `unknown` paid send and no stored response:
  1. `resolve-execution` refuses it, because Flow holds no observation to resolve it from.
  2. A lead `resume` or `supersede` refuses with `reconciliation_required`.
  3. `release` succeeds, but leaves the attempt `started`.
  4. A successor refuses with `sibling_attempt_not_terminal`.

  The work id was then dead. The 600 s runtime cap leaves an attempt in the same state.
- **No stop.** Flow installed no signal handler. Provider calls run in the parent, and each provider, the MAF child and the targeted test runs in its own session, so killing the parent leaves them running. No process identity was recorded, so nothing could find them later.

## Decision

A v8 attempt can end in two new receipt-backed terminal statuses, `cancelled` and `abandoned`. Both keep every uncertain row uncertain.

### Terminal statuses

- **One seal for both** (`ExecutionLedger.seal_terminal_uncertain`), in one ledger transaction under the caller's recovery lock, run lock and send lock. It:
  1. releases `allowed` grants as `not_dispatched`, with reason `<status>_unconsumed_grant`, leaving any row with dispatch evidence alone;
  2. closes open expansions with that cause;
  3. snapshots the attempt on its own connection;
  4. renders the receipt from that snapshot with a pure builder, which reads attempt files but makes no ledger or lock call;
  5. writes the receipt and compares its listed action and manager-call rows and statuses, its lineage, expansion and `manager_progress` blocks, and its termination with the ledger;
  6. sets the status, `sealed_receipt_sha256` and the actor, and bumps the owner generation.

  A refusal leaves at most an unsealed draft.
- **The receipt** records `termination` (actor, explanation, cause, the fenced pre-bump owner generation, and the lead generation) and `evidence_damage`. Damaged evidence is recorded rather than refused: a missing baseline, an oversized trace (by digest and size), or a replaced draft receipt. Abandon runs no test and writes nothing to the worktree.
- **Validation.** For v8, `validate_receipt` accepts an uncertain row only under `cancelled` or `abandoned`, requires `termination` and `evidence_damage` there, and forbids them anywhere else. A v8 receipt can no longer carry `unknown`.
- **Terminal means terminal.** `recover-delivery-lead`, `resolve-execution`, `decide-expansion` and resume all refuse with `attempt_terminal`, even for an attempt that had a recovery. A cancelled or abandoned attempt is never replayed.
- **Successors.** A new attempt on the same work id lists the terminal attempt in `predecessors` with its sealed receipt digest. Lineage limits keep counting its uncertain paid and verifier sends as spent, and a successor inherits only consumed expansion grants (ADR 0017).

### ADR 0016 amended

The lead-change blocker and the superseded seal skip exactly `{cancelled, abandoned}` attempts: those attempts sealed their uncertainty in a receipt. Any `started` attempt, and a v5–v7 attempt sealed `unknown`, still block.

### Process identity

- Every parent that dispatches for a v8 attempt writes one control record per owner generation, and never overwrites it. That is a live run, or a recovery in restart, pending or answer mode; seal-mode recovery starts no process. The record holds:
  - the pid;
  - a start time that doesn't depend on timezone or locale: sysctl `p_starttime` on macOS, `/proc/<pid>/stat` field 22 plus `boot_id` on Linux;
  - a machine id;
  - whether cancel is supported.
- Flow's own adapters register each process group they start (the MAF child, each provider call, the targeted test) with the leader's start time. The targeted test now runs in its own session, and the MAF launcher kills its whole group on exit. Injected test adapters are unchanged.
- **Limits.** The record is identity evidence only and grants no authority. Every destructive use re-checks the live process first. Flow also refuses to signal:
  - pid 1, itself or its own caller;
  - another user's process;
  - a group whose leader started before the parent that recorded it, since a tampered record could otherwise name an older process.

  The machine id is stored only as a digest. Processes Flow neither started nor recorded are out of scope, and so is Ollama server-side generation: the client socket closes, and nothing more is claimed. The Linux reader is parser-tested only.

### Cooperative cancel

- `flow run cancel-delivery` takes no lock. It checks the owner generation against a snapshot, which is advisory only. It verifies the parent from its control record: same machine, pid alive, start time unchanged. It writes a cancel request, re-checks the start time immediately before signalling (through a pidfd where the OS has one), sends SIGTERM, and waits up to 45 s. It reports `cancelled`, `attempt_finished` with the real receipt, or a stable refusal.
- **The parent's handler only sets a flag.** It raises `DeliveryCancelled`, a subclass of `Exception`, at most once, and only inside an interruptible wait: a provider subprocess, the MAF child pipe, the Ollama request, or the targeted test. A cancel already pending breaks the next wait on entry. Every authorization callback checks the flag first. SIGINT is unchanged.
- **Once the stack has unwound**, keyed on the flag rather than the exception:
  - in-flight sends are already `unknown`;
  - every recorded group is killed;
  - a valid cancel request for this attempt and owner generation seals `cancelled`.

  The seal polls the run lock and the send lock against a 30 s deadline instead of using the authority guard, so it works whatever the lead status is.
- **Anything else records an interruption.** A bare SIGTERM, a request for another generation, a missed deadline or a moved generation records a `cancel_signal` interruption, and the attempt stays `started`.
- **Disarm.** Once the runtime outcome is recorded, the flag no longer raises, so a late cancel finds the normal `completed` or `failed` receipt. The recovery path honours disarm too.
- **A cancel that doesn't seal leaves no request behind.** On a refusal, a timeout, or a parent that exits without sealing, the request is removed. So a later stray SIGTERM is not a cancel.
- **Residual windows.**
  - The parent marks its record closed before restoring the default SIGTERM action, and the command checks the closed marker again right before signalling. On macOS, which has no pidfd, a parent that finishes in the microseconds between that check and the signal can still be terminated after it has sealed.
  - If the ledger generation itself has moved at seal time, no interruption can be recorded under the parent's stale fence. The next recovery claim records `unmarked_process_exit` instead.
  - `cancel-delivery` relies on the recorded identity, not the lock probe, which only corroborates `stuck` and `inspect-delivery`.

### Abandon, the lead CLI and the stuck scan

- `flow run abandon-delivery` applies to a `started` v8 attempt no live process holds. Under the run lock it claims the attempt's recovery lock without waiting, and refuses by holder: `attempt_running` for a live run, `recovery_in_progress` for a recovery or decision. It then reaps every generation's recorded groups:
  - a leader alive with its recorded start time: the whole group is killed;
  - a leader that has exited: only this user's members that started at or after it are killed. Once every member has died, the pgid can be reused. A later, unrelated group under that pgid, owned by the same user and started later, would then have its members killed. R4 accepts that risk;
  - anything else is reported and never signalled.

  Then it seals `abandoned`. The cause comes from the ledger: a pending expansion, otherwise the latest interruption. It works whatever the lead status is and never changes the lead claim.
  - It takes the recovery lock (without waiting) before the run lock, so a live parent that holds the run lock through a guarded send is refused at once.
  - A lost attempt directory is recreated as a private directory, and the seal records the missing evidence.
  - After a hard parent death, a row the parent never marked `unknown` stays `started` in the receipt. It is just as uncertain, and lineage counts it as spent.
- `flow run delivery-lead` exposes `attention`, `release`, `resume` and `supersede` under the lead generation, with stable refusal codes.
- `flow run stuck` lists every `started` v8 attempt in the project, with liveness, lead status, uncertain counts, any open expansion, and one next command. There is a fifth answer besides `cancel-delivery`, `abandon-delivery`, `decide-expansion` and `recover-delivery-lead`: when a recovery or decision holds the fence with no live dispatching parent, the next command is `inspect-delivery`, because acting now would race it. `inspect-delivery` shows the same next command, the attempt status apart from the expansion status, the stopper and cause, `evidence_damage`, and each control record with its groups' liveness. Liveness comes from the control record; a lock probe that never creates or writes the lock file only corroborates it, and a live acquisition outlasts that probe.

### Actors

`--actor` is free-text attribution, the same for the operator and the Shaper, and is not authenticated. Cancel and abandon are destructive where an approval is not: they end an attempt and its paid work for good. So they are fenced on the owner generation the operator saw, and never on the actor.

## Consequences

- The dead end, the runtime-cap interruption and a paused expansion all end in `abandon-delivery` followed by a successor on the same work id. A live attempt can be stopped from a second terminal, with no surviving process from any recorded group.
- **No late-evidence route.** Evidence that turns up later for a cancelled or abandoned row has no way to reclassify it. The row stays `unknown` in a sealed receipt, and lineage counts it as spent. This is accepted: reopening a sealed attempt would bring back the ambiguity the seal removed.
- An operator can now end paid work by mistake. The generation fence and the identity checks limit this to the attempt the operator inspected, but they do not prevent it.
- Validation is on macOS. Real providers are not exercised by these tests; `v8-live-validation-3` covers them.

## Rejected alternatives

- **Sealing `unknown` for v8.** It would bring back ADR 0016's ambiguity; the new statuses record who stopped the attempt, and why.
- **A handler that interrupts every wait, or seals inside the handler.** Raising inside ledger or file I/O could leave a half-written transaction or receipt. Sealing only after the stack has unwound keeps every write in ordinary code.
- **Killing the parent from the cancel command.** That leaves unrecorded sessions running and never seals. Cooperative cancel lets the parent, which holds every fence, seal its own attempt.
- **Timezone-dependent `ps -o lstart`.** It reads differently across timezones and has one-second resolution (spike S1).
