# Research: observable successor requirements for PM and QR differentiation

- Owner role: business-analyst
- Date: 2026-09-09
- Confidence: High for the repair-2 failure and current-contract comparison; Medium for the candidate-method forecasts until exploratory trials and source verification occur

## Question

What user-visible behavior could distinguish product-manager (PM) and
quality-reviewer (QR) treatment bodies from their unchanged controls, what
fixtures can prove it without a false pass, and should repair-3 attempt both
replacements?

## Method and sources

- Read the approved repair requirements and acceptance criteria, formal quality
  and test reviews, and the prior business-analysis and product research under
  `.flow/runs/role-method-differentiation/`.
- Read the repair-2 frozen manifest, primary and counter prompts, designs,
  machine-readable scores, and all eight raw response records under
  `docs/evidence/role-method-differentiation/repair-2/`.
- Compared the candidate behaviors with the current PM and QR bodies and their
  composed corpus entries in `scaffolds/default/agents/` and
  `scaffolds/default/expertise/`.
- Read the repair-3 archive-retrieval note. Its search was unavailable; the
  preservation and new-envelope constraints below come from manually inspected
  local evidence outside the active retrieval selection.

## Findings

### What repair-2 establishes

- **Observed:** Both frozen role gates are false. PM treatment missed the
  required rate calculation while its unchanged control supplied the time-value
  classifications and delay-sensitive sequence. QR treatment and control both
  supplied the alternative explanation and the evidence that rejected it; both
  put the Critical heading before that chain. Counter cases passed in both arms.
- **Inferred:** The selected methods describe competent behavior already
  elicited by the unchanged contracts. A successor cannot call a conclusion,
  severity, a generic verification story, or a generic success metric a
  treatment-only effect.
- **Decided by prior review:** repair-2 remains immutable. A changed method,
  fixture, prompt, rubric, or score rule needs a separate frozen envelope; it
  cannot be repaired by rerun or rescore.

The user-visible job is to give a product decision-maker a reproducible,
appropriately cautious decision and give an acceptance owner findings whose
scope and evidentiary basis can be checked. It is not to add corpus entries or
make an output adopt a particular heading.

### Candidate comparison

| Candidate | Behavior absent as an explicit current contract | Observable treatment result | Control-overlap risk | Readiness |
| --- | --- | --- | --- | --- |
| PM: classify reversibility before setting decision pace and evidence burden | The PM body asks for risks and tradeoffs, but does not require a reversible/irreversible classification, the consequence of reversal, or a changed commitment posture. | Separates a reversible experiment from an irreversible commitment; chooses a bounded experiment/decision checkpoint for the former and a higher evidence threshold or explicit escalation for the latter, without prescribing technical rollback. | High: a capable control may independently suggest a pilot, phased launch, or more research. | Trial only; source locator and a discriminating pilot are needed. |
| PM: make a success metric resolvable | The PM body asks how the team will know success, but does not require a metric's population, source, baseline/comparator, threshold, decision date, and action on failure. | Writes a resolution contract or marks the metric not yet defined when one of those inputs is absent; does not turn a directional aspiration into a passing measure. | Medium-high: controls commonly propose a threshold and date when a prompt practically supplies them. | Stronger PM candidate, but needs a source-verified definition and exploratory comparison. |
| QR: derive an expected-content inventory before reviewing the artifact | QR reads the spec and artifact but has no requirement-to-artifact inventory or explicit rule to file a missing approved element. | Lists each supplied requirement, maps supplied proof, and reports the exact omitted element with the relevant requirement; distinguishes absent from not supplied. | Medium: controls can notice an obvious omission, especially when the prompt names it. | Strongest candidate for a future QR trial. |
| QR: label material evidence strength | QR requires a verification story and residual risks but does not require observed/read/author-asserted labels per material claim. | Separates direct observation, inspected evidence, and author assertion; limits the finding and names the exact missing proof. | Medium-high: the present QR body already asks for caveats and uncertainty, so labels can become cosmetic. | Trial only, preferably as a reviewer-verifiability method rather than a release replacement. |

The old alternative-explanation and delay-sequencing methods must not return as
requirements: their control overlap is observed, not merely predicted.

## Proposed successor requirements and evidence design

These are requirements for a future *exploratory* envelope, not approved
replacement requirements for the five-role release.

### PM resolvable-success-metric trial

1. The treatment must turn each claimed success measure into a resolution
   contract containing: named population/unit, data source, baseline or
   comparator, numeric threshold, assessment date/window, and the decision
   taken if the threshold is missed. If any input is absent, it must label the
   measure not yet resolvable and request only the missing input.
2. The primary fixture must give two launch options equal in stated strategic
   appeal, each with a different supplied telemetry source and baseline. One
   proposed measure must be directional (for example, "improve activation")
   and one must be resolvable from supplied data. It must also state the launch
   decision that the measure governs. The rubric must credit only the complete
   resolution contract and rejection of the directional measure, not a generic
   metric, recommendation, or caveat.
3. The control is the frozen unchanged PM body. It must be scored against the
   same criteria, and a pass requires treatment to satisfy every distinctive
   primary item that control misses. A control that independently completes the
   contract is a failed differentiation result, even if the treatment is good.
4. The counter fixture must withhold a necessary source or baseline while
   offering an attractive numerical target. Treatment passes only if it does
   not invent a source, baseline, or causal comparison and records the metric
   as unresolved. It may still recommend a reversible discovery step if that
   step is explicitly supported by the packet.

### QR expected-content-inventory trial

1. Before judging the implementation, treatment must create a requirement-to-
   evidence inventory for every supplied acceptance requirement. Each row must
   state `present`, `absent`, or `not supplied`; only `absent` supports an
   omission finding.
2. The primary fixture must contain a clean-looking implementation and passing
   tests that cover two of three explicit acceptance elements. The omitted
   element must be independently observable from the supplied diff, test
   output, and requirement; it cannot rely on speculation about undisclosed
   code. Treatment passes only when it maps the omitted element to its source
   requirement and states a concrete correction or proof request.
3. The counter fixture must map every requirement to supplied implementation
   or direct proof, while including an irrelevant file or an optional design
   preference. Treatment passes only when it completes the inventory without
   inventing an omission or treating an optional preference as approved scope.
4. A severity finding is separate from the inventory result. The trial may
   verify that an omission is found, but it must not score Critical severity
   unless the packet supplies the severity criteria and the QR's existing
   alternative-explanation rule is satisfied.

### Shared envelope requirements

- Freeze exact control and treatment bodies, corpus/source hashes, prompts,
  rubrics, client settings, scorer identity, and the stopping rule before any
  output is read. Keep arms identical except for body delta.
- Preserve all repair-2 bytes and record repair-3 start/end digests for the
  lead-developer contract and the prior evidence inventory. A current hash is
  insufficient evidence that nothing changed during a successor.
- Use at least one delete-or-negate-and-restore mutation per selected executable
  instruction. The associated deterministic assertion must fail on both
  deletion and semantic negation, then pass only after restoration.
- Retain raw successful and failed response envelopes, criterion-level scoring
  with response citations, parity metadata, and fixture/source hashes. Do not
  normalize, selectively rerun, or rescore a completed content response.
- Stop a role trial after the frozen primary and counter arms, one allowed
  infrastructure retry of the complete role set, and independent review. A
  treatment/control tie, treatment miss, control satisfaction of any
  distinctive primary item, counter over-application, missing parity, or
  ambiguous scoring is a failed trial. Do not tune the fixture after outputs;
  record its defect and begin a new versioned envelope if correction is useful.

## False-pass cases the fixtures must reject

| Edge case | Required guard |
| --- | --- |
| Missing data | The PM must not manufacture a baseline, telemetry source, cohort, value, or causal comparison; QR must distinguish `not supplied` from `absent`. |
| Unsupported arithmetic | Every quantity used for a PM calculation must have a stated numerator, denominator, units, and horizon. If an initial value or baseline is absent, prohibit total-value, percentage-change, or ROI claims. This closes repair-2's unsupported onboarding total. |
| Ordering disguised as analysis | Do not award a PM sequence merely because it is plausible. Credit requires the stated resolution contract or reversibility classification to change the requested decision. A treatment that announces "pilot first" without identifying reversibility and its decision consequence fails. |
| Negated or inert instruction | Literal snippets can survive "do not" wording. Test a deletion and a semantic negation of each selected instruction; both must break the relevant contract assertion. |
| Evidence preservation theater | A new manifest or current source hash does not prove the old record was retained. Compare pre-run and post-run hashes for frozen evidence and retained lead-developer material, and keep the receipt with the envelope. |
| Cosmetic evidence labels | QR does not pass merely by writing "observed" or "asserted." Each label must match the packet provenance and constrain the finding or residual risk. |
| Obvious omission | A QR control may find a plainly named missing item through ordinary review. Use an independently authored, clean-looking primary fixture and treat a control match as a failed differentiation result. |
| Severity leakage | Do not infer Critical from an omission or write order alone. Require stated impact/severity conditions and the existing alternative-explanation gate. |

## Questions requiring targeted research or exploratory trials

- **Targeted source research:** What verified, role-appropriate source and
  locator supports the PM resolution-contract fields and the PM reversibility
  boundary? The previous source list is a hypothesis, not a verified adoption
  record. What source supports QR inventory review and evidence-strength
  labeling without turning review into test-plan ownership?
- **Exploratory trials:** Can the unchanged PM control already create the full
  resolution contract when the prompt supplies concrete telemetry facts? Can
  the unchanged QR control already build an inventory and catch a non-obvious
  omission? A frozen pilot is needed before either behavior becomes a release
  requirement.
- **Fixture authoring:** An independent test-oriented owner should author and
  freeze the primary/counter packets before body changes. The same person who
  proposes the wording should not tune expected responses after seeing output.

## Implication for requirements and recommendation

- **Recommended decision:** narrow the releasable claim now to the three roles
  with recorded behavioral passes. Do not attempt two PM/QR replacement methods
  in this release.
- **Why:** two consecutive two-role attempts have no treatment-over-control
  evidence. The two strongest candidates still need source verification and
  discriminating pilot results, and the five-role claim requires both to pass.
  Adding two unproven methods would repeat the failure condition while delaying
  the demonstrated three-role value.
- **Follow-on shape:** run at most two separately versioned exploratory trials,
  beginning with QR expected-content inventory and PM resolvable metrics. A
  later definition may promote only a candidate that shows treatment-only
  behavior, passes its counter-case, and has a verified source locator. It may
  then decide whether pursuing the second role is worth reopening the five-role
  claim.

## Open follow-ups

- Product manager: decide whether the three-role subset has sufficient release
  value and set its user-facing success condition.
- Solution architect: confirm that narrowing does not imply a change to
  expertise composition or provenance policy.
- Test engineer: design and independently freeze pilot fixtures, rubric,
  scorer process, mutations, and preservation digest before a new trial.
- Engineer: explicitly approve any narrowed release definition or a separately
  scoped exploration. Neither is approved by this note.
