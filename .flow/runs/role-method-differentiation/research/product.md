# Research: outcome, scope, and measurable success for role-method differentiation

- Owner role: product-manager
- Date: 2026-09-09
- Confidence: High for the internal problem and release decision; Medium for
  the proposed public-source mappings until source verification records the
  exact editions and locators.

## Question

What outcome justifies a separate role-method release now, what is the
smallest useful scope, and what evidence would show that it changes the three
roles rather than repeating guidance they already have?

## Method and sources

- Read the definition brief at
  `.flow/runs/role-method-differentiation/brief.md`.
- Compared the current role bodies in
  `scaffolds/default/agents/product-manager.md`,
  `scaffolds/default/agents/quality-reviewer.md`, and
  `scaffolds/default/agents/lead-developer.md` against the proposed methods.
- Read the prior expansion's frozen evidence and disposition in
  `docs/evidence/agent-expertise-expansion/results.md`.
- Used the engineer-proposed source list as a hypothesis, pending independent
  source tracing: Reinertsen (cost of delay), Bezos shareholder letters
  (reversible decisions), Tetlock and Gardner (resolvable forecasts), Wiegers
  and Fagan (omission defects), Heuer (alternative hypotheses), ODNI ICD 203
  (evidence/confidence), Fairbanks (risk-driven design), Parnas and Clements
  (design-process documentation), and Humble and Farley (small batches and
  reversibility).

## Findings

### Opportunity and why now

The prior five-role expansion is blocked by its own all-five behavioral gate.
Product-manager and quality-reviewer treatments tied their unchanged role
bodies, and lead-developer over-applied planning to a one-file counter-case.
The structural work passes, but merging it would claim a measured improvement
the evidence does not show. This release turns that negative result into a
bounded repair: add methods that require an observable artifact or decision
the current bodies do not require.

The work is timely because the failed evaluation fixtures expose the exact
gap. Deferring leaves the intended roles either unchanged in practice or less
useful for small work, while adding more generic expertise would repeat the
same failure mode.

### What is new compared with the current bodies

| Role | Existing coverage | Distinct method to test | Product value |
| --- | --- | --- | --- |
| Product manager | It asks why now, tradeoffs, and how success will be known, but gives no decision rule for urgency, reversibility, or a metric that can fail. | Compare candidate urgency by value-decay shape and duration; classify reversibility before setting evidence depth; specify measurement source, threshold, date, and kill condition. | Makes sequencing and success conditions actionable instead of persuasive prose. |
| Quality reviewer | It reviews stated intent and changed artifacts, flags missing cases, and asks for a verification story, but does not first derive expected contents, challenge a confident critical theory, or label the strength of verification evidence. | Build a spec-derived expected-content list; test one alternative explanation before a critical; label claims observed, read, or author-asserted. | Reduces missed requirements and unsupported severe findings while making residual risk honest. |
| Lead developer | It requires plans for every story/change and a fixed five-section output, while only generally preferring reversible work. | Size planning to reversibility, blast radius, and test coverage; provide a short form for an atomic, reversible, tested change; retain full planning for material risk. | Prevents planning ceremony from delaying small safe fixes without weakening planning for irreversible work. |

### Scope recommendation

Ship one bounded method bundle, only for these three existing role bodies.
Each method must become an enforceable instruction or output-contract change,
not an additional inspirational source paragraph. The lead-developer short
form is an explicit output-format change because the present template creates
the documented over-planning behavior; corpus text alone cannot reliably
override it.

The minimum useful slice is:

1. source-verify every adopted method and preserve role-owned provenance;
2. modify only the three role bodies and any role-owned expertise records
   needed to render them;
3. add frozen, discriminating treatment/control fixtures that demand the new
   observable behavior;
4. run identical-arm comparisons and score both usefulness and inappropriate
   application; and
5. retain the prior fixtures as non-regression evidence, without reopening the
   blocked five-role release.

### Non-goals

- Do not merge, relax, or redefine the all-five behavioral gate of
  `agent-expertise-medium-confidence-expansion`.
- Do not add generic source-backed entries where a role-body or output-contract
  correction is required.
- Do not change Flow model routing, introduce retrieval/RAG, alter the
  composition architecture, or create a shared expertise registry.
- Do not make product-manager the owner of architectural reversibility,
  quality-reviewer the owner of implementation plans, or lead-developer the
  owner of product prioritization. Each method is used only to improve that
  role's own decision or review artifact.
- Do not require the short-form lead-developer plan for changes with irreversible
  state, public contracts, cross-cutting effects, or insufficient test coverage.

### Measurable success and release criteria

The release succeeds only if every role shows a named behavioral advantage
over its unchanged body on a discriminating primary case and does not overfire
on a counter-case. Same client, model, effort, prompt, budget, and scoring
rubric are required for both arms; raw outputs and invocation metadata stay in
the role evidence directory.

| Role | Primary observable advantage | Counter-case / boundary | Pass condition |
| --- | --- | --- | --- |
| Product manager | For a choice with differing deadlines and reversibility, the treatment compares decay shape/value per duration, proportionates evidence to reversibility, and gives a resolvable success plus kill condition. | A stable, reversible, low-cost experiment must not receive a false urgency claim or heavyweight evidence demand. | Treatment supplies all applicable fields and makes a justified sequencing difference or catches a decision flaw the control misses; it stays proportionate in the counter-case. |
| Quality reviewer | Given a clean but incomplete change, treatment derives an expected-content checklist and reports the omitted requirement; its verification story labels evidence strength. | A plausible apparent defect has a documented alternative explanation that makes the artifact correct. | Treatment identifies the true omission or downgrades an unsupported critical to a question, while the control misses it or asserts it without evidence; no false critical remains in the counter-case. |
| Lead developer | Given a local, reversible, covered change, treatment uses the short form, names the revert mechanism, and provides a direct one-slice plan. | A cross-cutting or irreversible change must receive full risk-proportionate planning rather than the short form. | Treatment is materially shorter and actionable for the local fix, yet retains full analysis for the higher-risk case; control evidence is retained for comparison. |

"Materially" must be operationalized before prompts run: a role-owned
rubric awards points only for the listed required observations, with a
predeclared pass threshold and an independent scorer. Word count alone cannot
be a quality metric. A tie is a failure, as in the previous release.

## Implication for requirements

- Add a requirement that each adopted method maps to a role-owned observable
  behavior absent from the current role body and to a verified source locator.
- Add a requirement that lead-developer has two output paths selected by
  reversibility, blast radius, and test coverage, with explicit disqualifiers
  for the short form.
- Add acceptance criteria for paired primary/counter cases, frozen prompts,
  arm parity, raw-output retention, independent scoring, and no ties.
- Add a release gate: all three role-level gates pass; otherwise the work is
  not merged and the failed role is routed to refinement.
- Keep source verification as an approval prerequisite; a source that cannot
  substantiate the stated method is excluded or rewritten before planning.

## Open follow-ups

- Source-verification owner: confirm durable editions, direct locators, and
  the precise claims for each proposed method before requirements approval.
- Test-engineering owner: predeclare scoring rubrics and thresholds before any
  treatment output is read, especially what counts as a material advantage.
- Solution/implementation owner: decide whether the three product-manager
  methods render as a compact decision checklist or separate expertise entries;
  preserve the role body as the single behavioral contract.
