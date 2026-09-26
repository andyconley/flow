# Review: manager-progress-retry

- **Date:** 2026-09-26.
- **Lane:** `flow-review`.
- **Reviewers** (both read-only, and distinct from the producer, which was the coordinator):
  - quality-reviewer (acceptance pass);
  - test-engineer (acceptance pass; expertise lookup `no_match`).
- **Compared against:** `requirements.md` (R1–R7), `acceptance-criteria.md` (AC1–AC9), `plan.md`, `adversarial-review.md` (A1–A7), `implementation-review.md`, `validation-results.md` and ADR 0018.

## Verdict

**Ready to accept and archive.** The quality review approved: every earlier "Fixed" item is present in the code, there is no scope drift beyond D4 and the approved D5, and the D5 condition only narrows an existing guard. The test review found AC1–AC3 and AC5–AC9 proven, and AC4 partly proven (R2 below).

## Findings and dispositions

| ID | Source | Sev | Finding | Disposition |
|---|---|---|---|---|
| R1 | quality | Suggestion, **raised to a fix** | A deeply nested reply within the 32 KB cap makes `json.loads` raise `RecursionError`. That escaped classification inside `observe_manager_response`, so the gateway would mark a completed paid call `unknown`, an unrecoverable uncertain send. **Reproduced**: a 30,007-byte reply raised it | **Fixed** (`54c271a`). The parser treats it as unparsable, and the `deeply_nested` corpus case and parity test cover it. Mutation (dropping the guard): caught |
| R2 | test | Important | AC4's clause "a retry past the runner ceiling is a hard denial" isn't tested for a retry specifically | **Accepted as residual risk.** Every manager call, retry or not, passes the same ceiling check at the top of `ManagerProxy.run` (`delivery_lead.py`, `manager_call > MAX_MANAGER_CALLS`), and the ledger's ceiling denial is generic ADR 0017 behaviour with existing tests. AC4 is recorded as **partly met** for this clause |
| R3 | quality | Suggestion | `_validate_manager_progress` ran before `manager_calls` was type-checked | **Fixed.** It now runs after the manager-call loop |
| R4 | test and quality | Suggestion | The OR-guard in `test_repair_doubles_only_invalid_backslashes` never asserted that the valid case isn't repaired | **Fixed.** `assertEqual(parsed.repaired, name != ...)` |
| R5 | test | Suggestion | The protocol-guard test calls the private `_validate_manager_progress` | **Kept.** It's needed, because the public path fails earlier for an unrelated reason, and it's documented in the test |
| R6 | quality | Suggestion | A retry call that is itself paused for expansion, then recovered, isn't tested | **Residual risk.** Replay derives the streak from the recorded sentinel-triggering text, deterministically (R4 of the requirements). The closest proof is `ReplayThroughRetryTests` (a retry granted from headroom, replayed through recovery) |

## Requirement fit

- **R1–R3 (repair, bounded retry, parser parity):** implemented as specified, including the architect's A1, where the 3rd unparsable reply aborts rather than letting MAF replan.
- **R4 (replay):** proven by `ReplayThroughRetryTests` and the D5 regression.
- **R5 (evidence):** the receipt block is recomputed from the rows, and the event shares the observation's transaction.
- **R6:** progress phase only.
- **R7:** ADR 0018.
- **D5:** included with your approval, because it was found by this run's tests, reproduced on unchanged `main`, and sits on the live run's critical path.

## Validation fit

- **Hermetic and MAF-gated tests** on the pinned MAF.
- **Mutation checks:** 11 of 11 caught. That's 10 from implementation plus the `RecursionError` guard.
- **Full suite:** see the addendum in `validation-results.md`.
- **Live proof:** still to come, from `v8-live-validation-2` attempt 2 after the v0.37.0 release.

## Residual risks

- R2 and R6 above.
- Parser parity is pinned to `agent_framework_orchestrations==1.2.0`, so `tests/test_progress_parse.py` must pass on every MAF pin change.
- Flow changes provider text in exactly one bounded way (doubling an invalid backslash). The raw text stays the recorded observation.
