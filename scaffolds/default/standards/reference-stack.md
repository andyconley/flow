# Reference Stack Standard

This standard captures the framework’s preferred standards and tool categories as a starting reference, not a mandatory one-size-fits-all stack.

## Core references by category

- architecture documentation: C4 plus ADRs
- observability instrumentation: OpenTelemetry-style thinking
- metrics and alerting: structured, standards-based approaches
- API contracts: OpenAPI / AsyncAPI where relevant
- testing: unit, integration, contract, and end-to-end at appropriate layers
- supply chain: SBOM, vulnerability scanning, signing, provenance where practical

## Tooling stance

Prefer:

- open standards over vendor lock-in
- diffable text artifacts over opaque binaries
- reusable tooling categories over project-specific one-offs

Projects should document actual chosen tools in project-specific definitions when the framework reference stack is narrowed to concrete implementations.

## Typical reference categories

- architecture: C4, arc42, ADRs
- design patterns: GoF, DDD, EIP, distributed-systems pattern libraries
- testing: Testcontainers, Pact, property-based and mutation testing
- observability: OpenTelemetry, Prometheus/OpenMetrics, Jaeger/Tempo, OpenSLO
- delivery: GitOps, progressive delivery, feature flags
- security: OWASP ASVS, OWASP SAMM, OPA/Kyverno, workload identity
- supply chain: SLSA, SBOM, cosign, in-toto
- documentation: Vale, Spectral, diagram-as-code
- APIs: OpenAPI, AsyncAPI, buf, contract and compatibility tooling
- events: CloudEvents, schema registry
- DX: Backstage, reproducible local development

Projects should explicitly record which of these are adopted, deferred, or intentionally excluded.
