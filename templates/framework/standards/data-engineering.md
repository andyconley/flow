# Data Engineering Standard

This standard defines how datasets, transformations, and data quality are treated as first-class engineering assets.

## Data contracts

Datasets should have explicit contracts covering:

- schema
- ownership
- freshness or quality expectations
- semantics
- change history

Contracts should make the meaning of data explicit, not just its shape.

## Transformation discipline

Transformations should be:

- version controlled
- testable
- documented
- reviewable like application code

## Data quality

Projects should validate critical data using checks such as:

- nullability
- uniqueness
- accepted values
- relationships
- freshness or completeness

Quality expectations should run both during development and in production-relevant pipelines where appropriate.

## Lineage and schema evolution

Where pipelines matter, lineage and schema evolution should be observable and governed rather than guessed.

## Relevant standards and tools

Principles:

- data contracts
- lineage
- governed schema evolution

Common tools:

- dbt
- Great Expectations / Soda
- OpenLineage / Marquez
- schema registries for event-driven data
