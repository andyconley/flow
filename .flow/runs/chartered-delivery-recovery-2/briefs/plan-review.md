# Brief: plan review, chunk 2

Run `chartered-delivery-recovery-2`, lane `plan`. Read-only; return findings inline.

## Task

Review `plan.md`, `validation-plan.md`, and `implementation-handoff.md` against the approved `requirements.md` (including its amendments) and `acceptance-criteria.md`. The question: could another agent implement chunk 2 from these files alone, and does every requirement and AC have a planned change and a named proof?

- **business-analyst:**
  - Map each requirement and AC to a plan change and a named test. Report any gap, any AC that the planned test doesn't actually observe, and any contradiction between the files.
  - Check that the operator's three-command workflow is fully specified: what they see, the value to pass, and the refusals.
- **product-manager:**
  - Scope discipline: anything planned beyond the approved scope, or approved scope missing.
  - Whether the 11-commit, two-group sequence stays reviewable and independently green.
  - Whether the out-of-scope list and the risks are honest.

## Evidence inventory

- **Intent:** `.flow/runs/chartered-delivery-recovery-2/requirements.md` (C1–C3, amendments), `acceptance-criteria.md`, `solution.md`, `adversarial-review.md`.
- **Plan:** `plan.md` (P1–P4, contracts, commits, risks), `validation-plan.md` (AC map, M1–M4), `implementation-handoff.md`.
- **Evidence:** `research/plan-architecture.md` and `research/solution-verify.md`, both carrying code anchors.
- **Code**, if you need to check an anchor: `cli/flow.py:604-612`, `cli/delivery_gateway.py`, `cli/execution_ledger.py`, `cli/delivery_recovery.py`, `tests/test_chartered_delivery_recovery.py`.

## Output

Findings ranked critical, important, or suggestion, each with the file and section and a proposed fix. Then a verdict: ready to approve, or needs changes. Keep it under ~500 words.
