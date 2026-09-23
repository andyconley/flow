# Implementation Handoff

## Header

- Work item: `shaper-delivery-runtime-contracts`
- Summary: Implement Chunk 1 of the approved Shaper-to-Delivery architecture as an end-to-end Flow-gated Magentic proof.
- Work type: Runtime contracts, lifecycle, persistence, CLI, provider integration, and evidence.
- Owner: Flow implementation coordinator.

## Problem statement

Flow has a working chartered Magentic path but lacks canonical Shaper/Delivery authority, an atomic ownership handoff, and a runtime-neutral operator inspection boundary. The operator needs one approved intent to become one bounded, explainable, independently verified real change without giving MAF or a provider policy authority.

## Desired outcome

An approved run can atomically enter planning with a sealed Delivery Charter and one fenced Delivery Lead, project into protocol v7, execute one Magentic-selected Claude or Codex producer, obtain Ollama verification, and seal a charter-linked receipt.

## In scope

- Everything listed in `plan.md` Chunk 1 sections A-G.
- Current Flow control plane reuse.
- Inspect-only v6 compatibility.
- One live handback run after deterministic validation.

## Out of scope

- Later solution chunks, ordinary Chat MCP, broad adapter continuation, amendments, nested subagents, and v6 execution/resume.

## Technical constraints

- Flow remains the lifecycle, policy, evidence, and recovery authority.
- MAF and provider-specific types stay outside canonical domain schemas.
- `run.json` replacement is the lifecycle commit point; do not claim cross-store ACID.
- No provider send occurs before charter, source, worktree, roster, generation, and orchestration validation.
- Keep historical v6 bytes unchanged.
- Use additive ledger evolution and retain existing unknown-call semantics.
- Do not broaden provider troubleshooting if the single live job exposes an environmental failure; preserve the evidence and report the unresolved handback gate.

## Required implementation handback

- Changed files and commit(s).
- ADR and contract/schema documentation.
- Focused and full-suite test results.
- Orchestration validation results.
- Current/v6 CLI inspection examples.
- Live Magentic attempt, selected producer and rationale, grants, diff/test evidence, Ollama verifier result, and sealed receipt.
- Deviations, unresolved risks, and follow-up work assigned to later chunks.
- Explicit proof that the superseded Work feasibility probe was not treated as a gate.

## Implementation stop conditions

- The transition cannot be made idempotent without weakening existing lifecycle guarantees.
- Protocol projection would require MAF/provider types in canonical contracts.
- Generation fencing cannot stop a stale owner before the send boundary.
- V6 inspection would require rewriting legacy evidence.
- The live task cannot be bounded to a clean worktree, narrow paths, and a targeted test.
