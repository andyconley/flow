# Plan: Chartered v8 Delivery Recovery

Status: **decisions P1–P5 recorded 2026-09-23; plan submitted for approval.** Base: `main` at `9436527` (v8 merged in PR #25).

The inputs are the approved `requirements.md` and `acceptance-criteria.md`, the accepted `solution.md` (Option A), `research/plan-architecture.md` (the design, with every code anchor), and `research/plan-validation.md` (the map from criteria to tests). Where this plan and the two research notes disagree, this plan wins.

## Problem Statement

- **What:**
  - Today, a protocol-v8 chartered attempt that is interrupted stays `started` with no receipt, or it is sealed `failed` or `unknown`. It can't be recovered. `resume_delivery` and `recover_delivery` are v5-only (`cli/delivery_gateway.py:567`, `:658`).
  - This work adds explicit v8 recovery. It:
    - reconciles the ledger first;
    - takes an exclusive claim;
    - reuses the test evidence the verifier judged;
    - never resends an uncertain call;
    - seals exactly one receipt with a `recovery` block;
    - supports a lead change that seals the old attempt as `superseded` and links a successor with lineage-wide limits.
- **Who:**
  - Operators, who run `flow run resume-delivery-lead` or `recover-delivery-lead`.
  - The Delivery Lead runtime.
  - Anyone who reads a receipt to audit a delivery.
- **Why now:** v8 made the verifier's verdict evidence-bound, but a crash still orphans the attempt. The v8 archive lists this as the main follow-up, and it comes before any live Ollama use.

## Desired Outcome

- An interrupted v8 attempt stays **interrupted and recoverable**.
- An explicit command returns it to a terminal receipt, with zero resends and without re-running a test whose output varies. If recovery isn't possible, the command refuses with a stable reason and changes nothing.

## Scope

### In scope: chunk 1 (this implementation cycle, file level)

Design details and anchors are in `research/plan-architecture.md` §2.

1. **Version routing and refusals.**
   - `RecoveryRefused(ContractError)` with stable codes:
     - `v6_inspection_only` and `v7_not_recoverable`;
     - `attempt_terminal` and `continuation_epochs_v5_only`;
     - `lead_generation_inactive`, `recovery_in_progress`, and `attempt_running`;
     - `reconciliation_required`;
     - `no_restorable_checkpoint` and `checkpoint_position_unrecoverable`;
     - `worktree_drift` and `evidence_binding_conflict`;
     - `sibling_attempt_not_terminal` and `predecessor_link_invalid`.
   - Every gate before the claim opens the ledger with `read_only=True`, because opening it for writing runs DDL.
2. **Interruption.**
   - For v8, a transport loss or uncertain send calls `record_interruption` and returns `status: interrupted` with no receipt.
   - `finish_attempt` refuses a v8 `unknown`.
   - v5, v6, and v7 are unchanged.
3. **Exclusive claim.**
   - A non-blocking `recovery_lock` file at `execution/recovery-<attempt>.lock`, which sits beside the ledger, not in the attempt directory.
   - `claim_chartered_recovery` does a compare-and-swap on `owner_generation`.
   - The lock order is `recovery_lock`, then `run_lock`, then `send_lock`, then SQLite. Neither `run_lock` nor `send_lock` is re-entrant.
   - Eligibility is checked **before** the claim, so a blocked attempt is never mutated.
   - **Live-attempt fence (from the BA review).** The live `_execute_prepared_delivery` holds the same per-attempt lock for the whole run. A process that dies releases its flock, so recovery on a live attempt refuses with `attempt_running` and changes nothing. A dead attempt with no interruption row is recorded as `unmarked_process_exit` when it is claimed.
4. **Reconcile first and checkpoint selection (R1).** Recovery requires a bound worker checkpoint for the highest-sequence action. Otherwise it refuses with `no_restorable_checkpoint`.
   - Mode `answer` handles a completed action, mode `pending` handles boundary (b), and mode `seal` handles boundary (i).
   - Checkpoint files the ledger has not bound are moved to `checkpoints-quarantine/<recovery_id>/`, and their digests are recorded.
5. **Runtime `pending` restore mode** in `runtime/maf_runner/delivery_lead.py`. It re-emits the saved proposal without answering it. The existing answer mode is unchanged. *This amends the requirements assumption "No runtime work is needed"; see decision P1.*
6. **Evidence reuse and drift.**
   - `_verify_chartered_edit` against the binding's `diff_digest`; a mismatch refuses with `worktree_drift`.
   - Once a verifier input exists, `tests = {job_contract.test.argv, passed, final test_digest}`, and the test is **not** run.
   - Before any verifier input exists, the test is run exactly once.
7. **Grants on recovery.**
   - An unconsumed action grant becomes `not_dispatched/recovery_unconsumed_grant` during the claim.
   - `regrant_recovered_action` re-grants it on the same row, counts it once, and writes a fresh `policy_allowed` event.
   - `reissue_recovered_manager_grant` covers an allowed but unsent manager call.
8. **Seal seam and runtime-outcome event.**
   - A keyword-only `seal_hook(point)` at `after-runtime-outcome`, `after-receipt-draft`, and `before-finish-attempt`. It is not on the CLI.
   - A `runtime_outcome_recorded` event is written before the receipt is built.
9. **Receipt.**
   - The builder is extracted as a pure refactor.
   - A v8 `recovery` block holds: interruptions, recoveries, resolutions, and `replaced_draft_sha256`.
   - Validator rules (a) to (f) are in plan-architecture §2 item 7.
   - `attempts.sealed_receipt_sha256` is stored when `finish_attempt` seals the receipt.
10. **Lead change (the ADR 0014 amendment).**
    - The lead guard in `change_lead_claim` is ledger-backed and replaces the inert `pending_unknown_actions` check. It fails closed if the ledger can't be read.
    - `seal_superseded_attempts` runs before the claim bump.
    - Abandonment remains available.
11. **Successor lineage.**
    - The v8 envelope gets a `predecessors` list, added only when it is non-empty.
    - `create_attempt` requires set equality with the ledger.
    - A sibling that is still `started` blocks `prepare`.
    - The task facts gain one line per predecessor.
12. **Limits across a lineage.**
    - Predecessors' paid sends and verifier sends count against the charter cap.
    - The retry rule stays per attempt.
    - The receipt gets `lineage_usage`.
    - `max_manager_calls` stays per attempt (P2).
13. **Inspection.**
    - `executable` and `resumable` use the `run.json` lead check, not the ledger fence. This fixes a bug in which recovered attempts showed as dead.
    - Adds eligibility, blockers (each with the evidence it needs), interruptions, recoveries, predecessors, and the sealed-digest match.
    - The CLI text output gains `recoverable:`, `blocking:`, and `predecessors:` lines.
14. **ADR 0016: chartered v8 recovery.**

### In scope: chunk 2 (next cycle, same run, component level only)

Chunk 2 criteria (AC4 a/c/e, AC5, the AC8 no-dispatch re-grant, the AC10 resolution subtests, and the AC12 worker-adapter mutation) have **no commit sequence or named tests yet, on purpose**. They get file-level traceability when chunk 2 is re-planned after chunk 1 merges, before its `start-implementation`. This is an accepted gap from the BA review.

- The `manager_call_resolutions` table and `resolve_unknown_manager_call`.
- Import of operator-supplied responses, validated with the `observe_*` checks.
- A v8 `resolve-execution` route with an authority guard and a compare-and-swap claim. Today it accepts v8 only by accident (R5).
- A resolution-binding check at continuation (AC5).
- `recovery.resolutions` for manager calls.
- Boundaries (a), (c), and (e), the AC8 no-dispatch re-grant, the AC10 added- and removed-resolution subtests, and the AC12 worker-adapter mutation check.
- Chunk 2 is re-planned at file level after chunk 1 merges.

### Out of scope

- Replaying an attempt with no bound checkpoint. The R1 verdict is fail-closed, and this can be revisited if MAF prompt determinism is proven.
- Any change to the ADR 0013 continuation epochs or to v5, v6, or v7 semantics.
- A live Ollama, Claude, or Codex run.
- Automatic or timed recovery.
- The v7 `close_pre_send_failure` allow-list defect, which is a separate flow-scout (D4).
- Codex and Claude verifier adapters.

## States and Contracts

### Attempt states (v8)

- `started` + no interruption: running.
- `started` + an interruption row: **interrupted, recoverable or blocked**.
- Terminal: `completed`, `failed`, `superseded`, or `abandoned`. For v8, `unknown` is never sealed.

### Contracts

- **CLI.**
  - `resume-delivery-lead` and `recover-delivery-lead` accept v8.
  - A refusal is `{"status":"refused","reason":<code>,"detail":...}` in JSON mode, and a non-zero exit through the existing `ContractError` handling.
  - Re-invoking after a completed recovery returns the current state with no mutation.
- **Ledger.**
  - New tables `attempt_interruptions` and `attempt_recoveries`, and the column `attempts.sealed_receipt_sha256`. The DDL is in plan-architecture §2.
  - All of it is additive and insert-only.
  - Old ledgers get empty tables, and `snapshot` guards on whether they exist.
  - Rolling back is safe.
- **Envelope.** `predecessors` is optional, v8 only, and covered by the envelope digest.
- **Receipt.** The optional v8 `recovery` and `lineage_usage` blocks. Receipts without them validate exactly as they do today.
- **Runtime.** `resume.kind = "pending"` has no `result`.
- **Workflow.**
  - Recovery is idempotent through the compare-and-swap and the unique `(attempt_id, generation)`.
  - A drift refusal after the claim leaves one claim row as the audit record.

### Recovery sequence

The Mermaid diagram is in `research/plan-architecture.md` §4. It runs: interrupt, read-only gate, eligibility, lock, claim and reconcile, evidence rebuild, restore, continue, seal.

## Commit Sequence (chunk 1)

Each commit follows Conventional Commits and passes the full suite on its own.

1. `docs(adr)`: ADR 0016.
2. `feat(ledger)`: the interruption and recovery tables and the sealed-digest column, plus an old-database migration test.
3. `refactor(gateway)`: extract the receipt builder and the reply-rebuild helpers.
4. `feat(gateway)`: v8 interruption instead of a sealed `failed` or `unknown` receipt. **This inverts and renames `test_v7_transport_loss_after_producer_seals_nonresumable_receipt` (`tests/test_chartered_delivery_gateway.py:725`), because that test actually runs v8.**
5. `feat(gateway)`: the `seal_hook` seam and `runtime_outcome_recorded`.
6. `feat(contracts)`: the predecessors validator and the receipt `recovery` validator, with tamper subtests.
7. `feat(recovery)`: the pure `cli/delivery_recovery.py` eligibility and evidence plan, with table tests U0 to U5.
8. `feat(ledger)`: the claim with compare-and-swap, release, regrant, manager reissue, and the runtime-outcome record.
9. `feat(runtime)`: the `pending` restore mode, with MAF-gated tests.
10. `feat(gateway)`: protocol routing and stable refusals, plus the v8 refusal in `resolve-execution` (P3), with the AC1 no-mutation tests.
11. `feat(gateway)`: `_resume_chartered`, with the AC4 chunk 1 matrix and AC2, AC3, AC6, AC7, and AC8.
12. `feat(delivery)`: the superseded seal and the ledger-backed lead guard (AC9).
13. `feat(delivery)`: predecessors and limits across a lineage.
14. `feat(inspect)`: recovery eligibility and blockers (AC11).
15. Mutation evidence, recorded in `validation-results.md`, with no repository file.

**PR split (P5, accepted):**
- **1a:** commits 1–11 plus 14 (inspection). Inspection ships in 1a so that the stated honest gap ("uncertain sends stay blocked *and visible*") holds from the first merge. This covers AC1–AC8, AC10 (generation and marker), AC11, and AC12 (test runner).
- **1b:** commits 12–13, the lead change and the lineage (AC9, R4).

## Validation

The full map is in `research/plan-validation.md`: 29 named tests in `tests/test_chartered_delivery_gateway.py`, plus the new `tests/test_delivery_recovery.py` for the pure module.

**Changes from that note:**

- **Kill mechanism.** Kill points raise `KillPoint(BaseException)`, not `RuntimeError`. `except Exception` at `delivery_gateway.py:909`, `:953`, and `:979` would otherwise turn the kill into a sealed failure, which is not what a process death looks like. `_run_v8` gains `kill_at=`.
- **Where each boundary is killed:**
  - (b): between the checkpoint bind (`:904`) and the grant use (`:906`), or before `prepare_verifier_send` for a verifier;
  - (d) and AC6: `after-runtime-outcome`, or a worker-side kill after the producer completes;
  - (f): after the verifier's response is observed and before its evaluation;
  - (g) and (h): after the evaluation;
  - (i): `after-receipt-draft` and `before-finish-attempt`. The second of these asserts `replaced_draft_sha256`.
- **AC3 ordering proof (from the BA review).** The worker and manager test doubles each record the ledger's event high-water when they are called. The assertion is that the `recovery_claimed` event and the call's `policy_allowed` or `recovery_regranted` event both **precede** every adapter call, not just that the call counts are zero.
- **AC9 sub-clause map:**
  - (1) recovery is refused once the lead generation is inactive: commit 10, test 21;
  - (2) a terminal superseded record: commit 12, test 22;
  - (3) a lead change is refused while an action is `unknown`: commit 12, test 23;
  - (4) abandonment still succeeds: commit 12, test 24.
- **Lineage limits (from the PM review).** Two named tests in commit 13:
  - `test_successor_paid_and_verifier_limits_count_predecessor_sends`
  - `test_successor_first_verifier_is_not_a_retry`
- **Additional tests:**
  - `test_recovery_refuses_a_live_attempt_with_attempt_running`;
  - `test_resolve_execution_refuses_v8_until_chunk_2` (if P3 is accepted);
  - `test_recovery_fails_closed_with_no_restorable_checkpoint_when_none_is_bound`, which covers U4 and U5;
  - a quarantine test in which a stale unbound checkpoint does not cause a sealed `failed`;
  - an inspection test in which a recovered attempt shows as executable;
  - a test that re-granting a manager call after a crash between grant and send succeeds;
  - a migration test that opens a pre-change ledger.
- **Regression:**
  - the v5 suites (`test_maf_recovery`, `test_execution_recovery`, `test_maf_continuation_supervisor`, and `test_maf_post_resolution_continuation`);
  - every existing `test_v7_*` and `test_v8_*`;
  - an `_assert_ledger_unchanged` snapshot helper used by the AC1, AC2 re-invoke, AC7, and eligibility-refusal tests.
- **Commands:**
  1. the focused suites;
  2. `python3.12 -m unittest discover -s tests` (baseline 1370 tests, all passing);
  3. `git diff --check`;
  4. an AC12 manual mutation: disable the evidence-reuse branch, confirm the `test_runner` zero-calls assertion fails, then restore it.
- **No live providers.** All tests are hermetic.

## Engineer Decisions (2026-09-23)

- **P1. Runtime change: accepted into chunk 1.** `requirements.md` carries a dated amendment in its Assumptions section.
- **P2. Manager-call budget: fresh per attempt.** Paid worker sends and verifier sends are counted across the lineage. `max_manager_calls` is not, and ADR 0016 records this.
- **P3. `resolve-execution`: refuses v8 until chunk 2**, with the stable reason `v8_resolution_requires_chunk_2`. v5–v7 are unchanged. The guard lands in commit 10.
- **P4. Unbound checkpoint files are quarantined**, with their digests recorded. The runner gets no exclude list.
- **P5. Chunk 1 ships as two PRs:**
  - **1a:** commits 1–11 plus 14;
  - **1b:** commits 12–13.

  Earlier phase-1 answers still hold: chunk 2 stays in this run as a second cycle, and chunk 2 is outlined here only.

## Owned Risks (updated)

- **R1:** resolved as fail-closed.
- **R2:** covered by the ledger's `sealed_receipt_sha256` and the inspection check that a recovery exists without a `recovery` block.
- **R3:** deferred to chunk 2.
- **R4:** resolved by lineage limits.
- **R5:** answered. `resolve-execution` accepts v8 only by accident, so it now refuses v8 until chunk 2 (decision P3).
- **R6:** the lead guard opens the ledger read-only and fails closed.
- **R7:** resolved, because v8 is merged.
- **New R8:** at boundary (d), no `repair.diff` may exist yet. The worktree is re-verified against the baseline and scope, and ADR 0016 records this.
- **New R9:** the MAF-gated `pending` mode tests skip unless `FLOW_MAF_PYTHON` exists (`tests/test_maf_delivery_lead.py:13-16`).
  - Locally, the pinned interpreter is present at `/private/tmp/flow-maf-runtime-spike-20260919`, so these tests run.
  - CI has no MAF job, so they skip there.
  - Validation must therefore run them locally and record that they ran, not that they were skipped.
  - **This is a merge gate.** The PR for 1a carries the local run log, which shows those tests ran and didn't skip.
