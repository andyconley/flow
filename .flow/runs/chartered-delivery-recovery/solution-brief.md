# Solution brief: chartered delivery recovery

- **Approved inputs:** `requirements.md` and `acceptance-criteria.md`, approved 2026-09-23. Engineer decisions D1 to D4 are in `adversarial-review.md`.
- **Engagement answers from the engineer (2026-09-23), binding constraints:**
  1. **One receipt.** A recovered attempt keeps one receipt covering the whole attempt, with the recovery facts added. There is no separate linked recovery receipt.
  2. **Non-terminal state.** An interrupted v8 attempt may stay in a non-terminal "interrupted, recoverable" state with no receipt until it finishes. So an attempt with an `unknown` call must not seal a terminal `unknown` receipt; it stays open and blocked until resolved.
  3. **Restart from baseline.** After a lead resume or supersede, the successor starts a new attempt from the charter baseline in a fresh worktree. It must also be aware of the previous runs. The coordinator reads this as: the new attempt durably links its fenced predecessors, and their outcomes are visible to the Delivery Lead's task facts and in inspection. Confirm or refine this interpretation.
  4. **Extend the existing commands.** `flow run resume-delivery-lead` and `recover-delivery-lead` accept v8. No new command.
  5. **A new ADR 0016** for chartered recovery, referencing ADR 0014.
- **Delivery:** two chunks (D1).
  - Chunk 1: boundaries that need no evidence.
  - Chunk 2: continuation after an operator resolution.
- **Evidence inventory:**
  - This run's `research/recovery-boundary.md`, `research/failure-scenarios.md`, and `adversarial-review.md`.
  - The v8 code at `/Users/andyconley/.codex/worktrees/verifier-contract/flow`:
    - `cli/delivery_gateway.py`: `resume_delivery` ~567, `recover_delivery` ~660, `_execute_prepared_delivery` ~740, the terminal and receipt logic ~990-1060, `prepare_chartered_delivery` ~250-420.
    - `cli/execution_ledger.py`: `create_attempt` ~230, `_claim_recovery_locked` ~250, `finish_attempt` ~1235, continuation epochs ~1260-1480, `resolve_unknown` ~889.
    - `cli/delivery_control.py`: the guard ~40, `change_lead_claim` ~210.
    - `cli/execution_contracts.py`: `_validate_magentic_receipt`.
    - `cli/flow.py` ~575-620 and ~977-1010.
  - ADRs 0012, 0014, and 0015 under `docs/adr/`.
  - v5 precedent: the archives `/Users/andyconley/src/flow/.flow/runs/maf-restart-reconciliation/archive.md` and `maf-post-resolution-continuation/archive.md`.
- **Applicable standard:** `scaffolds/default/standards/architecture.md` in the v8 worktree, including the five architecture dimensions and the ADR convention.
