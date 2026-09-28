# Implementation Handoff

Implement the four slices in `plan.md` in order. Primary surfaces are `cli/runstate.py`, `cli/orchestration.py`, `cli/flow.py`, focused lifecycle/orchestration tests, planning guidance, MAF ADR/support wording, and the existing blocked run through the new gated mechanism.

Safety invariants: original approved bytes and digests never change; the overlay cannot expand implementation authority; failures write no lifecycle state or events; reviewers remain read-only and independent; acceptance remains blocked until effective-manifest acceptance validation succeeds.

