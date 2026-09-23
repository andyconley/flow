# Definition Brief: Structured Verifier Contract

## Task

Define the smallest next slice that makes verifier output machine-checkable, rejects unusable verdicts before successful handback, and limits verifier calls independently from the global delegation budget.

## Confirmed direction

- Ollama is already accepted as functional for a bounded verifier route; do not repeat provider feasibility work.
- Flow remains the policy, evidence, and acceptance boundary.
- Magentic remains the Delivery Lead and may select only from the approved roster.
- The new slice should improve evidence quality without reopening producer routing, receipt recovery, or general nested-subagent control.

## Evidence inventory

- `.flow/runs/shaper-delivery-runtime-contracts/archive.md`: accepted outcome and explicit follow-ups.
- `.flow/runs/shaper-delivery-runtime-contracts/review.md`: accepted scope and residual risks.
- `cli/delivery_gateway.py`: current verifier dispatch, evidence injection, and terminal decision.
- `cli/execution_contracts.py`: v7 action, result, receipt, and limit validation.
- `tests/test_chartered_delivery_gateway.py`: current producer/verifier behavior and refusal tests.
- Archive retrieval selection `a5fb1606146fb0abb0ce9ec8a42d96cd26a59832b289421bc9be64e14d5d96a1` was unavailable because the isolated worktree initially lacked local identity. The merged archive above was inspected manually and was not a retrieved hit.

## Requested review

Identify the required user-visible outcome, exact acceptance behavior, non-goals, constraints, edge cases, and any architecture decision that would require `flow-solution` rather than direct planning. Keep the proposal narrow and implementation-ready.
