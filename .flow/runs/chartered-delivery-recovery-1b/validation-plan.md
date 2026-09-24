# Validation Plan: chunk 1b

- **New tests** (in `tests/test_chartered_delivery_recovery.py` unless noted):
  - `test_lead_resume_or_supersede_seals_the_old_attempt_as_superseded` (AC9.2; no-`unknown` fixture per E2; asserts released grant, event, `attempt_terminal` on recovery, and a v7 `started` row untouched);
  - `test_lead_resume_or_supersede_is_refused_while_any_action_is_unknown` (AC9.3; full before/after of `run.json`, claim files and ledger snapshot);
  - `test_lead_change_fails_closed_on_an_unreadable_ledger` and `test_lead_change_refuses_attempt_running_while_a_live_run_holds_the_lock` (AC9.3);
  - `test_abandonment_succeeds_while_actions_are_unknown` (AC9.4: `release` and lifecycle `block`);
  - `test_successor_envelope_lists_predecessors_and_create_attempt_requires_the_exact_lineage` (drop/add/alter subtests), `test_prepare_refuses_while_a_sibling_attempt_is_started`, and a first-attempt byte-identity check;
  - `test_successor_paid_and_verifier_limits_count_predecessor_sends` and `test_successor_first_verifier_is_not_a_retry`;
  - receipt `lineage_usage` tamper subtests (`tests/test_chartered_execution_contract.py` or the gateway suite) and a validator test that a same-generation predecessor is accepted (E4).
- **Changed tests:** AC9.1 fixture bumps `run.json` directly; `test_v7_supersede_after_preparation_blocks_worker_and_receipt_seal` must still show zero worker calls.
- **Commands:** focused suites; `python3.12 -m unittest discover -s tests` (baseline 1426, 0 skipped); MAF-gated `tests.test_maf_delivery_lead` with the pinned interpreter; `git diff --check`.
- **Mutation checks:** remove the ledger guard → AC9.3 test fails; drop `_lineage_usage` from `decide` → lineage-limit test fails. Restore after each.
- **Hermetic only;** no live providers.
