# Adversarial Review: chunk 2 definition

- **Work item:** `chartered-delivery-recovery-2`
- **Reviewer roles:**
  - `adversarial-product` (product-manager)
  - `adversarial-requirements` (business-analyst)
  - `adversarial-architecture` (solution-architect)
  - `adversarial-security` (security-reviewer)

  All four were read-only and ran concurrently against the first draft.
- **Status:** dispositioned. Engineer decisions C1–C3 were taken on 2026-09-24.
- **Advisory expertise:**
  - The business-analyst received one entry, "Reframe a product request as the job behind it" (request `19e1991d…`). Its disposition is `ignored/trigger_absent`, and the post-receipt is recorded.
  - An earlier request, `4e08b288…`, was never delivered and stays a pre-only receipt, reported as `not_observed`.
  - The other three roles take no expertise query.

## Evidence inventory

- **Already exists:** see `briefs/adversarial-review.md`. It lists the parent intent, ADRs 0012 and 0016, the 1b archive, and the code anchors for `resolve_attempt`, `resolve_unknown`, `regrant_not_dispatched`, `observe_*`, `claim_chartered_recovery`, and `send_lock`.
- **Checked at source by the orchestrator:**
  - ADR 0012 lines 11 and 15 (narrative claims are rejected; a lost response may stay blocked);
  - `execution_ledger.py:495-498` (the chartered claim refuses unresolved rows);
  - `verifier_contracts.py:157-175, 243` (evaluation computes its own bindings; the verifier shape check is shape only);
  - `execution_contracts.py:686-692` (evidence level must be Flow-observed).
- **How searched:** grep and reads by the orchestrator and each reviewer. The architecture review re-verified the draft's line anchors, which were slightly off.

## Findings and dispositions

| Source | Finding | Disposition |
|---|---|---|
| Architecture 3 (critical) | Operator response import contradicts ADR 0012. | **Requirement changed (C1):** Flow-owned evidence only; import is a non-goal. |
| Security C1 (critical) | An imported verifier `pass` can be forged onto any verifier action. | **Moot under C1.** Recorded as the precondition for any future import decision. |
| Security I1, I2, I3, I4 | Import records a false evidence level; an interrupted import could auto-complete; TOCTOU; replay. | **Moot under C1** for import. I2's atomicity point is kept for manager calls (requirement 3, AC4). |
| Architecture 1 (critical) | The chunk 1 CAS refuses unresolved rows; a v5-style bump breaks the v8 chain. | **Requirement changed:** requirement 1 states the fence invariant and chain continuity, and the mechanism goes to `flow-solution` (Q4). AC3 adds the `started`-row and chain-continuity checks. |
| Architecture 2 (critical) | v8 `resolved_not_dispatched` is unreachable, so AC8 tests an empty set. | **Requirement changed (C2):** guard it, don't build it; AC8's no-dispatch half is deferred with Q1. |
| Architecture 4 | Manager observe and resolve ordering conflict. | **Requirement changed:** atomic observation and resolution (requirement 3, AC4; Q5). |
| Architecture 5 | The receipt counts only action resolutions. | **AC changed:** requirement 9 and AC8 count manager calls too. |
| Architecture 6 | The "another attempt" subtest needs tampering. | **AC changed:** it uses an injected ledger row (AC2). |
| Architecture 7 | The A3 index. | **Assumption confirmed**, with a duplicate check. |
| BA F1 (critical) | The manager-call data path is undefined. | **Requirement changed:** a new append-only record with a unique key, kind-and-id binding (requirements 3 and 4, as architecture recommends); storage goes to Q5. |
| BA F2 | The problem statement overstated what is resolvable. | **Requirement changed:** the Problem section states what stays blocked. |
| BA F3 | Import provenance is untestable. | **Moot under C1.** |
| BA F4 | "Recovers explicitly" is unnamed. | **AC changed:** the operator sequence is named. |
| BA F5 | The refusal should point to inspection. | **Requirement changed:** requirement 10 and AC9. |
| Product F1 (critical) | Split observation-backed reconcile out. | **Rejected, with rationale:** under C1, reconcile is the ADR-compatible core of the chunk (architecture 3). Its operator-confirmed default needs no ADR change, and the choice is left to `flow-solution` (Q3). |
| Product F2 | Move the hardening items to a prerequisite PR. | **Rejected by the engineer (C3):** they stay in chunk 2. |
| Product F3 | The non-goals are honest. | Kept. |
| Product | Success criteria were missing. | **Added.** |
| Security (actor) | The actor is unauthenticated. | **Non-goal clarified**, and assumption A4 added. |
| Security S1 | Key resolutions by item kind. | **Requirement changed** (requirement 4). |
| Security S2 | The CAS should use a caller-supplied generation. | **Requirement changed** (requirement 1). |
| Security S3 | An orphaned provider child. | **Open for `flow-solution`**, under the "live run" detection in requirement 1. |

## Open questions

- **Q1:** closed. It stays impossible in chunk 2 (all four reviews agree).
- **Q2:** moot under C1.
- **Q3:** reconcile mode, for `flow-solution`.

## Approval impact

- **Requirement changes:** requirements 1–11 were rewritten. Import was removed, and the manager record, binding definition, no-dispatch guard, and inspection guidance were added.
- **Acceptance criteria changes:** the operator sequence was named; AC1 gained the unresolvable variants; AC2 gained the injected-row and generation subtests; AC3 gained the `started` and chain checks; AC4 (manager atomicity) and AC6 (guard) are new; AC8 was narrowed.
- **Non-goal changes:** operator import, ADR 0012 changes, the v8 no-dispatch regrant, and operator authentication.
- **Assumption changes:** A2 and A3 confirmed; A4 and A5 added.
- **Next-lane impact:** `flow-solution` (unanimous), for Q3–Q5, S3, and A4–A5.
