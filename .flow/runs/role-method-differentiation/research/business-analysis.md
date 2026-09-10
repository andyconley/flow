# Business analysis: role-method differentiation

## Observed problem

The prior expansion added corpus entries to three role bodies whose existing
prompts already asked for broadly similar behavior. Product-manager treatment
and control tied; lead-developer treatment over-applied planning to a small
fix. The useful release question is therefore whether each new method changes
an observable role-owned output without harming a counter-case.

## Existing gaps and user impact

| Role | Existing behavior | Missing decision method | User impact |
| --- | --- | --- | --- |
| Product manager | Asks why now, tradeoffs, and how success will be known. | No way to compare urgency over time, match evidence rigor to reversibility, or reject an unresolvable metric. | A recommendation can sound reasoned while still sequencing by assertion and promising success that cannot be measured. |
| Quality reviewer | Reviews the supplied artifact across correctness, risk, and verifiability; asks for a verification story. | No spec-derived inventory of expected content, alternative explanation before a critical, or distinction between run/read/author-asserted proof. | A clean partial change can be approved; confident but weak criticals and weak verification evidence can look stronger than they are. |
| Lead developer | Requires change surface, execution order, two delivery slices, risks, and verification for every change. | No proportionality rule or short form for an atomic, reversible, well-tested change. | A one-file correction receives invented steps, slices, and generic risks, making planning slower and less trusted. |

## Role boundaries

- Product manager may classify a decision's reversibility to set product
  decision rigor. It must not prescribe technical rollback mechanics; those
  belong to lead-developer or architect.
- Quality reviewer may derive expected contents from approved intent and
  classify the strength of evidence. It must not turn an unresolved alternative
  explanation into a critical finding.
- Lead developer owns technical blast radius, test coverage, and rollback path.
  Its short form must be unavailable where state, public contracts, migrations,
  cross-service coupling, or absent coverage make a reversal uncertain.

## Acceptance criteria

### Product manager

1. Given two otherwise comparable options whose value decays differently, the
   treatment states each decay shape and makes a value-over-time sequencing
   comparison; the control need not do so.
2. Given a reversible experiment and an irreversible commitment, the treatment
   classifies both and adjusts requested evidence or pace accordingly, without
   asserting engineering implementation details.
3. Each proposed success metric names a measurement source, threshold, date,
   and failure or kill condition. A vague directional metric is identified as
   insufficient rather than accepted.
4. On a settled statutory or date-bound decision, the treatment does not invent
   a decay analysis or delay a clearly required action.

### Quality reviewer

1. Before judging changed lines, the treatment derives an expected-content
   list from the supplied requirement and files a missing required element as a
   finding when the artifact omits it.
2. Before a critical finding, the treatment records one plausible explanation
   under which the artifact is correct and the evidence that rules it out. If
   it cannot rule that explanation out, it asks a question or lowers the
   finding rather than labeling it critical.
3. The verification story labels each material claim as observed, read, or
   author-asserted and names unverified material in residual risk.
4. On a complete, well-evidenced change, the treatment does not manufacture
   omission findings or downgrade directly observed proof.

### Lead developer

1. The treatment classifies reversibility, blast radius, and existing test
   coverage before choosing plan depth.
2. For an atomic, reversible, single-file change with relevant existing tests,
   it uses a short form: one concise change statement, the specific validation,
   and the rollback mechanism. It omits empty execution/slice/risk sections
   with a one-line reason rather than inventing content.
3. For a migration, public API change, stateful change, cross-cutting change,
   or weakly tested path, it uses the full plan and does not claim a cheap
   revert without establishing one.
4. The short form is clearer and materially shorter than the current full
   template while retaining enough information for implementation and review.

## Evaluation workflow

For each role and criterion, retain the unchanged base role body as control and
hold prompt, project input, runtime, model, and effort constant. The treatment
must include only the approved method change. Score outputs against a
prewritten, role-specific rubric that requires the distinctive behavior above;
generic quality, verbosity, or template compliance cannot count as improvement.
Use both a primary case that makes the method necessary and a counter-case that
makes over-application harmful. Record raw outputs, runner metadata, scoring,
and the reason for each gate decision.

## Risks and open questions

- Source tracing still must establish stable, role-appropriate pinpoint
  citations before wording is adopted.
- Reversibility is shared vocabulary across product and engineering. The role
  boundary above must appear in the prompts and fixtures so the two agents do
  not converge on duplicate technical advice.
- The lead-developer short form changes a fixed output contract. Its rendering
  and downstream consumers must be inspected before approval.
