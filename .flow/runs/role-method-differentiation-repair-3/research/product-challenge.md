# Research: product challenge for role-method differentiation repair-3

- Owner role: product-manager
- Date: 2026-09-09
- Confidence: High for narrowing now; Low-to-medium that a third PM/QR method
  can clear the behavioral gate without a new, evidence-backed problem.

## Question

Is a third attempt to differentiate product-manager and quality-reviewer worth
doing now, or should the release claim narrow to the three roles with passing
evidence?

## Evidence inventory and implications

| Evidence | What it establishes | Requirement implication |
| --- | --- | --- |
| `.flow/runs/role-method-differentiation/requirements.md` | The approved repair made both replacement role gates prerequisites for the combined five-role release. | The five-role claim cannot be released from repair-2; a narrower claim must say exactly which roles it covers. |
| `.flow/runs/role-method-differentiation/review.md` and `docs/evidence/role-method-differentiation/repair-2/results.json` | Both treatments and controls classified the useful concepts; product treatment also missed the required cost-per-duration comparison, and quality treatment filed Critical before completing its evidence chain. Each strict role gate is false. | Do not treat better wording, source tracing, or passing static checks as a behavior win. A successor needs a new role-owned observable that controls actually miss. |
| `scaffolds/default/agents/product-manager.md` and `scaffolds/default/agents/quality-reviewer.md` | The current contracts already call for sequencing tradeoffs, success conditions, evidence, verification, and uncertainty discipline. | Generic refinements are likely to overlap controls again. A candidate must change a required decision or review artifact, not add explanatory guidance. |
| Prior product, business-analysis, validation, scoring, and handback research | Earlier broader candidates were narrowed to one method each; the new frozen envelope had parity and criterion-level scoring, yet preserved the two failures. Three roles retain prior passing evidence. | The next useful unit is an honest three-role boundary. A third attempt must begin with a pre-screen, not another implementation-and-rerun cycle. |

## Options, value decay, and sequence

The estimates below use relative value units because the evidence contains no
adoption, support, or revenue data. One unit is the estimated value lost by one
week of delay; it is an ordering aid, not a measured business metric.

| Path | Decay shape and one-week delay cost | Estimated duration | Value per delivery week | Reversibility and evidence cost |
| --- | --- | --- | --- | --- |
| Narrow to the three demonstrated roles now | Gradual erosion: delaying a truthful, usable subset keeps a blocked five-role claim in place and postpones learning from the proven changes. Estimated 2 units/week. | 1 week to define the boundary, update the release/handback claim, and verify its evidence references. | 2.0 | Highly reversible: the PM/QR scope can be reopened under a new versioned envelope. Low incremental evidence cost because passing and failed evidence already exists. |
| Third PM/QR differentiation attempt now | Flat-to-gradual: no deadline or external user harm is evidenced, while two failed attempts lower the chance that another generic method adds value. Estimated 1 unit/week. | 4-6 weeks: candidate discovery, source tracing, control-gap screen, new designs and rubrics, implementation, and eight paired records. | 0.17-0.25 | Reversible only before production changes; each changed method, prompt, fixture, or rubric requires a new frozen envelope. High evidence cost and high risk of a third non-discriminating result. |
| Defer all release work | Gradual erosion, estimated 2 units/week for the demonstrated subset plus the lost opportunity to learn from it. | Indefinite. | 0 | Reversible, but it produces neither a bounded release nor new evidence. |

## Recommendation

**Narrow now to the three roles with demonstrated behavior; defer PM/QR
differentiation as a separate discovery item.** This has the best estimated
value per delivery week (2.0 versus at most 0.25), preserves the integrity of
the failed evidence, and releases the part of the work whose value is already
proven. It gives up a single five-role narrative for now. That tradeoff is
preferable to spending another multi-week cycle on methods that the current
controls have twice shown they can already perform.

The narrow release must not imply that product-manager or quality-reviewer
were validated. It should state that architect, test-engineer, and
lead-developer have passing evidence, while PM/QR repair-2 remains failed and
deferred. The exact first two role names and supporting evidence references
need confirmation from the retained passing-role inventory before release
wording is approved.

## Resolvable success and failure conditions

### Narrowed release

Success is reached when the requirements and handoff name only the three
passing roles, link their existing pass evidence, retain the repair-2 failure
record for PM/QR, and remove any claim that the five-role expansion passed.
Failure is any release material that treats source provenance, static checks,
or a tied control as PM/QR behavioral proof. If the passing-role inventory
cannot identify three separately supported roles, keep the work in definition
instead of releasing a count-based claim.

### Future third attempt

Only start a third attempt if a time-boxed discovery screen can produce, for
each selected role, all of the following before implementation:

1. A named user or operator consequence that the current contract leaves
   unresolved.
2. A behavior expressed as a required decision, finding, or artifact that an
   unchanged control demonstrably does not supply on a representative input.
3. A source-traced, role-bound method and a primary/counter fixture that make
   over-application costly.
4. A frozen, reproducible envelope with parity, criterion-level treatment and
   control predicates, and a strict no-tie pass rule.

The successor succeeds only if every selected role passes all frozen primary
predicates that its control misses and safely passes its counter-case. It fails
and returns to deferred scope if the pre-screen finds only overlap, the new
fixture relies on unsupported facts, controls meet the distinctive predicate,
or treatment misses any required predicate. Do not selectively rerun or rescore
repair-2.

## Assumptions and open questions

- The three cited prior passes remain current and can be located in the
  retained inventory; this note did not independently rescore them.
- A one-week narrowed-release duration assumes no production-body change is
  needed. If it needs a new release mechanism or substantial documentation,
  re-estimate before committing.
- The requirements need an explicit audience and adoption objective for a
  five-role claim. No current evidence says that five roles, rather than the
  demonstrated subset, is needed by a date or customer.
- If a PM/QR need is found, requirements must distinguish a genuine workflow
  failure from a desire for more method provenance or more detailed prose.
