# flow-solution

Use `flow-solution` for the activity that turns approved requirements into a recommended technical approach. It is an **optional pre-plan step** — appropriate when multiple approaches exist, architectural decisions need to be made, or the work needs to be broken into chunks before `flow-plan` can shape it.

## Overview

This command runs the divergent / exploratory phase: applies principles and patterns, explores options, walks tradeoffs, makes (or facilitates) a recommendation, captures decisions and risks, and proposes work chunks. Where `flow-plan` shapes one solution into a buildable plan, `flow-solution` decides *which* solution.

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

1. **Clarify the problem.** Restate in your own words; confirm understanding before proposing.
2. **Search for precedent.** Check service catalog and existing repos for similar solutions to mirror before designing greenfield.
3. **Explore options.** At least two viable approaches. If only one option exists, explain why alternatives were rejected.
4. **Walk the architecture dimensions.** Apply the five dimensions from `architecture.md`: domain boundaries, interfaces/data flow, state/persistence, operational shape, decision durability.
5. **Make tradeoffs explicit.** Complexity, reversibility, operational cost, time-to-deliver. Name the dimensions you're trading on.
6. **Recommend or facilitate.** Offer a recommendation with rationale, or facilitate the engineer's choice when they have the context.
7. **Capture.** Applicable rules (cited by section), options + tradeoffs, decision + rationale, owned risks, proposed work chunks, recommended artifacts.
8. **Recommend the next lane.** Usually `flow-plan` (to shape the chosen approach); occasionally `flow-scout` if the work turned out trivial; rarely further solutioning for split spikes.

## Output Format

**Always emit your result in the following format before ending the command.** Do not stop after gathering inputs — produce the output.

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

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "There's only one solution." | If you can't name an alternative, you haven't explored. Generate at least one rejected option. |
| "We don't need to consult patterns — this is obvious." | Patterns are why the domain has shape. Cite at least one. |
| "I'll figure out chunks during planning." | Solutioning's job is to produce the work-breakdown shape; planning shapes one chunk. |
| "The engineer is smart; they can decide without rule citations." | Citations build muscle. An engineer who sees the rule once learns it; an engineer told "trust me" doesn't. |
| "Risks can be tracked later." | Unowned risks at solutioning time become production incidents. |

## Red Flags

- single-option recommendation without rejected alternatives
- no rule citations
- risks without named owners
- "it depends" without naming the dimensions
- engineer's actual question is "how do I build this?" — that's planning, not solutioning
- proposed chunks are vague gestures rather than concrete vertical slices

## Escalation Rules

- Escalate to `architect` for cross-project or platform-shaping decisions.
- Escalate to `flow-plan` once the approach is chosen and the work is ready to be shaped.
- Escalate back to `business-analyst` or `product-manager` if requirements turn out to be under-specified.

## Verification

Before leaving `flow-solution`, confirm:

- [ ] problem is restated and confirmed
- [ ] at least two options considered (or single-option recommendation justified)
- [ ] applicable rules cited from loaded standards
- [ ] risks have named owners and concrete mitigations
- [ ] proposed chunks are coherent for `flow-plan`
- [ ] suggested artifacts named
- [ ] next lane recommended with rationale

## Finish Criteria

`flow-solution` is done when the engineer has a clear recommended approach with explicit tradeoffs, owned risks, and chunks ready for `flow-plan` to take into shaping.
