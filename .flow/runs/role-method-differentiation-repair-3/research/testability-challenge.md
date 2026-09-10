# Research: testability of the four remaining role methods

- Owner role: test-engineer
- Date: 2026-09-09
- Confidence: High for the evidence limits and proposed validation contract;
  Medium for the expected ranking until the bounded screen runs.

## Question

Can product reversibility classification, resolvable success metrics,
omission-first review, or evidence-strength labels show a treatment-only,
role-useful behavior against the unchanged `2712f5f1fb7f3ecabbc0bbcb77cdf9cd33431208`
controls without turning formatting or ordinary competent inference into a win?

## Method and sources

- Read the repair-3 testability, product, architecture, and requirements
  discovery briefs; the last three identify the four candidate methods and the
  immutable scope.
- Compared the frozen control bodies at the named commit with the current
  product-manager and quality-reviewer contracts. The controls already require
  tradeoffs, risks, success/follow-through, correctness, missing cases, and a
  verification story; an output that merely restates any of those is not a
  discriminating result.
- Read both prior generations of raw comparison designs/results under
  `docs/evidence/agent-expertise-expansion/` and
  `docs/evidence/role-method-differentiation/repair-2/`, especially the
  repair-2 designs, scorecard, manifest, and mutation record.
- Read the formal review and independent test audit at
  `.flow/runs/role-method-differentiation/review.md` and
  `review/acceptance-test.md`, plus the frozen scoring analysis. They establish
  that repair-2's treatment and control tied on substantive reasoning, the
  product fixture permitted unsupported total-value arithmetic, the quality
  boundary lacked a delete/restore mutation, and no repair-start preservation
  digest existed.
- Used `scaffolds/default/standards/research-evidence.md` to translate these
  findings into measurable acceptance constraints. No web research was needed:
  this question is about local testability, not a current external fact.

## Findings

### Candidate ranking

The ordering is a hypothesis for the screen, not a choice of implementation.
"Discriminability" means a treatment-only, observable decision difference;
"role value" means value to the role's normal output if that difference holds.

| Rank | Candidate method | Expected discriminability | Role value | Test oracle and principal risk |
| --- | --- | --- | --- | --- |
| 1 | Product: resolvable success metrics | Medium-high | High | Given a stated outcome and actual available telemetry, the response must name a source, baseline or explicit unknown, threshold, decision date, and a predeclared continue/stop condition. A generic "measure adoption" statement, an invented baseline, or a threshold with no decision consequence fails. The existing success-metrics output section makes a format-only score invalid. |
| 2 | Quality: evidence-strength labels | Medium | High | Given a review packet containing direct artifacts, documents, and author claims, each material conclusion must distinguish observed, read, and author-asserted support and must lower or defer a conclusion supported only by assertion. Labels without a changed finding, severity, or requested proof are formatting-only and fail. |
| 3 | Quality: omission-first review | Medium-low | Medium-high | From an approved criterion list and evidence packet, derive an expected-content list, identify one genuinely unproved required item, and request the smallest proof at its user/system boundary. Current controls already flag missing cases, so a generic omission finding is not enough. |
| 4 | Product: reversibility classification | Low-medium | Medium | From supplied rollback, state, and exposure facts, classify the decision and make evidence/slice depth proportionate to the classification. Current tradeoff, risk, scope, and learning-slice instructions make this particularly vulnerable to competent control inference and to over-applying a technical-planning concern in a product decision. |

The first two are worth screening because they can change an acceptance or
release decision in a way that can be scored from supplied facts. The latter
two are not ruled out, but should not consume a frozen acceptance envelope
unless the screen shows a repeatable treatment-only difference.

### Bounded exploratory pre-screen

This screen is a design-selection exercise only. Its artifacts must live in a
new versioned `exploration/` directory, carry `not acceptance evidence`, and
must never be imported into a later manifest, score, or release claim.

1. Before executions, freeze a screen packet with the unchanged control-body
   hashes, one candidate treatment body per method, injection mechanism,
   client/model/effort/budget, four fixture texts, scoring sheets, and a
   registry of intended runs. Do not edit the frozen repair-2 files.
2. Run exactly two primary fixtures and one counter fixture per candidate,
   with an identical prompt and client settings per treatment/control pair:
   24 envelopes total. The second primary is a near-miss designed to prevent
   a method from passing by keyword matching the first. Do not rerun an arm
   for a better answer; a transport/client failure invalidates its pair and is
   recorded once.
3. Score each redacted pair independently against only its predeclared atomic
   predicates. The scorer records the cited packet fact or response span for
   every pass. Reveal arm identity only after scoring is signed. A candidate
   advances only if treatment has a useful, correct treatment-only predicate
   in both primaries, treatment handles its counter safely, and no predicate
   win is solely headings, word count, a named-source reference, or a label.
   Otherwise defer that candidate for this release.

Use these fixture families and concrete oracles:

| Method | Primary fixtures | Counter fixture | Treatment-only screen predicate |
| --- | --- | --- | --- |
| Resolvable metrics | (a) an adoption outcome with an instrumented event stream and stated baseline; (b) a retention outcome with the source and baseline explicitly unavailable | an outcome request with no usable source or baseline | Name only supplied measurement facts, threshold, decision date, and stop/continue action; in the counter, request the missing source/baseline rather than fabricate a metric. |
| Evidence labels | (a) a defect claim supported by a failing test and a spec; (b) a claim supported only by a PR description while a log points to a plausible alternative | a packet where all supplied support is author assertion | Correctly distinguish evidence strength and change the finding to an evidence request or lower severity when support is asserted-only. |
| Omission-first | (a) a five-item acceptance list where one user-visible error assertion is absent; (b) an interface contract where one backward-compatibility proof is absent | a packet that proves every required item but includes an optional improvement | Derive the relevant required item, locate its absent proof, and request one boundary-level proof; do not call the optional item a required omission. |
| Reversibility | (a) a product choice that irreversibly commits customer-visible data; (b) a choice with a documented, tested revert and contained audience | a small reversible experiment with no irreversible state or public exposure | Classify from supplied facts and make the requested evidence/slice depth proportionate; do not declare a property that the packet does not establish. |

### Frozen successor gate, only for a screened-in method

The screen cannot be upgraded after the fact. A later acceptance envelope must
use newly authored, versioned fixtures and freeze the following before any live
response is read:

- candidate source/role wording, unchanged control body at its exact commit,
  prompt text, fixture packets, arm injection mechanism, model/effort/budget,
  turn limit, scorer instructions, pair-parity rule, atomic rubric, stopping
  rule, and expected run registry;
- SHA-256 digests at repair start for every mutable treatment/control source,
  both frozen bodies, fixtures, rubrics, raw-output directory, and retained
  lead-developer evidence. Add a delete/restore mutation for each selected
  executable boundary and demonstrate that semantic negation, not merely
  deletion, fails the deterministic assertion;
- two blinded independent scorers, an adjudication rule fixed before runs, and
  a retained evidence map from every scored predicate to a supplied packet fact
  and response span.

The envelope contains two paired primaries and one paired counter. For a role
to pass, all pairs must have parity and successful records; treatment must pass
every applicable primary predicate in both primaries; control must miss at
least one *useful, method-specific* predicate in each primary; treatment must
pass its counter without invention or over-application; and both scorers must
agree after the fixed adjudication rule. Any tie, ambiguous predicate, invented
input, client failure, mismatch, rubric deviation, or counter false positive
is a role failure. The formula and all raw envelopes are retained even on
failure. A changed candidate, prompt, fixture, body, model setting, rubric, or
run set starts a distinct envelope; it cannot be a selective rerun.

### Required false-pass controls

- **Vague metrics:** accept a metric predicate only when the packet supplies
  its source and the output provides a threshold, decision date, and action.
  Missing data must lead to an explicit measurement question, not a guessed
  number or a pass for metric-shaped prose.
- **Invented inputs and arithmetic:** fixtures include every numeric input
  required by a scored calculation, or prohibit the calculation. Each claimed
  input must cite the packet. This removes repair-2's unsupported onboarding
  total-value path.
- **Formatting-only and generic competence:** score consequences, not headings
  or vocabulary. A label, checklist, or classification earns no point unless
  it correctly changes the acceptance decision, severity, requested evidence,
  sequencing, or measurement action.
- **Semantic negation:** deterministic checks parse or test the required
  instruction's positive obligation and delete/restore plus negate/restore
  mutations. Raw substring presence is insufficient.
- **Selective reruns and changed rubrics:** freeze the registry and hashes
  before execution, retain all outputs and failures, blind score before arm
  disclosure, and version any post-score correction as a new envelope.
- **Counter overfit:** use a near-miss primary and counter per method. The
  counter's safe behavior is part of the role gate, not a narrative note.

## Implication for requirements

- Add a definition requirement that only a screened-in candidate can enter a
  successor acceptance envelope; all other candidates are deferred without a
  behavioral-lift claim.
- Add acceptance criteria for two blind-scored primaries, a paired counter,
  fact-cited atomic predicates, treatment-only useful behavior in each primary,
  parity, immutable raw retention, and the no-rerun stopping rule.
- Add explicit non-goals: no credit for prose structure, named-method words,
  generic competent inference, unsupported arithmetic, or a literal-only
  executable-boundary test.
- **Recommendation: narrow before proceeding.** Screen resolvable metrics and
  evidence-strength labels first; proceed to a frozen envelope only for a
  candidate that clears the screen. Defer omission-first and reversibility
  unless their screen results meet the same threshold. If neither leading
  candidate clears, narrow the release to the three roles with demonstrated
  behavior rather than attempting a third unmeasurable five-role claim.

## Open follow-ups

- Product-manager and quality-reviewer: confirm whether the role value of the
  two leading candidates justifies a 24-envelope exploratory screen.
- Solution/implementation owner: specify a semantic deterministic assertion
  mechanism before modifying role bodies; a text substring test is inadequate.
- Test-engineer: author the new fixture packets, rubric, run registry, and
  preservation-digest script only after the engineer approves the candidate
  scope and the screen budget.
