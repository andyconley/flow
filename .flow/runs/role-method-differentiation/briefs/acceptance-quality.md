# Acceptance review brief: quality reviewer

## Task

Judge the complete working-tree change against the approved definition, plan,
and all eight acceptance criteria. Review for missing work before reviewing the
changed lines. Read all eight repair-2 response envelopes and apply the frozen
stopping rule without relaxing or replacing it. Write the result only to
`.flow/runs/role-method-differentiation/review/acceptance-quality.md`.

## Evidence inventory

### Already exists

- Approved scope and release condition:
  `.flow/runs/role-method-differentiation/requirements.md:13-42`.
- Observable gates:
  `.flow/runs/role-method-differentiation/acceptance-criteria.md:3-31`.
- Approved slices and validation duties:
  `.flow/runs/role-method-differentiation/plan.md:9-45`.
- Executable role instructions:
  `scaffolds/default/agents/product-manager.md:50-58`,
  `scaffolds/default/agents/quality-reviewer.md:98-110`, and
  `scaffolds/default/agents/lead-developer.md:34-96`.
- Replacement corpora and vocabulary:
  `scaffolds/default/expertise/product-manager.jsonld`,
  `quality-reviewer.jsonld`, `lead-developer.jsonld`, and
  `competencies.md`.
- Deterministic assertions:
  `tests/test_expertise_composition.py:47-179` plus its existing loader, join,
  merge, and renderer tests.
- Frozen comparison contract and score:
  `docs/evidence/role-method-differentiation/repair-2/manifest.json`,
  `product-manager-design.md`, `quality-reviewer-design.md`, and
  `results.json`.
- Eight immutable response envelopes under
  `docs/evidence/role-method-differentiation/repair-2/runs/`, with hashes in
  `execution-results.json` and `results.json`.
- Fault-detection and preservation records:
  `repair-2/mutation-check.md` and `preserved-lead-developer.json`.
- Final-tree checks and implementation handback:
  `.flow/runs/role-method-differentiation/validation-results.md:1-65` and
  `HANDOFF.md:1-57`.

### Partially covered

- Lead-developer's current files and prior pass have reproducible hashes, but no
  repair-start digest exists. Non-mutation during this repair is explicitly
  author-asserted.
- Static runtime smoke passes; four live-client command/agent checks remain in
  `.flow/memory/STATE.md` and are not claimed complete.

### Checked and genuinely absent

- There is no passing repair-2 product-manager or quality-reviewer role gate:
  `results.json` records both as false.
- There is no combined five-role pass because acceptance criteria 2 and 4 fail.
- There is no repair-start lead-developer body/corpus digest.

### Search method

The root reviewer enumerated `git status --short`, `git diff --name-only`, and
every file below `docs/evidence/role-method-differentiation/repair-2`; read the
approved intent, role files, corpora, tests, manifest, scorecards, results,
validation, and handoff; searched exact selected and superseded identifiers;
and verified manifest, raw-response, current treatment-source, and retained
lead hashes with SHA-256.

## Review requirements

- Mark each acceptance criterion pass, partial, or fail.
- Before filing a Critical, state a plausible explanation under which the work
  is correct and identify the evidence that rules it out.
- Separate evidence you observed, read, and received as an author assertion.
- State whether the run may advance to `accept-review`.
