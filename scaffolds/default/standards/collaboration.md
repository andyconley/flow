# Collaboration Standard

This standard defines how work moves from idea to implementation to review.

## Roles

Every project should declare providers for these responsibilities:

- who shapes work
- who implements
- who reviews
- what makes work ready
- what the implementation handback must contain

The provider may be:

- a human
- the main coding agent
- a subagent
- another external agent

At minimum, every project should assign providers for:

- product ownership
- requirements shaping
- implementation
- acceptance review

## Durable sources of truth

Work should be understandable without relying on chat history.

By default, use this order:

1. issue tracker or assigned work item
2. project overlay and active standards
3. design or Storybook contract when UI is involved
4. code and ADRs
5. durable memory

If chat changes intended behavior, the durable artifacts should be updated.

## Ready-for-implementation gate

Implementation-ready work should include:

- the user or operational problem
- the desired outcome
- explicit in-scope items
- explicit out-of-scope items
- required states when UI is involved
- validation expectations

If those are missing, shape the work first instead of implementing from assumptions.

Projects may add stricter gates by work type, but should not loosen this minimum bar.

## Required artifacts by work type

For product or UX-heavy work, expect:

- user problem
- desired outcome
- scope boundaries
- required states
- design or Storybook expectations
- terminology alignment

For engineering hardening or bug work, expect:

- expected vs actual behavior
- impact
- known reproduction or evidence
- validation expectations

## Standard delivery loop

1. Problem framing
2. Shaping
3. Implementation handoff
4. Implementation
5. Handback
6. Review
7. Product or owner decision

Decision outcomes should be explicit:

- accept
- refine
- defer
- rescope

## Queue and status pattern

By default, shaped work should move through three states:

1. implementation-ready queue
2. in progress
3. in review

Projects may rename these states, but the pattern should stay explicit:

- shaping produces implementation-ready work
- implementation actively claims and progresses work
- completed implementation is handed back into review rather than declared done unilaterally

## Implementation inputs and responsibilities

Implementation should receive:

- the active work item
- the relevant standards and project rules
- any required design or Storybook contract
- validation and deployment expectations

Implementation is responsible for:

- code changes
- tests
- local validation
- deploy/runtime verification when required by the work
- a clear structured handback

## Handback expectations

Implementation handback should include:

- files changed
- tests and validation run
- deploy/runtime status when relevant
- deviations from plan
- follow-up risks, bugs, or debt

## Review expectations

- work should be understandable without relying on chat history
- shaping and implementation may be handled by different providers
- acceptance review should check requirement fit, UX fit, technical fit, and validation evidence

Unless a project explicitly says otherwise, review and implementation are different lanes.

If a project has separate review and implementation providers, review requests should default to review-only work unless the project explicitly asks the reviewer to implement a fix.

## Escalation pattern

Pause and re-shape when:

- two plausible product directions exist
- the work conflicts with active standards or requirements
- implementation would widen scope beyond the approved problem
- runtime behavior reveals a materially different issue than expected

## Relevant principles and references

- durable sources of truth over chat memory
- explicit handoff and handback
- separate shaping, implementation, and review lanes when roles are distinct
- specification by example for ambiguous or stateful behavior
