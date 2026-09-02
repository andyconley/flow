# Business Analysis: Agent Web Access Policy

## Desired outcome

Ship one Flow-owned boolean capability policy in the next minor release. Every
current and future merged-manifest agent inherits `web_research = true`, both
runtime adapters consume the same resolved decision, and rationale-backed
local-only exceptions survive unrelated agent replacement.

## Acceptance boundary

- Resolve and validate policy before either target calls `sync_outputs`.
- Preserve existing name-based agent replacement while merging capability
  exceptions independently by `(agent, capability)`.
- Fail on malformed overlays, invalid policy, and any governed Claude agent
  without an explicit `tools:` list before any write or stale managed-file
  deletion; omission can inherit tools and cannot represent a denial.
- Prove generated configuration and guidance without claiming live access,
  runtime enforcement, or behavioral compliance.

## Scope boundary

The work includes the resolver, both adapters, shared guidance, configuration
tests, ADR and migration documentation, release verification, and archive. It
excludes live web calls, per-task technical grants, skills, authenticated or
private browsing, model routing, and generated-file edits.
