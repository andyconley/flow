# Implementation quality-review brief

## Objective

Review the final repair-3 candidate against every approved requirement and
acceptance criterion. Derive the expected artifact inventory before reading the
diff, distinguish observed/read/asserted evidence, and challenge any critical
finding with one alternative explanation.

## Evidence inventory

- approved repair-3 requirements, acceptance criteria, plan, validation plan,
  and implementation handoff
- all repair-3 research, receipts, mutation records, and validation results
- complete `origin/main..HEAD` predecessor range plus scoped working diff
- protected preservation inventory and current release evidence map

## Boundaries

Write only `review/implementation-quality.md`. Do not edit production files,
tests, frozen evidence, or other review reports. Other agents are working in
the repository; do not revert or rewrite their work.

## Output

Give a severity-ordered verdict, omissions as findings, evidence strength per
claim, and required dispositions before formal `flow-review`.
