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
  never resent. Operator resolution of those rows is chunk 2 (the amendment
  below).
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
  a second concurrent recovery refuses with `recovery_in_progress`. The gates
  run again under `recovery_lock`, where no live run can advance the attempt,
  and worktree drift is checked there before the claim. The durable claim is
  a compare-and-swap on the ledger owner generation and the event high-water
  the gates saw, and it refuses any `started` or `unknown` row.
- **Truthful receipt.** A recovered v8 receipt carries a `recovery` block with
  its interruptions, recovery claims, relied-on resolutions, and the digest of
  any replaced unsealed draft. The validator requires the block whenever the
  receipt shows recovery evidence, checks the generation chain, and checks
  every owner generation against it. The ledger stores the sealed receipt
  digest so inspection can detect a removed block that receipt-only checks
  cannot see (R2).

## ADR 0014 amendment (implemented in chunk 1b)

A Delivery Lead `resume` or `supersede` first seals every `started` v8
attempt at or below the outgoing lead generation as terminal `superseded`,
releasing its unconsumed grants and bumping its owner generation so the ledger
fences its grants too, before the claim generation changes. v5, v6
and v7 attempts are not sealed; a stale v7 attempt is already fenced at every
dispatch. The lead guard reads the ledger: a lead change is refused with
`reconciliation_required` while any action or manager call is `started` or
`unknown` in any attempt of the run, v7 included, and with
`lead_guard_ledger_unreadable` when the ledger is unreadable, a symlink, or
missing while attempt directories exist. It is also refused with `attempt_running` while a live
process holds a `started` attempt's `recovery_lock`. That probe runs under
`run_lock`, inverting the lock order above, but it never waits, so it cannot
deadlock. `attention`, `release`, and the lifecycle `pause` and `block`
transitions stay unguarded, so abandonment remains available.

A successor attempt lists its predecessors in its envelope. The list must equal
the ledger's v8 attempts for the work item exactly, so a successor cannot drop
a predecessor, and a predecessor still `started` refuses the successor with
`sibling_attempt_not_terminal`. A predecessor's lead generation may equal the
successor's, so retrying after a failed attempt needs no lead change. Paid
worker sends and verifier sends are counted across the lineage and reported in
the receipt's `lineage_usage`. The seal compares `lineage_usage` with the
ledger's own count inside its transaction and refuses a receipt that differs,
since receipt validation alone can only bound the self-reported counts.
`max_manager_calls` stays per attempt, so a successor has a fresh manager
budget; the first verifier of a successor is not a retry.

## Amendment: v8 operator reconcile (chunk 2)

`resolve-execution` accepts a `started` protocol v8 attempt only as
`resolved_completed`, only for a producer or verifier action in `started` or
`unknown`, and only from that action's stored `response_observations` row.
That row exists when Flow died, or `complete` failed, after the response was
observed. The resolving transaction re-validates the observation against the
envelope and action and requires the recorded send (the adapter boundary
event, or the verifier's claimed send). The route refuses `--evidence-file`,
requires `--expected-generation`, and holds `recovery_lock`, then `run_lock`,
then `send_lock`, then SQLite; a live run therefore refuses it with
`attempt_running`. It appends the resolution at the current owner generation
without bumping it. That generation is already in the recovery chain (the
lead claim or the latest recovery), so the chain and the receipt's generation
checks are unchanged.

Recovery treats a resolved action as unblocked only when exactly one
resolution matches the action, this attempt, and a generation in the recovery
chain; otherwise it refuses `resolution_unbound`. A resolved verifier is then
evaluated like any completed, unevaluated verifier, with no resend.

Manager calls and actions without a stored observation are abandon-only:
Flow observes and completes a manager call in one step, so an unresolved one
never has a Flow-owned reply, and ADR 0012 accepts that a lost response stays
blocked. Inspection says so for each blocker. `regrant_not_dispatched`
refuses v8, and preparing a v8 chartered delivery, like the resolve route,
refuses a worktree that is, contains, or sits inside the project `.flow`.

Rejected: automatic reconcile inside the recovery claim (it complicates the
claim transaction and completes work with no operator act), and trace-backed
resolution (the Claude producer trace carries no action-bound digest).
Revisit when operator demand justifies automatic reconcile, or when a trace
gains an action-bound digest.

## Consequences

ADR 0013 continuation epochs stay v5-only. v5 recovery, and v6 and v7
receipts, keep their semantics; v6 is inspection-only and v7 is not
recoverable. `resolve-execution` reaches v8 only through the guarded route in
the chunk 2 amendment. The ledger gains additive, insert-only tables and a column; older code
ignores them.

Residual (R8): when a crash lands after the producer's edit but before its
diff is recorded, there is no durable reference to compare against. Recovery
re-verifies the worktree against the pinned baseline and scope, and that
worktree becomes the recorded diff. This is acceptable because no verifier has
judged anything yet.

Residual: a process death after Flow denied the latest proposal (for example
at the verifier cap) but before the runtime outcome is recorded leaves a
latest action with no bound checkpoint. R1 applies and recovery refuses with
`no_restorable_checkpoint`; restoring from an earlier checkpoint would
re-propose that action under a new identity. The remedy is a lead supersede
and a successor attempt (chunk 1b).

Residual: the same rule covers a process death after Flow grants the latest
proposal but before its checkpoint is bound. The latest action is `allowed`
with no bound checkpoint, so recovery refuses with `no_restorable_checkpoint`
and the remedy is again a successor. No send has happened in that window, so
nothing is lost but the proposal.

## Rejected alternatives

- **B, successor-only recovery.** Always superseding and starting a successor
  discards committed work and provider spend for every interruption.
- **C, runtime-owned resume.** Letting the runtime decide what to resend moves
  send authority out of Flow's ledger.
- **Baseline replay.** See R1 above.
