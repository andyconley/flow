# Lead-developer brief: two-role method repair

Inspect the approved repair before product edits. Compare the current working
tree, exact `HEAD` role bodies, requirements, acceptance criteria, and earlier
failed evidence. Identify the smallest coherent file-level change, hidden
coupling, and preservation hazards. Do not edit production files. Write only
`.flow/runs/role-method-differentiation/research/implementation-lead-repair.md`.

## Evidence inventory

- Approved repair: `requirements.md`, `acceptance-criteria.md`, `plan.md`.
- Current role bodies: `scaffolds/default/agents/product-manager.md`,
  `quality-reviewer.md`, and `lead-developer.md`.
- Corpora and joins: `scaffolds/default/expertise/*.jsonld` and
  `scaffolds/default/expertise/competencies.md`.
- Existing tests: `tests/test_expertise_composition.py`.
- Failed and passing history: `docs/evidence/agent-expertise-expansion/` and
  `docs/evidence/role-method-differentiation/`.
- Search method: inspect `git diff`, compare each affected file with
  `git show HEAD:<path>`, and search ids/names with `rg`.
