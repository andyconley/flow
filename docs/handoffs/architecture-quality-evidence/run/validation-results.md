# Implementation validation — 2026-09-11

Status: code ready for acceptance review. Technical proof remains incomplete because browser runtime checks have not run. Pilot acceptance and expansion are pending Andy's four-case exercise and judgment.

## Executed checks

| Check | Observed result | Scope and transfer verdict |
| --- | --- | --- |
| Full repository unittest discovery | 1019 tests, OK, 1 skipped; 248.108 seconds. `evidence/full-suite.txt`. | Direct regression run in isolated checkout before final narrow hardening. This is not an exact-final-bytes full-suite claim. |
| Final focused unittest discovery | 29 tests, OK; 7.449 seconds. `FLOW_ARCHITECTURE_PYTHON=/private/tmp/flow-architecture-tools/bin/python python3 -m unittest discover -s tests -p 'test_architecture*.py'`; `evidence/focused-tests-final.txt`. | Direct final implementation checks, including pinned-tool integration. |
| Real graph extraction | 45 modules, 151 internal direct-import edges, 318 source references; two extractions agreed. | Real v0.28.0 Flow specimen; proves this flat Python layout, not arbitrary repository or runtime-import completeness. See `research/implementation_graph.md`. |
| Four final packets | Compare, render and verify produced expected codes for all four cases. | Real controlled source copies through final tool implementation; `evidence/final/command-results.json`. These outcomes are evidence, not human review decisions. |
| Wrong-candidate binding | Verify exited 3 with candidate identity mismatch. | Direct final packet against a different durable candidate; `evidence/wrong-candidate-check.json`. |
| Model, policy and integrity regressions | Passing focused tests cover source/config/packet tampering, spans, inventory, cycles and touched baseline disposition. | Direct checks of changed code. Fixtures do not prove general analyzer completeness. |
| CRAP arithmetic | Independent expected values 5, 30, 8.125 accepted; zero denominator, negative and excessive numerator rejected. | Direct shared validator checks; `evidence/supplemental-contract-checks.json`. |
| Language contract | Opaque TypeScript-shaped IDs accepted by shared model, policy test and renderer. | Hand-authored contract fixture only. No TypeScript, Node.js, C# or C++ analyzer implementation claim. |
| Viewer source and asset checks | Eight tests pass; vendored asset hash, inert hostile JSON, local assets, projection and control construction checked. | Direct generator/source checks. Browser execution, accessibility and actual network behavior remain unverified. |
| Policy mutation | Temporarily disabled violation detection; covering test failed; original code restored. | Direct mutation check of new policy implementation; `evidence/policy-mutation-check.txt`. |
| Selected-function mutation | Same offset mutant survived weak test and was killed by stronger behavior assertion; import proof points inside disposable mutants workspace. | Real mutmut run on the approved existing `read_new_lines` specimen, not mutation coverage of all new pilot code. `evidence/run-v2/weak-strong-proof/`. |

The final source snapshots bind fresh quality output to each specimen. Radon complexity, statement coverage, separate branch counts, CRAP and native mutation outcomes are retained. Coverage comes from the explicitly identified supplemental selected-function behavior harness; it is not whole-suite coverage. The existing 64 collector tests were checked separately during collection. A native timeout remains a timeout, never a killed mutant or correctness claim.

Environment: macOS arm64, Python 3.14.6 analyzer environment; Tach 0.35.0, Radon 6.0.1, coverage 7.14.0, mutmut 3.7.0, Cytoscape.js 3.33.1. Hash-pinned distribution inventory: `evidence/tool-distributions.json` and checkout `scripts/architecture_evidence/requirements.lock`. The lock is platform-specific. Final snapshots also record collector and entrypoint digests.

## Review disposition and limits

Independent shared-code review found four blockers: touched-baseline false pass, nested canonicalization, invalid invocation exit code and report publication. All four were corrected and rechecked by the reviewer; see `research/implementation_graph.md`. Report receipt is the completion marker; an interrupted unmatched report is not verifiable.

Browser tool policy rejected local file navigation and explicitly prohibited workarounds. No alternate browser or localhost route was used. `browser-checklist.md` records pending runtime proof. Dynamic imports and unresolved-import classification are explicitly unsupported by this adapter. The generated Tach overlay is collected as an artifact rather than a separate checked-in overlay directory.

The four-review exercise is prepared under `evidence/review-exercise/README.md`; times and decisions are blank. Pair 2 is less tightly matched than pair 1; record this limitation and do not infer a causal speedup from four reviews. Neither pilot acceptance nor production rollout is approved by these automated checks.

Local implementation commit: `71858ad0e99fa21ea310c21088d2ce60562b7e5d` on `feat/architecture-evidence-pilot`. Staged whitespace check passed; no push or installation.
