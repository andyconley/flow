# Architecture challenge: role-method differentiation repair-3

- Owner role: solution-architect
- Date: 2026-09-09
- Confidence: High for the local capability boundary and precedent; Medium for
  the product policy until the engineer chooses what a composed entry may claim

## Question

Should Flow continue to require treatment-over-control behavioral lift for
every composed expertise method, release only the three roles with passing
evidence, or separate source-provenance coverage from demonstrated behavioral
lift?

## Method and sources

- Read the current framework architecture and file-layout contracts in
  `docs/architecture.md` and `docs/file-structure.md`.
- Read the composed-role declarations in `scaffolds/default/flow.toml`, the
  competency vocabulary, and the role-owned corpora and role contracts for the
  five evaluated roles.
- Read ADR 0008, the original expansion result, the approved repair-2
  requirements and acceptance criteria, the repair-2 orchestration record,
  frozen manifest, execution record, score, formal review, reconciliation, and
  handoff.
- Read the repair-3 archive-retrieval note. Retrieval was unavailable; the
  prior-run evidence cited here was manually inspected outside that active
  selection.
- Applied `standards/architecture.md` sections **Core principles**, **Domain
  rules**, and **ADR convention**; `standards/definition.md` sections
  **Approved requirements**, **Adversarial review**, and **Routing**; and
  `standards/research-evidence.md` sections **Source quality**, **Role research
  focus**, and **Synthesis**.

## Findings

### Three claims are currently coupled but have different evidence

The existing artifacts prove three different things:

1. A role-owned method has a source, pinpoint, competency join, trigger,
   required behavior, and failure mode. This is **provenance coverage**.
2. The framework validates and renders that entry through the declared composed
   role path in both adapters. This is **deterministic composition**.
3. A frozen treatment performs every distinctive primary behavior that an
   unchanged-body control misses and does not over-apply the method in a
   counter-case. This is **behavioral differentiation**.

Repair-2 passed the first two claims for product-manager and quality-reviewer
and failed the third. The score is not ambiguous: each treatment missed one
primary predicate, while each unchanged control satisfied two distinctive
predicates. The failure therefore shows no measurable marginal lift over the
frozen role body; it does not show missing provenance, a broken renderer, or a
bad competency join.

Behavioral differentiation is also contextual. It belongs to a versioned
combination of method wording, role body, prompt, rubric, runtime, and model.
Source provenance belongs to the corpus entry and remains meaningful when a
later runtime changes. Treating them as one timeless property makes a failed or
stale behavioral comparison appear to invalidate durable source metadata, or
makes good source metadata appear to prove runtime behavior. Neither inference
is supported.

### Capability-boundary options

#### Keep behavioral lift as the admission rule for every composed method

- Preserves the strongest interpretation of “expertise”: every shipped method
  must change behavior beyond the role contract.
- Prevents prompt growth that has no observed benefit.
- Makes corpus membership depend on a probabilistic, runtime-specific marginal
  comparison. A capable control can already perform a sound method, as both
  repair-2 controls did, so the gate can reject relevant, correctly composed
  knowledge because the role body already covers it.
- Would require a new versioned product and quality envelope; repair-2 cannot be
  rerun or rescored.

#### Narrow the release to the three roles with behavioral passes

- Makes the behavioral claim precise: architect, test-engineer, and
  lead-developer have passing evidence; product-manager and quality-reviewer do
  not.
- Avoids changing the meaning of “behaviorally differentiated.”
- If implemented as a composition rollback, it conflicts with the requested
  preservation of the current corpus and rendering and creates unrelated
  churn. If implemented only as claim narrowing, it is a valid subset of the
  recommended boundary below rather than a competing architecture.
- Leaves no durable label for the valid product and quality provenance and
  deterministic composition evidence.

#### Separate provenance coverage from behavioral lift

- Preserves the current role-owned corpus, competency joins, renderer, and all
  repair-2 evidence without converting a failed behavioral result into a pass.
- Allows Flow to say exactly what is proven per role and method. For the current
  five-role set, the honest result is five provenance-covered and
  deterministically composed roles, with behavioral differentiation proven for
  only architect, test-engineer, and lead-developer.
- Keeps behavioral lift mandatory for any “improves,” “differentiates,” or
  five-role behavioral release claim. Product-manager and quality-reviewer must
  remain explicitly failed or unproven for that axis until a new versioned
  envelope passes.
- Requires an explicit policy decision about whether provenance-covered but
  behaviorally unproven entries may remain in the shipped composed corpus. That
  policy cannot be inferred from ADR 0008 or repair-2.

## Recommendation

Adopt the third boundary: record provenance coverage and behavioral
differentiation as separate evidence dimensions, and narrow the present
behavioral release claim to the three passing roles.

The definition should establish two independent statuses rather than a single
pass:

- **Provenance/composition status** answers whether a role-owned entry has
  verified source metadata, valid competency relationships, an executable
  role boundary, and deterministic rendering.
- **Behavioral status** answers whether a named, versioned evidence envelope
  demonstrates safe treatment-over-control lift. A failed envelope remains
  failed; an absent or stale envelope is unproven, not passing.

This boundary keeps the corpus as deterministic domain data, consistent with
`standards/architecture.md` **Domain rules**, while keeping runtime evidence
attached to the versioned behavior it actually tested. It also follows **Core
principles** by avoiding changes to retrieval, routing, the merge model, or
role ownership when the observed failure is confined to the release claim and
two behavioral comparisons.

For repair-3, provenance-only status must not silently become sufficient for a
behavioral product claim. If the engineer permits such entries to remain
composed, the requirements should name the minimum admission floor and the
visible claim language. At minimum, the existing source, schema, rendering,
and safe counter-case evidence must remain intact; the product and quality
methods must still be labeled behaviorally failed under repair-2.

## Precedent and conflict dispositions

- **ADR 0008 applies and is honored.** It decides JSON-LD storage, inline
  source pinpoints, and per-role ownership. It explicitly does not approve
  retrieval or sync composition. Separating evidence statuses does not change
  its decided boundary and does not warrant a new ADR during definition.
- **The repair-2 frozen stopping rule applies and is honored.** Both failed
  role gates and the combined five-role behavioral release remain blocked.
  Repair-2 stays immutable. Any changed method, role body, prompt, fixture, or
  rubric requires a separate versioned envelope.
- **The approved repair-2 release relationship conflicts with a provenance-only
  five-role release.** It says the combined release is eligible only if both
  replacement methods pass. The engineer must explicitly approve superseding
  that relationship before Flow can ship or describe all five under a weaker
  claim. Until then, the narrower three-role behavioral claim is the only
  supported release claim.
- **The prior solution-architecture requirement remains applicable to
  behavioral claims.** Its rule that every method produce observable,
  role-owned behavior absent from the current body is the correct gate for
  claiming lift. It should not be reinterpreted as a provenance rule without an
  explicit definition change.
- **Archive retrieval supplied no ranked precedent.** The active selection
  remains unavailable. These dispositions come from manually inspected current
  project artifacts outside the active retrieval selection; the retrieval miss
  stays visible and creates no authority or lifecycle veto.

## Definition decisions

The engineer must approve these before routing:

1. Whether a provenance-covered, deterministically composed method may ship
   when behavioral lift is failed or unproven.
2. Whether repair-3 supersedes the earlier all-five behavioral release
   relationship with a two-axis claim: five-role provenance/composition and
   three-role behavioral differentiation.
3. The exact terms and prohibitions for those claims, including that failed,
   unproven, and stale behavioral evidence cannot be reported as passing.
4. The preservation constraints: repair-2 remains immutable; current corpus
   entries and role rendering remain unchanged unless a later approved method
   revision requires a new envelope.
5. Explicit non-goals covering retrieval, ranker behavior, model routing,
   overlay merging, general expertise architecture, and unrelated roles.

## Solution and plan work

After approval, solutioning should decide the smallest versioned evidence
contract that can represent the two statuses, their scope, and their relation
to a method/role-body/runtime combination. It should also decide whether the
status is recorded in an evidence manifest, release result, or another existing
artifact. Those representation and lifecycle choices are durable enough to
compare before implementation.

Planning should own file-level changes, migration or compatibility treatment
for existing evidence, validation fixtures, mutation checks, adapter checks,
documentation updates, and release wording. New product and quality behavioral
experiments belong in a later plan only if the approved definition still seeks
lift for those roles; they must use a new frozen envelope.

No retrieval, routing, ranker, corpus merge, or general renderer redesign is
needed to implement the recommended boundary.

## Implication for requirements and next lane

- Add separate success and acceptance criteria for provenance/composition and
  behavioral differentiation.
- Require every reported status to name its evidence scope and version.
- Preserve the three passing role results and the two failed repair-2 results
  without aggregation into an all-five behavioral pass.
- Require an explicit engineer supersession decision for the prior all-five
  release relationship.
- If approved, route to `flow-solution` because the versioned two-status
  evidence contract has more than one viable representation and will outlive a
  single implementation slice. Stay in definition until the admission policy
  and supersession decision are approved.

## Open follow-ups

- Product ownership must decide whether preserving composed but behaviorally
  unproven entries provides enough value to justify their prompt cost.
- Test engineering should define when behavioral evidence becomes stale across
  role-body, runtime, or model changes; definition should require explicit
  scope, while solutioning should choose the mechanism.
