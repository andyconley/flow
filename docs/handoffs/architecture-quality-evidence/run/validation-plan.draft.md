# Validation expectations — shaping draft

This is implementation proof to execute after plan approval, not completed test evidence. Use the isolated checkout and pilot source/config identities in planning-proposal.md. The root coordinator reconciles role findings; an independent reviewer examines source provenance, policy oracles and mutation proof before pilot acceptance.

| Proof | Method and required outcome | Criterion |
| --- | --- | --- |
| Repeatability | Two extractions into different directories produce byte-identical canonical graph JSON; manifests retain separate timing and exact tool/config identity. | A1 |
| Inventory | Every file under declared roots has one processing disposition; dynamic/unresolved import records are visible; an injected missing module record forces inconclusive. | A1–A3 |
| Source graph oracle | Hand-authored small import fixtures assert exact nodes/edges and 1-based source spans, including repeated imports, removed edges and unresolved targets. Real CLI baseline manually checked for pilot rules. | A2 |
| Boundary rules | Clean candidate passes; new watermark-to-collector and collector-to-harvest imports fail. Self-cycle, new component cycle and added cyclic edge inside an old component fail; removal-only cycle reduction does not become a new cycle. Existing violations stay in baseline ledger. | A3 |
| Integrity | Change candidate bytes, policy digest, adapter version/config, required raw artifact, or source excerpt after collection: never pass. Proven violation plus missing evidence remains visible under overall inconclusive. Unsupported schema rejected before rendering/evaluation. | A1/A3/A7 |
| Language contract | Hand-authored TypeScript-shaped fixture with opaque IDs, explicit hierarchy, source spans and unsupported metrics passes the same validator, viewer and policy tests without shared-code edits. Label fixture-only support. | Approved solution |
| Metric calculations | Independent examples: C=5, coverage=1 gives CRAP=5; C=5, coverage=0 gives 30; C=5, coverage=0.5 gives 8.125. Reject invalid fractions and missing/zero denominator; branch and statement units never silently merge. | A4 |
| Real selected function | Preserve Radon/coverage raw results, source hash and native function mapping. Changed or renamed function requires new evidence. Baseline research result C=5, statements 18/18, branches 6/6 is a historical observation, not an expected candidate value. | A4 |
| Mutation behavior | Baseline passes. Prove imported module is within disposable mutant workspace. Hold source/operator constant: selected mutant survives weak assertion and is killed by strengthened behavior test. Preserve operator, location, test hash, tool version, commands, timings and native result records. No generated mutants or tool failure is inconclusive. | A5 |
| Mutation status | Fixture adapter output covers killed, survived, timeout, skipped and tool failure; uncovered is derived only from actual coverage. Equivalent is a separate reasoned reviewer disposition, never guessed from survival. | A5 |
| Browser behavior | Open report offline in supported local browser, then move it away from source checkout. Inspect baseline/candidate/delta, filters, reset, node/edge details and source excerpts. Verify loading, empty, filtered-empty, invalid-data and partial states. Keyboard-only node/edge list and controls work; status is not color-only. | A2 / solution |
| Browser safety | Hostile labels/source containing HTML and closing-script text display literally; path traversal/unsafe links rejected; no external requests during viewing; source contents are never executed. | Local report contract |
| Review binding | Existing review.md links packet, policy and source identities. Controlled wrong-candidate link yields inconclusive; packet regeneration cannot silently alter an existing review. | A7 |

## Test execution shape

Use standard unittest fixtures for deterministic policy/model/adapter behavior, subprocess integration tests for CLI outcomes and a real browser check for local report behavior. The new test module is `tests/test_architecture_evidence.py`; add browser test harness only as isolated development tooling. Never claim screenshots alone prove graph or metric correctness. Raw adapter logs and source/oracle assertions supply that proof.

Targeted invocation is `python -m unittest discover -s tests -p 'test_architecture_evidence.py'` because tests is not a Python package. Exercise `verify` against intact and tampered report receipts, viewer assets and candidate source; an intact failing packet verifies integrity successfully while retaining its failing policy result.

Baseline selected tests exist at `tests/test_flow.py:4103` (CodexCollectorTests) and `:4531` (ClaudeCollectorTests). Run them from the isolated checkout with `PYTHONPATH=cli:tests python -m unittest test_flow.CodexCollectorTests test_flow.ClaudeCollectorTests`. During mutation, run equivalent selected pytest nodes only after proving import resolution into the mutated workspace. Use disposable data and test directories.

At integration completion run `python -m unittest discover -s tests` and `git diff --check` in the isolated checkout, plus the documented pilot/browser checks. Generated-help and sync checks apply only if implementation unexpectedly changes those surfaces; proposed pilot avoids them. Record commands, interpreter/platform, exit codes and artifact paths in validation-results.md. Existing baseline failures are recorded and distinguished from regressions, not hidden by reruns.

## Four-review exercise

The implementing engineer prepares two matched pairs of distinct controlled real-code changes and freezes a separate oracle before Andy sees review materials. Include at least one clean change, forbidden dependency, new cycle and complex/undertested function or weak assertion across the four cases; defects may coexist. Keep mutation weak/strong test proof separately reproducible. Do not present the same exact diff twice.

Within each pair keep size and seeded-defect difficulty comparable; record the matching rationale. Pair 1 order is ordinary review then evidence-assisted review; pair 2 reverses that order. Each review receives the same kind of requirements, source diff and tests. Only treatment receives generated architecture/quality evidence. The oracle is not bundled with either condition. Timer starts when review materials open and stops on written disposition. Record preparation/collection time separately.

Per case record: case/source ID, pair and condition/order, elapsed review time, disposition, structural explanation with source references, confidence, found seeded defects, missed defects and false positives. Independently validate unexpected real defects before counting them as false positives. One reviewer and four cases yield directional evidence only; acknowledge learning and expectation bias.

Finish with two distinct outcomes: technical proof complete/incomplete, and Andy's expand/revise/defer judgment with measured overhead. Missing proof is not completion; a completed exercise can honestly recommend defer. Any missed seeded architectural violation prevents expand until revision. Do not create a speedup threshold or treat an unsuccessful hypothesis as permission to omit results.
