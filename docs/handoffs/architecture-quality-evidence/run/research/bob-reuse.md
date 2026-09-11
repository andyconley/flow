# Bob tool reuse and language adapters — 2026-09-10

Status: solution research and user steering; no solution approval or implementation authorization inferred.

## Superseding direction — reference implementations, not forks

Andy subsequently supplied https://www.youtube.com/watch?v=zcLPGC-tvgk (LIVE: Uncle Bob on Software Fundamentals in the Age of AI) and reported Bob's guidance: his implementations suit his projects; point an agent at them as examples and have it build an implementation suited to your own project rather than copying them. The video page was retrieved, but no transcript was available through that retrieval; this statement is attributed to Andy's account, not independently verified or a direct quotation.

This supersedes the fork-first recommendation below. Use the repositories to identify capabilities, interaction patterns and observable behavior, then specify and implement Flow's own design against approved requirements. Do not copy or translate Bob's source into Flow. Reuse independently licensed third-party libraries when appropriate. Licensing clarification for Bob's code is no longer a prerequisite for selecting this independent implementation path.

Retain the modular language layer for Python, TypeScript/Node.js, C# and eventual C++. Extract reference capabilities into a behavior checklist: architecture drilldown and source traceability; graph-based dependency rules; metric provenance; targeted mutation results; explicit missing evidence. Define acceptance fixtures independently from Bob's implementation and retain the bounded Python pilot. Tach and Cytoscape remain candidates evaluated against these requirements, not automatically selected or rejected. No lifecycle approval or implementation occurred as part of this correction.

Andy requires an eventual modular language layer for Python, TypeScript/Node.js, C#, and potentially C++. He means actual fork/extension/enhancement of Bob's tools, not only inspiration. The Python pilot remains bounded; its architecture must not bake Python assumptions into the shared contract.

## License findings

Reviewed public source snapshots of arch-view, dependency-checker, crap4clj, Acceptance-Pipeline-Specification, clj-mutate, crap4java, mutate4java, dry4clj, and swarm-forge. No LICENSE/COPYING/NOTICE grant found; GitHub metadata reports no detected license. crap4clj README explicitly states Copyright Robert C. Martin, all rights reserved. Public visibility is not sufficient permission to distribute an enhanced derivative. GitHub permits on-platform viewing/forking; broader reuse requires applicable licensing or permission. This is a reuse dependency, not evidence that every Bob repository has identical terms.

Sources: https://github.com/unclebob/crap4clj#license and https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository

## Concrete extension candidates

- arch-view: highest priority. core.clj accepts --in-edn architecture data, bypassing Clojure scanning. Existing input/model/layout/UI separation permits adapter-fed visualization. Must generalize dot-separated namespace hierarchy (currently drops first segment), explicit component identity, source mapping, and reload in file-input mode. Current Quil/Swing viewer is JVM desktop, not a browser library. EDN ingestion is an inspected code seam, not validated multilingual support. Sources: https://github.com/unclebob/arch-view/blob/master/src/arch_view/core.clj and https://github.com/unclebob/arch-view/blob/master/src/arch_view/domain/architecture_projection.cljc
- dependency-checker: extract graph-level cycle, allowed/forbidden dependency and exception logic behind normalized input. Parsing/component grouping is Clojure-specific. Abstractness requires language-specific definitions; do not compare unknown values as zero. Source: https://github.com/unclebob/dependency-checker/blob/master/src/dependency_checker/core/graph.clj
- CRAP family: extend report/evidence contracts; complexity and coverage acquisition stay per language. crap4java uses JaCoCo instruction coverage, which must not be silently equated to Python statement or branch coverage. Formula alone does not justify porting a whole engine. Source: https://github.com/unclebob/crap4java
- Mutation family: candidate reuse of differential scheduling, fingerprints, isolated workers and result reporting; operators and build/test execution remain language-specific. mutate4java embeds manifests in source comments; proposed Flow manifests remain sidecars and invalidation must include tests, dependencies, tool versions and build configuration, not only source hashes. Source: https://github.com/unclebob/mutate4java
- Acceptance-Pipeline-Specification: portable Gherkin-to-JSON IR plus runner-worker protocol and project adapters. Strong later candidate. Its acceptance mutations change example values in IR, not application source: preserve separate evidence categories. Source: https://github.com/unclebob/Acceptance-Pipeline-Specification
- dry4clj: possible later duplication evidence through normalized syntax fingerprints and similarity. Language-specific normalization remains required. Source: https://github.com/unclebob/dry4clj
- swarm-forge: wholesale orchestration fork overlaps Flow ownership; lower priority than focused components.

## Revised recommendation to assess

Tach is a candidate Python adapter, not the shared architecture core. Cytoscape is an alternative browser renderer, not yet the selected solution. Assess arch-view and dependency-checker reuse first, conditional on explicit license terms. Keep Flow responsible for versioned graph/evidence schema, policy identity, provenance, baseline comparison and review workflow.

Adapters declare supported graph/metric/test capabilities, stable language-qualified identifiers, explicit containment, source spans, edge kinds, unresolved analysis, coverage denominators and build context. Missing capability means unsupported/inconclusive. Cross-language runtime connections need separate evidence and must not be invented from imports.

Small next feasibility decision: feed the bounded Python graph through the existing arch-view file-input seam; assess hierarchy and source navigation; compare extension effort against browser implementation. Add a second-language contract fixture without claiming a working second-language analyzer. Acceptance should require adapter changes without changes to shared policy/viewer code, preserved provenance and explicit unsupported metrics. Actual derivative code work remains conditional on reuse rights; this note does not approve a fork or change lifecycle state.
