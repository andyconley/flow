# Implementation quality review: repair-3 candidate T

## Review Summary

### Verdict

- **NOT READY for formal `flow-review`.** The active six-role behavior is
  internally consistent, but candidate digest `T` does not cover the complete
  production range that will ship, and the mutation evidence does not meet the
  approved receipt contract. Acceptance criteria 7 and 10 therefore remain
  unproven.

### Expected-content inventory

This inventory was derived from the approved requirements and acceptance
criteria before comparing the implementation evidence.

| Criterion | Required content and proof | Comparison result |
| --- | --- | --- |
| 1 | Parsed manifest set equals the six named composed roles; PM/QR absent. | Pass. The source, focused test, and final receipt agree on the exact set. |
| 2 | Frozen architect/lead-developer/test-engineer bodies and corpora; role ownership, source metadata and locators, forward/reverse joins; one generated section in each adapter. | Pass. Frozen hashes, release map, corpus inspection, focused tests, and isolated adapter record agree. |
| 3 | Three-role-only release map with body/corpus hashes, entry IDs, locators, source revision, passing gate, result, and four immutable records per role. | Pass. `release-evidence-map.json`, the final receipt, and current release summary agree; PM/QR are absent. |
| 4 | PM/QR exact base bodies remain invocable and have no composed declaration, selected corpus, active reverse edge, or generated Expertise section; refreshed Claude/Codex outputs reflect that state and guards reject reintroduction. | Pass for active state. Source tests, final receipt, isolated output hashes, and installed readback agree. Mutation execution proof has the criterion-7 gap below. |
| 5 | All 112 protected historical files remain byte-identical and visibly failed; current evidence stays outside protected roots and makes no pass implication. | Pass. The protected inventory and direct final-validator run report 112 matching per-file hashes and matching tree digests; current summary preserves the failed disposition. |
| 6 | Start-anchored final receipt checks every protected path and all six retained hashes, detecting missing/replaced paths and unexplained deltas. | Pass. The final validator directly produced 165 checks and zero failures from the frozen inputs. |
| 7 | Deterministic guards for cohort, inactivity, retained schema/joins/rendering/current claims, plus three separately executed and restored mutations with reproducible receipts. | **Not proven.** The guards pass and the mutations are described, but the required mutation receipt fields are absent. |
| 8 | Focused/full/help/diff/sync/adapter/static-smoke/doctor checks against the final candidate, plus dated Claude and Codex `test-engineer` observations with expected method/model/effort. | Pass for candidate behavior, subject to correcting the manual-cell description. Direct reruns passed 49 focused and 996 full tests, diff check, static smoke, and both doctor modes. The native record contains conclusive responses and configured identities. |
| 9 | Every fixed current surface says three added roles and six composed roles, while immutable historical roots remain excluded and retain their failed language. | Pass. The inspected active documents are scoped correctly and the only five/eight-role references on the active surface describe rejected or historical states. |
| 10 | Complete production delta from `origin/main` through the scoped working tree is classified, within the approved boundary, and bound into `T`; exceptions are explicitly dispositioned. | **Fail.** Two shipping production paths in `origin/main..HEAD` are absent from both the classification and `T`. |

### Findings

#### Critical

- **[`evidence/change-surface.json`:146, 153-181] `T` omits two production
  files that ship in the required review range.** Direct comparison of
  `origin/main..HEAD` plus the scoped working tree found changes to
  `cli/expertise.py` and
  `docs/adr/0008-author-expertise-entries-as-json-ld-per-role.md`. Neither path
  appears among the 27 paths hashed into `T`, and `out_of_scope_changes` is
  empty. This conflicts with acceptance criterion 10 and the plan's requirement
  to review the complete `origin/main..HEAD` predecessor range and later prove
  every production file in `C` matches `T` (`plan.md`:104-106, 180-193).
  Rebuild the change-surface ledger from the complete release delta, classify
  both paths as inherited predecessor production changes or explicit scope
  exceptions, add every shipping production path to the digest, calculate a
  new `T`, and rebind affected evidence before formal review.

  Alternative explanation considered: `2712f5f` could be an already accepted
  baseline, making `T` intentionally limited to repair-3's working-tree delta.
  The approved plan rules that out for this release: `origin/main` is still at
  `090b4df`, the three predecessor commits must be carried into `C`, and formal
  review explicitly covers the complete predecessor range. Those two files
  therefore ship even though repair-3 did not edit them after its start.

#### Important

- **[`evidence/mutations/pm-reintroduction.md`:3-14;
  `retained-role-removal.md`:3-12; `semantic-negation.md`:3-15] The mutation
  records are summaries, not the required receipts.** None retains the command,
  original and mutated SHA-256 values, diagnostic excerpt, or complete restored
  SHA-256 required by `validation-plan.md`:80-83. The validation result's claim
  that detailed commands, hashes, exit statuses, and diagnostics are present
  (`validation-results.md`:72-73) is false. The described mutations are
  well-chosen and would be strong if observed, but these artifacts do not let an
  independent reviewer distinguish an executed failing mutation from an
  implementer assertion. Rerun all three separately, capture every required
  field and the successful post-restoration focused run in each receipt, then
  regenerate the validation result against the new `T`.

- **[`validation-results.md`:40-53] Most final command results lack the durable
  command evidence promised by the validation plan.** The table reports times
  and outcomes but no log paths, and the run contains no final logs for the full
  suite, help check, sync checks, smoke, or doctor despite
  `validation-plan.md`:62 requiring command, start/end time, exit status,
  source/tree identity, and log path. I directly reproduced the focused and full
  suites, final verifier, diff check, smoke, and doctor results, so this is an
  evidence durability gap rather than a detected behavior failure. Persist
  bounded outputs or structured receipts for every final command and bind each
  to the corrected `T`; label prior table-only entries as implementer-reported
  until then.

- **[`validation-results.md`:49] The static-smoke transfer wording conflates
  direct closure with an approved substitution.** `flow runtime smoke` currently
  emits two command-discovery cells and two role-invocation cells that name
  `support-lead`. The Claude and Codex `/flow-status` cells are directly closed.
  The approved repair-3 plan deliberately supersedes the generic role cells with
  a stronger, change-relevant `test-engineer` matrix; those cells were not
  literally executed as written. Revise the record to say exactly that. No
  extra `support-lead` invocation is required, and the plan-specific native
  matrix satisfies criterion 8.

#### Suggestions

- Record the strict-doctor variance as an accepted improvement in the formal
  disposition. The approved baseline named five warnings; direct observation
  now shows four because `telemetry.claude.harvest` remains present and changed
  to `ok` after the fresh harvest. Both doctor modes have zero errors, no warning
  was added or raised in severity, and no production doctor code changed. This
  meets the safety purpose of the frozen set, but the explicit disposition is
  needed because the validation plan used exact-set language.

### Requirement Fit

- The production behavior fits the narrowed three-role requirement: architect,
  lead-developer, and test-engineer are active; business-analyst, SRE, and
  support-lead remain active; PM/QR match their frozen bases and are inactive.
- Historical preservation is unusually strong: the start inputs are separate
  from the final receipt, all 112 protected paths are checked individually, and
  aggregate tree hashes remain supplementary.
- No candidate PM/QR experiment, provenance-only admission policy, routing,
  retrieval, overlay, or unrelated role change was found in the repair-3
  working delta. The complete shipping range still needs the two predecessor
  paths classified and bound into `T`.
- Security and UI dimensions do not apply to this configuration/documentation
  narrowing. Operational and release-identity risk do apply and are addressed
  by the `T -> C -> R` contract once `T` is complete.

### Validation Fit

- **Directly observed in this review:** 49 focused tests passed; 996 full tests
  passed; the final frozen validator returned 165 checks and zero failures;
  `git diff --check` passed; static runtime smoke returned `ok: true` with four
  manual cells; normal doctor returned exit 0 with four warnings and no errors;
  strict doctor returned its expected exit 1 with the same four warnings and no
  errors; the two omitted `T` paths were found by direct Git-range comparison;
  stored Codex parent/child transcript files match the hashes in the live record.
- **Artifacts read:** approved requirements, acceptance criteria, plan,
  validation plan, implementation handoff, production diff, start/final and
  change-surface receipts, preservation and release maps, isolated adapter
  inspection, live-client record, current docs, tests, and all three mutation
  summaries.
- **Implementer-reported but not durably reproduced by its cited artifact:**
  original timestamps and outputs for user sync/check, help drift check, the
  isolated adapter commands, mutation executions, and the Claude raw capture.
  The live-client JSON embeds the Claude response and the complete Codex
  transcript hashes are independently resolvable, so the native result is
  conclusive; the absent mutation details are not.

### What's Done Well

- PM/QR inactivity is checked across source hashes, manifest state, absent
  baseline corpora, loader behavior, shared rendering, isolated outputs, and
  installed outputs rather than inferred from one surface.
- The three-role release map is exact, hash-addressed, and excludes the two
  failed roles while retaining their failed evidence unchanged.
- Native Claude and Codex checks use the same concrete malformed-email fixture
  and expose the expected method, model/effort, observable error, test level,
  and failure path.

### Residual Risks

- Until `T` covers the complete shipping production range, a later `C == T`
  check can succeed for its listed paths while silently omitting production
  behavior that will be merged.
- Until mutation commands, hashes, and diagnostics are retained, criterion 7
  depends on the implementer's account rather than independently reviewable
  evidence.
- Candidate native evidence does not prove the post-release install. The
  approved second Claude/Codex matrix after `R` remains mandatory.
- Remote `main` may advance after this point; the planned pre-integration fetch
  and affected revalidation remain necessary.

**Acceptance disposition: NOT READY.** Correct the `T` boundary and mutation
receipts, refresh the bound validation artifacts, and then enter formal
`flow-review`.

---

## Resolution and re-review — 2026-09-10

This section preserves the initial findings above and records their disposition
against corrected candidate `T`
`4e0a00b81c22d5a7cc2136018188e117893e9ff592813b3ccdb53be400dd8f33`.
The verdict in this section supersedes the initial readiness verdict for the
corrected candidate.

### Finding resolutions

| Initial finding | Resolution | Re-review evidence |
| --- | --- | --- |
| Critical: `T` omitted `cli/expertise.py` and ADR 0008. | **Resolved.** | `evidence/change-surface.json` now defines the complete `origin/main` through HEAD plus scoped working-tree review range, classifies both paths as inherited predecessor production, and includes them in a 29-path digest. A direct Git-range comparison found no changed production-like path outside `T`. The final verifier checks both required predecessor paths, all 29 current states and hashes, the production digest, and the passing change-surface verdict. |
| Important: mutation summaries lacked required receipt fields. | **Resolved.** | Each of the three receipts now records target, original/mutated/restored SHA-256, timestamps, exact failing and restoration commands, expected/observed exits, diagnostics, and raw fail/restoration logs. The raw logs show the named guards failing for PM reintroduction, test-engineer removal, and semantic negation, followed by 49 passing tests after byte restoration. |
| Important: final command results lacked durable logs. | **Resolved.** | `evidence/logs/receipt.json` indexes 17 bounded command logs with command, start/end time, expected/observed exit, verdict, and SHA-256. I independently recomputed every indexed log hash with zero mismatches. The final verifier also checks each log hash and binds the receipt to corrected `T`. |
| Important: smoke record claimed all four generic cells were literally closed. | **Resolved.** | `validation-results.md` now says the two command-discovery cells were directly executed and the two generic `support-lead` prompts were superseded by the approved, stronger Claude/Codex `test-engineer` matrix. It claims no `support-lead` result. |
| Suggestion: explicitly disposition the five-to-four doctor warning change. | **Resolved for implementation review; retain in formal disposition.** | The validation record now says the implementation quality and SRE reviews accept the operational improvement while formal review must record the evidence-contract variance. Durable normal and strict doctor logs show zero errors and four warnings; `telemetry.claude.harvest` remains present as `ok`. |

### Re-reviewed acceptance inventory

| Criterion | Corrected disposition |
| --- | --- |
| 1 | Pass: exact six-role parsed composition remains verified. |
| 2 | Pass: retained hashes, ownership, sources, locators, joins, and both adapter outputs remain verified. |
| 3 | Pass: the frozen release map remains exact to the three passing additions and its records remain hash-valid. |
| 4 | Pass: PM/QR exact base bodies, inactivity, generated absence, installed reconciliation, and reintroduction detection remain verified. |
| 5 | Pass: all 112 protected historical paths remain byte-identical and visibly failed. |
| 6 | Pass: the expanded final receipt now returns 249 checks, zero failures, and retains start-anchored per-file proof. |
| 7 | Pass: deterministic guards and all three separately restored mutations now have reproducible, hash-indexed evidence. |
| 8 | Pass: final command logs, isolated and installed adapter inspection, and persisted Claude/Codex captures are bound to corrected `T`. The plan-specific native matrix satisfies the role check; the doctor improvement is explicitly dispositioned. |
| 9 | Pass: current release claims remain three added roles and six composed roles, with historical failure language excluded from current-claim interpretation. |
| 10 | Pass: all shipping production-like paths found in the complete release delta are included in the 29-path `T`; the predecessor `.flow/memory/STATE.md` commit blob and excluded working delta are separately classified with distinct hashes and commit behavior. |

### Evidence observed on re-review

- **Directly observed:** the corrected change-surface content; zero production
  paths outside `T` from an independent Git-range/working-tree comparison; the
  final verifier returning 249 checks and zero failures; recomputation of all
  17 command-log hashes with zero mismatches; mutation fail/restoration log
  contents; and raw Claude/Codex capture hashes.
- **Artifacts read:** corrected validation results, all three mutation receipts,
  log receipt, live-client record, raw native captures, change-surface ledger,
  and final receipt.
- **Implementer assertions remaining:** the observer attribution and historical
  execution circumstances in the native record. Their material outputs,
  identities, hashes, and transfer to `T` are now persisted and verifier-bound,
  so no acceptance criterion depends on an unbacked assertion.

### Remaining risks

- Formal review must explicitly accept the safer four-warning doctor set because
  the approved validation plan froze an exact five-warning baseline.
- The reviewed candidate still precedes `C`, merge, semantic release `R`, and
  post-release installed-client readback. The approved `T -> C -> R` identity
  checks and second native matrix remain mandatory and cannot be inferred from
  this pre-release review.
- Remote `main` can move before integration; the planned fetch and affected
  revalidation remain required.

### Re-review verdict

**READY for formal `flow-review`.** All initial critical and important findings
are resolved for corrected candidate `T`; no new acceptance-readiness defect was
found.
