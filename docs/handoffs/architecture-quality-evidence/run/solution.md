# Solutioning Summary

Approved by Andy in this conversation on 2026-09-10: "yes, I approve. finalize the solution and move into flow-plan". This captures the proposed-design.md recommendation; implementation and plan approval are separate.

## Problem
Engineers reviewing agent changes need source-derived architecture visibility, explicit dependency-boundary checks and attributable code-quality evidence. Flow must support modular Python, TypeScript/Node.js, C# and eventual C++ integration while proving a bounded Python pilot first.

## Session Model Advice
Coordinator recommendation recorded during solutioning: judgment, gpt-5.6-sol/high. Active parent unknown to the CLI; no switch performed. Delegated roles: solution-architect, gpt-5.6-sol/medium; test-engineer, gpt-5.6-terra/medium, per configured role routing (not an independent runtime attestation).

## Evidence and decision history
Use requirements.md and acceptance-criteria.md as approved definition inputs. research/solution-retrieval.md records unavailable archive retrieval and the retained selection; inspected repository evidence is outside that selection. research/bob-reuse.md records the superseded fork assessment and final independent-implementation direction. Bob's repositories are behavior references, not implementation dependencies.

## Recommended approach

Build a small Flow-owned evidence contract, policy evaluator and interactive local viewer using independently licensed libraries. Study Bob's tools for observable capabilities without copying or translating his implementation. Language-specific analyzers plug into that contract. Reuse the existing review workflow rather than add a lifecycle or service.

Alternative: integrate separate analyzer-native reports and viewers with a thin evidence index. This is quicker initially but duplicates navigation and makes baseline joins, source attribution and cross-language consistency harder. Recommend the shared contract because the explicit Python/TypeScript/C#/eventual C++ requirement makes those joins durable needs. Keep adapter execution out of viewer code so the rendering library remains replaceable.

## Contracts and ownership

- Snapshot: schema version, source baseline/candidate hashes, selected scope, processed/excluded/failed inventory, build context, adapter/tool versions and raw artifact references. Snapshot identity covers analysis overlays separately from source identity.
- Architecture: opaque language-qualified node IDs, explicit parent/component IDs, display names and source spans; directed edges with kind, resolution status and supporting source locations. Never infer hierarchy by splitting names on dots. Imported, called, inherited and runtime-observed edges remain distinguishable.
- Quality: symbol ID, source identity, metric definition, value, denominator and collector. CRAP declares its coverage basis. Mutation records retain native outcomes and separate reviewer dispositions. Unsupported, failed and absent evidence are explicit states rather than zero values.
- Policy: separately approved rule identity and scope, prohibited edges and new-cycle criteria, explicit exceptions and baseline comparison. Graph evaluation uses normalized edges; adapters determine language semantics, not approval policy.
- Review packet: snapshot pair, policy results, quality evidence, analysis gaps and raw source pointers. The existing review.md links this packet. The viewer reads files; it does not execute tests or change approval policy.

Applicable principles carried from prior standards review: Architecture Standard — Domain and integration boundaries (separate analyzer semantics from Flow policy); Interfaces and data flow (versioned explicit contracts); State and persistence (immutable evidence files); Operational shape (local bounded execution); Decision durability (replaceable adapters and renderer). See solution-architecture.md for prior source review.

## Language layer

Each adapter can expose graph extraction, complexity collection, coverage ingestion and mutation execution as separate capabilities. An ecosystem may use several tools. Shared code consumes the contract without importing a language parser. Python is implemented first; TypeScript/Node.js and C# are intended next consumers, with C++ reserved as a later adapter that carries build configuration. Cross-language service calls or bindings require separately identified evidence; import graphs alone do not establish them.

Tach remains the candidate Python graph provider, Radon and coverage.py the demonstrated metric providers, and mutmut the unverified mutation candidate. Cytoscape.js remains the recommended rendering library for a Flow-owned browser UI. Versions, feasibility and limitations are in solution-architecture.md and solution-testing.md; these are candidates, not claims of end-to-end completion.

## Review and enforcement

1. Produce baseline and candidate snapshots in an isolated pinned environment.
2. Validate provenance and inventory before evaluating policy. Missing required evidence makes the review inconclusive.
3. Show changed components/edges, new cycles and explicitly prohibited edges, with source drilldown and visible unresolved analysis.
4. Attach complexity, coverage, CRAP and targeted mutation evidence for the selected function. Numeric quality thresholds stay advisory during the pilot.
5. Engineer records the decision in the existing review artifact. Only seeded new-cycle/prohibited-edge cases fail the isolated pilot checker; no production gate changes.

## Smallest useful pilot and measurable outcomes

Use the already inspected Flow v0.28.0 source baseline and collector/watermark area. Scan CLI context for graph completeness; constrain enforcement and mutation to approved pilot scope.

- Every processed/excluded/failed file is accounted for; every displayed dependency has a source pointer or explicit unresolved status.
- Each seeded new-cycle and forbidden-edge case fails the isolated checker; unchanged baseline findings remain distinguishable from new findings.
- The selected function has source-matched complexity, declared coverage basis, CRAP and targeted mutation outcomes; a controlled weak-test candidate is distinguished from stronger evidence. Missing evidence cannot produce a pass.
- The same viewer and evaluator accept Python output and a hand-authored second-language contract fixture without edits to shared code. The fixture tests opaque IDs, explicit hierarchy and missing capabilities; it does not establish real second-language support.
- Pan/zoom, component filtering, baseline/candidate comparison and source drilldown work locally without a runtime network dependency.
- Complete the approved four-change/two-pair engineer review exercise, recording review time, seeded misses and false positives. Report directional results without claiming a generalized speed improvement.

## Proposed delivery chunks and risks

1. Contract plus Python graph-to-viewer slice, including second-language fixture and source drilldown. Implementing engineer owns graph completeness and exact source joins; reject unmapped evidence as inconclusive.
2. Baseline comparison and isolated boundary checks. Andy owns policy decisions; implementing engineer owns fixture verification and protection against stale policy identity.
3. Function quality evidence and targeted mutation. Implementing engineer owns mutmut compatibility and mutant-loaded-path proof; test reviewer owns outcome interpretation. Return an explicit alternative decision if the runner is incompatible.
4. Existing review integration and measured pilot. Andy owns reviewer decisions and pilot interpretation; implementing engineer records reproducible environment and evidence artifacts.

No commitment to a custom language analyzer or universal metric thresholds. Suggested planning artifacts: versioned contract/schema, adapter conformance fixtures, policy fixtures, viewer interaction checklist, and reproducible pilot protocol.


## Next lane
flow-plan: shape the approved chunks into implementation-ready work, retaining compatibility and evidence risks.
