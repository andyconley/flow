# Brief: file-level plan, chunk 2 (architect)

Run `chartered-delivery-recovery-2`, lane `plan`. Read-only; return the plan inline and the orchestrator records it in `research/plan-architecture.md`.

## Task

Produce a file-level implementation plan for Option A (`solution.md`) that another agent could implement without chat context. For each change, give the current anchor (`file:line` at HEAD), the change, and the tests that prove it. Give a commit sequence in two groups (guards and hardening; then reconcile), where each commit leaves the suite green.

## Settled decisions (do not reopen)

- **Option A:** operator-confirmed reconcile through v8 `resolve-execution`, from the stored `response_observations` row only, recorded at the **current** owner generation with no bump. The operator then runs `recover-delivery-lead`. A resolved verifier goes through the existing boundary (f) path.
- **v8 CLI contract (plan engagement, 2026-09-24):**
  - v8 **refuses** `--evidence-file`.
  - v8 **requires** `--expected-generation N`.
  - v8 refuses `resolved_not_dispatched` and `still_unknown` with stable reasons.
  - Today `--evidence-file` is required for every path (`cli/flow.py:604-612`). v5–v7 must keep their behavior, so work out how the parser and the routing handle this.
- **Worktree guard:** v8 chartered only. Prepare and the v8 resolve route refuse a worktree that contains the project's `.flow/` directory.
- **v8 no-dispatch guard:** `regrant_not_dispatched` refuses v8 (C2).
- **Hardening:** `send_lock` opens with `O_NOFOLLOW`, and the MAF-gated tests read `FLOW_MAF_PYTHON`.
- **Manager calls are abandon-only.** No manager resolution record.
- **Lock order:** `recovery_lock`, then `run_lock` (via `delivery_authority_guard`), then `send_lock`, then SQLite.

## Questions the plan must answer

1. **Where the v8 route lives.** `execution_gateway.resolve_attempt` refuses v8 at `:911-913`. Does the route go in `delivery_gateway.py` next to `_resume_chartered`, and how does `flow.py` dispatch to it?
2. **How to resolve a `started` row.** `resolve_unknown` accepts only `unknown`/`allowed` (`execution_ledger.py:1273`) and takes an `evidence` list validated by `validate_recovery_resolution`. What does the v8 evidence list contain (for example `{kind: "flow_response_observation", action_id, result_digest}`)? Does it pass that validator, or does it need a v8-specific ledger method?
3. **Binding at continuation.** Where does eligibility (`delivery_recovery.py:89-96`) learn that a resolved row is unblocked? After `resolved_completed` the row is `completed` with reason `operator_resolved_completed`, so which check enforces "a resolution at a chain generation, for this attempt and action" (parent AC5)? Define the chain as in requirement 4.
4. **Receipt.** Show that `build_recovery_block` (`delivery_recovery.py:~167`) and the validator rule (f) (`execution_contracts.py:~438`) already count the resolution, or say what changes. Show that a resolution at the current generation stays inside the validator's chain (`execution_contracts.py:404-431`); this is risk R1.
5. **Inspection.** Where the `EVIDENCE_NEEDED` text (`delivery_recovery.py:39`) changes to "resolve-execution (stored response)" or "unresolvable; abandon only", and how the refusal points to `inspect-delivery`.
6. **Lead change after resolution.** Confirm that 1b's `lead_change_blocker` clears once the row is `completed`.
7. **Drift after resolution (risk R3).** Confirm that recovery's worktree drift check runs after a resolution.
8. **ADR 0016 amendment text.**

## Evidence inventory

- **Intent:** `.flow/runs/chartered-delivery-recovery-2/requirements.md` (including "Amendments from flow-solution"), `acceptance-criteria.md`, `solution.md`, `research/solution-verify.md`.
- **Parent:** `.flow/runs/chartered-delivery-recovery/research/plan-architecture.md` (the 1a file-level plan, as a format precedent).
- **Code:**
  - `cli/flow.py:604-612`
  - `cli/execution_gateway.py:900-966`
  - `cli/execution_ledger.py`: `resolve_unknown` (:1248), `regrant_not_dispatched` (:1309), `send_lock` (:213), `claim_chartered_recovery` (:~470), `lead_change_blocker`, `_unresolved_action` (:624)
  - `cli/delivery_gateway.py`: `resume_delivery` (:832), `recover_delivery` (:930), `_resume_chartered`, `_recovery_gates`, `prepare_chartered_delivery` (worktree checks :346-353)
  - `cli/delivery_recovery.py`, `cli/delivery_projection.py`, `cli/execution_contracts.py`
- **Tests:** `tests/test_chartered_delivery_recovery.py` (boundary tests, `RecoveryHarness`, `LeadChangeFenceTests`), `tests/test_chartered_delivery_gateway.py`, and the MAF files with hardcoded paths: `test_maf_continuation_supervisor.py:16`, `test_maf_recovery.py:230,260,301`, `test_maf_post_resolution_continuation.py:39`.

Keep it under ~1200 words.
