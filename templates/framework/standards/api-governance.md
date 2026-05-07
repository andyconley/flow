# API Governance Standard

This standard defines how service and interface contracts are designed, validated, versioned, and retired.

## Contract-first principle

The contract should exist before or alongside the implementation, not be reconstructed after the fact.

Typical lifecycle:

1. design
2. lint and review
3. mock or validate against consumers
4. implement
5. verify
6. publish
7. version or deprecate

## Internal and external API tiers

Projects should distinguish between:

- external customer-facing APIs
- internal service-to-service APIs

External APIs usually need stricter compatibility and longer deprecation windows.

## Schema and contract validation

Useful validation layers include:

- schema validation against the formal spec
- consumer-driven contract testing
- breaking-change detection between versions
- spec-driven fuzzing for edge cases

These layers are complementary:

- schema validation catches structural drift
- consumer-driven contracts catch behavior consumers actually rely on
- breaking-change checks catch version-to-version incompatibilities

## API style guide

Projects should define and enforce conventions for:

- URL structure
- naming
- pagination
- error format
- response codes
- field formats

Consistency across services reduces integration friction.

Useful defaults:

- resource-oriented URLs
- explicit, consistent error envelopes
- ISO date/time formats
- string IDs
- cursor pagination for growing collections

## Versioning and deprecation

Choose and document a versioning strategy per API surface.

Deprecation should include:

- explicit notice
- migration path
- tracked sunset timing
- traffic awareness before removal

## Client generation and protocol governance

Where appropriate, use code generation and compatibility tooling for:

- REST/OpenAPI
- gRPC/Protobuf
- async APIs
