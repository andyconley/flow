# Deployment and Delivery Standard

This standard defines how code moves safely from commit to release.

## Delivery principles

- deploy and release are separate concerns
- the artifact is the unit of deployment
- every meaningful gate should be automated
- if a failed gate is ignored routinely, the gate is broken

## GitOps and desired state

When infrastructure or deployment configuration is managed declaratively:

- the desired state should live in version control
- changes should be reviewed in pull requests
- manual production drift should be treated as a defect

## Progressive delivery

Prefer delivery mechanisms that reduce blast radius:

- feature flags
- canary rollout
- blue/green rollout
- staged environment promotion

Default:

- `DO` progressively release risky changes
- `DO` couple rollout decisions to observable signals where possible
- `AVOID` all-at-once production cutovers without a rollback path

## Immutable artifact principle

Build once, promote the same artifact through environments.

Defaults:

- artifact versions should be explicit and traceable
- rollbacks should use a previous known-good artifact
- `DO NOT` patch live production instances manually

## CI/CD gates

Typical delivery gates include:

- static analysis
- secret scanning
- dependency vulnerability checks
- unit and integration tests
- contract checks where applicable
- artifact build and publish
- environment validation
- smoke or end-to-end verification

Projects should tighten these based on risk and deployment model.

Typical cadence:

- every commit: fast local or CI checks
- every pull request: unit, integration, and contract-level checks as needed
- pre-release or production promotion: environment verification and smoke/end-to-end confidence checks

## Progressive rollout discipline

Prefer rollout strategies that allow observation before full exposure.

Useful patterns:

- canary
- blue/green
- feature-flag rollout
- staged environment promotion

If a change cannot be rolled back quickly, that constraint should be explicit before release.

## Release evidence

Before production release, the team should know:

- what changed
- what was validated
- what rollout path is being used
- what rollback path exists
- who owns monitoring during the release window

## Relevant standards and tools

Principles:

- GitOps
- progressive delivery
- immutable infrastructure

Common tools:

- ArgoCD / Flux
- Argo Rollouts
- OpenFeature-style flag systems
