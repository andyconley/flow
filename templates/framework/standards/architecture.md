# Architecture Standard

This standard defines the architectural defaults a project starts from.

## Core principles

- design for change, not perfection
- prefer reversible decisions where possible
- align boundaries to real domain concepts rather than convenience
- make core logic testable without dragging runtime or UI dependencies into it
- treat long-lived architectural choices as explicit decisions, not accidental drift

## Layering

Default boundary:

1. UI / transport
2. application / domain
3. persistence / external integration

Rules:

- UI and transport concerns stay separate from domain logic
- domain logic is testable without full runtime dependencies
- integrations are translated at the boundary rather than leaked through the app
- non-trivial long-lived decisions are captured in ADRs

If a project uses handlers, resolvers, or controllers, those layers coordinate work but should not become the domain model.

## Domain rules

Core business rules should live in deterministic, testable modules whenever possible.

Changes to:

- calculations
- scheduling or dependency logic
- entity invariants
- forecasting or transformation rules

should be implemented so they can be tested independently of the outer runtime.

When logic is extracted from prototypes, legacy tools, or prior systems, separate the pure logic from the original I/O shell instead of porting the whole shape blindly.

## Frontend architecture rules

If a project has a user-facing UI:

- required states should be explicit
- reusable UI patterns should be treated as part of the architecture, not just styling
- design-contract artifacts such as Storybook can serve as architectural contracts for stateful UI

If a project is mid-migration between stacks, treat the legacy stack as transitional and avoid investing in broad redesign work there unless the project explicitly chooses to.

## Domain and integration boundaries

Use anti-corruption at external boundaries.

Do not let:

- third-party API payloads
- database schema quirks
- legacy models
- transport details

become the domain model by accident.

Boundary adapters should normalize external data into project-owned shapes before it reaches the inner layers.

## ADR convention

Create an ADR when a decision affects:

- runtime stack direction
- long-lived UI architecture
- domain boundaries
- data ownership
- integration strategy

ADRs should describe context, decision, alternatives considered, and consequences.

Run-level decisions can live in memory first, but any decision with multi-ticket or long-lived consequences should graduate to an ADR.

## Relevant standards and references

Principles:

- domain-driven design
- hexagonal or ports-and-adapters architecture
- ADRs as durable decision records

Common reference artifacts:

- C4
- arc42
- DDD references such as Evans and Vernon
