# ADR 0010: Separate architecture evidence from language tools

## Status

Accepted for the isolated architecture-evidence pilot. This is not a production adoption decision.

## Context

Flow needs source-bound structural and selected-function quality evidence for a Python CLI review pilot, while future adapters may use different graph, coverage, complexity, or mutation tools. Letting an analyzer define policy or report behavior would couple reviewer decisions to a single language ecosystem.

## Decision

The pilot owns a versioned snapshot and packet contract, graph comparison, policy evaluation, integrity checks, and local HTML rendering under `scripts/architecture_evidence/`. Language adapters provide normalized evidence and retain their native raw outputs. The viewer reads validated files and does not execute analyzers, tests, mutation, or policy approval.

Python starts with Tach for static direct imports, Radon and coverage.py for the selected function, and mutmut for a targeted mutation proof. These are pinned pilot inputs, not universal tools or acceptance thresholds. The TypeScript-shaped fixture tests contract portability only; it does not claim an implemented second-language adapter.

Policy is Flow-owned and limited to approved direct-import rules. It is bound to a manually created, copied approval receipt and source identity. Existing review artifacts remain the decision record.

## Consequences

- Adapter replacement does not require changing policy or report code when it preserves the evidence contract.
- Missing source joins, quality evidence, approval binding, or required artifact integrity produce `inconclusive`, never a pass.
- The pilot carries an up-front contract and evidence-packaging cost in exchange for source attribution and future adapter isolation.
- Production commands, lifecycle changes, CI/runtime enforcement, custom analyzers, and broad cross-language support remain outside this decision.
