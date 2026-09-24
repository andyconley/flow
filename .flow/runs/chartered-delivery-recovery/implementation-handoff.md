# Implementation Handoff: Chartered v8 Delivery Recovery (chunk 1a)

This handoff is for `flow-implement`. It is self-contained: read it with `plan.md`, which holds the scope and the decisions, and `research/plan-architecture.md` §2, which holds the design and every code anchor.

## Starting point

- **Worktree:** `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`
  - Branch `codex/chartered-delivery-recovery-definition`, rebased on `main` at `9436527`. v8 is merged.
  - Create an implementation branch named `codex/chartered-delivery-recovery-1a`.
- **Interpreter:** `python3.12`. The system `python3` is 3.9, and `cli/` does not import under it.
- **Baseline:** `python3.12 -m unittest discover -s tests` passes 1370 tests with 0 skipped.
  - The zero skips depend on the local MAF interpreter at `/private/tmp/flow-maf-runtime-spike-20260919/bin/python`, or the path in `FLOW_MAF_PYTHON`.
  - **Confirm that path exists before you start.**
- **Run state:** `plan_approved`. The implementation cycle opens with `flow run transition chartered-delivery-recovery start-implementation`.

## What to build (1a)

1a is commits 1–11 and 14 in `plan.md` "Commit Sequence". In order:

1. **ADR 0016** (`docs/adr/0016-chartered-v8-recovery.md`). It records:
   - Option A;
   - the R1 fail-closed rule and its revisit condition;
   - the `pending` restore mode and checkpoint quarantine;
   - that v8 never seals `unknown`;
   - the lock order `recovery_lock`, then `run_lock`, then `send_lock`, then SQLite;
   - the live-attempt fence;
   - the ADR 0014 amendment (the implementation lands in 1b, but the ADR records it now);
   - predecessor set equality;
   - lineage-counted limits: paid sends and verifier sends, with manager calls kept per attempt (P2);
   - the R8 residual;
   - rejected alternatives B, C, and baseline replay.
2. **Ledger schema:** `attempt_interruptions`, `attempt_recoveries`, and `attempts.sealed_receipt_sha256`. The DDL is in plan-architecture §2. Guard the existence checks in `snapshot`, and add an old-database migration test.
3. **Refactor:** extract `_build_chartered_receipt` and the reply-rebuild helper. Existing tests stay unchanged.
4. **v8 interruption.**
   - Add the `record_interruption` branch and the `finish_attempt` v8 `unknown` refusal.
   - Invert and rename `tests/test_chartered_delivery_gateway.py:725` (`test_v7_transport_loss_after_producer_seals_nonresumable_receipt`). It actually runs v8, and the flip is intended.
5. **`seal_hook` seam** at `after-runtime-outcome`, `after-receipt-draft`, and `before-finish-attempt`, plus the `runtime_outcome_recorded` event.
6. **Contracts:** the `predecessors` envelope validator and receipt `recovery` validator rules (a)–(f), each with a tamper subtest. Add a v7 completed-receipt regression test.
7. **`cli/delivery_recovery.py`:** pure eligibility and the evidence plan. Add table tests for U0–U5, the `attempt_running` case, and every mode.
8. **Ledger:**
   - `recovery_lock`;
   - `claim_chartered_recovery` (compare-and-swap);
   - release and `regrant_recovered_action`, which writes a fresh `policy_allowed` event;
   - `reissue_recovered_manager_grant`;
   - `record_runtime_outcome`.

   **The live `_execute_prepared_delivery` also holds `recovery_lock` for the whole run** (this is the live-attempt fence).
9. **Runtime `pending` restore mode** in `runtime/maf_runner/delivery_lead.py`, with MAF-gated tests.
10. **Routing and refusals** in `resume_delivery` and `recover_delivery`.
    - Add the `RecoveryRefused` codes.
    - `resolve-execution` refuses v8 with `v8_resolution_requires_chunk_2` (P3).
    - Add the AC1 no-mutation tests. Pre-claim gates open the ledger with `read_only=True`.
11. **`_resume_chartered`:**
    - claim, quarantine, evidence rebuild, restore (answer, pending, or seal mode), continue, seal with the `recovery` block and `replaced_draft_sha256`;
    - tests for the AC4 chunk-1 kill matrix, AC2 concurrency and re-invoke, AC3 ordering, AC6, AC7, and AC8.
12. *(commit 14)* **Inspection:**
    - `executable` and `resumable` come from the `run.json` lead check;
    - add eligibility, blockers with the evidence each needs, interruptions, recoveries, predecessors, and the sealed-digest match;
    - add the CLI text lines.

**1b (a separate PR, after 1a merges):** commit 12 (the superseded seal and ledger-backed lead guard, AC9) and commit 13 (predecessors and lineage limits).

## Rules that must hold

- **v5–v7 semantics are unchanged.** The ADR 0013 epochs stay v5-only, and every new path is gated on protocol 8.
- **No uncertain call is ever resent.** Eligibility refuses `started` or `unknown` rows with `reconciliation_required` before any claim.
- **A refusal before the claim mutates nothing, byte for byte.** Use `_assert_ledger_unchanged`.
- **Kill tests raise `KillPoint(BaseException)`.** `except Exception` at `delivery_gateway.py:909`, `:953`, and `:979` would otherwise simulate the wrong state.
- **`seal_hook` is keyword-only** and is not wired into `cli/flow.py`.
- **Tests are hermetic:** no network, no live providers.
- **Conventional Commits,** one logical change per commit, and the full suite passes after each commit.

## Known traps (from plan-architecture §0)

- Opening the ledger for writing runs DDL, so gates must open it read-only.
- A recovered attempt's ledger fence no longer equals the lead generation. Inspection must read `run.json`.
- A replayed manager grant expires when it is consumed, so it must be re-issued in place under recovery.
- Grant expiry reads only `policy_allowed` events. A regrant must write one.
- `run_lock` and `send_lock` are not re-entrant. Release both before `_execute_prepared_delivery`.
- Unbound pending checkpoint files make the runner abort as ambiguous. Quarantine them before any restore.

## Done means

- Every 1a item in `validation-plan.md` passes.
- The MAF-gated tests **ran** locally, not skipped, and the log is in the PR description.
- The AC12 test-runner mutation check is recorded in `validation-results.md`.
- `mark-handback-ready` passes with `validation-results.md` and `HANDOFF.md`.
