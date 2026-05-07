# Event-Driven Standard

This standard defines reusable expectations for event-driven systems.

## Event principles

- events should describe facts that happened
- event consumers should be resilient to duplication and delay
- event schemas should evolve deliberately

## Event naming

Use clear, domain-meaningful naming conventions. Past-tense fact events are the default for domain events.

## Envelope and schema

Projects should choose a consistent event envelope and schema strategy.

Useful defaults include:

- CloudEvents for event metadata
- AsyncAPI for channel and message documentation
- schema registries for compatibility enforcement

## Delivery expectations

- `DO` design consumers to be idempotent
- `DO` use dead-letter handling for failed messages
- `DO` define correlation identifiers for request/response or workflow tracing
- `AVOID` silently dropping unprocessable events

## Compatibility and evolution

Projects should define a compatibility mode and enforce it in CI where tooling supports it.
