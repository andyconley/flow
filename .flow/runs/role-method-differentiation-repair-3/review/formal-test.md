## Review Summary

### Verdict

- Ready to accept/archive for the reviewed candidate `T` `4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`, subject to the formal acceptance record explicitly accepting the strict-doctor variance below. This is not an acceptance of commit, merge, release, or post-release installation: those are deliberately post-review `T -> C -> R` obligations.

### Findings

- Critical: none.
- Important: the approved validation plan required the frozen five-warning set from strict doctor, while final strict doctor has four warnings. `telemetry.claude.harvest` changed from warning to `ok` after the planned harvest refresh. The result has zero errors, no new or elevated warning, and the same release-relevant diagnostics remain `ok`; it is an improvement, but it is still a literal variance from the plan and must be recorded as an accepted deviation by the accepting reviewer.
- Suggestions: after commit, compare every production path in `C` to this exact `T` before integration, then obtain the required post-`R` native-client records. Candidate evidence cannot serve as that later proof.

### Evidence Read and Reproduced

- Read the approved definition, acceptance criteria 1-10, plan, validation plan, implementation handoff, production scaffold/configuration, JSON-LD corpora, composition test suite, receipts, mutation records and raw logs, current-claim search, live-client records and raw captures, implementation-quality review, and SRE release-readiness assessment.
- **Observed now:** `/opt/homebrew/bin/python3.12 -m unittest tests.test_expertise_composition` passed 49 tests; `verify_frozen.py --mode final` passed 250 checks with zero failures; `git diff --check` and `scripts/regenerate-flow-help.py --check` passed.
- **Read from durable, hash-bound evidence:** the final full suite passed 996 tests; user and isolated Claude/Codex sync/check, smoke, doctor, adapter readback, and current-claim checks have recorded expected exits and SHA-256 log receipts. The verifier rechecked each referenced log hash and both native raw-capture hashes.
- **Asserted only until delivery:** `C` equals `T`, remote integration, release workflow, semantic release `R`, refreshed install, and repeated live-client proof. They are correctly absent before formal acceptance and do not support this candidate verdict.

### Criterion-by-Criterion Assessment

| Criterion | Result | Proof and oracle strength |
| --- | --- | --- |
| 1. Exact six-role cohort | pass | The parsed manifest set equals architect, business-analyst, lead-developer, SRE, support-lead, and test-engineer. `test_manifest_marks_exactly_the_shipped_roles_composed` fails for an added PM and for a removed test-engineer declaration. |
| 2. Retained role/corpus integrity and composition | pass | Hash checks bind all three retained bodies and corpora to the start receipt; schema, source, locator, role-prefixed ID, forward/reverse joins, and a single shared-renderer section in each adapter are tested. `verify_frozen.py` independently repeats retained hash, map, locator, and active-cohort checks. |
| 3. Exact evidence map | pass | The map permits exactly architect, lead-developer, and test-engineer, requires pass gates, bodies/corpora/results, source locators, IDs, and four hash-checked experiment records per role. A missing retained declaration makes the exact-cohort guard fail. |
| 4. PM/QR base-only behavior | pass | PM and QR hashes equal their `2712f5f` controls; they are present in the manifest but not composed, have no active corpus, load no corpus, and render no Expertise section. The PM reintroduction mutation failed both cohort and inactive-surface guards. |
| 5. Historical failed evidence preservation | pass | The final verifier checks all 112 protected paths and both historical tree digests; each matched. The current release README is outside protected roots and calls the PM/QR treatment gates failed. |
| 6. Per-file final receipt | pass | `final-receipt.json` and the independent final verifier report 250 checks and zero failures, including retained hashes, protected paths, active state, complete candidate production surface, command logs, and raw captures. This is per-file proof rather than aggregate-only counting. |
| 7. Deterministic and restored-mutation proof | pass | Focused test suite passed on this review. Raw mutation logs show PM reintroduction (two named failures), test-engineer declaration removal (named set failure), and a negated lead-developer obligation with its former vocabulary preserved (positive-obligation regex failure). Every receipt records original/mutated/restored hashes and a post-restoration 49-test pass. |
| 8. Repository/runtime/native-client proof | pass with recorded doctor variance | The durable 996-test, adapter, sync/check, smoke, and normal-doctor evidence is successful. Native Claude and Codex records are both `observed`, tied to `T`, have hash-verified captures and installed/isolated output equality, configured model/effort, visible test-oracle method, and all four fixture-oracle elements. Strict doctor has the nonblocking four-vs-five warning variance described above. |
| 9. Current release claims | pass | The fixed-surface current-claim search and its focused test reject affirmative five/eight-role language. Current docs, summary, validation record, and handoff describe three additions and six total; historical/rejected references are explicitly classified. |
| 10. Bounded production surface | pass | The 29-path candidate manifest is hash-bound to `T`, explicitly includes the inherited loader and ADR paths, classifies PM/QR corpus removals as absent, and excludes the pre-existing unstaged `.flow/memory/STATE.md` delta. No retrieval, routing, overlay, schema, or renderer change is claimed within this candidate. |

### Validation Fit

- The core test oracles can fail on the wrong release rather than merely checking vocabulary. The three restored negative mutations specifically demonstrate cohort exclusion, retained-role completeness, and positive semantic obligation detection.
- Claude's live response supplies representative input, observable `row 7`/`email` error, integration test level, and recovery/error handling; Codex supplies the same four required elements. Both records bind to the exact candidate digest and raw capture hashes. This is stronger evidence than static generated text.
- The candidate/post-release boundary is sound: the acceptance plan requires candidate records now and repeats them only after `R`; no pre-release artifact is presented as a release observation.

### Residual Risks

- Formal acceptance must explicitly disposition the planned five-warning versus observed four-warning strict-doctor result. It should accept the improvement only because no release-relevant diagnostic regressed and normal doctor is `ok` with zero errors.
- The candidate has not yet become source commit `C` or release `R`. The required production hash comparison, remote reconciliation, four workflow jobs, public release checks, develop-install refresh, and post-release native records remain hard delivery gates.
