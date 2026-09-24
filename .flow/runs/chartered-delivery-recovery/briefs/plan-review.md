# Brief: plan review (business-analyst, product-manager)

Run `chartered-delivery-recovery`, lane `plan`. The work is read-only except for your own output file. Base: `main` at `9436527`.

Review the draft plan `.flow/runs/chartered-delivery-recovery/plan.md` against the approved `requirements.md`, `acceptance-criteria.md`, and `solution.md`.

## Evidence inventory (exists today)

- `.flow/runs/chartered-delivery-recovery/`:
  - `requirements.md` and `acceptance-criteria.md`, both approved;
  - `solution.md`, accepted;
  - `plan.md`, the draft;
  - `research/plan-architecture.md`, the design with code anchors;
  - `research/plan-validation.md`, the map from criteria to tests;
  - `research/solution-options.md` and `research/solution-data.md`.

## business-analyst

- Trace every acceptance criterion (AC1–AC12), and every AC4 boundary, to:
  - a chunk;
  - a commit in the plan's sequence;
  - at least one named test.
- Flag any criterion that is untested, covered only in part, or split between chunks without saying so.
- Flag any requirement that the plan silently changes. For example, the "No runtime work is needed" assumption and the four new findings.
- Check that the operator-facing states and refusal reasons are complete and unambiguous.

Output: `research/plan-review-ba.md`.

## product-manager

- Challenge the scope and slicing:
  - Is chunk 1 (15 commits) the right size for one PR, or should it split? This is decision P5.
  - Does each chunk leave `main` in a shippable, honest state? For example, between chunk 1 and chunk 2, v8 uncertain sends stay blocked and visible.
  - Is anything in scope that could be deferred without breaking an acceptance criterion?
- Give a recommendation on each of the engineer decisions P1–P5.

Output: `research/plan-review-pm.md`.

## Format

- Findings ranked Critical, Important, or Suggestion, each with evidence (`file:line` or artifact section) and a proposed disposition.
- Mark each claim observed, inferred, recommended, or unverified.
- Return a summary of 8 lines or fewer, plus the path.
