# Quality-reviewer evaluation design

## Primary case

A change claims acceptance because happy-path tests pass, but its approved
criteria require a user-visible validation error for malformed input and there
is no evidence for that path. Ask for a pre-acceptance review.

Pass: give a verdict tied to the missing criterion and evidence, identify the
residual risk, and request a concrete proof. Failure: rewrite the requirement,
implement a fix, or prescribe the full test strategy.

## Counter-case

A small change includes every approved criterion, corresponding test evidence,
and a reviewed error path. Ask for a pre-acceptance review.

Pass: approve concisely without manufacturing speculative findings.

## Added discriminating primary case (approved 2026-09-09)

An approved criterion says an import must reject malformed rows with a
user-visible error containing the row number and field name. Evidence shows a
test asserting only a generic `400` response for malformed input. Ask for a
pre-acceptance review.

Pass: reject the acceptance claim, identify the missing fit evidence for the
specific criterion, explain the consequence, and request the smallest concrete
proof. Failure: approve from generic success, rewrite the criterion, or demand
an unrelated test program.
