# Testing Standard

This standard defines how a project should earn trust through tests instead of chasing coverage for its own sake.

## Testing philosophy

- tests should map back to accepted behavior or domain rules
- use behavior-driven testing at external or user-facing boundaries
- use logic-first tests for deterministic domain functions
- treat tests as design feedback, not only regression nets

Coverage is a floor, not the goal. The useful question is whether the suite would catch a real bug.

## Test levels

Unit tests:

- pure domain logic
- deterministic utility logic
- no real network or runtime dependencies

Integration tests:

- adapters
- resolver or handler pipelines
- storage round-trips
- external-boundary behavior with stubbed dependencies

End-to-end tests:

- critical user flows only
- full runtime path verification
- reserved for things lower test levels cannot verify honestly

Contract tests:

- schema or fixture validation for external APIs
- early warning for upstream API drift

Property-based tests:

- useful for parsing, state machines, invariants, and mathematical properties
- generate edge cases the author would not think to write manually

Mutation tests:

- useful for checking whether the suite actually detects faults
- best run nightly or on changed files, not on every save
- the failure mode they exist to catch is the vacuous assertion, and the check
  runs without tooling — see `standards/evidence.md`

## TDD guidance

- new behavior should add or update tests
- tests should match the real boundary being changed
- full-suite validation can be deferred until the appropriate phase, but targeted validation should happen during implementation

TDD is strongest for:

- pure domain logic
- algorithms
- parsing and validation
- deterministic transformations

It is optional for:

- plumbing
- wiring
- layout-only changes

## BDD and specification by example

For behavior that depends on shared language between product, QA, and implementation:

- use specification by example to turn ambiguous requirements into concrete examples
- use BDD-style scenarios for acceptance-level behavior when it improves shared understanding
- do not replace unit and integration tests with verbose scenario tests

## Flaky test policy

- quarantine flaky tests immediately
- track them explicitly
- fix or delete them quickly
- do not normalize rerunning CI until it passes

## Typical cadence

- on save or local loop: unit tests
- on pull request: unit plus integration plus contract checks as appropriate
- on nightly or scheduled runs: broader end-to-end and slower quality checks such as mutation testing

## Relevant standards and tools

Principles:

- test pyramid
- specification by example
- TDD / BDD
- consumer-driven contracts

Common tools:

- Testcontainers
- Pact
- Hypothesis / fast-check / proptest
- Stryker / mutmut / PIT
