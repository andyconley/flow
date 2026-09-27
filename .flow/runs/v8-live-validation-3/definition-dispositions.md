# Definition Dispositions: v8-live-validation-3

These are the dispositions for the findings in `adversarial-review.md` (adversarial-architecture, 2026-09-27).

| # | Disposition |
|---|---|
| C1 | **Requirement changed.** Andy decided option (a) on 2026-09-27. `shaper-intent.json` now seals `expansion_headroom.paid_worker_calls: 1`, set before approve-definition; it validates. Both open questions are closed. |
| I1 | **Requirement and AC changed.** R4's call numbers apply to the first attempt. In a successor, AC4 is met by any `charter_headroom` grant. The budget is stated as lineage totals. |
| I2 | **Requirement changed.** R6 adds a verifier precondition, checked from `inspect-delivery` before a successor launches, and notes that a successor has no verifier retry. |
| I3 | **Requirement changed.** Change 5 is restated: a successor's edit becomes an expansion request, granted automatically under headroom 1. The accepted tradeoff and the `not_dispatched` edge case (S5) are recorded. |
| I4 | **Requirement and AC changed.** A successor follows any terminal predecessor under the same sealed limits. "Retuned limits" is removed. Supersede is a Python fallback, recorded as a gap. |
| I5 | **AC changed.** AC8 adds the outcome "`failed` by manager or producer model behaviour, where Flow's check held". |
| I6 | **AC and requirement clarified.** "Worker limit" means a D1-class cap. The adapter timeouts are an accepted environmental or model-latency outcome. |
| I7 | **AC and requirement changed.** Change 6 and AC12 now cover D4 and D5. |
| I8 | **AC changed.** D7 is checked by the facts line in the ledger's manager request. The delegation text is recorded as an observation only. D6 is checked by its reason text. |
| S1 | **AC changed.** AC13 names the ledger attempt `owner_generation` and says the lead claim is unchanged. |
| S2 | **AC changed.** The `stuck` checks are scoped to this work id. |
| S3 | **Requirement changed.** The reset steps before a successor are spelled out. |
| S4 | **AC changed.** AC2 gives the exact `expansion_headroom` map. |
| S5 | **Folded into Change 5.** |
| S6 | **AC changed.** AC6 records whether the paused call was a D4 retry. |
