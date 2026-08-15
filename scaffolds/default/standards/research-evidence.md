# Research Evidence Standard

This standard defines how Flow roles gather and use evidence during definition, solutioning, planning, and review.

## Research questions

Research starts with a named question.

Good questions include:

- What standards govern this kind of work?
- What internal precedent should we mirror?
- What do comparable tools, teams, or products do?
- What user reports or support cases show this matters?
- What operational incidents, alerts, logs, or support load make this urgent?
- What security, privacy, data, or rollout constraints should shape the requirements?

Do not research background without saying what decision the research will inform.

## Source quality

Prefer primary and durable sources:

1. active project artifacts, issue trackers, support tickets, incidents, logs, dashboards, ADRs, runbooks
2. official standards, vendor documentation, and framework docs
3. internal precedent in existing repos
4. reputable public examples and comparable tools
5. anecdote, clearly labeled as low-confidence input

When evidence is stale, incomplete, or second-hand, say so.

## Role research focus

| Role | Primary question | Looks at | Requirement impact |
|---|---|---|---|
| `product-manager` | Is this worth doing, and why now? | comparable products, roadmap pressure, user/business value, opportunity cost | success criteria, priority, non-goals, defer/reject |
| `business-analyst` | Is the problem/workflow clear enough? | user reports, current workflows, stakeholder gaps, workarounds | personas, workflows, acceptance criteria, open questions |
| `solution-architect` | Is the capability boundary sound? | standards, internal precedent, architecture docs, comparable implementations | constraints, assumptions, next lane, architecture questions |
| `sre` | Is there operational evidence or risk? | incidents, logs, alerts, runbooks, dashboards | reliability requirements, rollout constraints, observability criteria |
| `support-lead` | Is this causing support burden? | tickets, FAQs, escalation notes, docs gaps | user pain evidence, support acceptance criteria, docs requirements |
| `test-engineer` | Can this be proven? | existing tests, validation patterns, measurable criteria | acceptance criteria, testability constraints, open questions |
| `security-reviewer` | Could this create abuse or exposure? | policy, auth/data flows, third-party risks, threat cases | security constraints, non-goals, approval blockers |
| `data-engineer` | Does data shape/lifecycle matter? | schemas, ownership, migrations, retention, lineage | data constraints, lifecycle requirements, migration questions |
| `ux-specialist` | Is the experience coherent? | journeys, accessibility, interaction patterns, content | user states, UX acceptance criteria, terminology |

## Research notes

Use `templates/research-note.md` for durable research.

Each note includes:

- question
- method and sources
- findings
- implication for requirements or decision
- confidence
- open follow-ups

Research is not complete when links are gathered. It is complete when findings change, confirm, or rule out a requirement, acceptance criterion, non-goal, assumption, or next lane.

## Confidence

Use simple confidence labels:

- High: primary source, current, directly relevant
- Medium: credible source, partial fit, or some uncertainty
- Low: anecdotal, stale, indirect, or insufficient

Low confidence evidence can shape open questions. It should not be the only basis for approval.

## Synthesis

The command or lead role synthesizes research by translating findings into one of these outcomes:

- requirement added or changed
- acceptance criterion added or changed
- non-goal clarified
- assumption confirmed or rejected
- open question recorded
- next lane changed
- idea deferred or rejected

## Relevant principle

Evidence exists to change the work. A pile of links without requirement impact is not a definition artifact.
