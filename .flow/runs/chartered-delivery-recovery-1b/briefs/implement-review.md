# Brief: implementation review, chunk 1b

Read-only review of the 1b commits on `codex/chartered-delivery-recovery-1b` (range given by the coordinator at dispatch). Judge the diff against `requirements.md` (E1–E5), `acceptance-criteria.md` (AC1–AC6), and `plan.md`.

## Evidence inventory (what already exists)

- Lead control: `cli/delivery_control.py` (`change_lead_claim`, `run_lock`, `delivery_authority_guard`).
- Ledger: `cli/execution_ledger.py` (`recovery_lock`, `send_lock`, `_unresolved_action`, `create_attempt`, `decide`, `_v8_limit_reason`, `_verifier_usage`, `claim_chartered_recovery`, `snapshot`).
- Contracts: `cli/execution_contracts.py` (`_validate_predecessors`, the v8 receipt usage recompute, `_validate_recovery_block`).
- Gateway: `cli/delivery_gateway.py` (`prepare_chartered_delivery`, `_build_receipt`, task facts in `_run_prepared_delivery`).
- Inspection: `cli/delivery_projection.py`, `cli/flow.py` `inspect-delivery` text output.
- ADR: `docs/adr/0016-chartered-v8-recovery.md`, `docs/adr/0014-shaper-delivery-ownership.md`.
- Tests: `tests/test_chartered_delivery_recovery.py`, `tests/test_chartered_delivery_gateway.py`, `tests/test_delivery_control.py`, `tests/test_chartered_execution_contract.py`, `tests/test_structured_verifier_ledger.py`.
- Parent design: `.flow/runs/chartered-delivery-recovery/research/plan-architecture.md` items 8–10.

## Questions

1. Can any refusal path (guard, unreadable ledger, live lock, sibling, link mismatch) mutate `run.json`, a claim file, or the ledger?
2. Can a successor evade the paid or verifier caps (dropping a predecessor, a concurrent prepare, a regrant path that skips the lineage count)?
3. Do `decide`, `_v8_limit_reason`, `_verifier_usage`, and the receipt recompute agree?
4. Is v5–v7 behavior unchanged, and is the first attempt's envelope byte-identical?
5. Lock order: is the non-blocking `recovery_lock` probe under `run_lock` deadlock-free, and is any lock left held on an error path?

Report findings with severity (blocker, major, minor, nit), `file:line`, and claim status (observed, inferred, recommended, unverified). Write only the output file named in the manifest.
