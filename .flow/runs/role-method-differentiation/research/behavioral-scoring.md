# Behavioral scoring: role-method differentiation

## Evidence inventory

- Frozen role rubrics: `docs/evidence/role-method-differentiation/*/design.md`
- Raw treatment and pre-change control outputs:
  `docs/evidence/role-method-differentiation/*/runs/*.json`
- Acceptance gate: `.flow/runs/role-method-differentiation/acceptance-criteria.md`

All twelve records were observed as successful client responses. Treatment and
control use the same model within each role and case. This review accepts the
run record's assertion that the controls contain the pre-change `HEAD` bodies.

## Verdict

**FAIL — 1 of 3 role gates passes.** The release-wide all-three gate is not
met. Product-manager and quality-reviewer show useful treatment behavior, but
their controls already satisfy part of the new primary behavior. Under the
approved no-tie rule, those role gates fail.

## Product-manager — FAIL

### Primary

- **Value decay: tie.** Both arms identify the regulatory cliff and flat-value
  feature, then sequence the regulatory work first.
- **Rigor by reversibility: tie.** Both arms recognize the cheap reversible
  experiment and recommend running it quickly or in parallel to gain evidence.
- **Resolvable success and failure: treatment advantage.** Treatment supplies
  a source (compliance/legal sign-off), threshold (100% coverage), timing
  (before the deadline and a two-week escalation boundary), and failure
  condition. Control provides a source and deadline, but no equally concrete
  threshold plus failure boundary.

The treatment satisfies the absolute primary rubric, but two distinctive
methods are already present in control. The no-tie gate therefore fails.

### Counter

**PASS.** Treatment treats the settled statutory date as a hard scheduling
constraint, does not invent discovery delay, and limits work to settled
compliance scope. There is no harmful over-application relative to control.

## Quality-reviewer — FAIL

### Primary

- **Spec-derived omission: tie.** Both arms independently identify the omitted
  malformed-input requirement and block acceptance.
- **Evidence-strength labels: treatment advantage.** Treatment explicitly
  classifies the test claim as `author-asserted` and distinguishes absent
  observation. Control calls the claim unverified and unsupported, but does not
  apply the required observed/read/author-asserted taxonomy.

The treatment is clearer and more reproducible, but the omission behavior is
already present in control. The no-tie gate therefore fails.

### Counter

**PASS with a clear treatment advantage.** Treatment states the plausible
correct explanation, treats the suspected defect as an open question rather
than a critical issue, and asks for a discriminating test. Control files the
same unresolved issue under Critical Issues. The treatment exhibits the
required critical-finding calibration without approving unsupported behavior.

## Lead-developer — PASS

### Primary

**PASS with a clear treatment advantage.** Treatment classifies the change as
atomic, local, reversible, and covered; emits only the short form; names the
existing focused test; and names the one-command revert. Control contains good
proof and revert advice, but still fills the full multi-section plan. The
observable distinction is proportional plan depth rather than verbosity alone.

### Counter

**PASS.** Treatment selects the full plan for a stateful public API migration,
keeps compatibility and migration stages explicit, and identifies the point of
no return. It does not over-apply the short form. Control also produces a full
plan, which is expected non-regression behavior for this counter-case.

## Required disposition

Do not accept or merge the three-role release under the current acceptance
criteria. The smallest honest choices are to refine the product-manager and
quality-reviewer fixtures toward behaviors their controls do not already
perform, or revise the approved gate so method precision can count when the
control already approximates the behavior. Either choice changes the accepted
evaluation contract and should occur before another treatment run.

## Evidence limits

- Observed: raw output content, successful response status, model identity,
  turn counts, and rubric comparisons.
- Read: requirements, acceptance criteria, plans, and frozen design summaries.
- Author-asserted: controls were generated from exact pre-change `HEAD` bodies.
- The durable evidence directories contain rubric summaries and outputs, but
  do not retain the exact prompts or a standalone run manifest. A future rerun
  cannot establish prompt parity from these artifacts alone.
