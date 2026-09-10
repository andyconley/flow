# Formal acceptance quality brief

## Objective

Judge candidate production tree `T`
`4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`
against the approved definition, plan, and acceptance criteria. Review for
missing required content before reviewing defects in present content. Produce
a clear acceptance recommendation; do not edit production or lifecycle files.

## Evidence inventory

- Approved intent exists in `requirements.md`, `acceptance-criteria.md`,
  `plan.md`, and `validation-plan.md`.
- The complete 29-path production boundary and hashes exist in
  `evidence/change-surface.json`; it includes inherited `cli/expertise.py` and
  ADR 0008. The two PM/QR corpus paths are explicit absence markers.
- Implementation evidence exists in `validation-results.md`, `HANDOFF.md`,
  `evidence/final-receipt.json`, `evidence/logs/receipt.json`, mutation
  receipts, and live-client records.
- Earlier implementation review exists in `review/implementation-quality.md`.
  Its initial findings are preserved and its appended re-review marks them
  resolved. SRE evidence exists in `research/release-readiness.md`.
- The remaining known acceptance decision is the five-warning plan baseline
  versus four-warning final doctor result. The missing warning,
  `telemetry.claude.harvest`, is recorded as `ok`, not absent.
- No source commit `C`, merge, or release `R` exists yet; the plan puts those
  after formal acceptance.

The inventory was established from `evidence/change-surface.json`, direct Git
status/range inspection, the command receipt, and the current handoff. Verify
those claims independently and correct any disproved premise in the report.

## Review instructions

Read the complete requirements, acceptance criteria, plan, validation plan,
production diff and all current production artifacts before issuing a verdict.
Map criteria 1-10 individually. Separate observed evidence from artifacts read
and implementer assertions. Before filing any Critical finding, state one
alternative explanation and the evidence that rules it out. Explicitly decide
whether the improved four-warning doctor set satisfies criterion 8.

## Output

Write only `review/formal-quality.md` under this run. Use the Flow review
summary format, with prioritized findings, requirement fit, validation fit,
residual risks, and an explicit ready-or-refine recommendation.
