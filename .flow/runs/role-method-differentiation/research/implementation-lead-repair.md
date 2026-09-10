# Implementation lead repair assessment

## Current state

`HEAD` has neither product-manager nor quality-reviewer corpus files and neither
role body has either repair method. The working tree added two entries for each
role and three body additions for each role. The approved repair narrows that
work: retain only time-sensitive sequencing for product-manager and
alternative-explanation calibration for quality-reviewer. The current body
test still asserts the unselected reversibility, success-metric, omission, and
evidence-label additions, so it would preserve the rejected scope.

The earlier behavioral evidence is correctly negative: both prior primary
cases tied the exact `HEAD` controls. The lead-developer short/full-plan
contract and its two existing corpus entries have passing evidence and must not
change.

The competency prose is already inconsistent with the actual corpus: the
current tree has 25 entries and 20 vocabulary terms, while the prose claims 22
and 16. Do not hand-edit its counts from the old claim; recalculate after the
replacement. The intended repaired shape is 23 entries and 18 terms.

## Minimum coherent change

1. In `scaffolds/default/agents/product-manager.md`, retain only the priority
   instruction that names decay shape, compares cost of delay with delivery
   duration, and sequences by value lost through delay. Remove the added
   reversibility and success-metric/kill-condition wording.
2. In `scaffolds/default/expertise/product-manager.jsonld`, remove
   `flow:entry/product-manager/tie-priority-to-an-outcome-and-evidence` and
   retain `flow:entry/product-manager/sequence-by-value-decay`, rewriting its
   required behavior to cost-of-delay divided by duration. Its Reinertsen
   citation must record the verified edition and locator before evidence runs.
3. In `scaffolds/default/agents/quality-reviewer.md`, remove the added
   omission preamble and evidence-label rule. Retain one rule requiring a
   plausible correct explanation and the evidence that rules it out before a
   Critical; otherwise require a question or lower severity. Renumber the
   existing rules.
4. In `scaffolds/default/expertise/quality-reviewer.jsonld`, remove both
   `flow:entry/quality-reviewer/require-observable-proof-for-an-acceptance-claim`
   and `flow:entry/quality-reviewer/review-for-omissions-and-evidence-strength`.
   Replace them with one entry, recommended id
   `flow:entry/quality-reviewer/calibrate-critical-findings-with-an-alternative-explanation`,
   backed by a verified Heuer source with the required Chapter 8 locator.
5. In `scaffolds/default/expertise/competencies.md`, remove the three
   superseded reverse edges/terms, retain `Sequence by value decay`, add the
   matching critical-calibration term and reverse edge, then recalculate the
   coverage table and join totals from the final corpus.
6. In `tests/test_expertise_composition.py`, replace the unselected body
   expectations with the two approved minimum instructions; add explicit
   presence assertions for the replacement ids and absence assertions for all
   three superseded ids. Keep the manifest, renderer, and reverse-join tests;
   they cover the composition boundary shared by Claude and Codex.

## Evidence and preservation

Create a new, versioned repair envelope below
`docs/evidence/role-method-differentiation/repair-2/`; never overwrite the
existing raw transcripts, designs, or failure results. Freeze the exact HEAD
control bodies, generated treatment bodies, prompts, rubric, model settings,
and stopping rule before running. The previous primary fixtures are not
reusable because their controls already performed the tested behavior. The new
product primary must force a cost-of-delay/duration comparison; the quality
primary must supply an initially plausible correct explanation and evidence
that distinguishes it. Both counter cases must reject over-application.

After the two new gates pass, the combined result may cite the preserved
architect/test-engineer passes and lead-developer pass, while clearly marking
the earlier product-manager and quality-reviewer attempts as superseded failed
evidence.

## Preservation hazards

- The working tree is shared and the affected corpus files are untracked. Do
  not restore from `HEAD`; there is nothing there to restore.
- The corpus and `competencies.md` are a bidirectional join. Changing an id,
  name, or `teaches` edge without its reverse listing breaks release-time
  validation even when agent rendering succeeds.
- `flow.toml` and the shared renderer already opt these roles into composed
  bodies. Do not change the composition architecture or model routing for this
  content repair.
- Preserve `scaffolds/default/agents/lead-developer.md`,
  `scaffolds/default/expertise/lead-developer.jsonld`, and its prior evidence
  byte-for-byte for this repair.
