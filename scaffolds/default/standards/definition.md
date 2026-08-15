# Definition Standard

This standard defines how Flow turns early ideas into approved requirements.

## Scope

Definition is for features, architectural capabilities, and workflow or process capabilities.

Bug reports stay in planning for now. A bug-shaped request has expected behavior, actual behavior, impact, and reproduction or evidence. Route those to `flow-plan` unless the work is really a broader capability definition.

## Approved requirements

Approved requirements include:

- problem or opportunity
- audience, operator, maintainer, or affected role
- desired outcome
- success criteria
- acceptance criteria
- non-goals
- constraints
- assumptions
- evidence and research implications
- open questions
- explicit approval status

Approval means the engineer or owner agrees the requirements are good enough to feed `flow-plan` or `flow-solution`. Approval does not mean the implementation approach has been chosen.

## Artifact choice

Use a structured chat summary only when all are true:

- the definition is small
- no research files were needed
- no multi-session handoff is expected
- the requirements can be understood without private chat context

Use a durable artifact when any are true:

- the definition may span sessions
- research notes were created
- multiple roles participated
- the work affects an architectural capability or project scope
- the requirements will be reviewed, archived, or handed to another agent

## Role participation

Definition always involves:

- product perspective for outcome, priority, success criteria, and non-goals
- requirements perspective for users, workflows, ambiguity, and acceptance criteria
- solution perspective for capability boundaries, standards, precedent, and feasibility assumptions

The opening role depends on the problem. Product-led ideas start with product. Architecture-led capabilities start with solution architecture.

## Adversarial review

Requirements are not ready until they have been challenged.

The review asks:

- Is this worth doing now?
- Is the scope too broad or too vague?
- Are users, workflows, and acceptance criteria testable?
- Are non-goals explicit enough to protect the scope?
- Are standards, precedent, constraints, and feasibility assumptions represented?
- What evidence would change or invalidate these requirements?

Every adversarial finding gets a disposition.

## Routing

After approval:

- route to `flow-solution` when technical options, durable architecture decisions, or work chunks still need exploration
- route to `flow-plan` when requirements and the likely approach are clear enough for implementation planning
- stay in definition when evidence, scope, or approval is missing
- defer or reject when the evidence does not justify the work

## Relevant principle

Definition protects planning from becoming discovery in disguise. Planning can be fast only when the outcome and requirements are already clear.
