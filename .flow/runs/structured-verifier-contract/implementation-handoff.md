# Implementation Handoff

## Objective

Implement protocol-v8 structured verifier evaluation in the three chunks defined in `plan.md`, preserving Flow ownership, Magentic coordination, truthful provider-call states, and v7 compatibility.

## Start here

1. Read `requirements.md`, `acceptance-criteria.md`, `solution.md`, `plan.md`, and `validation-plan.md`.
2. Begin with dormant v8 contracts and evaluator; do not cut active jobs to v8 until chunk 3.
3. Commit and run the full suite after each chunk.

## Non-negotiable boundaries

- Record a returned provider response before evaluating its structured content.
- Magentic proposes the retry; Flow authorizes or denies it.
- Unknown means uncertain transport only.
- V7 validation and meaning remain unchanged.
- No live Ollama smoke, prompt tuning, quorum, producer changes, nested subagents, or general retry framework.

## Acceptance evidence

- Focused evaluator, migration, ledger concurrency/replay, gateway, receipt, and compatibility tests.
- Final full-suite result.
- Updated ADR and handback stating that no new Ollama runtime proof was performed.

## Stop conditions

- Stock Magentic cannot act on normalized retry eligibility within the approved boundary.
- The response-before-evaluation requirement would require changing producer result semantics.
