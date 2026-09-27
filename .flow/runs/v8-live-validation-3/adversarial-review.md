# Adversarial Review: v8-live-validation-3 definition (adversarial-architecture)

Reviewer: `adversarial-architecture` (solution-architect, opus). Read-only, and run against `main` at v0.38.0. Each claim is tagged `observed`, `inferred` or `recommended`.

## Focus answers

1. **Paid calls in a successor.**
   - Base 1 with lineage scope does **not** hard-block a successor's edit. The edit fails `paid_call_cap` with units = 1, which becomes an expansion request (`execution_ledger.py:537-559`, `:1251-1256`). It then pauses for a decision when no headroom is left (`:491-500`). Run 2 attempt 2 showed this live (`v8-live-validation-2/validation-results.md:31-32`). *(observed)*
   - `paid_worker_calls` is a valid headroom key (`delivery_contracts.py:40-46`; `execution_contracts.py:351-357`). 1 + 1 ≤ the ceiling of 6, and paid ≤ delegations (`delivery_contracts.py:117-120`). *(observed)*
   - A successor gets the grant automatically when the predecessor didn't spend the unit (`execution_ledger.py:463-467`). In attempt 1 the unit is almost unreachable, because of `producer_already_completed` (`:543`) and the no-edit fail-fast (`delivery_gateway.py:614`). *(inferred)*
2. **Manager base 4 with headroom 1.**
   - Attempt 1 still gets an automatic grant at call 5 and an escalation at call 6 (`execution_ledger.py:1427-1437`).
   - D4 retries only add counted calls (`delivery_lead.py:187-190`), which can move the events earlier. The hermetic test is `tests/test_maf_progress_retry.py:115-140`.
   - Rounds can't escalate (base 6 = the ceiling). *(observed)*
   - The events are lost when the manager skips review, or with an inspect-only turn. In a successor, the manager headroom has already been spent across the lineage (I1).
3. **What would refuse.**
   - `start-plan` refuses any change to the approved intent, requirements or acceptance criteria (`runstate.py:495-508`, `delivery_control.py:133-136`).
   - Prepare refuses on digests, a roster larger than the base, a dirty worktree including untracked files, the HEAD, or a sibling that is still `started` (`delivery_gateway.py:380-438`).
   - Abandon and successor are mechanically sound, and the reused worktree passes the `.flow` identity check. *(observed)*

## Findings

| # | Severity | Finding | Recommended disposition |
|---|---|---|---|
| C1 | Critical | The recommended `paid_worker_calls` headroom is not in `shaper-intent.json` and is deferred to the plan. But the intent is frozen at approve-definition, and start-plan refuses any change. | Decide Change 5 in the definition. If accepted, add it to the intent before approval. Close both open questions. |
| I1 | Important | Headroom is spent across the lineage, so the "call 5 automatic" expectation can't also hold in a successor. | Scope R4's call numbers to attempt 1. In a successor, AC4 is met by any automatic grant. State the budget as lineage totals. |
| I2 | Important | The verifier ceiling of 2 is lineage-wide, so a successor may be unable to verify at all. | Allow a successor only while the lineage has a verifier send left, checked from `inspect-delivery`. A successor has no verifier retry. |
| I3 | Important | Change 5's premise is wrong: a successor's edit escalates rather than being impossible. | Restate it as option (a), headroom 1 with an automatic grant, versus option (b), headroom 0 with an escalation, and state the tradeoff: with (a), no one reads the editor task before the paid send. |
| I4 | Important | R6 and AC10 omit a successor after `failed`, and keep "retuned limits", which is impossible after sealing. Supersede has no CLI, and a superseded attempt has no receipt digest. | A successor follows any terminal predecessor, under the same sealed limits, on a reset worktree. Supersede is a Python fallback, recorded as a gap. |
| I5 | Important | AC8 has no outcome for a model-behaviour failure that Flow caught. | Add a "`failed` by manager or producer model behaviour" outcome. |
| I6 | Important | AC8 and AC12 call a worker limit a Flow defect, but the known risks accept adapter timeouts. | "Worker limit" means D1-class caps. The 120/300/60 s timeouts are an environmental or model-latency outcome. |
| I7 | Important | D4 and D5 are on the planned path but missing from AC12. | Add D4 (`manager_progress`, no failure on one malformed reply) and D5 (recover after a `charter_headroom` grant). |
| I8 | Important | AC12's D7 bullet mixes a model-behaviour check with a Flow fix. | Check that the facts line appears in the manager request, and check the D6 reason text. Record the delegation text as an observation. |
| S1 | Suggestion | "Owner generation goes up" is ambiguous. | The ledger attempt `owner_generation` becomes N+1; the lead claim is unchanged. |
| S2 | Suggestion | `stuck` is project-wide. | Scope the check to this work id. |
| S3 | Suggestion | The reset before a successor isn't spelled out. | Save the diff, run `reset --hard d6d771f2` and `clean -fd`, then confirm porcelain is empty including untracked files. |
| S4 | Suggestion | The AC2 headroom check is vague. | Compare `envelope["expansion_headroom"]` with the exact map. |
| S5 | Suggestion | A paid unit can be spent inside attempt 1 (a `not_dispatched` edit, then a re-proposal). | Record it; it is not a defect. |
| S6 | Suggestion | AC6 doesn't say whether the paused call was a D4 retry. | Record it. |

## Confirmed
- The note that delegations and verifier units cover a verifier retry, not a second edit.
- The facts text in v0.38.0 (`delivery_gateway.py:1377-1380`).
- The 600 s deadline route.
- The abandon, then successor, route.
- The current intent passes `validate_shaper_intent`, both as it is and with `paid_worker_calls: 1` added.
