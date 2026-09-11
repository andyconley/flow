## Product Decision Summary

### Opportunity
- **Observed:** The approved pilot addresses a concrete review problem: one engineer needs candidate-bound, source-attributable architecture and quality evidence to make an accept, needs-changes, or inconclusive decision without reconstructing the CLI from a diff.
- **Observed:** The value hypothesis is architecture visibility first; dependency policy and selected-function quality evidence test whether that visibility can support a more trustworthy review. The exercise measures directional usefulness, not a promised review-speed gain.
- **Observed:** The user has confirmed all four chunks together, in an isolated checkout with a standalone local browser report. Production adoption, new workflow lanes, and real non-Python adapters remain outside the pilot.

### Recommendation
- **Prioritize:** Treat the four chunks as one bounded pilot, with hard learning gates between them. Do not split the pilot into separate adoption commitments.
- **Why:** The final review exercise depends on provenance, graph semantics, policy comparison, quality evidence, and existing-review linkage working together. Shipping only a viewer or only metrics would not test the stated reviewer decision outcome.
- **Recommended sequence:**
  1. Establish the versioned contract, pinned baseline/candidate identity, inventory classification, and Python graph/source-provenance path; prove the hand-authored second-language fixture can be consumed.
  2. Add local visualization, baseline/candidate comparison, and isolated policy evaluation; exercise clean, forbidden-edge, and new-cycle fixtures before any reviewer exercise.
  3. Add selected-function complexity, coverage, CRAP, and targeted mutation evidence. Stop for an explicit alternative decision if mutmut cannot prove the mutant-loaded path or preserve required result states.
  4. Link the complete candidate-bound packet and approved policy from the existing review artifact, then run the four-change/two-pair exercise.
- **Dependency rule:** A later chunk may consume only evidence that is candidate-bound, versioned, and classified. Missing, stale, incompatible, or unmapped required evidence yields `inconclusive`; it cannot be represented as a passing result.

### Scope
- **Minimum useful slice:** One pinned Flow Python CLI revision, one coherent CLI area with direct dependencies and one expressible rule, controlled baseline/candidate changes, a local file-reading browser report, one selected changed-function quality/mutation proof, and the approved review exercise.
- **Deferred scope:** Production gates or CI/runtime enforcement; a new lifecycle; universal thresholds; custom analyzers; broad changed-function quality coverage; real TypeScript/Node.js, C#, or C++ execution; claims of cross-language support from the fixture.
- **Scope pressure to resist:** Sophisticated visualization, wider metric collection, and adapter work would consume pilot capacity without strengthening the central decision: whether the packet improves review of the selected Python change set.

### Risks and Tradeoffs
- **Observed risk:** Graph completeness and exact source joins are foundational. An attractive viewer with unexplained extraction gaps would create false confidence; inventory/provenance proof must precede policy conclusions.
- **Observed risk:** Mutation compatibility and proof that the tested path loads the intended mutant remain unverified. The pilot should preserve the explicit fallback decision rather than weaken the acceptance exercise.
- **Observed risk:** Four reviewer exercises produce directional evidence only. Order alternation, a frozen seeded-defect oracle, separate preparation time, and false-positive/miss recording reduce bias but do not establish statistical proof.
- **Tradeoff:** A shared contract costs more up front than separate native reports, but it is justified within this pilot because it permits a shared evaluator/viewer and tests opaque IDs, hierarchy, unavailable capability, and source attribution before future language investment.
- **Assumption requiring validation:** The selected CLI area has deterministic tests, meaningful dependencies, an expressible direct-import rule, and one changed function suitable for the quality/mutation demonstration. If discovery disproves any of these, rescope the area before building downstream chunks.

### Success
- **Definition of done:**
  - A1-A5 fixture evidence passes: deterministic normalized snapshots; manually checked graph/source provenance; clean and violation policy outcomes; correctly defined selected-function quality data; and weak-versus-strengthened behavioral mutation evidence with native states retained.
  - Every in-scope module/file is processed, excluded, failed, or unresolved with an explanation; dynamic/unresolved imports remain visible and outside completeness claims.
  - The local report supports the required reviewer actions: changed edge/component inspection, source drilldown, filtering, baseline/candidate comparison, and visible analysis gaps without a runtime network dependency.
  - The packet and engineer-approved policy are bound to the reviewed candidate and linked from the existing `review.md`; reuse for a different candidate is rejected or inconclusive.
  - The four-change/two-pair exercise completes under the approved protocol, recording disposition, time, confidence, seeded defects found, misses, and false positives. A missed seeded architectural violation or any mandatory fixture failure requires revision before an expansion decision.
  - The engineer records `expand`, `revise`, or `defer` with the measured overhead and directional evidence. No implementation result becomes a production gate through this pilot.
- **Unverified:** No measurements have run, no toolchain is selected or installed as a completed integration, and no evidence yet shows reviewer improvement, mutation-runner feasibility, complete source joins, or second-language production support.
