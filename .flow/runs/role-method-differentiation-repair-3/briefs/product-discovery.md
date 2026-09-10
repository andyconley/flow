# Definition brief: product challenge

## Task

Decide whether a third attempt to differentiate product-manager and
quality-reviewer expertise is worth doing now, or whether the five-role claim
should narrow to the three roles with demonstrated behavior. Compare the likely
value, delay cost, duration, reversibility, and evidence burden of those paths.
Recommend one path and write only to
`.flow/runs/role-method-differentiation-repair-3/research/product-challenge.md`.

## Evidence inventory

### Already exists

- Approved repair-2 outcome and release relationship:
  `.flow/runs/role-method-differentiation/requirements.md`.
- Formal failed verdict and criterion dispositions:
  `.flow/runs/role-method-differentiation/review.md`.
- Frozen criterion scores:
  `docs/evidence/role-method-differentiation/repair-2/results.json`.
- Current role contracts:
  `scaffolds/default/agents/product-manager.md` and
  `scaffolds/default/agents/quality-reviewer.md`.
- Prior candidate methods appear in the engineer's supplied source analysis and
  are summarized in the prior run's research and handoff artifacts.

### Partially covered

- Three roles have prior passing differentiation evidence; the combined
  five-role value has never been demonstrated.
- Candidate PM and QR methods have conceptual source support but have not been
  screened for behavioral distinctiveness against the current controls.

### Checked and genuinely absent

- No repair-2 pass exists for either role.
- No evidence currently establishes that another attempt is more valuable than
  releasing or documenting the three-role subset.

### Search method

The coordinator read the approved repair, formal review, scorecard, current role
bodies, prior evidence tree, run inventory, and the unavailable archive-search
result. Exact failed criteria and control successes were extracted from
`results.json`.

## Required output

- State the urgency/decay shape for each path.
- Classify reversibility.
- Recommend proceed, narrow, or defer with explicit tradeoffs and success/failure
  conditions.
- Name assumptions and questions that requirements must resolve.
