# Implementation Review: manager-progress-retry

- **Reviewers:** quality-reviewer and test-engineer, both read-only, 2026-09-26. The test-engineer's expertise lookup returned `no_match`.
- **Verdicts:** the quality review requested changes (two Important issues). The test review found coverage gaps. Every finding is dispositioned below. The fixes are in commit `b377351`, except T5.

| ID | Source | Sev | Finding | Disposition |
|---|---|---|---|---|
| Q1 | quality | Important | The runner treated a reply as unparsable when MAF couldn't re-read the canonical text, but Flow's `classify` didn't. So for an escaped fence inside a string, the runner would retry while the ledger and receipt recorded nothing | **Fixed.** `parse_progress` now runs the round-trip check itself, with stdlib copies of MAF's rules, so both sides share one decision. The MAF-import check stays in the runner as a parity guard. Test: `escaped_fence_in_string` in the corpus and the parity test |
| Q2 | quality | Important | `progress["next_speaker"]["reason"]` could raise a `KeyError` inside MAF's `except Exception`, which MAF would silently retry, then replan | **Fixed.** Uses `.get("reason")`, so the existing bounded-rationale check raises `PolicyAbort`. Test: `test_progress_without_a_speaker_reason_aborts_without_retry_or_replan` |
| Q3 | quality | Suggestion | A non-dict manager call in a receipt raised an `AttributeError` | **Fixed.** It's now a `ContractError` |
| Q4 | quality | Suggestion | Name the "call 3" constant | **Not changed.** That line predates this change, and a comment already explains it |
| Q5 | quality | Suggestion | A stripped post-ADR receipt passes a standalone validation | **Documented** in ADR 0018. The seal catches it, and a sealed file is protected by `sealed_receipt_sha256` |
| T1 | test | Critical | The A3 shape rule was tested only at the unit level | **Fixed.** `test_progress_missing_a_ledger_item_is_retried_like_unparsable` runs through the runner |
| T2 | test | Critical | The protocol-below-8 tamper case failed on an earlier, unrelated check | **Fixed.** The test calls `_validate_manager_progress` directly and asserts the "requires protocol v8" message. Mutation M10 is now caught |
| T3 | test | Important | Nothing proved the event shares the observation's transaction | **Fixed.** `test_progress_diagnostic_event_commits_with_the_observation`: a classifier failure leaves the call `started`, with no observation event |
| T4 | test | Important | AC9's design-doc reference was reported missing | **Rejected, with evidence.** `docs/maf-adoption-design.md:24` references ADR 0018 |
| T5 | test | Suggestion | A progress retry that is itself denied at the runner ceiling isn't tested | **Deferred.** The ceiling denial is generic to manager calls (ADR 0017 tests). Recorded as residual risk |
| — | mutation | — | M7 survived (a valid `\\` pair dropped from the scan) because the repair only runs on broken replies | **Fixed.** `test_repair_keeps_valid_pairs_in_a_reply_that_needs_repair`. M7 is now caught |
| — | suite | — | The release-staging sibling list lacked `runner_progress` | **Fixed.** It was added to the list in `tests/test_flow.py`. The module is covered, because `execution_contracts` and `execution_ledger` import it |
