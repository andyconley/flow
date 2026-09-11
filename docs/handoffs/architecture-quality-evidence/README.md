# Architecture and quality evidence: cross-computer handoff

The Flow pilot is implemented and ready for acceptance review. It combines a Python source-derived dependency graph, an interactive local report, explicit architecture rules and selected-function quality evidence. **It has not been accepted for production adoption.** Browser runtime validation and Andy's four timed reviews remain open.

Repository: `andyconley/flow` · branch: `feat/architecture-evidence-pilot` · implementation commit: `71858ad` · baseline: Flow v0.28.0, `6055b6b2dd4ca5fe9a9879d61523bbd08fa0736d`.

This handoff packages the discussion and all durable run artifacts through the implementation handback on September 11, 2026. It is a synthesized discussion record, not a verbatim chat transcript. Research claims retain their original observation dates and uncertainty; this packaging step did not refresh upstream repositories or reverify the YouTube transcript.

## Pick up on another computer

Use a dedicated workspace so the original relative Flow paths resolve:

```sh
mkdir -p ~/work/flow-evidence
cd ~/work/flow-evidence
git clone --branch feat/architecture-evidence-pilot git@github.com:andyconley/flow.git flow-architecture-pilot
cd flow-architecture-pilot
python3 docs/handoffs/architecture-quality-evidence/restore.py --verify-only
python3 docs/handoffs/architecture-quality-evidence/restore.py --destination ../.flow/runs/architecture-quality-evidence
```

The restore script verifies the compressed archive and every file digest, rejects unsafe archive entries, and refuses to overwrite an existing destination. It needs only Python's standard library. Allow roughly 0.5 GB of disk space for extracted run artifacts, plus the checkout. You do not need analyzers installed to read the saved reports or inspect the evidence.

Start with `../.flow/runs/architecture-quality-evidence/evidence/review-exercise/README.md`. Follow its assigned order and open only the material for the current case. Do not inspect the private scoring oracle or all generated reports before the timed exercise. Fill the four blank review records with actual times, findings and decisions. Complete the browser checklist during the appropriate evidence-assisted case.

To verify a saved packet against its durable candidate source, from the checkout:

```sh
python3 scripts/architecture_evidence_pilot.py verify \
  --packet ../.flow/runs/architecture-quality-evidence/evidence/final/case-b-packet \
  --candidate ../.flow/runs/architecture-quality-evidence/evidence/review-exercise/case-b/candidate-source \
  --report ../.flow/runs/architecture-quality-evidence/evidence/final/case-b-report.html
```

Verification establishes file/identity consistency, not acceptance of the candidate. Do not edit archived JSON to substitute new machine paths: those bytes are evidence. Historical absolute paths are retained as provenance; new collection uses a new config and new output directories.

## What we discussed and decided

The original research request concerned Uncle Bob Martin's recent work on CRAP, cyclomatic complexity and agentic coding, with a requested cutoff of December 2025 onward. The discussion narrowed to his source-derived architecture visualization, then to the Flow stage needed to assess a comparable enhancement. The recommendation was definition first, then solution and plan, before implementation or tool selection.

We separated three needs:

| Need | What it answers | Pilot treatment |
| --- | --- | --- |
| Architecture visualization | What structure and dependencies does this source actually have, and what changed? | Baseline/candidate/delta graph with source drilldown. |
| Dependency-boundary enforcement | Does the change violate an explicitly approved architectural rule? | Direct-import prohibitions and new-cycle detection; isolated checker only. |
| Code-quality evidence | What evidence supports confidence in the changed behavior, and where is it weak? | Complexity, statement coverage, separate branch counts, CRAP and targeted mutation outcomes. |

Code-quality evidence is the third category; it can annotate the architecture view but is not itself a dependency rule. CRAP combines complexity and coverage: `C² × (1 − coverage)³ + C`. Its coverage definition matters. A Python statement percentage must not be silently compared with a Java instruction or branch percentage. Mutation testing asks whether tests detect a deliberate behavioral defect; a survivor is not automatically equivalent, and a timeout is not a kill.

One early user message used “mutex testing.” The approved solution and delivered pilot concern **mutation testing**. Mutex/concurrency correctness testing is a different concern and was not implemented in this scope.

Andy required a modular language layer for Python, TypeScript/Node.js, C# and possibly C++. We therefore kept Flow's graph/evidence contract, baseline comparison, policy and presentation separate from analyzers. The Python pilot is real; a hand-authored TypeScript-shaped fixture exercises the shared contract. It does not establish TypeScript analysis. C# and C++ remain future adapters, with build context and language semantics to be designed separately.

## Bob's tools and the reuse decision

The discussion initially considered actual forks/extensions of Bob's publicly visible repositories. Research identified useful behavior in architecture drilldown, dependency checks, CRAP, mutation scheduling/results and acceptance-pipeline contracts. The inspected repositories did not establish a broad license grant; those observations are dated research, not a claim about their current legal status.

Andy then supplied [the YouTube discussion](https://www.youtube.com/watch?v=zcLPGC-tvgk) and explained Bob's advice: point an agent at the implementations as examples and build your own version for your project. The retrieved page did not provide a transcript, so the attribution remains Andy's account rather than a verified direct quote. **The approved direction superseded the fork-first proposal: independently implement Flow's design, using Bob's tools as behavioral references.** No Bob source was copied or translated into this pilot.

| Reference | Behavior worth studying later | Flow boundary |
| --- | --- | --- |
| [arch-view](https://github.com/unclebob/arch-view) | Architecture projection, cycles, drilldown and file-input seam. | Reference for interaction and traceability; Flow uses a browser viewer and explicit hierarchy. |
| [dependency-checker](https://github.com/unclebob/dependency-checker) | Allowed/forbidden dependencies, cycles and exception semantics. | Flow evaluates engineer-approved rules over normalized edges. |
| [crap4clj](https://github.com/unclebob/crap4clj), [crap4java](https://github.com/unclebob/crap4java) | Metric reports and attribution. | Language-specific complexity and coverage remain adapter responsibilities. |
| [clj-mutate](https://github.com/unclebob/clj-mutate), [mutate4java](https://github.com/unclebob/mutate4java) | Differential scheduling, fingerprints, isolated workers and native results. | Future behavior references; operators, builds and execution remain language-specific. |
| [Acceptance-Pipeline-Specification](https://github.com/unclebob/Acceptance-Pipeline-Specification) | Portable acceptance representation and runner/worker contracts. | Later exploration; example-value mutations are distinct from application-source mutations. |
| [dry4clj](https://github.com/unclebob/dry4clj) | Duplication evidence and syntax normalization. | Deferred capability. |
| [swarm-forge](https://github.com/unclebob/swarm-forge) | Agent hardening workflow. | No wholesale orchestration fork; Flow retains lifecycle ownership. |

The detailed, superseded and final positions are retained in [bob-reuse.md](run/research/bob-reuse.md). Read its superseding direction first; lower sections preserve earlier proposals and are not active instructions.

## Approved solution and workflow

1. Collect immutable baseline and candidate snapshots in isolated environments, with source/config/tool identity and complete declared inventory.
2. Validate provenance before evaluating policy. Missing required evidence produces inconclusive.
3. Show structural changes, new cycles and forbidden edges with source references and explicit capability limits.
4. Attach required evidence for the one selected function. Numeric quality measures remain advisory.
5. Record engineer disposition in the existing review artifact. Flow's existing acceptance authority remains in place.

Tach supplies Python static internal imports and source-line reports. Cytoscape.js supplies graph rendering primitives; Flow owns the UI. Radon, coverage.py and mutmut supply distinct quality capabilities. The shared layer owns normalization, identity, policy and presentation. None of these dependencies is treated as a universal analyzer or a replacement for review.

The approved four chunks were graph/viewer, boundary comparison, selected-function quality/mutation and measured review integration. Andy approved all four, an isolated checkout and interactive local presentation. The lane proceeded through definition, solution, plan and implementation approvals. The recorded lifecycle is `handback_ready`, meaning ready for acceptance review, not accepted or archived.

## What is implemented

| Surface | Implementation |
| --- | --- |
| CLI | [architecture_evidence_pilot.py](../../../scripts/architecture_evidence_pilot.py): `collect`, `compare`, `render`, `verify`; separate from installed Flow commands. |
| Contract and integrity | [model.py](../../../scripts/architecture_evidence/model.py), [snapshot.py](../../../scripts/architecture_evidence/snapshot.py), schema and canonical hashes. Source excerpts and raw artifacts are bound to evidence. |
| Rules and deltas | [policy.py](../../../scripts/architecture_evidence/policy.py), [delta.py](../../../scripts/architecture_evidence/delta.py): approved direct-import rules, cyclic-edge comparison and baseline ledger. |
| Python adapters | [adapters](../../../scripts/architecture_evidence/adapters): Tach, Radon, coverage and mutmut. |
| Local report | [report.py](../../../scripts/architecture_evidence/report.py), vendored Cytoscape and asset manifest. Inline data/assets; source text is inert. |
| Tests | Four `tests/test_architecture*.py` modules and contract/config/policy fixtures. |
| Design and usage | [pilot guide](../../architecture-evidence-pilot.md), [ADR 0010](../../adr/0010-separate-architecture-evidence-from-language-tools.md). |

The graph pilot scans Flow's CLI context and enforces approved collector/watermark boundaries. The selected quality specimen is `cli/jsonl_watermark.py::read_new_lines`. Fresh disposable collection ties coverage and mutation proof to source identity. Coverage uses an explicitly labeled supplemental behavioral harness; 64 existing collector tests were checked separately. It is not whole-suite coverage.

New prohibited edges and new cyclic edges fail the isolated checker. Existing violations remain visible; a touched baseline violation requires disposition and leaves the overall result inconclusive. Invalid invocation returns 2; missing/stale/incompatible evidence returns 3; proven compare violations return 1. `render` and `verify` can succeed for an intact failing packet without accepting it.

The adapter supports the inspected flat Python static-import layout. Dynamic imports and unresolved-import classification are explicitly unsupported. Shared opaque IDs and explicit parent fields avoid baking Python namespace rules into the viewer. Cross-language calls, service traffic and runtime dependencies need separate evidence later.

## Validation and remaining acceptance

- Final focused suite: **29 tests passed**, including the pinned real-tool integration.
- Earlier full repository run: **1,019 tests, one skipped**. It preceded final narrow hardening; final focused tests cover those later changes.
- Real graph: **45 modules, 151 internal edges, 318 source references**; repeat collections agreed.
- Four final compare/render/verify sequences returned expected results. Wrong-candidate verification returned inconclusive.
- A direct policy mutation was caught by the covering test and restored.
- On the selected existing-function specimen, the same offset mutant survived a weak assertion and was killed by a stronger assertion. Actual import-path evidence points into the disposable mutant workspace. This is distinct from mutation coverage of all new pilot code.
- Independent CRAP vectors and invalid coverage denominators were checked. TypeScript-shaped contract validation/rendering is fixture proof only.

Four shared-layer review blockers were fixed and rechecked: touched baseline false pass, nested canonical ordering, invalid invocation exit code and report/receipt publication. Role capacity required reuse of existing agents; review independence is limited and explicitly described in the run. See [validation-results.md](run/validation-results.md) for check-by-check scope and limitations.

Browser automation rejected the local file URL and explicitly prohibited workarounds. No browser execution, keyboard accessibility or runtime network claim is made. Andy must perform the [browser checklist](run/browser-checklist.md) manually. The four timed reviews and expand/revise/defer judgment have not happened. Review materials and the separate frozen oracle are prepared; no times or decisions were invented. Pair 2 is less tightly matched than pair 1, so report that limitation and do not claim a causal speedup.

## Artifact map

| Item | Contents |
| --- | --- |
| [run/](run/) | Readable exact copies of requirements, approvals/state, solution, plan, validation plan, research, briefs, role reviews, reconciliations and handoff. Historical drafts remain labeled as history. |
| [run-artifacts.tar.xz](run-artifacts.tar.xz) | Complete durable run, including all evidence, intermediate attempts, final packets/reports/receipts, raw tool results, review sources and private scoring oracle. |
| [artifact-manifest.json](artifact-manifest.json) | Archive hash plus size and SHA256 for every archived file. |
| [restore.py](restore.py) | Portable verification and extraction; no third-party dependencies and no overwrite. |
| `evidence/final/` after restore | Final source snapshots, four packet directories, standalone reports, receipts and command results. Prefer these over earlier runs. |
| `evidence/run-v2/weak-strong-proof/` after restore | Successful weak/strong mutation behavior proof; earlier tool-code identity is preserved. |
| `evidence/review-exercise/` after restore | Review order, source diffs, requirements, candidate sources, blank review forms, treatment reports and separately frozen oracle. |

All 26,316 durable run files are preserved, including raw intermediate diagnostics; the exact count and bytes are authoritative in the manifest. Disposable tool environments, downloaded wheel caches and unrelated Codex conversations/checkouts are not run artifacts and are not included. The source implementation is ordinary branch content. Original absolute machine paths remain inside historical evidence and are not prerequisites for reading or verifying restored packets.

## Recreate tools only when new collection is needed

The supplied lock targets macOS arm64 and Python 3.14. On that platform, from the checkout:

```sh
python3.14 -m venv ../pilot-tools
../pilot-tools/bin/python -m pip install --require-hashes -r scripts/architecture_evidence/requirements.lock
FLOW_ARCHITECTURE_PYTHON="$(cd ../pilot-tools && pwd)/bin/python" python3 -m unittest discover -s tests -p 'test_architecture*.py'
```

Copy the config fixture outside the source checkout and replace its executable placeholders with absolute paths to the new environment. Keep the archived config and policy receipts unchanged. A different OS/Python requires a newly resolved and verified platform lock; the current lock is not a cross-platform promise. Use fresh output locations for new collection, preserving existing evidence and approvals. Follow the pilot guide for command order and receipt semantics.

The original `.flow` artifacts belonged to the workspace above the checkout. Restoring them at the documented location preserves that relative layout. It does not install Flow or synthesize project configuration. If lifecycle CLI discovery on the new host needs setup, inspect that host's existing Flow configuration before changing it. The documents and direct pilot commands remain usable independently.

## Resume instructions for the next agent

Read this README, `run/plan.md`, `run/validation-results.md` and `run/review.md`. Verify the archive and restore it as shown. Use final evidence, not historical failed attempts, for the current state. Preserve approved scope and policy. Do not restart discovery, silently change thresholds or claim missing human evidence is complete.

The immediate next work is manual browser validation and the four-review exercise, followed by scoring and Andy's expand/revise/defer decision. Fix any observed defects in this branch with fresh evidence and appropriate tests. Only after the missing acceptance evidence is resolved should the normal Flow review/acceptance process advance. Do not merge, release, install or expand languages merely because the implementation is committed.
