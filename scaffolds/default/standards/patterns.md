# Patterns Standard

This standard defines the shared pattern vocabulary teams should use in design discussions, ADRs, and code review.

## Why patterns matter

Patterns encode intent. Their value is the shared language they create, not mechanical implementation.

Use patterns to:

- describe recurring design choices
- make tradeoffs explicit
- help reviewers recognize misapplied solutions

## Rule severity tags

- `DO` means strong default; deviations should be deliberate
- `CONSIDER` means good default, but context matters
- `AVOID` means usually wrong and should be justified
- `DO NOT` means prohibited unless the project explicitly defines an exception

## Pattern layers

Use patterns at the right layer:

1. code-level patterns
2. application and domain patterns
3. integration patterns
4. infrastructure patterns

Do not solve an infrastructure problem with a code-only pattern, and do not drag infrastructure complexity into the code layer.

## Code-level defaults

Common patterns teams should recognize:

- Strategy for replacing long branching trees with named interchangeable behavior
- Adapter for isolating incompatible interfaces
- Decorator for logging, retry, caching, and similar cross-cutting concerns
- State for explicit lifecycle transitions
- Command for deferred execution, auditability, or undoable actions
- Observer or native reactive primitives for event-style coordination
- Factory Method for creation that varies by context

Defaults:

- `DO` adapt patterns to language idioms instead of cloning textbook class shapes
- `AVOID` Singleton for mutable or shared service logic
- `DO NOT` implement patterns mechanically without understanding the problem they solve

## Application and domain defaults

Common domain patterns:

- Aggregate
- Repository
- Domain Event
- Value Object
- Specification
- Domain Service

Defaults:

- `DO` keep aggregate boundaries small enough to protect real invariants
- `DO` model significant lifecycle changes as domain events
- `DO` prefer value objects over untyped primitives for meaningful domain concepts
- `AVOID` infrastructure logic inside aggregates or domain services

## Integration defaults

Common integration patterns:

- Outbox
- Saga
- Dead Letter Channel
- Idempotent Receiver
- Competing Consumers
- Correlation Identifier
- Splitter / Aggregator

Defaults:

- `DO` treat dead-letter handling as mandatory for message-driven systems
- `DO` design consumers to be idempotent
- `DO` use outbox when reliable event publishing matters
- `AVOID` distributed transactions when compensating flows are more practical

## Infrastructure defaults

Common infrastructure patterns:

- Circuit Breaker
- Bulkhead
- Retry with Backoff
- Timeout
- Health Endpoints
- Canary
- Strangler Fig
- Feature Flags

Defaults:

- `DO` set explicit timeouts for external dependencies
- `DO` combine retries with backoff and jitter
- `DO` use progressive rollout patterns for production changes
- `AVOID` big-bang rewrites when strangler-style migration is viable

## Team pattern charter

Projects should maintain a short list of patterns they expect engineers to recognize and apply by name. Significant pattern choices and deviations should be recorded in ADRs.

Good default charter:

- code layer: Strategy, Adapter, Decorator, State, Command
- domain layer: Aggregate, Repository, Domain Event, Value Object, Specification
- integration layer: Outbox, Saga, Dead Letter Channel, Idempotent Receiver
- infrastructure layer: Circuit Breaker, Bulkhead, Retry/Backoff, Canary, Strangler Fig
