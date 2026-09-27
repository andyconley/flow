# Acceptance Criteria: step5-cancellation (revision 2)

All criteria are hermetic:
- the parent runs in a harness subprocess with stub adapters;
- the stubs spawn real `start_new_session` subprocesses through the registrar;
- blocked-state synchronization uses files or FIFOs, not sleeps;
- there are no paid or live calls.

"Owner generation" means the ledger attempt owner generation.

## Live cancel

- **AC1. Cancel during a blocked provider call.**
  - A stub provider is blocked inside the send section. `cancel-delivery` with the correct owner generation finishes within 45 s.
  - Results:
    - a sealed `cancelled` receipt, with the actor, explanation and cause;
    - the in-flight action is `unknown` and never resent;
    - unconsumed grants become `not_dispatched`, with reason `cancelled_unconsumed_grant`;
    - the owner generation is bumped;
    - no process from any recorded group survives;
    - the parent exits.
  - It passes with the lead `active`, `attention_required` and `released`.
  - **AC1b:** the same result when the cancel lands while the parent is blocked on the MAF child read.
  - **AC1c:** one variant uses a fake `claude` executable on `PATH`, so the real edit worker registers its group.
- **AC2. Cancel refusals.** Each refusal mutates nothing and sends no signal:
  - a dead parent: `attempt_not_live`;
  - a pid alive with a different start time: `process_identity_mismatch`;
  - a different machine id: `foreign_machine`;
  - a stale owner generation: `owner_generation_stale`;
  - a terminal attempt: `attempt_not_started`;
  - `cancel_supported: false`: `cancel_unsupported`.
  - Also: the start time read is unchanged when `TZ` is changed.
- **AC2b. Bare SIGTERM.** A SIGTERM with no cancel request leaves the attempt `started`, with an interruption recorded and no receipt.
- **AC2c. Cancel races the finish.**
  - A cancel issued after the runtime outcome is recorded yields `completed` or `failed`, never `cancelled`. `cancel-delivery` reports `attempt_finished` with that receipt.
  - A stale generation found at seal time leaves the attempt `started`, with an interruption recorded.

## Abandon

- **AC3. Abandon a stuck attempt.** `abandon-delivery` seals `abandoned`, with uncertain rows kept `unknown`, grants released, expansions closed, the owner generation bumped, and the actor and cause recorded. Starting states:
  - **(a)** the live-run dead end: an `unknown` paid send, no stored response, the lead `released`; repeated with the lead `active` and `attention_required`;
  - **(b)** an attempt interrupted by the runtime cap;
  - **(c)** an interrupted recovery run;
  - **(d)** an `expansion_paused` attempt with a pending request, which is closed as `abandoned`;
  - **(e)** a missing baseline, an oversized trace, and a stale draft receipt, each sealing with the matching `evidence_damage` entry.
- **AC4. Abandon refusals and reaping.**
  - A live holder refuses with `attempt_running`, and nothing is signalled.
  - A recovery claim or decision in flight refuses with `recovery_in_progress`.
  - A stale owner generation refuses.
  - A recorded group whose leader is alive with a matching start time is killed before the seal.
  - A group whose leader has exited has its matching members killed.
  - An entry whose start time doesn't match is reported and not signalled.
  - Groups from every owner generation's control record are considered.

## Receipts, terminality, successor

- **AC5. Receipts.**
  - *Validator:* `validate_receipt` accepts valid `cancelled` and `abandoned` receipts, rejects uncertain rows under any other status, and requires `lineage_usage` only when there are predecessors.
  - *Seal:* the seal refuses when its listed rows or statuses differ from the ledger, and `sealed_receipt_sha256` matches the file.
- **AC6. Terminality.** For a cancelled or an abandoned attempt, each of these refuses and nothing is resent:
  - `recover-delivery-lead`;
  - `resolve-execution`;
  - `decide-expansion`;
  - resume.
- **AC7. Successor.** After AC1, AC3(a), AC3(b) and AC3(d):
  - a new attempt on the same work id runs to completion with stubs;
  - it lists the predecessor with its receipt digest;
  - lineage limits count the predecessor's `unknown` paid send as spent;
  - after AC3(d), only consumed grants are inherited.
- **AC8. Scoping.**
  - `delivery-lead resume` succeeds when the only uncertainty in the run belongs to a cancelled or abandoned attempt.
  - It refuses with `reconciliation_required` when the uncertainty is in a `started` attempt, or in a v7 attempt sealed `unknown`.

## Operator surface and docs

- **AC9. Lead CLI.** `flow run delivery-lead` performs all four actions with the lead generation. Each existing refusal surfaces as its stable code with a non-zero exit.
- **AC10. Diagnostics.**
  - `inspect-delivery`, for a cancelled attempt, an abandoned attempt, and a started attempt, shows:
    - the attempt status, separately from the expansion status;
    - the actor, cause and `evidence_damage`;
    - control-record liveness;
    - uncertain rows;
    - the correct next command.
  - `flow run stuck`, over a project with one live attempt, one stuck attempt, one expansion-paused attempt and one completed attempt:
    - lists exactly the three `started` attempts, each with the right next command;
    - is read-only;
    - exits 0.
- **AC11. Docs.**
  - ADR 0019 is written, covering everything in R10.
  - The step 5 progress in `docs/maf-adoption-design.md` is updated.
  - The CLI help is regenerated.

## Proof

- **AC12.** The full suite is OK with 0 skipped, run with `FLOW_MAF_PYTHON`. Each of these mutations must fail the criteria listed:
  - allow uncertain rows only for `abandoned`: AC1 and AC5 fail;
  - blocker excludes all terminal statuses: AC8 (the v7 case) fails;
  - skip the start-time check: AC2 and AC4 fail;
  - seal `cancelled` without a cancel request: AC2b fails;
  - allow resume on `abandoned`: AC6 fails;
  - keep raising after the outcome is recorded: AC2c fails.
