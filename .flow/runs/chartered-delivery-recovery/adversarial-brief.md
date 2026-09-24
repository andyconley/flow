# Adversarial review brief: chartered delivery recovery

Challenge the **draft** requirements from your accountable perspective. Do not rewrite them. Report findings with dispositions.

## Under review
- `requirements.md`
- `acceptance-criteria.md`
- `reconciliation.md`

## Evidence inventory
- Discovery notes:
  - `research/recovery-boundary.md` (architecture)
  - `research/failure-scenarios.md` (business analysis)
  - `research/increment-scope.md` (product)
- Code: the v8 worktree at `/Users/andyconley/.codex/worktrees/verifier-contract/flow`, in `cli/delivery_gateway.py`, `cli/execution_ledger.py`, `cli/delivery_control.py`, and `cli/delivery_projection.py`.
- Governing documents: ADRs 0012, 0014, and 0015 under `docs/adr/`, and `docs/maf-adoption-design.md`.
- Predecessor archives: `/Users/andyconley/src/flow/.flow/runs/maf-restart-reconciliation/archive.md` and `/Users/andyconley/src/flow/.flow/runs/maf-post-resolution-continuation/archive.md`.

## Dispositions
Give each finding one of these dispositions:
- requirement changed
- acceptance criterion changed
- non-goal clarified
- assumption confirmed
- assumption rejected
- open question recorded
- next lane changed
- defer
- reject

For each finding, cite file:line or a section, and give a claim status: observed or inferred.
