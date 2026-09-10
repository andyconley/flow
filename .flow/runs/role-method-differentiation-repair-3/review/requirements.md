# Adversarial review: requirements

- Reviewer role: business-analyst
- Verdict: **Further definition required**
- Confidence: High for the contradictions and testability findings below; medium
  for the product value of either release boundary because no adoption or
  workflow evidence was supplied.

## Evidence inventory

### Already exists

- The draft definition and ten proposed acceptance criteria.
- The immutable repair-2 requirements, formal review, independent test audit,
  manifest, frozen scorecard, prompts, and eight raw response records.
- Current working-tree configuration, role bodies, role corpora, competency
  vocabulary, architecture/file-layout documentation, and composition tests.
- Repair-3 research from product, architecture, requirements, testability,
  candidate-source inventory, and archive retrieval.

### Partially covered

- The draft names a live-client check and preservation receipts, but it does
  not settle whether an unavailable live client blocks acceptance or identify
  the exact immutable record set for every retained passing role.
- The draft has a clear claim-narrowing path, while the architecture research
  recommends a different preservation/two-axis path. No engineer decision
  resolves that choice.

### Checked and genuinely absent

- No approved repair-3 boundary, supersession decision, two-axis status
  contract, or PM/QR candidate screen exists.
- No current workflow/adoption evidence establishes that removal of PM/QR
  active content helps users rather than merely makes the release claim more
  accurate.

## Problems to fix

### Critical — the draft selects an unapproved boundary that conflicts with the architecture recommendation

**Observed:** Requirements 1, 3, 5, and 7 and acceptance criteria 1, 4, 7,
9 require a six-role composed cohort and removal of PM/QR corpus, competency,
rendering, and documentation surfaces. The current working tree declares eight
composed roles and the architecture/file-layout docs name all eight. In
contrast, `research/architecture-challenge.md` recommends retaining the
five-role corpus/rendering and separating provenance/composition from
behavioral differentiation. It expressly says that a composition rollback
conflicts with preserving the current corpus and rendering. The same research
identifies an explicit engineer choice over whether behaviorally failed entries
may remain composed.

**Why this matters:** The draft calls this a reversible narrowing, but it is an
implementation and product-policy choice: it changes which generated guidance
users receive, deletes active provenance-covered material, and rejects the
only documented alternative capability boundary. Neither research establishes
that removal provides more user value than retaining it with accurate claims.

**Required disposition:** Before approval, record one engineer decision:

1. **Claim-only/two-axis boundary:** retain current corpus and composition,
   report five provenance/composition-covered roles and exactly three
   behaviorally differentiated roles; or
2. **Six-role removal boundary:** remove PM/QR active composition and corpus,
   state the user-facing reason and a precise compatibility consequence.

If option 2 is selected, requirements 3 and 7 must explicitly supersede the
architecture recommendation and the prior all-five release relationship, and
the non-goal excluding a two-axis status contract must say that it is an
intentional rejected alternative. If option 1 is selected, requirements 1, 3,
5, 7 and criteria 1, 4, 7, 9 must be rewritten; the current six-role count is
wrong for that boundary.

**Maps to:** requirements 1, 3, 5, 7; non-goals; constraint on supersession;
acceptance criteria 1, 4, 7, 9; open question 1.

### Critical — preservation scope contradicts requested removal and is not a complete evidence contract

**Observed:** Requirement 3 calls for removal of PM/QR active corpora,
competency edges, rendering, and current-cohort documentation. Requirements 4
and 6 and criteria 5 and 6 require preserved historical evidence and matching
before/after digests. The current draft does not enumerate which paths are
historical evidence versus removable active surfaces, nor identify the
authoritative passing record(s) and immutable baseline for each of architect,
lead-developer, and test-engineer. A generic directory-tree hash can pass even
if a record is moved, excluded from the release map, or replaced alongside a
matching aggregate count.

**Why this matters:** A wrong implementation could delete a raw PM/QR envelope
while retaining only a summary, or retain three unnamed passing records while
the release documentation links a different role. It could also rewrite a
failed source-verification record while preserving a new digest made after the
rewrite.

**Required change:** Add an explicit preservation inventory to the requirements
or acceptance criteria before planning. It must name: (a) the two failed
evidence roots, including raw response, prompt/design, manifest, score, review,
and source-verification files; (b) the exact named passing primary/counter
records for each retained role; (c) paths that may change under the chosen
boundary; and (d) a start receipt containing per-file hashes made before any
mutation. The final receipt must compare against that start receipt and require
an explicit disposition for every changed inventory member. Aggregate counts
are supplementary, never the preservation proof.

**Maps to:** requirements 2, 4, 6; success criterion on digests; acceptance
criteria 3, 5, 6; constraint on failed evidence immutability.

### Important — live-client acceptance has two incompatible outcomes

**Observed:** The final success criterion requires one newly composed role to
load through each live client after refresh. It then says inability to verify a
live client is a release limitation rather than a passed result. Acceptance
criterion 8 says the checks "pass" and requires the two live observations,
while also requiring observed, asserted, and unavailable evidence to be
reported separately.

**Why this matters:** A release reviewer cannot decide whether unavailable
Claude or Codex proof blocks acceptance. A wrong implementation can report an
unavailable client as a limitation and still mark criterion 8 passed.

**Required change:** Choose one policy. Recommended: make live-client evidence
a release blocker only for an install/runtime change; for this content-and-
claim narrowing, allow it as a named unverified limitation with no "pass" or
"loaded" assertion. If it remains a blocker, define the exact client action,
expected artifact, and failure disposition in planning. In either case,
separate automated delivery checks from client-observed evidence in the success
criteria and acceptance criterion 8.

**Maps to:** success criterion on final-tree validation; acceptance criterion
8; constraint on claim scope.

### Important — the mutation criterion is vacuous for two independent guards

**Observed:** Acceptance criterion 7 asks for “at least one delete-or-negate
mutation” proving both an exclusion guard and a retained-role guard. One
mutation normally violates one boundary, and a literal deletion can pass a
substring-only test even when a semantically negated instruction remains. The
repair-2 test audit already found that literal body assertions were partial
proof; repair-3 testability requires deletion *and* semantic-negation checks
per selected executable boundary.

**Required change:** Require separate mutations for each guard: one that
reintroduces a PM/QR active surface (or, under the two-axis boundary, makes a
false behavioral-pass claim) and one that removes or changes a retained
role/evidence mapping. For each, specify whether the semantic contract is
tested, not merely a phrase's presence. This is a testability constraint, not
a request to choose implementation mechanics in the definition.

**Maps to:** acceptance criterion 7; constraint that deterministic render or
source provenance alone does not prove behavioral differentiation.

### Important — the desired outcome lacks a user-visible compatibility statement

**Observed:** The outcome says PM/QR are restored and no longer composed, but
does not say what a user invoking either role will receive after the change,
how a project overlay behaves, or whether existing generated copies are
reconciled. “Outside active expertise composition” could mean an unchanged
base agent without an expertise section, an absent agent, or a stale generated
copy until sync.

**Why this matters:** The affected audience is maintainers and generated-agent
users. They cannot evaluate the release impact from a corpus/file removal
description alone.

**Required change:** State the future workflow in outcome language: PM and QR
remain available as base roles (if that is the intended boundary), their next
sync produces no expertise section, and no user should infer their failed
methods still apply. If any of these are not true, state the actual behavior
and add the compatible migration/communication requirement. Do not prescribe
renderer internals here.

**Maps to:** desired outcome; requirements 1 and 3; success criterion on active
PM/QR bodies; acceptance criterion 4; assumptions.

### Important — criterion 10 is too broad to be meaningfully verified

**Observed:** Criterion 10 bans every PM/QR candidate trial, retrieval/index
change, model-routing change, overlay change, corpus-format change, renderer
redesign, and unrelated role edit. Several of these are not bounded by a path,
behavior, or baseline. The definition otherwise requires documentation,
composition tests, generated-adapter checks, and develop-install refresh.

**Why this matters:** A reviewer cannot distinguish an intentional adjacent
test adjustment from a prohibited renderer redesign, and a broad text search
can falsely fail historical evidence that must retain those terms.

**Required change:** Keep the listed non-goals, but make the acceptance
criterion test the selected boundary's declared change set and explicit
exceptions. State that immutable historical evidence is excluded from exact
searches. Require an unexpected-delta disposition for any changed production
surface outside that set.

**Maps to:** non-goals; requirements 4, 6, 7; acceptance criteria 9 and 10.

## Risks and false-pass cases

| Risk | A wrong result that could pass now | Requirement or criterion change |
| --- | --- | --- |
| Aggregate role count | Six configured roles but a retained role has no named passing evidence, or a stale/mismatched record is cited. | Require per-role record IDs, envelope scope, and hash in criterion 3. |
| Reintroduced PM/QR method | PM/QR corpus is empty but their repair-2 instruction remains in a base body or generated adapter. | Test base body, corpus, manifest mode, and generated body separately; require semantic absence, not only a corpus count. |
| History erased by relabeling | Raw repair-2 files remain but a README/release note calls the methods superseded without the word “failed.” | Require each current summary and handoff to name the failed gate and forbid “superseded” as a pass-adjacent substitute. |
| Unrelated historical hits | A repository search reports five-role text in frozen evidence as a current release claim. | Restrict current-claim searches to declared active docs/config surfaces and require historical-path exclusions. |
| Preservation receipt created late | Final hashes match a receipt generated after edits. | Freeze and date a pre-mutation receipt; final validation must reference that receipt's immutable digest. |
| Live proof ambiguity | Static checks pass and an unavailable client is recorded as though it loaded. | Select explicit blocker/limitation policy and use distinct result fields. |
| Source provenance mistaken for lift | All corpus/joins/render tests pass and release language says “validated expertise.” | Require “behavioral differentiation” claims only where a named passing envelope is cited. |

## Approval readiness

The draft has a valuable, bounded objective: stop reporting failed PM/QR
methods as a five-role behavioral success and preserve the failed record. It is
not approval-ready because the central release boundary is unresolved and
several acceptance conditions can pass without proving the intended user-facing
or preservation outcome.

Stay in `flow-define` until the engineer selects the six-role removal or
claim-only/two-axis boundary, accepts its PM/QR compatibility consequence, and
the preservation and live-client policies are made testable. Then update the
draft and rerun adversarial review before routing.

## Recheck

- **Release-boundary conflict — unresolved pending engineer choice.** The
  revised draft clearly selects the six-role removal path, explains the base-role
  outcome, defers provenance-only admission, and limits the supersession to the
  prior all-five release relationship. The architect's two-axis alternative is
  still a documented, viable alternative, and open question 1 correctly keeps
  this removal boundary contingent on explicit engineer approval. Do not mark
  the definition approved until that choice is made.
- **Preservation scope and named proof — resolved.** The start receipt binds the
  preservation inventory and release-evidence map. The inventory names the two
  evidence roots, the complete prior run, and passing records; the map names
  each released role, source revision, entry IDs, result, and response hashes.
  I recomputed all listed inventory and named-record hashes and both receipt
  reference hashes: they match. Criteria 3, 5, and 6 now reject a late receipt,
  missing/replaced path, aggregate-only proof, and mismatched role record.
- **Live-client result policy — resolved.** The success criterion and criterion
  8 now make both dated live observations blocking and state that static output
  cannot substitute for an unavailable or inconclusive record.
- **Independent mutation guards — resolved.** Criterion 7 now requires a
  restored PM/QR reintroduction mutation, a separate retained-role/evidence
  mutation, and a semantic-negation failure for a role instruction; substring
  presence alone is explicitly insufficient.
- **User-visible PM/QR compatibility outcome — resolved.** The desired outcome
  and requirements 3–4 specify that both roles remain invocable through exact
  pre-repair base bodies, normal sync removes stale expertise sections, and
  historical failure evidence remains separate.
- **Bounded non-goal/scope verification — resolved.** Criteria 9–10 define
  active-document search with immutable-history exclusions, a declared change
  surface, and a blocking disposition for any other production path.

The revised draft is approval-ready once the engineer explicitly approves the
six-role removal boundary and its narrow supersession. No further requirements
ambiguity from this review remains.
