# Formal acceptance test brief

## Objective

Independently assess whether the proof can detect a wrong narrowed release and
whether acceptance criteria 1-10 are supported for candidate `T`
`4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`.
Do not edit production, evidence, or lifecycle files.

## Evidence inventory

- Observable criteria and commands exist in `acceptance-criteria.md` and
  `validation-plan.md`.
- The focused suite is `tests/test_expertise_composition.py`; the recorded
  final runs are 49 focused tests and 996 repository tests.
- The start/final validators and receipts are
  `verify_frozen.py`, `evidence/preimplementation-verification.json`, and
  `evidence/final-receipt.json`. The latest receipt reports 250 checks.
- Three negative-test receipts and their raw logs exist under
  `evidence/mutations/` and `evidence/logs/mutation-*.log`.
- Exact command/log provenance exists in `evidence/logs/receipt.json`; current
  claim evidence is `evidence/logs/current-claim-search.log`.
- Candidate Claude/Codex evidence exists in
  `evidence/live-client-records.json` and `evidence/live/`.
- Post-release `R` checks are intentionally absent because formal acceptance
  precedes commit and release; they cannot support pre-release acceptance.

The inventory was built from the validation plan, filesystem listing, command
receipt, and final verifier. Verify paths, hashes, and non-vacuous oracles
directly before relying on it.

## Review instructions

Read the implementation and test code as well as the original plan and
criteria. Re-run bounded checks where useful. Confirm the three mutations
actually fail the named guards and were restored. Distinguish observed, read,
and asserted proof. Flag omissions as findings. Judge the doctor variance and
native-client transfer explicitly.

## Output

Write only `review/formal-test.md` under this run. Give a criterion-by-criterion
result, prioritized gaps, evidence strength, and an explicit acceptance
recommendation.
