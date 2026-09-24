# Brief: acceptance review, chunk 1a

Run `chartered-delivery-recovery`, lane `review`. The review is read-only: return findings inline and the orchestrator records them in `review.md`.

## Task

Judge chunk 1a against its intent. The question is not "is the code clean". It is whether 1a delivers the acceptance criteria assigned to it, and whether the proof actually establishes them.

- **Diff:** `git diff e43c109..HEAD`, on branch `codex/chartered-delivery-recovery-1a` in `/Users/andyconley/.codex/worktrees/delivery-recovery/flow`. There are 13 code and doc commits and 1 evidence commit, `0b47695`.
- **In scope for 1a:** AC1, AC2, AC3, AC4 (boundaries b, d, f, g, h, i, and transport loss), AC6, AC7, AC8, AC9 clause 1, AC10 (the generation and marker checks), AC11, and the test-runner half of AC12.
- **Out of scope, so don't report these as defects:**
  - **Chunk 2:** AC4 (a), (c), (e); AC5; the AC10 resolution subtests; the AC12 worker-adapter mutation.
  - **Chunk 1b:** AC9 clauses 2 to 4, the superseded seal, and lineage limits.
  - **Mismapping:** if a criterion is mapped to the wrong chunk, report that as a mismapping.

## Evidence inventory (exists now)

- **Intent:**
  - `.flow/runs/chartered-delivery-recovery/acceptance-criteria.md`
  - `plan.md`
  - `implementation-handoff.md`
  - `validation-plan.md`, which maps each AC to its proof and its chunk
  - `docs/adr/0016-chartered-v8-recovery.md`
  - `research/plan-architecture.md`
- **Implementation evidence:**
  - `validation-results.md`: the proof map for each AC, command results, and the AC12 mutation check
  - `HANDOFF.md`
  - `validation/*.log`, including `maf-gated.log` (11 ran, 0 skipped)
- **Prior review:**
  - `research/implement-review.md`: 18 quality and security findings with dispositions; the fixes are in `3a69f3f`
  - `briefs/implement-review.md`: the invariants that review challenged
- **Code:**
  - `cli/delivery_recovery.py` (new)
  - `cli/delivery_gateway.py`: `_resume_chartered`, `_recovery_gates`, `_check_chartered_evidence`, `_rebuild_chartered_evidence`, `_seal_attempt`, `_build_receipt`, `_run_prepared_delivery`, and the routing in `resume_delivery` and `recover_delivery`
  - `cli/execution_ledger.py`: `recovery_lock`, `claim_chartered_recovery`, `regrant_recovered_action`, `reissue_recovered_manager_grant`, `record_interruption`, `record_runtime_outcome`, and `finish_attempt`
  - `cli/execution_contracts.py`: `_validate_recovery_block` and `_validate_predecessors`
  - `cli/execution_gateway.py`: the v8 refusal in `resolve_attempt`
  - `cli/delivery_projection.py`
  - `cli/flow.py`
  - `runtime/maf_runner/delivery_lead.py`: pending mode
- **Tests:**
  - `tests/test_chartered_delivery_recovery.py` (new)
  - `tests/test_chartered_delivery_gateway.py`
  - `tests/test_delivery_recovery.py` (new)
  - `tests/test_structured_verifier_ledger.py`
  - `tests/test_maf_delivery_lead.py`
- **Results:**
  - The full suite ran 1420 tests: OK, 0 skipped (python3.12, local MAF interpreter).
  - CI has no MAF job, so the local MAF log is the gate.

## Output

Return:

1. A verdict: ready to accept, needs refinement, or wrong slice.
2. Findings ranked critical, important, or suggestion. Give each one `file:line`, a concrete scenario, and a claim status: observed, inferred, or unverified.
3. For each in-scope AC, state whether it is met, partially met, or not met, with the specific test or code that decides it.

Don't re-raise the dispositioned findings in `research/implement-review.md` unless the fix is wrong or incomplete.
