# Implementation plan: role-method differentiation repair

## Risk posture

This is a local, reversible content and test change, but the release claim
depends on live behavioral evidence. Keep the product edits small and spend
the validation effort on frozen treatment/control comparisons.

## Slice 1 — replace the two failed methods

- Replace product-manager's redundant entry and competency with time-sensitive
  sequencing based on cost of delay divided by duration.
- Keep only the matching product-manager role-body instruction.
- Replace quality-reviewer's redundant entries and competencies with
  alternative-explanation calibration for Critical findings.
- Keep only the matching quality-reviewer role-body instruction.
- Preserve lead-developer unchanged.

## Slice 2 — deterministic proof and documentation

- Update corpus/role contract tests to require the replacement ids and reject
  the superseded ids.
- Reconcile competency counts and reverse joins from the shipped corpus.
- Preserve the first attempt's evidence and add a clearly versioned repair
  evidence envelope.
- Update the run artifacts and combined five-role result so failed history and
  current evidence are distinguishable.

## Slice 3 — frozen behavioral comparison

- Before any treatment run, store exact prompts, rubrics, settings, body hashes,
  current source revision, and the pre-declared stopping rule.
- Run product-manager and quality-reviewer treatment/control primary and
  counter cases with client/model/effort/turn/budget parity.
- Score at criterion level. Each treatment must satisfy every distinctive
  primary item and each control must miss every distinctive item. Counter-case
  over-application fails.

## Validation and handback

- Run the focused suite and a meaningful role-instruction mutation check.
- Run the full Python 3.12 suite, `git diff --check`, sync both user adapters,
  verify both with `--check`, then run runtime smoke and doctor.
- Record evidence provenance per check, independent quality review, findings
  dispositions, and a review-ready handback.

## Approval status

Approved by Andy Conley on 2026-09-09 with replacement entries, minimum
role-body wording, strict treatment advantage, and retained historical evidence.
