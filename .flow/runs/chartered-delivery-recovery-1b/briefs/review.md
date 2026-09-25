# Brief: acceptance review, chunk 1b

Run `chartered-delivery-recovery-1b`, lane `review`. The review is read-only: return findings inline and the orchestrator records them in `review.md`.

## Task

Judge chunk 1b against its intent. The question is not "is the code clean". It is whether 1b delivers AC1–AC6 in `acceptance-criteria.md`, with decisions E1–E5 in `requirements.md`, and whether the proof actually establishes them.

- **Diff:** `git diff 79cbffb..HEAD -- cli docs tests`, on branch `codex/chartered-delivery-recovery-1b` in `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`. Code commits: `34d4354` ADR, `c67d18f` seal and guard, `15e15b4` lineage, `d21a2d2` guard test, `e16e8bd` review fixes. `2760098` is evidence only.
- **Out of scope, so don't report these as defects:**
  - **Chunk 2:** resolving v8 `unknown` sends; the case where a resolved `unknown` unblocks a lead change (E2); the lineage count in `regrant_not_dispatched`.
  - A CLI command for lead resume or supersede.
  - Any change to v5–v7 semantics, except the intended one: a v7 `started`/`unknown` send now blocks a lead change (requirement 2).
  - **Mismapping:** if a criterion is proved by the wrong test, or the test does not reach the assertion the AC names, report that.

## Evidence inventory (exists now)

- **Intent:** `.flow/runs/chartered-delivery-recovery-1b/requirements.md`, `acceptance-criteria.md`, `plan.md`, `validation-plan.md`, `implementation-handoff.md`; `docs/adr/0016-chartered-v8-recovery.md` (amendment section); parent `.flow/runs/chartered-delivery-recovery/requirements.md` requirement 10 and R4, and `research/plan-architecture.md` items 8–10.
- **Implementation evidence:** `validation-results.md` (AC map, mutation list, residuals), `HANDOFF.md`, `validation/full-suite.log` (1442 OK, 0 skipped), `validation/maf-gated.log` (11 OK, 0 skipped), `validation/mutations.log` (M1a, M1b, M2, M3, M4).
- **Prior review:** `research/implement-review.md` (quality, plus the disposition table for both reviews) and `research/implement-review-security.md`. Fixes are in `e16e8bd`.
- **Code:** `cli/delivery_control.py` (`change_lead_claim`, `_fence_and_seal_attempts`), `cli/execution_ledger.py` (`lead_change_blocker`, `started_v8_attempts`, `seal_superseded_attempts`, `v8_lineage`/`_v8_lineage_locked`, `create_attempt`, `_lineage_usage`, `decide`, `_v8_limit_reason`, `_verifier_usage`), `cli/execution_contracts.py` (`_validate_predecessors`, `lineage_usage` validation and recompute), `cli/delivery_gateway.py` (`prepare_chartered_delivery`, `_build_receipt`, task facts), `cli/delivery_recovery.py`.
- **Tests:** `tests/test_chartered_delivery_recovery.py` (`LeadChangeFenceTests`, `SuccessorLineageTests`, `SuccessorLineageTamperTests`, the moved AC9.1 test), `tests/test_chartered_delivery_gateway.py`, `tests/test_structured_verifier_ledger.py`.
- **Test runner:** `python3.12 -m unittest …`; the system `python3` is 3.9 and fails to import. Read-only means do not edit files; running focused tests is allowed.

## Output

Return:

1. A verdict: ready to accept, needs refinement, or wrong slice.
2. Findings ranked critical, important, or suggestion. Give each one `file:line`, a concrete scenario, and a claim status: observed, inferred, or unverified.
3. For each AC (AC1–AC6), state whether it is met, partially met, or not met, with the specific test or code that decides it.

Don't re-raise the dispositioned findings in `research/implement-review.md` unless the fix is wrong or incomplete. The accepted residuals (no dedicated `unknown` manager-call trigger test; no regrant-path lineage test) may be re-weighed, but say why.
