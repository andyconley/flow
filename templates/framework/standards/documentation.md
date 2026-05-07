# Documentation Standard

This standard defines how documentation is treated as code.

## Core principle

Documentation is part of the definition of done. A feature without updated docs is incomplete.

## Durable documentation types

Projects should distinguish between:

- process docs
- architecture docs
- ADRs
- API contracts
- runbooks
- product or user guidance

## Format defaults

Default to text-first, version-controlled formats such as:

- Markdown
- OpenAPI / AsyncAPI
- diagram-as-code formats

Primary-source documents should not live only in slides, PDFs, or chat.

## Diagramming as code

If a diagram matters to architecture or operations, it should be reviewable and diffable.

Suitable defaults include:

- Mermaid
- D2
- Structurizr DSL

## Workflow integration

Documentation should be updated in the same change that changes the behavior when possible.

Typical expectations:

- README updates when setup or usage changes
- ADRs for important decisions
- runbook updates when operational behavior changes
- API contract updates when interfaces change

## Documentation CI

Projects should consider automation such as:

- prose linting
- markdown linting
- link checking
- API spec linting
- doc-site build validation

## Repository layout guidance

Common durable layout:

- `README.md` for purpose and quickstart
- `docs/decisions/` or equivalent for ADRs
- `docs/architecture/` for diagrams and narrative architecture
- `docs/runbooks/` for operational playbooks
- `docs/api/` for contract artifacts

Projects may rename locations, but the taxonomy should remain clear.
