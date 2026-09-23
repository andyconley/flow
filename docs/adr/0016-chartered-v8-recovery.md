# ADR 0016: Chartered v8 recovery from the latest bound checkpoint

- Status: accepted
- Date: 2026-09-23

## Decision

An interrupted protocol v8 chartered attempt is recovered in place, on the
same attempt, from its latest Flow-bound Magentic worker checkpoint (Option
A). Recovery is an explicit operator command, never a timer, grant expiry, or
process-exit side effect. Only one recovery can own an attempt at a time.

- **No terminal `unknown` for v8.** A v8 transport loss or uncertain send
  records an `attempt_interruptions` row and leaves the attempt `started`.
  `finish_attempt` refuses a v8 `unknown` seal as defense in depth. A process
  death leaves no row; the next recovery claim records it as
  `unmarked_process_exit`.
- **Reconcile first.** Eligibility is decided on a read-only snapshot before
  any claim. Any action or manager call in `started` or `unknown` refuses with
  `reconciliation_required`, before any claim or mutation. Uncertain calls are
  never resent. Operator resolution of those rows is chunk 2.
- **Fail closed without a bound checkpoint (R1).** Recovery requires a bound
  worker checkpoint for the attempt's highest-sequence action. Otherwise it
  refuses with `no_restorable_checkpoint`. A replay from the charter baseline
  is rejected: a re-proposed action has a new checkpoint and therefore a new
  identity, and manager prompt determinism across a fresh start is unproven.
  Revisit this rule when a spike proves byte-deterministic manager prompt
  serialization on the pinned MAF version and there is operator demand; it
  would then be an additive `baseline_replay` mode.
- **Three restore modes.** `answer` restores a completed action with its
  rebuilt reply (the existing MAF restore). `pending` restores an action whose
  grant was never consumed: the runner re-emits the saved proposal with its
  original checkpoint and identity, and Flow re-grants it. `seal` skips MAF
  when the runtime outcome was already recorded and only the receipt remains.
- **Checkpoint quarantine.** Checkpoint files the ledger never bound are moved
  to `checkpoints-quarantine/<recovery_id>/` before restore, and their digests
  are recorded in the recovery row. A stale unbound pending checkpoint would
  otherwise make the runner abort as ambiguous.
- **Evidence reuse.** Once a verifier input is bound, recovery reuses its
  `diff_digest` and `test_digest` and never reruns the targeted test. Before
  any verifier input exists, the test runs exactly once. The worktree is
  re-verified against the recorded diff; any drift refuses with
  `worktree_drift` before any send.
- **Grants.** A claim releases every unconsumed action grant as
  `not_dispatched/recovery_unconsumed_grant`. Re-proposal re-grants the same
  row under fresh limits that exclude the row itself, so it counts once, and
  writes a fresh `policy_allowed` event so grant expiry measures from the
  re-grant. An unconsumed manager grant is re-issued in place.
- **Lock order.** `recovery_lock` (non-blocking, beside the ledger), then
  `run_lock` (the delivery authority guard), then `send_lock`, then SQLite
  `BEGIN IMMEDIATE`. The live v8 execution also holds `recovery_lock` for its
  whole run, so recovering a running attempt refuses with `attempt_running`;
  a second concurrent recovery refuses with `recovery_in_progress`. The
  durable claim is a compare-and-swap on the ledger owner generation.
- **Truthful receipt.** A recovered v8 receipt carries a `recovery` block with
  its interruptions, recovery claims, relied-on resolutions, and the digest of
  any replaced unsealed draft. The validator requires the block whenever the
  receipt shows recovery evidence, checks the generation chain, and checks
  every owner generation against it. The ledger stores the sealed receipt
  digest so inspection can detect a removed block that receipt-only checks
  cannot see (R2).

## ADR 0014 amendment (implemented in chunk 1b)

A Delivery Lead `resume` or `supersede` first seals every `started` v7 or v8
attempt of the outgoing lead generation as terminal `superseded`, fencing its
owner generation, before the claim generation changes. The lead guard reads
the ledger: a lead change is refused while any action or manager call is
`started` or `unknown`, and fails closed when the ledger is unreadable.
Abandonment remains available.

A successor attempt lists its predecessors in its envelope. The list must equal
the ledger's attempts for the work item exactly, so a successor cannot drop a
predecessor. Paid worker sends and verifier sends are counted across the
lineage. `max_manager_calls` stays per attempt, so a successor has a fresh
manager budget; the first verifier of a successor is not a retry.

## Consequences

ADR 0013 continuation epochs stay v5-only. v5 recovery, and v6 and v7
receipts, keep their semantics; v6 is inspection-only and v7 is not
recoverable. `resolve-execution` refuses v8 until chunk 2 adds a guarded v8
route. The ledger gains additive, insert-only tables and a column; older code
ignores them.

Residual (R8): when a crash lands after the producer's edit but before its
diff is recorded, there is no durable reference to compare against. Recovery
re-verifies the worktree against the pinned baseline and scope, and that
worktree becomes the recorded diff. This is acceptable because no verifier has
judged anything yet.

## Rejected alternatives

- **B, successor-only recovery.** Always superseding and starting a successor
  discards committed work and provider spend for every interruption.
- **C, runtime-owned resume.** Letting the runtime decide what to resend moves
  send authority out of Flow's ledger.
- **Baseline replay.** See R1 above.
