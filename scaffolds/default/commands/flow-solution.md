# flow-solution

Use `flow-solution` for the activity that turns approved requirements into a recommended technical approach. It is an **optional pre-plan step** after `flow-define` when multiple approaches exist, architectural decisions need to be made, or the work needs to be broken into chunks before `flow-plan` can shape it.

<HARD-GATE>
Do NOT produce options, recommendations, design artifacts, or the structured "Solutioning Summary" output until you have completed the Engagement Phase: restated the problem in your own words, surfaced your explicit unknowns, and the engineer has confirmed your understanding. This applies regardless of how well-specified the request seems. A confidently-drafted design built on assumed context is worse than asking and being told.
</HARD-GATE>

## Overview

This command runs the divergent / exploratory phase: applies principles and patterns, explores options, walks tradeoffs, makes (or facilitates) a recommendation, captures decisions and risks, and proposes work chunks. Where `flow-plan` shapes one solution into a buildable plan, `flow-solution` decides *which* solution.

The command runs in **three explicit phases**: Engagement (dialogue to confirm the problem) → Solutioning (precedent search, options, tradeoffs, recommendation) → Capture (emit the structured Solutioning Summary). The phases are gated; do not collapse them into a single response.

## When to Use

Use this command when:

- multiple viable approaches exist
- architectural decisions are needed (boundaries, integration, patterns)
- the engineer needs guidance on which principles/patterns apply
- cross-cutting impacts across services or contracts
- the work needs to be broken into chunks before planning

**When NOT to use:** trivial XS changes (`flow-scout`), work with a single obvious approach (skip to `flow-plan`), implementation already started (`flow-resume`).

## Primary inputs

- approved requirements (feature definition + acceptance criteria + high-level success criteria)
- definition artifacts or research notes from `flow-define` when available
- engineer's initial understanding of the problem
- existing context (code, prior tickets, related designs, ADRs)

## Primary outputs

- recommended technical approach (or facilitated decision)
- applicable principles/patterns/standards cited by section
- options considered with pros/cons and explicit tradeoffs
- proposed work chunks for `flow-plan` to shape
- owned risks with mitigations
- suggested design artifacts (spike, ADR, contracts, diagrams)
- next-lane recommendation

## Composition

Core roles (always invoked):

- `solution-architect` for option exploration, principle/pattern citation, tradeoff articulation, and artifact recommendation

Conditional roles (invoked by `solution-architect` when relevant):

- `architect` when decisions are durable, cross-project, or platform-shaping
- `test-engineer` when test strategy is non-trivial
- `security-reviewer` when design touches auth, secrets, external APIs, or sensitive data
- `data-engineer` for data model changes
- `sre` for operational concerns (scaling, observability, deployment)
- `business-analyst` when requirements need re-clarification
- `product-manager` when scope or priority questions surface

## Solutioning Workflow

### Phase 1 — Engagement

Open with dialogue. Do not produce options, designs, or the Solutioning Summary in this phase.

**Scope check (do this first).** If the request describes multiple independent subsystems, cross-cutting epics, or work that obviously needs decomposing before a single solutioning pass can shape it, flag this immediately. Don't spend questions refining details of a problem that needs to be split first. Help the engineer decompose into sub-problems and ask which they want to take through solutioning first.

For appropriately-scoped problems, your first reply must contain three things and only these things:

1. **Restated problem** — describe what you understand the engineer is trying to solve, in your own words. Not a quote of the request — a translation.
2. **Explicit unknowns** — list what you DON'T yet know. Surface gaps in scope, constraints, success criteria, integration points, non-functional requirements, and assumptions you'd need to verify. "I'm assuming X" is more useful than confidently asserting X.
3. **Clarifying questions** — 3 to 5 specific questions whose answers would close the highest-impact unknowns. Prefer multiple-choice or yes/no over open-ended when possible. Ask **one question at a time** if you anticipate the answer will reshape the next question; otherwise group a small set.

**Hard checkpoint.** Do not proceed to Phase 2 until the engineer has confirmed your problem statement and answered enough of the questions that the unknowns are reduced to manageable. If a question turns out to surface a deeper unknown, ask the follow-up before moving on. Returning to Phase 1 mid-engagement is allowed and expected.

### Phase 2 — Solutioning

Only enter this phase after the Phase 1 hard checkpoint passes.

1. **Search for precedent.** Check service catalog and existing repos for similar solutions to mirror before designing greenfield.
2. **Explore options.** At least two viable approaches. If only one option exists, explain why alternatives were rejected.
3. **Walk the architecture dimensions.** Apply the five dimensions from `architecture.md`: domain boundaries, interfaces/data flow, state/persistence, operational shape, decision durability.
4. **Make tradeoffs explicit.** Complexity, reversibility, operational cost, time-to-deliver. Name the dimensions you're trading on.
5. **Recommend or facilitate.** Offer a recommendation with rationale, or facilitate the engineer's choice when they have the context.
6. **Cost posture check (informational only).** Run `flow cost active`. If the tool recommends acting on this session (`/clear` or `/compact`), note that when proposing chunks — a heavy session is a reason to *suggest* /clear before a long chunk starts, or to *suggest* that mechanical chunks could be routed to smaller-model agents; the suggestion rides alongside the chunk proposal and never reshapes it. If `flow cost summary --days 7` shows a Codex capacity line, note it verbatim — no interpretation. Nothing here blocks solutioning, changes which option is technically right, or alters the chunks the work itself calls for. If `flow` or the usage store is unavailable, skip this step silently.

### Phase 3 — Capture

Only enter this phase after the engineer has either accepted the recommendation or made their own decision in response to Phase 2.

1. **Capture.** Applicable rules (cited by section), options + tradeoffs, decision + rationale, owned risks, proposed work chunks, recommended artifacts.
2. **Recommend the next lane.** Usually `flow-plan` (to shape the chosen approach); occasionally `flow-scout` if the work turned out trivial; rarely further solutioning for split spikes.

## Output Format

**Emit the structured output below only in Phase 3 — after the engagement and solutioning phases have completed.** Do not produce this template in your first reply to the engineer.

```md
## Solutioning Summary

### Problem
[Restated in plain language; confirmed with the engineer]

### Applicable rules
- [standard / section] — [one-line why it applies]
- [standard / section] — [one-line why it applies]

### Options
#### Option A: [name]
- Shape: [1–2 lines]
- Pros: [bullets]
- Cons: [bullets]
- Reversibility: [low / medium / high]

#### Option B: [name]
[same structure]

### Recommendation
- [Chosen option + rationale, or "engineer's call — here's how I'd decide"]

### Proposed chunks
[Vertical slices for `flow-plan` to shape; each independently mergeable]
1. [chunk]
2. [chunk]

### Risks (owned)
- [risk] — Owner: [name]; Mitigation: [concrete plan]

### Suggested design artifacts
- [e.g., Spike Form B per `templates/spike-template.md`; ADR; OpenAPI contract; sequence diagram]

### Next lane
- `flow-plan` | `flow-scout` | further solutioning
- Why:
```

## Anti-Pattern: Skipping the Engagement

Every consultation goes through the Engagement Phase. A "simple" or "well-specified" request is *exactly* where unexamined assumptions cause the most wasted design work. The dialogue can be short (a single round of confirmation for genuinely well-specified problems), but you MUST produce the restate-unknowns-questions reply and the engineer MUST confirm before any options are drafted.

The most common failure mode of this role is jumping straight to options and architecture because the request *looks* clear. Resist it. Confidently-drafted designs built on inferred context are how solutioning produces irrelevant or wrong work.

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I have enough context from the request to draft a design." | Solutioning starts with what you DON'T know, not what you can infer. If you didn't have to ask anything, you skipped the work. |
| "The problem is well-specified; I don't need to clarify." | Specified ≠ unambiguous. Your restated version may differ from the engineer's intent in ways neither of you would catch without saying it out loud. |
| "I'll ask questions as they come up while drafting." | The engineer should answer questions before the design exists, not be cornered into accepting one because it's already drafted. |
| "There's only one solution." | If you can't name an alternative, you haven't explored. Generate at least one rejected option. |
| "We don't need to consult patterns — this is obvious." | Patterns are why the domain has shape. Cite at least one. |
| "I'll figure out chunks during planning." | Solutioning's job is to produce the work-breakdown shape; planning shapes one chunk. |
| "The engineer is smart; they can decide without rule citations." | Citations build muscle. An engineer who sees the rule once learns it; an engineer told "trust me" doesn't. |
| "Risks can be tracked later." | Unowned risks at solutioning time become production incidents. |

## Red Flags

- proceeding to Phase 2 (options) before the engineer has confirmed the problem statement
- first reply contains options, architecture content, or the structured Solutioning Summary template
- restating without surfacing explicit unknowns or questions
- producing the structured output template in a single reply
- single-option recommendation without rejected alternatives
- no rule citations
- risks without named owners
- "it depends" without naming the dimensions
- engineer's actual question is "how do I build this?" — that's planning, not solutioning
- proposed chunks are vague gestures rather than concrete vertical slices

## Escalation Rules

- Escalate to `architect` for cross-project or platform-shaping decisions.
- Escalate to `flow-plan` once the approach is chosen and the work is ready to be shaped.
- Escalate back to `flow-define` if requirements, outcome, evidence, or approval turn out to be under-specified.

## Verification

Before leaving `flow-solution`, confirm:

- [ ] Phase 1 happened — first reply was restate + unknowns + questions; no options drafted yet
- [ ] engineer confirmed the problem statement before Phase 2 began
- [ ] at least two options considered (or single-option recommendation justified)
- [ ] applicable rules cited from loaded standards
- [ ] risks have named owners and concrete mitigations
- [ ] proposed chunks are coherent for `flow-plan`
- [ ] suggested artifacts named
- [ ] next lane recommended with rationale
- [ ] the cost posture check ran — mentioned alongside the chunk proposal when it surfaced anything, silent when it didn't, skipped silently if flow was unavailable

## Finish Criteria

`flow-solution` is done when the engineer has a clear recommended approach with explicit tradeoffs, owned risks, and chunks ready for `flow-plan` to take into shaping.
