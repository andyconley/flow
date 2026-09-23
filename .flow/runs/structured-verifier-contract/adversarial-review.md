# Adversarial Review

## Evidence inventory

- Accepted predecessor: `.flow/runs/shaper-delivery-runtime-contracts/archive.md` and `review.md`.
- Current implementation: `cli/delivery_gateway.py`, `cli/execution_contracts.py`, and `tests/test_chartered_delivery_gateway.py`.
- Automatic archive retrieval was unavailable at lane entry because the isolated worktree lacked local identity. The accepted predecessor was inspected manually outside that selection.

## Dispositions

- Product: fixed the first-slice cap at one verifier call and removed another Ollama feasibility proof from scope.
- Requirements: distinguished provider completion, verdict evaluation, attempt status, and transport uncertainty.
- Architecture: added explicit compatibility and versioning requirements; routed to `flow-solution` rather than direct planning.
- Scope: deferred retries, quorum, semantic scoring, prompt optimization, producer routing, historical reconciliation, and nested subagents.

## Remaining decision for solution

- Choose protocol v8 or an explicit negotiated verifier-contract version. In either case, existing v7 receipts remain readable and their historical meaning does not change.

