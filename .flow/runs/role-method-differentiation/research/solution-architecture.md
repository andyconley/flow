# Solution architecture: role-method differentiation

- Owner role: solution-architect
- Date: 2026-09-09
- Confidence: High for the internal capability boundary; Medium for individual
  public-source mappings until the source-verification record confirms exact
  editions and locators.

## Question

Where should the proposed product-manager, quality-reviewer, and lead-developer
methods live, and does each source support a role-owned behavior that is absent
from the current canonical role body?

## Method and evidence

- Read the canonical role bodies in `scaffolds/default/agents/`.
- Read the existing role-owned JSON-LD corpus entries and ADR 0008.
- Read the failed expansion review and its frozen evaluation amendment.
- Read this run's brief, business analysis, and product research.
- Applied `standards/architecture.md` sections **Core principles**, **Domain
  rules**, and **ADR convention**; `standards/definition.md` sections
  **Approved requirements**, **Role participation**, and **Routing**;
  `standards/research-evidence.md` sections **Source quality**, **Confidence**,
  and **Synthesis**; and `standards/testing.md` section **BDD and specification
  by example**.
- Assessed source fit from the engineer-supplied descriptions and already
  collected web evidence. This note does not independently certify a source
  locator.

## Capability boundary

The canonical role body owns the behavioral contract: when a method applies,
which role owns the decision, and what output shape the agent must produce.
The role-owned JSON-LD corpus teaches source-backed methods inside that
contract. Composition may add expertise, but an appended entry should not be
expected to negate a mandatory instruction or fixed output template earlier in
the same agent body.

This yields three boundaries:

1. **Product-manager** owns priority, evidence depth for a product decision,
   and resolvable outcome measures. It may classify whether a commitment is
   reversible, but it does not design a technical rollback.
2. **Quality-reviewer** owns the comparison between approved intent, supplied
   artifacts, and evidence. It may challenge a critical theory, but it does not
   resolve implementation ambiguity by assumption.
3. **Lead-developer** owns technical reversibility, blast radius, coverage, plan
   depth, validation, and rollback. The canonical role body must select between
   short and full output paths because its current fixed template is itself the
   source of the observed over-planning.

These are role-local changes. They do not change the composition boundary,
JSON-LD storage model, model routing, retrieval, or another role's ownership.
The boundary follows **Core principles** by making the smallest reversible
change and **Domain rules** by keeping the selection logic in the role contract
that owns it.

## Source-to-behavior fit

### Product manager

| Proposed method | Fit to the current body | Source fit and wording constraint | Placement |
| --- | --- | --- | --- |
| Cost-of-delay shape and CD3 | Distinct. The body asks “why now” but supplies no comparison rule. | Strong conceptual fit to Reinertsen if stated as cost of delay divided by duration and if cliff, gradual, and flat profiles describe how delay changes economic impact. Avoid collapsing this into generic feature value divided by effort. | JSON-LD method entry, plus a compact role-body instruction that priority recommendations must compare time sensitivity when candidates differ. |
| Reversible and irreversible product decisions | Distinct. Tradeoffs cover cost and displacement, not whether the commitment can be undone. | Strong fit to the one-way/two-way-door distinction. “A cheap irreversible choice deserves more scrutiny than an expensive reversible one” is an application of the principle, not a quotation or independently established formula. Constrain the role to decision rigor and pace; technical reversibility remains with engineering. | JSON-LD method entry with an explicit role boundary; role-body trigger before prioritize/defer/rescope decisions. |
| Resolvable success and kill conditions | Distinct. The body asks how success will be known but permits an unbounded directional answer. | Partial-to-strong fit to resolvable forecasts and calibration. Threshold and timeframe are direct requirements for resolution; measurement source and kill condition are Flow's operationalization and must be labeled as such rather than attributed verbatim to Tetlock and Gardner. | JSON-LD method entry; role-body Success contract requires measurement source, threshold, date, and failure/kill condition when a metric is proposed. |

### Quality reviewer

| Proposed method | Fit to the current body | Source fit and wording constraint | Placement |
| --- | --- | --- | --- |
| Review for absence | Distinct despite the existing phrase “missing cases.” The current body starts from the supplied work; it does not first derive an expected-content inventory from approved intent. | Strong fit to missing-requirement defect classes and checklist-based inspection. The observable behavior is a spec-derived inventory before the diff is judged. | JSON-LD method entry and a role-body review-order instruction. |
| Alternative explanation before a critical | Distinct. Rule 6 handles felt uncertainty, not unrecognized competing explanations. | Strong conceptual fit to Analysis of Competing Hypotheses, adapted to review. The bounded behavior is one plausible correctness explanation plus evidence that rules it out. If it cannot be ruled out, classification becomes a question or a lower-severity finding. | JSON-LD method entry; role-body rule governing Critical Issues. |
| Observed, read, and author-asserted evidence | Distinct. The current Verification Story renders tests and runtime checks as yes/no without evidence strength. | Medium fit to ICD 203 sourcing and confidence principles. The three labels are a Flow-owned taxonomy, not ICD terminology unless source verification proves otherwise. Define each label locally: observed means the reviewer witnessed execution or output; read means the reviewer inspected the artifact but did not execute it; author-asserted means the claim was supplied without independent inspection. | JSON-LD method entry plus a role-body Verification Story format change. |

### Lead developer

| Proposed method | Fit to the current body | Source fit and wording constraint | Placement |
| --- | --- | --- | --- |
| Plan depth proportional to reversibility, blast radius, and coverage | Distinct and corrective. The body currently says to evaluate every change across five dimensions. | Strong conceptual fit to Fairbanks's risk-driven design, adapted from architecture effort to implementation-planning effort. The three selectors must be explicit and deterministic enough to test. | Canonical role-body selection rule, supported by a JSON-LD source entry if desired. |
| Collapse sections with no real content | Directly corrects the fixed Output Format. | Partial source fit to Parnas and Clements. Their work supports honest reconstruction of reasoning but does not by itself establish “omit empty headings.” The requirement is better grounded in Flow's observed failure and the role's existing rule to avoid document bulk. Do not present section omission as a quoted source rule. | Canonical role-body output contract only; optional source entry may explain the anti-theater principle but cannot own the behavior. |
| Proceed when rollback is cheaper than further planning | Useful only after narrowing. The literal wording could bypass Flow lane gates or hide state left behind. | Partial-to-strong fit to small batches and deployment safety, but “planning past that point buys nothing” is too absolute. Encode: after requirements are approved and short-form eligibility is established, recommend one reversible slice and name the tested rollback mechanism. | Canonical short-form rule plus a supporting corpus entry. It must not authorize skipping required definition, review, or validation gates. |

## Options

### Option A: Put every method in JSON-LD expertise entries

- Keeps all source provenance in the existing ADR 0008 model.
- Avoids changing canonical role templates.
- Fails the lead-developer case because appended expertise would compete with a
  mandatory five-section format. Prior evidence already shows this failure
  mode. It also leaves the quality-reviewer Verification Story structurally
  unable to distinguish evidence strengths.

### Option B: Split method knowledge from role contract

- Put source-backed decision and review methods in each role's JSON-LD corpus.
- Put triggers, role boundaries, evidence labels, and output-path selection in
  the canonical role body.
- Replace the lead-developer single fixed format with explicit short and full
  forms. Short form is eligible only when the change is atomic, local,
  reversible, and covered by relevant tests. State, migration, public-contract,
  cross-cutting, or weak-coverage changes require the full form.
- This is the smallest option that addresses both missing expertise and the
  demonstrated template defect.

### Option C: Put all methods and citations directly in role bodies

- Makes behavior explicit in one file.
- Duplicates the source/provenance mechanism settled by ADR 0008 and weakens
  structured competency joins and corpus validation.
- Creates unnecessary architectural drift for no behavioral gain over Option B.

## Recommendation

Use Option B. The role body remains the single executable contract, while
JSON-LD remains the source-backed knowledge boundary established by ADR 0008.
This preserves existing architecture and changes only the contract elements
that the failed evaluations proved defective.

For lead-developer, the short form should contain:

- one change statement and affected file/module;
- the specific validation to run;
- the named rollback mechanism; and
- one line stating why full planning sections are inapplicable.

Any short-form disqualifier selects the full existing plan. “Reversible” is not
enough by itself: rollback must restore prior observable state, relevant tests
must exist, and the blast radius must be local. These conditions prevent a
small code diff from disguising an irreversible data or contract change.

## Decision durability and artifacts

No new ADR is warranted. ADR 0008 already owns corpus format, citations, and
role ownership. The proposed role contracts are local, reversible prompt
changes and do not meet `standards/architecture.md` **ADR convention** triggers.
If the short/full selection later becomes a shared framework schema consumed by
multiple commands or tools, revisit that conclusion.

The definition should produce:

- approved requirements and acceptance criteria for all three role contracts;
- a source-verification record with exact edition, stable source, and locator
  for every adopted method;
- frozen primary and counter-case fixtures with predeclared rubrics;
- an explicit treatment manifest that hashes the unchanged control and changed
  treatment bodies; and
- a mapping from each requirement to role-body change, JSON-LD entry, or both.

No C4, sequence, or state diagram is useful for this local prompt-contract
change. The mapping table and paired evaluation fixtures are the smallest
artifacts that expose the relevant boundaries and proof.

## Requirement implications

1. Require every method to produce an observable role-owned behavior absent
   from the current body; generic improvement or added prose does not count.
2. Require source locators to distinguish the source's claim from Flow's
   operationalization, especially for measurement source/kill condition,
   observed-read-asserted labels, section omission, and the one-slice rule.
3. Require the product-manager reversibility method to stop at decision rigor;
   technical rollback details are out of role.
4. Require quality-reviewer omission inventory before artifact judgment and
   downgrade any critical whose competing correctness explanation is not ruled
   out.
5. Require lead-developer short/full selection in the canonical role body, with
   all eligibility conditions and disqualifiers tested.
6. Preserve the previous failed entries and fixtures unchanged. This run adds a
   distinct method release; it does not rewrite the earlier evidence.
7. Gate release per role using primary and counter cases under identical arms,
   with raw outputs, invocation metadata, hashes, independent scoring, and no
   ties. This follows `standards/testing.md` **BDD and specification by example**
   by turning the boundary into concrete examples.

## Open follow-ups

- Source verification must confirm exact locators before requirements approval.
  Where a source supports only the principle, requirements must label the
  concrete Flow behavior as an adaptation.
- Test engineering must predeclare what counts as “materially shorter” without
  rewarding omission of applicable proof or rollback detail.
- Planning should inspect whether any consumer parses role output headings. If
  a consumer does, the short form needs a compatibility decision before the
  role body changes.
- After source and consumer checks, the likely next lane is `flow-plan`; the
  architecture choice is sufficiently bounded that a separate solution lane
  is unnecessary unless a parsed-heading dependency is found.
