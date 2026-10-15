# Implementation Handoff

Use this template to move shaped work into implementation without relying on chat memory.

## Header

- Work item:
- Summary:
- Work type:
- Owner:

## Problem statement

Describe the user or operational problem in plain language.

## Desired outcome

Describe what should be true when the work is complete.

## Why now

Optional prioritization or urgency context.

## In scope

- item
- item

## Out of scope

- item
- item

## User journey and required states

- journey:
- required states:
  - loading
  - empty
  - error
  - success

## Design or Storybook expectations

- existing artifacts to update:
- new artifacts to add:
- shared patterns to use:

## Technical constraints

- likely files or modules:
- architectural rules:
- adapters or runtime boundaries:
- known risks:

## Acceptance criteria

- criterion
- criterion

## Validation requirements

- targeted tests:
- repo-wide tests:
- deploy required:
- E2E required:
- logs review required:
- mutation check (ran / not run / why):
- validated in (environment, and known deltas from the original):
- orchestration manifest and stage results (when delegated, shared-state, or revision-2 gated work):
- verifier identity and independence (required for high-risk work):

## Required handback

For verification-v1 workflows, link `verification-plan.json` and `verification.json`.
The specialist supplies actual producer session and assignment identities and
ordinary test results in its handback. After execution returns, the host alone
runs `flow workflow check` to record the tested workspace, registered evaluator
inputs, commands, results, environment and log hashes. Specialists must not create
or edit `verification.json` or captured logs; report host verification as pending
until the host records it. Independent review must explain equivalent test repairs.
Material or uncertain changes to approved success conditions require separate
user approval in a linked successor workflow. The host uses `workflow repair` for narrowed
repairs; the two-attempt allowance persists across sessions.

- files changed
- test and validation results
- deploy/runtime status
- deviations from plan
- follow-up bugs, risks, or tech debt
- claims reconciled and external-mutation records completed
