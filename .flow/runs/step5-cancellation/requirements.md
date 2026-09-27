# Requirements: step5-cancellation

MAF adoption step 5, slice 1 of the remaining work: operator and Shaper control over chartered v8 delivery attempts. This is revision 2, which folds in the adversarial review (`definition-dispositions.md`).

## Problem

An operator cannot stop a live v8 attempt, and cannot recover a stuck one, without dropping into Python. Both live runs hit this.

An attempt with an unknown send and no stored response dead-ends:

1. `resolve-execution` refuses it.
2. A lead change refuses it with `reconciliation_required`.
3. `release` succeeds but leaves the attempt `started`.
4. A successor attempt refuses with `sibling_attempt_not_terminal`.

The work id is then dead (`research/abandon-seal.md`). The 600 s runtime cap leaves an attempt in exactly this state. Flow installs no signal handlers, provider calls run in the parent process, and no process identity is recorded (`research/live-child-cancel.md`).

## Audience

- **Andy**, operating from the CLI.
- **The Shaper**, a delegated-approval role, using the same CLI with attribution only (`research/shaper-authority.md`).

## Desired outcome

An operator or the Shaper can:
- find what is stuck;
- **cancel** a live v8 attempt cleanly;
- **abandon** a stuck one;
- continue the same work id with a **successor attempt**.

In every path, uncertainty stays uncertain in the record, and nothing is resent.

## Engineer decisions (2026-09-27)

| Decision | Summary |
|---|---|
| 1a, then 1b | One slice, with live cancel redesigned inside it. |
| 2a | Reuse is a successor attempt in the same run, linked by `predecessors`. |
| 3a / Ba | Live cancel targets the **parent** process. |
| 4a | v8 only. |
| 5 / Da | The operator and the Shaper may both act. `--actor` is free-text attribution. |
| Aa | Seals are receipt-backed: `cancelled` or `abandoned`. |
| Ca | Process groups are recorded, and abandon reaps any that survive. |
| 2a (sequencing) | Build this slice before `v8-live-validation-3`. |
| 3y | An attempt interrupted by the runtime cap is an explicit abandon case. |
| 4y | Add a `flow run stuck` scan. |
| — | The lead CLI is in scope. |

## Generations

- **Cancel and abandon** fence on the ledger attempt **owner generation** (`--expected-generation`). Refusal: `owner_generation_stale`.
- **`delivery-lead`** fences on the **lead generation**, with its existing refusal.
- Receipts record both generations.

## Requirements

### R1. Process identity record

Every parent that dispatches for a v8 attempt writes a control record in the attempt directory, one per owner generation, never overwritten. That covers:
- a live run;
- a recovery run in restart, pending or answer mode.

Each record contains:
- the parent pid;
- a canonical process start time, read independently of timezone and locale (macOS: sysctl/libproc or `TZ=UTC LC_ALL=C ps -o lstart=`; Linux: `/proc/<pid>/stat` field 22 plus `boot_id`);
- a stable machine id (macOS `IOPlatformUUID`, Linux `/etc/machine-id`), with the host name kept for display only;
- the attempt id and owner generation;
- `cancel_supported`.

Each process group Flow starts is appended with its leader's start time as it starts:
- the MAF child;
- each provider call;
- the targeted test.

Groups are registered through a registrar callback passed to the adapters and test runner. The targeted test runs with `start_new_session=True`. The record is identity evidence only; it grants no authority.

### R2. Cooperative cancel in the parent

- **Install order.** Install the SIGTERM handler, then write the control record. At exit, mark the record closed, then restore the handler. If the handler cannot be installed, write `cancel_supported: false`.
- **The handler** sets `cancel_requested`. It raises a one-shot `DeliveryCancelled`, a subclass of `Exception`, only while an *interruptible* flag is set, and never raises twice. The flag is set only around:
  - the MAF child read/write waits;
  - provider subprocess waits;
  - the Ollama request.

  Elsewhere the parent checks the flag at the next boundary, before any authorization call.
- **After the stack unwinds**, keyed on the flag rather than the exception type, the parent:
  - makes no new authorizations;
  - kills the MAF child group with `os.killpg` (the supervisor cleanup also moves to `killpg`), plus any in-flight provider or test group;
  - lets the existing handlers mark in-flight sends and manager calls `unknown`;
  - checks the flag *before* the existing v8 `record_interruption` branch.
- **Sealing `cancelled`** happens only if a valid cancel request (R3) exists for this attempt and owner generation. Otherwise the parent takes the existing interruption path, so a stray SIGTERM leaves the attempt `started` and recoverable.
- **Seal fences** are the same as R4. Lock acquisition polls non-blocking against a 30 s shutdown deadline. If the deadline passes or the generation check fails, the parent records an interruption instead, and the attempt stays `started` for abandon.
- **Disarm.** Once the runtime outcome is recorded, raising is disarmed and the normal seal completes, as `completed` or `failed`.
- **SIGINT** behaviour is unchanged.

### R3. `flow run cancel-delivery <work-id> <attempt-id> --actor A --explanation E --expected-generation N`

- Takes no lock, apart from a non-blocking `recovery_lock` probe that it releases at once. It reads a read-only snapshot for an advisory generation check.
- Verifies the parent is live: same machine id, the pid is alive, and the start time matches. The start time is re-checked immediately before signalling, using `pidfd` on Linux where available.
- Writes a cancel request atomically (attempt id, generation, actor, explanation, nonce), then sends SIGTERM, then waits up to 45 s for a terminal status.
- Reports one of:
  - `cancelled`, with the receipt path;
  - `attempt_finished`, with the real receipt;
  - a refusal from the table below.

### R4. `flow run abandon-delivery <work-id> <attempt-id> --actor A --explanation E --expected-generation N`

- **Applies to** a `started` v8 attempt that no live process holds. The non-blocking `recovery_lock` probe must succeed, and no recovery claim or decision may be in flight.
- **Reaping comes first**, across every control record (every generation):
  - leader alive with a matching start time: kill the group;
  - leader gone: kill members with that pgid, the same uid, and a start time at or after the recorded one;
  - anything else is reported, never signalled.
- **Then it seals `abandoned`** under these fences: `run_lock`, `recovery_lock`, `send_lock`, `BEGIN IMMEDIATE`, and a check against the owner generation.
- **Lead state:** it works when the lead is `active`, `attention_required` or `released`, and does not change the lead claim.
- **Covered cases:**
  - an attempt interrupted by the runtime cap;
  - an interrupted recovery;
  - an `expansion_paused` attempt, whose pending request is closed as `abandoned`, and whose successor inherits consumed grants only (ADR 0017).

### R5. Cancelled and abandoned seals

- **Receipt source.** The receipt is built from the ledger snapshot and envelope.
- **Damaged evidence.** Evidence fields may be null, with an explicit `evidence_damage` list for:
  - a missing or unreadable baseline;
  - an oversized trace, recorded by digest and size;
  - a replaced draft receipt.
- **Abandon runs no test and writes nothing to the worktree.**
- **What the seal does:**
  - releases `allowed` grants as `not_dispatched` with reason `cancelled_unconsumed_grant` or `abandoned_unconsumed_grant`;
  - closes open expansions with that cause;
  - bumps the attempt owner generation;
  - records the actor, explanation, terminal cause, and both generations.
- **Row check.** The seal compares the listed action and manager rows, including status, against the ledger inside its transaction.
- **Lineage.** `lineage_usage` follows the existing rule: present only when there are predecessors.
- **Validation.** `validate_receipt`, which is pure, accepts uncertain rows only under `cancelled` or `abandoned`.
- **Sealing.** `sealed_receipt_sha256` is recorded.
- **Refusals** happen only when:
  - the ledger is unreadable;
  - the attempt directory is a symlink;
  - the attempt directory is absent and cannot be created safely.
- **Terminal.** Resume, recovery, `resolve-execution`, `decide-expansion` and resend all refuse.

### R6. Uncertainty scoping

- The lead-change blocker and the supersede-seal check exclude exactly `{cancelled, abandoned}` attempts. A v5–v7 attempt sealed `unknown`, and any `started` attempt, still block.
- Lineage limits keep counting those attempts' uncertain paid and verifier sends as spent.

### R7. Successor

- A new attempt on the same work id prepares normally.
- It lists the terminal attempt in `predecessors`, with its receipt digest.
- Predecessor validation and the lineage reader accept both statuses.

### R8. `flow run delivery-lead <work-id> {attention|release|resume|supersede} --expected-generation N [--owner ID]`

This wraps `change_lead_claim`, keeps every existing refusal, and returns stable codes with a non-zero exit.

### R9. Diagnostics

**`inspect-delivery`** shows:
- the **attempt status** (separately from the expansion status);
- the actor and cause;
- `evidence_damage`;
- each control record and which recorded groups are alive;
- uncertain rows;
- the exact next command.

**`flow run stuck`** scans every run in the project and lists each `started` v8 attempt with:
- whether it is live;
- lead status;
- uncertain row counts;
- open expansion;
- the single next command (`cancel-delivery`, `abandon-delivery`, `decide-expansion` or `recover-delivery-lead`).

It is read-only and exits 0 whether or not it finds anything.

### R10. ADR 0019

ADR 0019 records:
- the terminal statuses `cancelled` and `abandoned`;
- the amended ADR 0016 invariant, where uncertainty blocks a lead change except in those two statuses;
- the process-identity record and its limits;
- the cooperative cancel mechanism;
- attribution-only actors, noting that cancel and abandon are destructive where an approval is not;
- the accepted consequence that late evidence for a cancelled or abandoned row has no reclassification route.

## Reason codes

| Command | Codes |
|---|---|
| `cancel-delivery` | `attempt_not_live`, `process_identity_mismatch`, `foreign_machine`, `owner_generation_stale`, `attempt_not_started`, `cancel_unsupported`, `cancel_timeout` (the attempt stays `started`), `attempt_finished` (informational) |
| `abandon-delivery` | `attempt_running`, `recovery_in_progress`, `owner_generation_stale`, `attempt_not_started`, `lead_guard_ledger_unreadable`, `attempt_dir_unsafe` |
| `delivery-lead` | the existing `change_lead_claim` reasons |

## Success criteria

- A live v8 attempt with a provider call blocked in flight can be cancelled from a second terminal within the deadline, leaving no surviving process from any *recorded* group. The result is a `cancelled` receipt and a successor-ready work id.
- The live-run dead end (an unknown paid send, then `release`) and a runtime-cap interruption both end in `abandon-delivery` followed by a completed successor on the same work id.
- `flow run stuck` names the stuck attempt and the exact command to run, without the operator knowing the work id.
- No uncertain send is resent or reclassified without evidence, in any path.

## Non-goals

- Protocols 5–7.
- A charter-sealed automatic cancel condition.
- MCP ingress (slice 4).
- Authenticating actors.
- Any change to `resolve-execution`.
- A graceful checkpoint-then-stop cancel.
- Changing the runtime cap's own behaviour, which still records an interruption; abandon then covers it.
- Cancelling from another machine.
- Non-POSIX platforms.
- Ollama server-side generation. The client socket closes, and nothing further is claimed.
- SIGINT semantics.
- Processes that are neither started by Flow nor recorded.

## Constraints

- There is no back-compat requirement, and older attempts are not migrated.
- Tests are hermetic: stub providers, a harness subprocess for the parent, real process groups and signals, file or FIFO synchronization instead of sleeps, and one test with a fake `claude` on `PATH`. No paid or live calls.
- The ledger and the existing fences stay authoritative, and the existing lock order is kept.

## Assumptions

- The parent holds `recovery_lock` for the whole v8 attempt (observed).
- The provider and supervisor waits retry on EINTR, so interruption must be explicit (observed, F1).
- The kernel guarantees for reaping pgid members after the leader has exited need a planning spike (open, F11).

## Evidence and research implications

- `research/live-child-cancel.md` → R1–R3.
- `research/abandon-seal.md` → R4–R7 and R10.
- `research/shaper-authority.md` → attribution.
- `adversarial-review.md` F1–F21 and `adversarial-product.md` P1–P6 → revision 2 (`definition-dispositions.md`).
- The precedent `chartered-delivery-recovery-1b` is honored: its fences, lineage and caps are reused.

## Open questions (for planning)

- The macOS start-time source: sysctl/libproc or `ps`.
- The pgid-member reaping guarantee after the leader exits (F11 spike).

## Approval status

Approved by Andy on 2026-09-27 (revision 2).
