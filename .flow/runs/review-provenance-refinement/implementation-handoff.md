# Implementation Handoff

Implement the four slices in `plan.md` in order. Treat the original orchestration manifest and approved artifact digests as immutable Delivery authority. The amendment is a constrained review overlay, not a replacement of historical truth.

## Primary surfaces

- `cli/runstate.py`: lifecycle event, atomic recording, verification, acceptance binding.
- `cli/orchestration.py`: constrained-delta and effective-manifest validation.
- `cli/flow.py`: CLI exposure and output.
- `tests/test_flow.py`, lifecycle/orchestration tests, and focused real-run fixtures.
- planning command documentation and ADR/support documents identified by the MAF review.
- `.flow/runs/maf-runtime-readiness-2`: approved amendment/dispositions and fresh review evidence only through the new mechanism.

## Safety invariants

- No original approved byte or digest changes.
- No post-hoc expansion of implementation authority.
- Failed operations write neither lifecycle state nor event history.
- Fresh reviewers remain read-only and independent from producers/evidence collection as required.
- `accept-review` remains impossible until acceptance-stage validation succeeds.

