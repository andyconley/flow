# Plan analysis: active surfaces, lifecycle, and acceptance traceability

- Owner role: business-analyst
- Date: 2026-09-09
- Confidence: High for active source/evidence surfaces and acceptance mapping;
  medium for release publication details until the delivery plan names its
  branch, version, and release mechanism.

## Scope and current state

**Observed:** the run is in `planning` after `approve-definition` and
`start-plan`. The approved outcome is a six-role composed cohort: retained
architect, lead-developer, and test-engineer additions plus unchanged
business-analyst, SRE, and support-lead. Product-manager (PM) and
quality-reviewer (QR) remain invocable base roles, but lose active composition
and the two failed repair-2 methods.

The start receipt binds pre-mutation retained role/corpus hashes and its two
referenced evidence controls. The preservation inventory binds every protected
historical evidence file and the complete prior definition/review run. The
release-evidence map names the three passing roles, their source records,
role/corpus hashes, entry IDs, and primary/counter record hashes.

**Decision carried into planning:** do not change either protected evidence root
or the prior run. Do not run a PM/QR candidate screen. A later candidate screen
needs a separately approved work item and envelope.

## Active surface map

| Surface | Required final state | Why it is active | Change rule |
| --- | --- | --- | --- |
| `scaffolds/default/flow.toml` | Exactly six composed agents: architect, business-analyst, lead-developer, SRE, support-lead, test-engineer. PM/QR use the verbatim/default path. | It is the composition admission point used by the shared renderer. | Change permitted; verify exact set, not count. |
| `scaffolds/default/agents/product-manager.md` | Exact frozen pre-repair base body; no value-decay instruction. | This is the PM body users receive after sync. | Change permitted; compare to frozen control hash/content. |
| `scaffolds/default/agents/quality-reviewer.md` | Exact frozen pre-repair base body; no repair-2 alternative-explanation instruction. | This is the QR body users receive after sync. | Change permitted; compare to frozen control hash/content. |
| `scaffolds/default/expertise/product-manager.jsonld`, `quality-reviewer.jsonld` | Absent from shipped baseline. | Removal prevents accidental future admission and removes their active competency-edge source. | Removal permitted; this is separate from frozen evidence. |
| `scaffolds/default/expertise/competencies.md` | Remove only PM/QR terms, `Taught by` edges, and associated counts; retain all released-role terms/edges. | It supplies forward vocabulary and reverse joins. | Change permitted; test both joins and totals. |
| Retained three role bodies and `.jsonld` corpora | Byte-identical to start receipt. | They are the released methods/boundaries. | Protected: any delta blocks acceptance. |
| `tests/test_expertise_composition.py` | Six-role set, PM/QR inactivity, retained mapping, shared render, non-vacuous mutations. | It is the deterministic composition contract. | Change permitted; prove behavior/evidence, not only literals/counts. |
| `docs/architecture.md`, `docs/file-structure.md` | State six-role cohort; no current eight/five-role claim. | Current user-facing architecture statements. | Change permitted; historical evidence is outside this search scope. |
| New release summary, validation record, and handoff under this run | Name three passing roles and PM/QR failure; carry final receipt/live records. | They make the narrowed claim reviewable without altering history. | New/update permitted outside protected roots. |
| Generated Claude/Codex user outputs | PM/QR are base-only with zero expertise sections; each client observes one newly composed role's method/model/effort. | User-facing reconciliation result. | External state: refresh and readback required. |

### Scope exception to resolve before implementation

**Observed:** `.flow/memory/STATE.md` is already modified but acceptance
criterion 10 does not list it in the declared production change surface. The
delivery plan must add it as an explicit operational-handoff surface with an
expected delta, or leave it unchanged. It must not become a silent exception.

## Lifecycle and state record

| State | Required transition and record | Exit evidence |
| --- | --- | --- |
| Planning baseline | Record approved definition, receipts/maps, current commit, tracked-diff digest, and declared change surface. Validate orchestration before dispatch/shared mutation. | Inputs match receipt/map; scope agreed. |
| Implementation candidate | Restore PM/QR base bodies; remove active corpora/terms/declarations; update tests/current docs; create new current-release artifacts. Do not alter retained sources/history. | Diff contains only declared surfaces or explicit scope disposition. |
| Local verification | Run composition/join/render tests, both mutations, semantic-negation check, full suite, whitespace, adapter checks, static smoke, doctor; create final per-file receipt. | Logs, restored-mutation records, final receipt, candidate revision. |
| Formal review | Review all criteria, evidence map, final receipt, current-doc search, and validation record. | No unexplained delta, overclaim, scope exception, or missing live proof. |
| Commit and merge | Commit accepted final tree; record SHA and target/PR; verify merged revision. | Clean post-commit state and merged-SHA readback. |
| Release | Publish intended release from merged revision; record tag/version, release artifact/URL, and release notes. | Published identity resolves to merged SHA and says three-role expansion. |
| Develop/install refresh | Refresh verified source; run both user syncs and checks; capture generated outputs. | Install/source identity, sync/check results, PM/QR base-only bodies. |
| Live Claude and Codex proof | In each client, load one retained newly composed role and observe method plus configured model/effort. | Both dated records conclusive; either unavailable/inconclusive result blocks criterion 8. |

Merge, release, install, and live-client steps are sequential. A successful
static renderer check proves the shared generation path only; it cannot close a
pending client observation.

## Acceptance traceability

| Criterion | Observable artifact or check | Pass condition | False-pass guard |
| --- | --- | --- | --- |
| 1 — exact cohort | Parsed manifest test and generated-body inventory. | Exact named six-role set; PM/QR absent. | Set equality, not count. |
| 2 — retained methods/joins/rendering | Receipt comparison, schema/join tests, generated-body checks. | Each role matches body/corpus hash and source/entry mapping and renders in both adapters. | Corpus/source alone is not generated-body proof. |
| 3 — named behavioral evidence | Release-evidence map, new summary, record hashes. | Exactly three named roles, each with passing mapped gate/immutable records. | Reject count, duplicate, PM/QR record, stale hash, aggregate pass. |
| 4 — PM/QR inactive but usable | Frozen-control comparison, manifest/corpus/edge/render checks, refreshed install. | Base bodies match controls, roles invoke, no active expertise section. | Test each surface; empty corpus alone is insufficient. |
| 5 — failed history retained | Inventory comparison and current-summary/handoff review. | Every protected path/hash remains; current text names failure. | Renamed/replaced file or “superseded” is insufficient. |
| 6 — start/final preservation | Start receipt, final receipt, per-file report. | Final report references frozen start inventory; no unexplained mismatch. | Aggregate counts/hashes are supplementary. |
| 7 — deterministic guards/mutations | Focused tests and two restored mutations plus negation result. | Cohort/inactivity/joins/rendering/docs/mapping pass; each mutation first fails its guard. | One mutation or a substring check cannot prove both guards. |
| 8 — delivery/live clients | Test logs, install proof, two dated client records. | Automated checks and both client observations pass. | Static smoke/sync cannot substitute for a client. |
| 9 — current release language | Fixed active-doc search, new summary, validation, handoff. | Active surfaces say three roles/six total; protected history excluded. | Retained historical five-role text must not false-fail. |
| 10 — bounded change | Change-surface ledger and final diff classification. | Every production path is listed or blocking/dispositioned. | Passing tests do not waive unrelated changes. |

## False-pass ambiguities to keep visible

1. **Frozen PM/QR body source:** name the exact frozen-control path/hash.
   Removing highlighted sentences alone does not prove the pre-repair body.
2. **Base-role availability:** a source file can exist while adapters omit it or
   a stale generated copy retains expertise. Verify client/readback after sync.
3. **User overlay:** remove only shipped PM/QR baseline corpora; do not delete
   user-owned experience corpora. Verbatim PM/QR must prevent such corpus from
   rendering for this release.
4. **Active versus historical wording:** freeze the active-document search
   surface before validation; protected evidence must retain historical claims.
5. **Live-record schema:** record role, client, timestamp, installed revision,
   visible method marker, configured model/effort, observer, and result.
6. **Published identity:** record the relation from accepted candidate to commit,
   merge, tag, install source, and each client observation.

## Delivery slices

1. **Narrow active composition:** restore PM/QR base bodies; remove their
   baseline corpora, vocabulary edges, and composed declarations; update cohort
   tests.
2. **Make the claim reviewable:** update active docs and create release
   evidence/validation/handoff artifacts; build preservation/mutation proof
   without touching protected history.
3. **Deliver to users:** complete review, merge/release identity checks,
   develop-install refresh, adapter checks, and both live-client observations.

No PM/QR behavioral redesign, source adoption, candidate trial, retrieval,
routing, overlay, renderer, or corpus-format work belongs in these slices.

## Draft plan recheck

The draft plan, validation plan, and implementation handoff cover the approved
six-role workflow, protected-evidence receipt, `C -> S -> R` release lineage,
user-overlay boundary, current-versus-historical claim search, and both
candidate and post-release live-client observations. `.flow/memory/STATE.md`
is now explicitly dispositioned as operational state: it is in the active
surface/allowlist, records only observed results, and is not canonical evidence.
That resolves the earlier silent-scope concern.

Two defects need correction before plan acceptance:

1. **Vocabulary count is wrong.** The draft repeatedly specifies a
   **15-term/21-entry** final vocabulary. The current vocabulary has 18
   `###` terms and 23 entries. Removing only the one PM and one QR active term
   and entry yields **16 terms and 21 entries**. The plan, validation oracle,
   handoff, and any documentation/test expectation must use the correct exact
   count or deliberately identify one additional term for removal. Otherwise a
   wrong vocabulary can appear compliant under an internally inconsistent plan.
2. **The semantic-negation guard is incorrectly optional.** Acceptance
   criterion 7 requires a role-instruction semantic-negation failure. The
   validation plan permits a “not applicable” result if no positive assertion
   remains and relies on structural/hash guards. Retained released role bodies
   are explicitly required to remain executable contracts, so select one
   positive retained-role obligation and prove that a negation preserving the
   searched words fails the semantic guard. A hash mismatch alone cannot prove
   that the test rejects an inverted obligation.

Subject to those changes, the state and surface contracts map to criteria 1–10
without another material false-pass gap. In particular, the plan correctly
requires PM/QR base-body equality plus verbatim rendering, rather than treating
baseline-corpus deletion as proof that user-owned overlay expertise was deleted
or that a generated client has refreshed.
