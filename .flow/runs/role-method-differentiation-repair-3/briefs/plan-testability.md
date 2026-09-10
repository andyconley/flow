# Planning brief: release proof

## Role

Act as Flow's test-engineer. Specify proof that detects both incorrect narrowing
and incomplete delivery.

## Inputs

- `requirements.md`
- `acceptance-criteria.md`
- all three files under `evidence/`
- the prior formal review and repair-2 results

## Questions to answer

1. What deterministic checks prove the exact six-role set, inactive PM/QR
   composition, retained joins/rendering, and immutable historical evidence?
2. How should the two separate restored mutations be run and recorded?
3. What exact Claude and Codex live-client observations are required for
   `test-engineer`, including expected method, model, and effort?
4. What evidence proves commit, merge, semantic release, remote tag/release,
   develop-install refresh, and final live state?

Write the result to `research/plan-testability.md`. Do not edit production files
or protected evidence.
