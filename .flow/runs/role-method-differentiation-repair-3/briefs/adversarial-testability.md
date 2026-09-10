# Adversarial review brief: testability

## Task

Audit whether every acceptance criterion in the narrowed draft has a feasible,
non-vacuous oracle. Focus on exact cohort membership, PM/QR exclusion, historical
evidence preservation, named three-role pass evidence, semantic mutations,
documentation searches, and live-client proof. Write only to
`.flow/runs/role-method-differentiation-repair-3/review/testability.md`.

## Evidence inventory

### Already exists

- Draft definition/criteria, prior deterministic tests, frozen hash manifests,
  raw behavioral records, adapter checks, static smoke, and formal proof audit.
- Current diff identifies all PM/QR and retained-role production surfaces.

### Partially covered

- Repair-2 lacks repair-start preservation hashes and a quality mutation.
- Static smoke requires manual live-client checks.

### Checked and genuinely absent

- No repair-3 start receipt, implementation validation plan, or final tree yet.
- No accepted automated substitute for native client loading.

### Search method

The coordinator compared the draft criteria with all existing test/evidence
surfaces and prior review gaps.

## Required output

- Identify vacuous or infeasible checks and give replacements.
- Separate definition outcomes from plan-level procedures.
- State whether acceptance can reliably block a wrong narrowed release.
