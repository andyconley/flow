# Brief: implementation review, chunk 1a (quality and security)

Run `chartered-delivery-recovery`, lane `implement`. The review is read-only: return findings inline and the orchestrator records them.

## What changed

The diff under review is `git diff e43c109..HEAD`, 12 commits on branch `codex/chartered-delivery-recovery-1a`, in `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`. It implements chunk 1a of ADR 0016: explicit, exclusive recovery of an interrupted protocol v8 chartered attempt from its latest Flow-bound Magentic worker checkpoint.

## Evidence inventory (exists now)

- Design and scope:
  - `docs/adr/0016-chartered-v8-recovery.md`
  - `.flow/runs/chartered-delivery-recovery/plan.md`
  - `implementation-handoff.md`
  - `validation-plan.md`
  - `acceptance-criteria.md`
  - `research/plan-architecture.md` (the §2 design with code anchors)
- Pure rules: `cli/delivery_recovery.py`.
  - `recovery_eligibility` (modes answer, pending and seal; the R1 fail-closed rule)
  - `rebuild_chartered_evidence_plan`
  - `restore_position`
  - `build_recovery_block`
  - the `RecoveryRefused` reason codes
- Ledger: `cli/execution_ledger.py`.
  - `attempt_interruptions` and `attempt_recoveries` DDL, and `attempts.sealed_receipt_sha256`
  - `_recovery_view` in `snapshot`
  - `recovery_lock`
  - `claim_chartered_recovery`
  - `regrant_recovered_action` and `_v8_limit_reason`
  - `reissue_recovered_manager_grant`
  - `record_interruption` and `_record_interruption_locked`
  - `record_runtime_outcome`
  - `finish_attempt` (refuses a v8 `unknown` and stores the sealed digest)
- Gateway: `cli/delivery_gateway.py`.
  - `_peek_snapshot`, `_lead_active` and `_resume_chartered`
  - `_unbound_checkpoints` and `_quarantine_checkpoints`
  - `_verify_chartered_baseline` and `_rebuild_chartered_evidence`
  - `_execute_prepared_delivery` (the live fence wrapper) and `_run_prepared_delivery`, including the `recovery` and `seal_hook` keywords, the regrant hook in `on_action` and the reissue hook in `on_manager`
  - `_seal_attempt` and `_build_receipt` (the recovery block and replaced-draft digest)
  - `_completed_reply`
  - routing in `resume_delivery` and `recover_delivery`
- Other code:
  - `cli/execution_contracts.py`: `_validate_predecessors` and `_validate_recovery_block`
  - `cli/execution_gateway.py`: the `resolve_attempt` v8 refusal
  - `cli/delivery_projection.py`: `lead_claim_active` and the v8 inspection view
  - `cli/flow.py`: the refusal `code` and the inspect-delivery text lines
  - `runtime/maf_runner/delivery_lead.py`: the `pending` restore mode
- Tests:
  - `tests/test_chartered_delivery_recovery.py` (new): refusals, the kill matrix and inspection
  - `tests/test_chartered_delivery_gateway.py`: `CharteredFixture`, the flipped transport test and the seal-hook tests
  - `tests/test_delivery_recovery.py` (new): table tests
  - `tests/test_structured_verifier_ledger.py`: the claim, regrant, reissue, lock and migration tests
  - `tests/test_maf_delivery_lead.py`: the MAF-gated pending-mode test
- Current results: the full suite passes (1417 tests, 0 skipped with the local MAF interpreter). With the evidence-reuse branch disabled, the AC6 test fails.

## Invariants to challenge

1. No uncertain call is ever resent. `started` or `unknown` rows refuse before any claim.
2. A refusal before the claim mutates nothing. Gates read the ledger read-only.
3. A released grant counts once against the limits. A regrant writes a fresh `policy_allowed` event.
4. Lock order is `recovery_lock`, then `run_lock`, then `send_lock`, then SQLite. There are no nested acquisitions of the non-re-entrant locks.
5. v5 through v7 behavior is unchanged. Every new path is gated on protocol 8.
6. The receipt `recovery` block cannot be forged or removed without detection, beyond the stated R2 residual.
7. The test runner is never rerun once a verifier input is bound. Worktree drift refuses before any send.
8. Chunk 2 and 1b scope is out: operator resolution, the superseded seal, lineage limits.

## Output

Return findings ranked by severity: blocker, major, minor, or nit. Give each one `file:line`, a concrete failure scenario, and a claim status (observed, inferred, recommended, or unverified). Say explicitly if an invariant holds. Don't report missing 1b or chunk-2 features as defects.
