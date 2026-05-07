# FinOps Standard

This standard defines how engineering teams treat cost as an operational and design concern.

## Core principle

Cost is a non-functional requirement, not a finance-only afterthought.

## Visibility

Teams should be able to answer:

- which team or service is spending money
- what environments cost
- what changed cost
- whether cost maps to value delivered

## Governance

Projects should adopt:

- consistent tagging or attribution
- cost review in design and infrastructure changes
- anomaly detection or budget awareness

Cost ownership should be attributable by service, team, environment, or customer where practical.

## Optimization order

Typical order of operations:

1. right-size resources
2. remove waste
3. use discounted or lower-cost compute appropriately
4. optimize architecture where justified

## Unit economics

When practical, map cost to a business or technical unit rather than only tracking total spend.

## Relevant standards and tools

Principles:

- FinOps lifecycle: inform, optimize, operate
- tagging and attribution discipline
- unit economics

Common tools:

- Infracost
- cost anomaly detection
- FOCUS for normalized cost data
