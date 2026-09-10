# Quality-reviewer brief: two-role method repair

Review the final diff and evidence against every acceptance criterion. Derive
the expected artifact list before reading changed lines, distinguish observed,
read, and author-asserted proof, and test an alternative explanation before any
Critical finding. Write only `.flow/runs/role-method-differentiation/review/quality-repair.md`.

## Evidence inventory

- Approved contract: `requirements.md`, `acceptance-criteria.md`, `plan.md`.
- Expected product files: two role bodies, two JSON-LD corpora, competency
  vocabulary, deterministic test, evidence/readme/result updates, final
  validation results and handoff.
- Preserved product: lead-developer role/corpus and prior passing evidence.
- Proof locations: `docs/evidence/role-method-differentiation/repair-2/`,
  `validation-results.md`, and focused/full command outputs cited there.
- Search method: inspect `git diff --name-status`, use `rg` for replacement and
  superseded ids, parse every new JSON record, and compare all criteria to the
  evidence inventory.
