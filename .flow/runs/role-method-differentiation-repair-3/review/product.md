# Product adversarial review: narrowed role-method release

- Reviewer role: product-manager
- Date: 2026-09-09
- Evidence reviewed: repair-3 draft requirements and acceptance criteria; all
  six repair-3 research notes; repair-2 formal review and frozen scores.

## Verdict

**Keep the three-role narrow release. Do not adopt the two-axis policy or fund
the candidate screen in repair-3.** The draft has a bounded, reversible path to
release behavior already proven for architect, lead-developer, and
test-engineer. Neither a customer deadline nor a measured PM/QR workflow harm
supports delaying that path for a 24-envelope exploration. The proposed
two-axis policy would preserve PM/QR provenance and deterministic composition,
but it would also preserve active prompt cost and introduce an admission-policy
decision whose user value is unmeasured.

## Critical findings

- None. The draft does not claim that PM/QR passed, preserves their failed
  evidence, and explicitly requires approval before it supersedes the old
  all-five release relationship.

## Important findings

- **The outcome is technically resolvable, but its product-success language is
  still vague.** “Value erodes gradually” is a prioritization inference, not a
  measurable adoption or support result; the evidence inventory explicitly
  says no such signal exists. The draft should say that repair-3 succeeds as an
  evidence-correct release when its named technical criteria pass, and makes no
  adoption, support-load, or global-agent-improvement claim. If the engineer
  wants a product outcome beyond that, requirements need a measurement source,
  threshold, review date, and resulting decision.

  - Proposed disposition: change the success-criteria framing before approval.
    Retain the current 3/3 evidence threshold and add an explicit statement
    that it is the release-success measure for this work item.

- **The rejection of the two-axis option should be recorded as a product
  tradeoff, not merely a non-goal.** Architecture evidence supports preserving
  valid PM/QR provenance and deterministic composition while retaining their
  failed behavioral status. The draft chooses removal, which is reasonable
  because no evidence shows that retaining that active prompt content produces
  user value sufficient to offset runtime and policy complexity. Without that
  stated disposition, a later reader could mistake removal as a consequence of
  failed behavior rather than the chosen admission policy for this release.

  - Proposed disposition: keep removal and add the decision rationale: the
    release only admits active composed content with demonstrated behavioral
    lift; a provenance-only admission policy is deferred, not rejected as
    invalid. Revisit it only if an identified user need outweighs measured
    prompt/runtime cost and the engineer explicitly approves the policy.

- **The candidate-screen deferral is correctly scoped but needs a resolvable
  trigger.** Research ranks resolvable metrics and evidence-strength labels as
  the best hypotheses, yet their sources are not verified and their expected
  treatment-only lift remains unobserved. “Separate work item” alone leaves
  when to spend the 24-envelope cost open-ended.

  - Proposed disposition: retain deferral. Permit a new screen only after a
    named PM/QR workflow failure or adoption need is recorded, exact source
    locators are verified, and the engineer approves its fixed budget and
    frozen screen packet. A screen result is not acceptance evidence; it may
    advance a candidate only under the testability note's strict no-tie rule.

## Suggestions

- In release-facing language, use “three-role expansion with behavioral
  evidence” rather than “the expertise expansion” where the latter could imply
  a completed five-role outcome.
- Before planning, identify the exact evidence summary and handoff files that
  will carry the retained-role mapping. Acceptance criterion 3 requires named
  immutable primary and counter records, so a generic aggregate summary cannot
  satisfy it.

## Decision and sequencing

The narrow path remains first: it has gradual value decay, low incremental
evidence cost, and a reversible PM/QR deferral. The candidate screen has no
evidenced urgency, requires source verification plus 24 exploratory envelopes,
and can only produce a hypothesis for a later acceptance envelope. The
two-axis option is a durable product-policy decision, so it should enter a
separate definition and solution path only when preserving unproven active
content has demonstrated value.
