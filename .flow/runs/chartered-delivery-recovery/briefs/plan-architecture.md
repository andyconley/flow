# Brief: plan architecture and R1 spike (architect)

Run `chartered-delivery-recovery`, lane `plan`. The work is read-only except for the output file. Base: `main` at `9436527`, which has protocol v8 merged.

## Task

1. **Run spike R1, read-only.**
   - Can a v8 attempt that was interrupted before any Magentic checkpoint was bound be replayed safely from the charter baseline?
   - "Safely" means three things: no provider resend, no duplicate grant, and no ledger row whose meaning changes.
   - Give a verdict: `safe-replay` (with the exact conditions under which it holds) or `fail-closed` (`no_restorable_checkpoint`).
   - Cite code with `file:line` for every claim.
2. **Produce a file-level design for chunk 1.** For each design item in `solution.md` (1–10, 12, 13), name:
   - the functions to add or change, with their current `file:line` anchors;
   - any new ledger table or column, with its DDL shape and migration or compatibility notes;
   - new receipt fields and the validator changes;
   - the lock order, and where the exclusive claim lives.
3. **Propose a commit sequence** inside chunk 1. Each commit is one logical change, green on its own, and follows Conventional Commits.
4. **Draft the recovery sequence diagram** (Mermaid): interrupt, then recovery claim, reconcile, evidence rebuild, restore, continue, seal.
5. **Outline chunk 2 at the component level only.** Also say whether `resolve-execution` supports v8 today (R5).

## Evidence inventory (exists today)

- Approved inputs:
  - `.flow/runs/chartered-delivery-recovery/requirements.md`
  - `acceptance-criteria.md`
  - `solution.md` (Option A, accepted)
  - `research/solution-options.md`, the table of how each boundary is handled
  - `research/solution-data.md`, the ledger design
  - `research/recovery-boundary.md`
  - `research/failure-scenarios.md`
- Gateway, `cli/delivery_gateway.py`:
  - `prepare_chartered_delivery` :233
  - the v8 envelope and the `job_contract.test.argv` pin, around :376–:391
  - `resume_delivery` :567, which is v5-only
  - `recover_delivery` :658, which is v5-only
  - `_execute_prepared_delivery` :741
  - checkpoint binding :900–:905
  - the chartered test evidence shape, around :564
- The ledger `cli/execution_ledger.py`: `prepare_verifier_send`, `observe_response`, `resolve_unknown`, `verifier_inputs`, `verifier_evaluations`, and the checkpoint tables.
- `cli/execution_contracts.py`: receipt validation, including the v8 evaluation recompute and the cross-bind under `has_structured_verifier_evaluations`.
- `cli/delivery_control.py`: the precedent for `failure_point`.
- `cli/verifier_contracts.py`: the v8 evaluator.
- ADRs:
  - `docs/adr/0012-flow-owned-maf-recovery.md`
  - `0013-flow-owned-terminal-continuation.md`
  - `0014-shaper-delivery-ownership.md`
  - `0015-flow-owned-structured-verifier-evaluation.md`
- Tests:
  - `tests/test_chartered_delivery_gateway.py`, which has the `_run_v8` helper
  - `tests/test_maf_recovery.py`
  - `tests/test_execution_recovery.py`
  - `tests/test_structured_verifier_ledger.py`
  - `tests/test_delivery_control.py`
- Test runner: `python3.12 -m unittest discover -s tests`. The system `python3` is 3.9, and `cli/` does not import under it.

## Constraints

- v5 through v7 behavior and receipts must stay unchanged. The ADR 0013 epochs stay v5-only.
- Uncertain calls are never resent. v8 never seals a terminal `unknown` receipt.
- Mark each claim `observed`, `inferred`, `recommended`, or `unverified`.

## Output

Write `.flow/runs/chartered-delivery-recovery/research/plan-architecture.md`. Return a summary of 10 lines or fewer, plus the path.
