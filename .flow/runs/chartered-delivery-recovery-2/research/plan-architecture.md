# Research: file-level plan, chunk 2 (plan-architecture, architect)

- **Method:** read-only. Every anchor was read at HEAD (`b38989b`).
- **Labels:** [O] observed in code, [I] inferred, [U] unverified.
- **Advisory expertise:** request `1c907546…`, `no_match`.

The orchestrator condensed the report into `plan.md`. The findings below are what the plan relies on.

- **Route location [O].** `delivery_gateway` imports `execution_gateway` (`delivery_gateway.py:31`). The new public `resolve_execution` therefore lives in `delivery_gateway.py`, peeks the protocol (the pattern at `:942-947`), sends v8 to `_resolve_chartered`, and leaves v5–v7 on the unchanged `execution_gateway.resolve_attempt`. Its v8 refusal (`:911-913`) stays as defense in depth.
- **Why `resolve_unknown` is not reused [O].**
  - Its status gate is `{unknown, allowed}` (`execution_ledger.py:1273`).
  - It has no protocol check, no compare-and-swap, and no role check.
  - Its evidence comes from the caller.
  - The evidence item `{"kind":"flow_response_observation","path":"ledger:response_observations/<action_id>","sha256":<result_digest>}` passes `validate_recovery_evidence` (`execution_contracts.py:1044-1054`).
- **Binding [O].**
  - Eligibility today checks status only (`delivery_recovery.py:89-96`). A resolved row becomes `completed/operator_resolved_completed` (`execution_ledger.py:1301`).
  - The snapshot selects resolutions `WHERE attempt_id=?` (`:1993`), so a row injected under another attempt is invisible.
  - The claim's event high-water compare-and-swap (`:491-494`) catches a resolution written after eligibility was decided.
- **Receipt and R1 [O].**
  - `build_recovery_block` (`delivery_recovery.py:167-177`) and rule (f) (`execution_contracts.py:438-441`) already count `operator_resolved_*`.
  - The validator never reads a resolution's generation (`:389-390`).
  - v8 `owner_generation` starts at the claim generation (`execution_ledger.py:290`) and changes only through a recovery claim (`:500`) or the supersede seal (`:428`), so the current generation is always in the chain.
  - A bump would cause a spurious `unmarked_process_exit` (`:508-512`) and break `expected_generation` (`execution_contracts.py:417-419`).
- **Lead change [O].** `lead_change_blocker` and the seal match `started`/`unknown` only (`execution_ledger.py:624-632`, `:407`).
- **Drift (R3) [O and I].**
  - `_check_chartered_evidence` runs before the claim (`delivery_gateway.py:669-672`).
  - After a resolution, the rebuilt plan re-verifies scope, and checks against the bound diff when a verifier input exists (`:748-753`).
  - **Residual [I]:** a resolved producer with no verifier input is checked for scope only.
- **Fixture compatibility [O and I].**
  - The gateway fixture keeps `root/worktree` beside `root/.flow` (`test_chartered_delivery_gateway.py:40-43`) [O], so the worktree guard does not break existing tests [I].
  - `tests/test_chartered_delivery_recovery.py:1106` expects the old evidence text and must change.
- **Migration [O].** None; there is no schema change.
