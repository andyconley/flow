# Plan Review: shaper-expansion-approval

- **Reviewers:** architect (architecture) and test-engineer (validation). Both were read-only and ran in parallel on 2026-09-25.
- **Expertise briefs:** `no_match` for both roles, so no advisory entries were attached.
- **Orchestrator spot-checks:** A1 (`cli/maf_supervisor.py:473-489`), A2 (`delivery_gateway.py:1351-1354`, `delivery_lead.py:203-204`), A3 (`execution_ledger.py:758-771`, `:880-904`) and A4 (`:718-727` per attempt against `:751-755` lineage) were confirmed against the code.

## Architecture findings

| ID | Sev | Disposition |
|---|---|---|
| A1 | blocking | **Accepted.** In C1, the v8 supervisor guards are bounded by the `runner_limits` ceilings, not base + 1. Regression test in C7. |
| A2 | blocking | **Resolved by E5 (a).** A denied manager call has no text to return, so AC7 "deny, resume, complete" can't be met for manager-kind denials. |
| A3 | major | **Accepted.** `decide` and `decide_manager_call` evaluate every predicate. Expansion applies only when no hard predicate fails. The request carries the set of failing expandable limits, amount 1 each, and headroom must cover all of them. Keying stays one request per denied row. |
| A4 | major | **Resolved by E6 (a).** This refines E3 and AC8, matching grant scope to counter scope. |
| A5 | major | **Accepted.** `_v8_limit_reason` (`:573-605`), `:1170` and the receipt checks (`execution_contracts.py:378-379`, `:901`, `:971-974`) all go through `_effective_limit`: the ledger readers in C2, the receipt readers in C6. |
| A6 | major | **Accepted.** The pending request row written in the denial transaction *is* the pause marker; there is no separate pause table. `bind_magentic_checkpoint` accepts a denied row only when it has a pending expansion request. `claim_chartered_recovery` accepts `restart` and skips the `unmarked_process_exit` write for expansion pauses. A worker pause that was never bound (a crash window) refuses with `reconciliation_required`. |
| A7 | major | **Accepted.** A manager pause that comes after a worker denial resumes in `answer` mode with the recorded denial reply. Restart is allowed only when the attempt has zero action rows. |
| A8 | major | **Accepted,** as a wording correction to AC6 that doesn't change its intent. The row changes status from `denied` to `allowed` with reason `expansion_granted`. The original denial stays in events and the request row. Receipt validation accepts that reason only with a matching consumed grant. |
| A9 | major | **Accepted.** The ledger keeps `reason=<limit>` and adds `expansion: {request_id, status}`, so C2 keeps the suite green, and the gateway starts acting on it in C3. |
| A10 | minor | **Accepted.** `recovery_lock` gains a `decide` holder with its own refusal reason. |
| A11 | minor | **Accepted.** A top-level envelope key `expansion_headroom`, projected at prepare from the canonical charter. `validate_envelope` and `validate_delivery_charter` are updated. A consistency rule is added: paid headroom ≤ delegation headroom when paid base ≤ delegations base. |
| A12 | minor | **Accepted.** Cancelling pending requests on supersede or release (inside `seal_superseded_attempts`) moves into C4. |

## Validation findings

| ID | Sev | Disposition |
|---|---|---|
| T1 | major | **Accepted.** The AC10 tests use the `threading.Barrier(2)` + `ThreadPoolExecutor` pattern from `tests/test_structured_verifier_ledger.py:131-137`, with no sleep-based ordering. |
| T2 | blocking | **Accepted, as a clarification.** Inline automatic approval (a solution amendment) makes request plus grant one transaction. The AC4 crash test injects a failure before commit (both roll back, and a rerun records one request and one grant), then replays after commit (the same request, no second draw). The oracle is the grant count and headroom remaining. |
| T3 | major | **Accepted.** The M1 test asserts that the result is `expansion` with status `pending` (and the gateway reports `expansion_paused`) when headroom is 0 and the effective limit is below the ceiling, so a ceiling refusal can't hide the mutation. |
| T4 | minor | **Accepted.** Each AC9 tamper case gets its own test. |
| T5 | minor | **Accepted.** v5, v6 and v7 attempts that hit `delegation_cap` and `paid_call_cap` still produce the legacy denial shape and no request row. |
| T6 | minor | **Accepted.** The end-to-end cases name the fixture parameter `shaper_intent(limits=…, expansion_headroom=…)`. Spike scenarios S2, S2b and S3 become pinned tests in `test_maf_expansion.py`. |

## Engineer decisions (2026-09-25: E5 (a), E6 (a))

- **E5, a denied manager call.** Recommended: a manager deny seals the attempt `failed`, with reason = the limit, using the existing seal mode, and AC7 applies to worker denials only. The alternative, Flow inventing manager text, would put Flow-authored words in the manager's mouth and contradicts ADR 0012.
- **E6, grant scope follows counter scope.**
  - Recommended: headroom stays one lineage-wide pool, so supersede never refills it (E3 still holds). A consumed grant raises the limit only for the counter it applies to:
    - across the lineage, for paid and verifier calls;
    - for its own attempt, for delegations, manager calls and rounds, since a successor's per-attempt counters restart at the base anyway.
  - Unconsumed approved grants on a superseded attempt become `lapsed`.
  - AC8's line "a successor inherits the lineage's grants" is refined to "inherits remaining headroom and the lineage-counter grants".
