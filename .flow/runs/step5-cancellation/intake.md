# Intake: step5-cancellation

Operator and Shaper control over chartered v8 delivery attempts (MAF adoption step 5).

## Engineer decisions (2026-09-27)

1. **(a) One slice** covering all three situations:
   - cancel a live supervised attempt;
   - abandon a stuck attempt (left `started` or with uncertain sends, and no live process);
   - continue the same work id afterwards.
2. **(a) Work-id reuse** is a successor attempt in the same run, linked by `predecessors`, following the existing lineage from `chartered-delivery-recovery-1b`.
3. **(a) Live cancel** signals the supervised child. An in-flight provider call becomes `unknown`, the receipt is sealed `cancelled`, and the uncertainty is reconciled through the existing resolve route.
4. **(a) v8 only.**
5. **Both the operator and the Shaper** may cancel.

## Precedent (archive retrieval, selection `144e9cf4`)

`chartered-delivery-recovery-1b` (current):
- `resume` or `supersede` seals `started` v8 attempts as `superseded`;
- a lead change refuses on `reconciliation_required`, `lead_guard_ledger_unreadable`, `attempt_running` or `recovery_in_progress`;
- `release` and lifecycle `block` stay open;
- a successor lists `predecessors`, and a started sibling refuses with `sibling_attempt_not_terminal`.

## Known pain (live runs)

- `change_lead_claim` has no CLI (gap `delivery-lead-claim-cli`).
- A released attempt with uncertain sends stays `started`, so no successor can start and the work id is dead (gap `run-supersede-transition`).
