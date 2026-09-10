# Implementation handoff: three-role expertise expansion

- Work item: `role-method-differentiation-repair-3`
- State: ready for formal `flow-review`
- Candidate production tree `T`: `4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`
- Production surface: 29 declared paths across the full inherited
  `origin/main..2712f5f` range and the scoped repair-3 working tree

## Delivered behavior

The active baseline composes exactly six roles: architect, business-analyst,
lead-developer, SRE, support-lead, and test-engineer. This release retains the
source-backed architect, lead-developer, and test-engineer methods, corpora,
source locators, competency joins, shared-renderer output, and passing evidence.
The production digest includes the inherited `cli/expertise.py` loader and ADR
0008 as well as the repair-3 changes.

Product-manager and quality-reviewer are restored to their exact `2712f5f`
base-role bodies. Their repair-2 baseline corpora, composed declarations,
active vocabulary edges, and generated Expertise sections are absent. User
overlays remain untouched. Both repair-2 generations remain as failed
historical evidence; the 112 protected files and both protected tree digests
are byte-identical to the frozen inventory.

The current release summary is
`docs/evidence/three-role-expertise-expansion/README.md`. It reports only the
three additions with passing gates and retains the failed PM/QR disposition.

## Validation evidence

- `evidence/final-receipt.json` reports 250 checks and zero failures across
  protected history, retained hashes, active state, the complete production
  surface, command logs, and native captures.
- The focused expertise suite passes 49 tests. The full repository suite passes
  996 tests.
- Durable logs cover help and whitespace checks, user and isolated
  Claude/Codex sync and drift checks, static runtime smoke, normal and strict
  doctor runs, Flow run verification, and generated/installed adapter
  readback.
- Three separately executed negative mutations prove that guards reject PM
  reintroduction, test-engineer removal, and a semantic negation of the
  lead-developer obligation. Every mutation records the failure and exact byte
  restoration before the passing focused run.
- Fresh native Claude and Codex sessions loaded `test-engineer` and produced
  the required concrete row-7/email test oracle. Claude used
  `sonnet`/`medium`; Codex used `gpt-5.6-terra`/`medium`. Fresh command checks
  also loaded `/flow-status` and `$flow-status`.
- The two generic support-lead role cells from static smoke were superseded by
  the approved, stronger test-engineer matrix. No support-lead live result is
  claimed.

The detailed mapping from acceptance criteria 1-10 to evidence is in
`validation-results.md`. Independent implementation-quality and SRE reviews
both judge the corrected candidate ready for formal review.

## Formal-review disposition

The approved plan recorded five strict-doctor warnings. Final normal and
strict doctor output contain four warnings and zero errors because
`telemetry.claude.harvest` changed from warning to `ok` after the planned
harvest refresh. No warning was added or escalated, and release-relevant
diagnostics remain `ok`. The quality and SRE reviews accept this as a safer
operational state. Formal review must explicitly accept the exact-set evidence
variance before `T` advances to `C`.

The pre-existing `.flow/memory/STATE.md` working-tree delta remains
byte-identical to its captured start hash
`237cf7b512e212f586e9a8d283346244e51932f8cac06bea72e3ff8572d7a8ea`.
It is excluded from `T`, must remain unstaged, and is not repair-3 evidence.

## Next transition and delivery boundary

Run formal `flow-review` against `T`, the bounded working diff, all protected
paths, mutation receipts, native records, and the doctor variance. No source
commit has been created because the approved contract is `T -> formal review
-> C`.

After review acceptance, create source commit `C` only if every production
hash still matches `T`. Then fetch and reconcile the remote, integrate and
push, observe all four semantic-release jobs, verify the public tag/release and
changelog-only release commit `R`, refresh the develop install from `R`, and
repeat the installed Claude/Codex checks. Publication or installation evidence
cannot be inferred from this pre-release handoff.

## Roles engaged

The run engaged solution-architect, business-analyst, product-manager,
test-engineer, lead-developer, quality-reviewer, SRE, tech-writer, and explorer
lanes. Their assignments and evidence paths are recorded in
`orchestration.json` and `findings-reconciliation.md`.
