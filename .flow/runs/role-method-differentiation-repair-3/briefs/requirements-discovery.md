# Definition brief: requirements challenge

## Task

Translate the repair-2 failure into observable requirements for a successor.
Identify candidate product-manager and quality-reviewer behaviors that are absent
from the unchanged contracts, the fixtures needed to expose them, and the edge
cases that prevent a false pass. Recommend whether requirements should target
two new methods or narrow the release. Write only to
`.flow/runs/role-method-differentiation-repair-3/research/requirements-challenge.md`.

## Evidence inventory

### Already exists

- Prior definition and acceptance criteria:
  `.flow/runs/role-method-differentiation/requirements.md` and
  `acceptance-criteria.md`.
- Formal quality and test reviews:
  `.flow/runs/role-method-differentiation/review/acceptance-quality.md` and
  `review/acceptance-test.md`.
- Eight frozen response records, prompts, rubrics, and scores under
  `docs/evidence/role-method-differentiation/repair-2/`.
- Current product-manager and quality-reviewer role bodies and composed corpus
  entries under `scaffolds/default/`.

### Partially covered

- Earlier candidate methods include product reversibility and resolvable success
  metrics, plus quality omission review and evidence-strength labels. They have
  not been evaluated against the unchanged bodies.
- Repair-2 exposed fixture ambiguity and literal-test weaknesses but did not
  define successor corrections.

### Checked and genuinely absent

- No approved successor behavior, primary fixture, counter-case, or stopping rule
  exists.
- No repair-start preservation digest exists for a successor run.

### Search method

The coordinator read all approved and reviewed artifacts, searched the current
role bodies for the candidate concepts, and inspected the machine-readable
criterion-level scorecard and stated evidence gaps.

## Required output

- Separate user-visible outcome from implementation or corpus structure.
- Propose measurable treatment and control conditions with counter-cases.
- Cover missing data, unsupported arithmetic, ordering, negation, and evidence
  preservation edge cases.
- State which questions require targeted research or exploratory trials.
