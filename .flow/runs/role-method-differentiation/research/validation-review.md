# Validation readiness review

Reviewed 2026-09-09 against the approved requirements, acceptance criteria,
validation plan, current role-body changes, deterministic tests, and the twelve
raw behavioral response records. This review makes no production changes.

## Evidence that is present

- The role-body contract is deterministic: the focused suite passed locally
  (`44` tests, 2026-09-09). It checks the new source-body boundary text and
  composed-corpus invariants.
- Generated adapters are current: `flow sync claude --user --check` and
  `flow sync codex --user --check` passed locally.
- Static runtime smoke passed with four existing manual checks still required:
  command discovery and one agent invocation in each of Claude and Codex.
- `flow doctor` passed and reports the active develop source as this checkout.
- Twelve JSON records exist: treatment and claimed pre-change controls for the
  primary and counter case of each target role. All parse as JSON and report
  `is_error: false`.

## Blocking findings

### Critical: no criterion-level scoring record exists

Requirement 5 and acceptance criterion 5 require frozen, criterion-level
scoring and reject ties. `docs/evidence/role-method-differentiation/results.md`
only says that scoring remains for independent review. The three design files
describe outcomes in prose but do not enumerate individual rubric items,
scores, a scorer, or a pass/fail disposition. The raw responses therefore
cannot establish the no-tie gate.

Required repair: create a scorecard for each role/case that names each frozen
criterion, quotes or points to the relevant response evidence, assigns a score
to treatment and control, and concludes pass/fail under the approved rule:
treatment satisfies every distinctive item that control misses.

### Critical: product-manager primary is visibly a tie on the stated new method

The control primary already describes the regulatory item's value as a hard
cliff, defers the flat-value feature, and uses a small reversible probe. The
treatment supplies more detail but that is not a valid win under the explicit
ban on verbosity-only wins. Since the gate requires treatment to satisfy a
distinctive item that control misses, this primary cannot pass as currently
designed. A scorecard must record this failure unless a frozen, objective
criterion shows otherwise.

### Critical: quality-reviewer primary is also a tie on the core behavior

The control primary identifies the missing approved malformed-input behavior
and calls the unsubstantiated test claim unverified. The treatment improves the
wording by naming a benign alternate explanation and marking the claim
`author-asserted`, but the design did not freeze those as separately scored
items. The existing prose-only design makes it impossible to distinguish a
substantive win from a more detailed restatement. It needs a frozen rubric and,
if the new labels/alternative explanation are the intended differentiators, a
new discriminating fixture that requires them.

### Important: arm provenance and parity are not reproducible

The raw JSON records preserve outputs and model names, but not prompts,
commands, agent-body digests, effort, or a run manifest. `results.md` asserts
that controls use pre-change `HEAD` bodies, but it contains no commit digest or
replay command. The records alone cannot prove the required unchanged-body
control or identical settings. The lead-developer primary records happen to
share three turns and the same model; other pair details cannot establish full
parity.

Required repair: add a frozen run manifest with the exact prompt, source-body
commit/digest, treatment-body digest, client command/settings, output cap, and
record path for each arm. Rerun any pair whose original invocation cannot be
reconstructed.

### Important: the test proof is narrow

The 44 focused tests prove static snippets and composition. They do not prove
that the short-form selection is applied to a qualified change, that a
disqualifying change selects the full form, or that evidence labels are
rendered in a generated adapter body. The behavioral pairs partly cover these
claims, but are blocked by the missing scorecards and provenance.

## Observations for scoring

- Lead-developer has the strongest apparent evidence. Treatment primary uses
  the short form with change, proof, and revert; treatment counter explicitly
  selects a full plan for a stateful public-contract migration. The control
  primary is verbose rather than short form. This can pass if the scorecard
  maps the evidence to frozen criteria and verifies arm provenance.
- Quality-reviewer treatment counter appropriately lowers the plausible
  critical to an open question; control counter files it as critical. This is
  likely discriminating evidence once criterion-level scoring exists.
- Product-manager treatment counter calls the legal deadline a cliff. That is
  consistent with the counter-case, but the scoring rule must verify it does
  not invent delay or turn the settled requirement into a normal tradeoff.

## Release readiness verdict

**Not ready for `mark-handback-ready`, formal acceptance review, or merge.**
The deterministic integration evidence is green, but the behavioral release
gate is not proven and two primary cases appear to fail the no-tie rule. First
add reproducible manifests and criterion-level scorecards. Then either record
the primary failures honestly and refine the fixtures/methods, or show a
pre-frozen distinctive criterion the controls actually miss. Only after all
three roles pass both cases can the run move to review.
