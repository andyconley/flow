# Architecture and quality evidence — definition draft
Status: definition and acceptance criteria approved by Andy in this task on 2026-09-10.

## Intent and audience
Engineers need to understand and assess agent-produced structural changes without reconstructing the entire codebase from a diff. Flow should connect source-derived architecture visibility, explicit dependency enforcement, and code-quality evidence in one review workflow.

## Confirmed scope
User approved Flow's Python CLI as the pilot. Architecture visibility is the primary pilot outcome, supported by dependency rules and CRAP, complexity, coverage, and targeted mutation evidence. Tool selection is deferred.

## Proposed workflow
1. Record immutable baseline and candidate source identities; collect dependency graphs using the same analyzer configuration.
2. Inspect module-level before/after views, changed edges, cycles, and source locations. Drill down where supported; show extraction limitations explicitly.
3. Compare discovered dependencies to engineer-approved rules. Inferred existing edges are an unapproved baseline, not architectural permission.
4. Attach changed-function complexity, coverage, CRAP, and targeted mutation results. Preserve underlying measures and explain missing evidence.
5. Reviewer assesses behavior, architecture, evidence, and exceptions against intent; existing Flow acceptance remains authoritative.

## Enforcement boundaries
Approved forbidden dependencies and cycles may block pilot acceptance. Numeric complexity, CRAP and mutation measures begin advisory. Failure behavior is demonstrated by the isolated pilot checker only; existing Flow review remains the acceptance authority and no production gate is changed. Missing required boundary evidence must be inconclusive, never a pass. Optional unsupported metrics are visibly unavailable. Agents cannot silently change rules, thresholds, exclusions or baselines to pass. Any revision is separately visible and engineer-approved. No claim that a passing graph or score proves correctness.

## Smallest useful pilot
One pinned Flow Python CLI revision; one coherent CLI area and its direct dependencies, selected by static inventory during solutioning. Use an isolated copy and controlled candidate changes. Include a clean change, a forbidden edge, a new cycle, a complex undertested function and a weak assertion. No changes to the dirty development checkout. No production adoption, multiple languages, custom analyzer development or universal threshold in scope.

## Proposed acceptance criteria
A1. Both graphs identify source revision/content, analyzer version, configuration, scope and exclusions. Repeated extraction of identical input yields identical normalized graph data.
A2. Added/removed edges and cycles match a manually checked controlled fixture; every displayed edge links to supporting source. Dynamic/unresolved imports remain explicit.
A3. Approved forbidden-edge and cycle fixtures fail; the clean fixture passes. Missing, stale or incompatible required evidence cannot pass.
A4. Changed-function report preserves complexity and coverage definitions, raw values, CRAP formula and mapping limitations. Known calculation fixtures match independently calculated results; unknown coverage is not zero or 100 percent.
A5. Targeted mutation exposes a deliberately weak assertion; a strengthened behavior-based test kills that mutant. Surviving, equivalent, uncovered, timed-out and skipped mutations remain distinct. This is fixture evidence, not proof of a universally effective suite.
A6. A reviewer completes comparable exercises with and without the artifacts. Record time, seeded defects found, false positives and missed defects. Use matched changes and alternate order to reduce learning effects. A small pilot gives directional evidence, not statistical proof. Expansion requires no missed seeded architectural violation and an engineer judgment that visibility improved enough to justify measured overhead; no arbitrary speedup promise.
A7. Evidence is attached to the existing review/handoff and cannot be reused for a different candidate revision. No new lifecycle lane. Production runtime gate integration is outside this pilot and requires a later explicit decision.

## Source evidence already inspected in this conversation
- https://github.com/unclebob/arch-view/blob/master/README.md — source-derived Clojure namespace viewer; cycles and drill-down.
- https://github.com/unclebob/dependency-checker/blob/master/README.md — explicit boundary rules and cycle failures; initialization infers existing edges and requires judgment.
- https://github.com/unclebob/crap4clj — complexity plus coverage, analyzer-specific definitions.
- https://github.com/unclebob/swarm-forge/blob/six-pack/swarmforge/roles/hardender.prompt — changed-file CRAP and differential mutation; current policies not universal laws.
- /Users/andyconley/.flow/source/scaffolds/default/commands/flow-review.md — comparison to intent, independent high-risk verification.
- /Users/andyconley/.flow/source/scaffolds/default/standards/testing.md — behavior-based tests and mutation testing already supported.
Prior archive search was unavailable: no_project_overlay. These are manually inspected sources outside any retrieval selection. Web evidence reflects September 10 inspection and mutable upstream pages, not pinned tool selection.

## Open questions and next work
Solutioning must select a coherent module scope, baseline revision, extraction approach, presentation surface and feasible instrumentation. Definition review must challenge overbreadth, fairness of review comparison and gate semantics. Full requirements need explicit user approval after adversarial review. No tools selected or installed.

## Review-driven clarifications
- Primary action: one engineer issues accept/needs-changes/inconclusive against the same requirements and seeded-defect oracle; the artifact supports that decision.
- Graph scope: declared static Python module imports, with resolved file/line provenance. Dynamic/unresolved imports are categorized and excluded from completeness claims. Capture environment and normalization rules; renamed/moved functions need explicit mapping or become removed/new, never silently inherit coverage.
- New cycles and newly introduced approved forbidden edges fail. Existing violations are reported in a separate baseline ledger; baselining does not approve their design. Any touched existing violation receives a reviewer disposition.
- Rules, exclusions and scope are versioned in an engineer-approved policy artifact bound to baseline and candidate identities. Violations fail; absent/stale/incompatible required evidence is inconclusive; both prevent a successful pilot gate. This is normal-workflow integrity, not a guarantee against malicious agents.
- Complexity, coverage, CRAP and targeted mutation are required for selected changed functions in the pilot area. Missing required metrics are inconclusive. Outside the area is out-of-scope, distinct from unavailable. CRAP is C² × (1 − coverage)³ + C, with coverage unit/denominator and complexity rules declared.
- Mutation baseline tests must pass. A selected behavioral mutant must survive the weak assertion and be killed by an improved behavioral test. Equivalence and exclusion claims require reasons.
- Comparison protocol: one exploratory engineer, four bounded matched changes organized into two pairs, alternating which condition comes first. Each condition includes ordinary code, requirements and tests; only the treatment adds the evidence packet. Timer begins at opening supplied material and ends with written disposition. Preparation/collection time is logged separately. Freeze a seeded-defect oracle before review; findings not supported by it or independently validated are false positives. Record missed defects, correct disposition, time and confidence. This is directional evidence; learning effects remain a limitation.
- Include at least one real isolated CLI structural change; synthetic fixtures validate calculations/extraction but cannot alone demonstrate usefulness.
- Canonical artifact requirement: existing review.md links the candidate-bound architecture/quality evidence packet and approved policy. Reviewer verifies candidate identity before acceptance. Layout and CLI integration are solution choices.
- Expansion decision: after measurements, engineer records expand/revise/defer with reasons. Mandatory fixture failures or missed seeded architectural violations require revision before expansion; no universal metric threshold or speedup target is assumed.

## Pilot effort boundary
Select an area with deterministic existing tests, meaningful direct dependencies and one expressible architectural rule. Limit initial CRAP/mutation proof to one selected changed function. Broader changed-function reporting is a later expansion; required metric unavailability in the selected function makes that proof inconclusive. Presentation sophistication and production CI/runtime enforcement are out of scope.

## Architecture review dispositions
Flow owns review workflow, provenance, result states and revision binding. Language analyzers and project policy are replaceable inputs; custom analyzer development is excluded.
Inventory processed, excluded, failed and unresolved modules. Every in-scope module must be classified; unexplained extraction gaps make required boundary evidence inconclusive.
Each rule records identity/version, direction, scope and direct-versus-transitive semantics. The initial pilot uses direct module-import dependencies; inferred transitive reachability may be shown separately but is not silently treated as an import edge.
Review exercise output includes explanation of structural change, source locations, seeded violations, confidence and accept/needs-changes/inconclusive disposition. Report correctness and directional usefulness separately.
