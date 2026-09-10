# Acceptance review brief: test engineer

## Task

Audit whether the implementation and evidence can detect the failures named by
the approved acceptance criteria. Check the deterministic tests, mutation
record, frozen treatment/control design, raw hashes, delivery logs, and declared
manual boundary. Write the result only to
`.flow/runs/role-method-differentiation/review/acceptance-test.md`.

## Evidence inventory

### Already exists

- Acceptance criteria:
  `.flow/runs/role-method-differentiation/acceptance-criteria.md:3-31`.
- Validation design and required stopping rule:
  `.flow/runs/role-method-differentiation/validation-plan.md` and
  `docs/evidence/role-method-differentiation/repair-2/manifest.json`.
- Literal role/corpus/manifest/render assertions:
  `tests/test_expertise_composition.py:47-179`.
- A targeted product instruction mutation record:
  `docs/evidence/role-method-differentiation/repair-2/mutation-check.md`.
- Frozen prompt and rubric files, eight raw response envelopes, execution
  metadata, and criterion scores in `repair-2/`.
- Final execution logs under
  `.flow/runs/role-method-differentiation/research/repair-2/`, including focused
  and full suites, adapter checks, runtime smoke, doctor, and whitespace.
- Current validation summary:
  `.flow/runs/role-method-differentiation/validation-results.md:10-65`.

### Partially covered

- The mutation check directly exercises the product executable boundary; the
  quality boundary is protected by a literal assertion but was not separately
  mutated.
- Static smoke proves generated surfaces and policy metadata; the four declared
  live-client checks remain manual.

### Checked and genuinely absent

- No behavioral output satisfies the full product primary treatment rubric.
- No behavioral output satisfies the quality primary ordering rubric.
- No unchanged-body control misses every distinctive primary item.
- No repair-start lead-developer digest exists.

### Search method

The root reviewer enumerated the tracked and untracked change surface, read the
test module and frozen designs, parsed every JSON record, recomputed the manifest
and record hashes, compared current treatment-source hashes to the manifest, and
ran focused/full suites plus adapter, smoke, doctor, and whitespace checks.

## Review requirements

- Identify vacuous or missing proof, if any, with a concrete wrong
  implementation that could still pass.
- Verify the machine-readable score follows the frozen formula.
- Distinguish test pass from product acceptance and state which criteria block.
- State whether evidence supports `accept-review`.
