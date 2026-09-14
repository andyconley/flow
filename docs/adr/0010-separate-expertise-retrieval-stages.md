# ADR 0010: Separate expertise eligibility, ranking, admission, delivery, and disposition

- Status: accepted
- Date: 2026-09-11
- Decision owner: repository owner
- Related work: `agent-expertise-rag-applicability-admission`
- Scope: durable retrieval boundaries, data ownership, persistence, evidence,
  client parity, failure posture, and rollout; provider and admission-strategy
  selection remain conditional on the frozen campaign

## Context

Flow currently validates role-owned expertise as JSON-LD and composes the
complete merged corpus into generated agent files. That design made the first
three evidence-backed roles useful, but it does not scale as every role's
corpus grows. The next capability must select a small set of relevant methods
for a bounded task while preserving the authority, provenance, and five-part
method shape established by ADR 0008.

The first semantic experiment found acceptable methods within the top three
for all 21 critical positive fixtures, including all three semantic
no-overlap cases. It also showed that semantic score is not an applicability
decision. Applicable and plausible-but-inapplicable scores overlapped: a
threshold low enough to keep the weakest positive also admitted a right-role,
close-vocabulary negative. Ranking evidence can narrow a corpus; it cannot by
itself decide that an agent should see or follow a method.

This creates five different claims:

1. a method is authoritative and eligible for this role;
2. its meaning is semantically close to the task;
3. it is applicable enough to present;
4. its complete canonical entry was delivered within the contract limits; and
5. the role agent applied it, rejected it, or needed more context.

Collapsing any two claims hides a failure. In particular, an unavailable
provider or admission gate must not appear as a successful no-match, and a
high-ranked method must not silently become accepted precedent. Claude and
Codex also must not derive different applicability decisions from their
adapter-specific prompts.

## Decision

Implement expertise retrieval as one Flow-owned, provider-neutral application
service with five ordered stages: **eligibility, semantic ranking, candidate
admission, complete-entry delivery, and agent disposition**. Each stage emits
a versioned Flow-owned value. A later stage may narrow or annotate an earlier
stage's result but may not restore excluded IDs, reorder ranked IDs, rewrite
canonical content, or relabel a failed stage as no-match.

### Canonical authority and derived state

Role-owned JSON-LD remains the only authority for method identity, prose,
sources, competencies, layer, ownership, lifecycle, and supersession. The
service first validates one canonical snapshot and applies deterministic role,
layer, owner, lifecycle, graph, and schema eligibility. Entries without the
required authority do not reach the provider.

SQLite is a disposable projection, not a second corpus. It stores only derived
metadata and finite float32 vectors needed for semantic rank. It does not own
canonical prose or lifecycle state. A stale, corrupt, incompatible, or
identity-mismatched projection is replaced from a freshly validated canonical
snapshot; it is never repaired by granting authority to its rows.

Task/query prose, normalized task facts, query vectors, ranked results,
admission inputs, delivered envelopes, trigger and failure-mode views, and
model inputs remain transient during ordinary execution. They are not written
to the projection, result caches, or normal receipts.

### One admission boundary before client adapters

Flow creates one bounded, versioned `AdmissionInput` after deterministic
eligibility and ranking and before either client adapter. It binds the role,
canonical corpus and entry digests, provider and ranker identity, ordered
candidate window, ephemeral normalized query view and task facts, applicable
limits, and admission-contract revision.

The admission Strategy may return decisions only for IDs in that ordered
window. It cannot fetch more corpus rows, alter scores, restore an ineligible
entry, or reorder candidates. Delivery then rehydrates admitted IDs from the
same canonical snapshot, verifies their digests, and packs complete entries by
the Flow-owned byte limit.

Claude and Codex consume the same normalized outcome from this service. Their
adapters may vary only in declared presentation and timing fields. They may not
normalize the task independently, derive new task facts, rank, admit, remap a
state, or change IDs, order, limits, and reason codes. This shared pre-adapter
contract is the unit of static parity and live-client verification.

### State and failure posture

The application service owns the single mapping from stage results to the
outer result. `no_match` is successful only when valid deterministic
eligibility produces an empty set or a valid admission decision rejects every
ranked candidate. Provider, projection, ranker, gate, schema, digest, packing,
receipt, or adapter failure retains its exact degraded state. It never becomes
`no_match`.

Flow invokes no alternate provider, scorer, gate, hosted service, or complete
corpus when the selected path is unavailable. The compact base role and the
rest of Flow continue with retrieval visibly unavailable. A fallback would
make behavior depend on the machine's installed capabilities and would erase
the evidence needed to distinguish absence from failure.

### Linked evidence without task retention

Before role delegation, Flow writes one immutable, private pre-agent receipt
for the normalized result. The receipt contains request and revision
identities, stage states, ordered IDs and digests, closed reason codes, limits,
and non-prose measurements. It excludes task text, task spans, task facts,
canonical method prose, triggers, failure modes, model inputs or outputs,
free-form reasons, and raw exception text.

After delegation, Flow validates exactly one disposition for every delivered
ID: `applied`, `ignored`, or `insufficient_context`. It writes a separately
immutable post-agent receipt linked to the pre-agent request and receipt
identity. Missing, duplicate, reordered, mismatched, or behavior-inconsistent
handback is `not_observed`; it fails the behavior evidence without erasing the
pre-agent record or valid evidence for unaffected IDs.

Projection, admission, and delivery/disposition identities are independent.
A provider, vector, or corpus change invalidates the projection and downstream
evidence. A fact, rule, threshold, or admission-contract change invalidates
admission and downstream evidence without rebuilding unchanged vectors. A
packing, rendering, prompt, or handback change invalidates delivery and
behavior evidence without rerunning semantic ranking.

### Per-role rollout

The service and generated protocol ship disabled. Stages 1-4 may qualify the
shared contract as `qualified_disabled`; that status enables no agent.
Support-lead is the first role that may move to `retrieval_enabled`, and only
after its separate blinded behavior and live Claude/Codex evidence passes.
Every other role stays composed until equivalent role-owned behavior evidence
earns its own decision. Rollback sets the role to `composed`, regenerates both
clients, and leaves canonical JSON-LD unchanged.

### Admission candidates in this campaign

The first frozen comparison contains only calibrated semantic similarity and
reviewed deterministic trigger rules behind one Strategy port. The approved
selector, held-out evaluation, platform checks, and support-lead behavior gate
choose whether either may be enabled. This ADR does not select the provider or
winning Strategy; a second evidence-based ADR records that decision only after
the campaign completes.

A learned classifier, cross-encoder, or entailment gate is deferred. Thirty
calibration fixtures cannot support training an applicability model, and a
pretrained free-text gate adds artifact, license, runtime, footprint,
calibration, and explanation obligations. The Strategy port preserves a clean
place for a separately approved learned challenger later.

## Alternatives considered

- **Treat the top semantic ranks as admitted.** Rejected because evaluation-v1
  established retrieval recall, not applicability. A close negative can rank
  above a valid weak positive.
- **Use one semantic threshold as the architecture.** Rejected as the durable
  boundary because observed positive and plausible-negative scores overlap.
  Calibrated similarity remains one finite campaign candidate behind the
  admission port.
- **Let each generated client decide applicability.** Rejected because prompt
  and runtime differences would create two policies, prevent normalized parity,
  and make evidence incomparable.
- **Compose the complete corpus when retrieval fails.** Rejected because it
  hides operational failure, changes behavior by environment, defeats bounded
  context, and can reintroduce methods that deterministic eligibility removed.
- **Persist tasks, facts, envelopes, or model inputs for debugging.** Rejected
  because durable user-task content is not required to prove stage behavior.
  Linked code-and-identity receipts supply the necessary audit trail.
- **Enable all roles once shared retrieval passes.** Rejected because correct
  selection does not prove that every role uses retrieved advice correctly.
  Behavior qualification belongs to each role.
- **Select a learned gate now.** Rejected for this campaign because the small
  fixture set, runtime cost, and weaker traceability do not justify the added
  boundary. It remains a future Strategy candidate, not a runtime fallback.

## Consequences and owned follow-up

- The service has more explicit states and identities than a single retrieval
  call. That complexity is intentional: it keeps authority, relevance,
  applicability, delivery, and observed use separately falsifiable.
- JSON-LD authoring gains lifecycle and rule-coverage obligations before an
  entry can participate in a retrieval-enabled role. User-owned entries without
  reviewed authority remain unknown rather than being inferred current.
- The projection can always be deleted and rebuilt. No database migration may
  become the only route to recovering canonical expertise.
- Receipts support failure analysis without retaining task or method prose, but
  they cannot reproduce a task from storage alone. Frozen evaluation artifacts
  carry their own separately governed inputs.
- Missing runtime capability leaves Flow and its base agents usable while
  automatic expertise retrieval is unavailable. Install and doctor checks must
  name the exact missing artifact, runtime, permission, or supported remedy.
- Calibration and held-out fixtures are evaluation evidence, not production
  training data or implicit rules. Their frozen identities and approvals gate
  scoring.
- A second ADR is required after evidence selects a concrete provider, model,
  admission Strategy, executable configuration, and initial role disposition.

## Revisit conditions

Revisit this decision when one of these conditions is observed:

- a separately frozen corpus and held-out campaign shows that neither approved
  deterministic candidate can preserve applicable recall and reject plausible
  inapplicability;
- production false admissions, abstentions, or `insufficient_context` rates
  exceed an approved role threshold and the failures are attributable to the
  admission boundary rather than source quality or eligibility;
- a learned challenger can meet the same local-only, privacy, deterministic
  packaging, platform, footprint, latency, receipt, and role-behavior gates;
- the corpus grows enough that exact ranking or the disposable projection no
  longer meets the supported environment budgets; or
- a future client cannot consume the normalized contract without changing its
  domain meaning, requiring a versioned contract revision rather than an
  adapter-specific policy.

The five claims remain separate when the scorer, provider, gate, store, or
client changes. A future implementation may replace a component behind its
port; combining the stages requires new evidence and a superseding ADR.

## Evidence

The decision is grounded in the approved definition, solution, implementation
plan, and evaluation-v1 evidence retained under
`.flow/runs/agent-expertise-rag-applicability-admission/`. ADR 0008 remains the
authority for JSON-LD ownership and authoring. This ADR intentionally records
the stable boundary before the provider and admission winner exist.
