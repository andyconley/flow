# Plan: Global Flow Agent Web Access Policy

- Work item: `agent-web-access-policy`
- Status: Approved
- Decision owner: Andy Conley
- Target release: v0.23.0 through semantic-release
- Date: 2026-09-02

## Problem statement

Flow assigns current external research to many role agents, but capability is
currently encoded only in one Claude source file and has no shared Codex
mapping. This can block an assigned researcher, drift across runtimes, or lose
an intended local-only exception during overlay replacement.

## Desired outcome

One reusable semantic policy enables `web_research` for every current and future
registered agent. A separately keyed, rationale-backed exception ledger can
deny or deliberately re-enable the capability without coupling that choice to
agent-body replacement. Claude and Codex receive native configuration plus one
shared instruction boundary. The complete change ships and is publicly
verified as the next minor Flow release.

## Scope

### In scope

- Boolean capability catalog with `web_research` as the only recognized key.
- Framework default plus independently merged framework/user exceptions.
- Strict, pre-write validation and deterministic actionable errors.
- Fatal handling of malformed user-overlay TOML.
- Claude and Codex native mappings and shared enabled/disabled guidance.
- Removal of the manual web-tool declaration from `solution-architect.md`.
- Unit, renderer, fake-home inventory, overlay, idempotence, and atomicity tests.
- ADR, runtime adapter documentation, overlay semantics, and migration examples.
- Source commit/push, automated v0.23.0 publication and public verification,
  review, and Flow archive.

### Out of scope

- Live or delegated web calls, provider/account entitlement checks, or telemetry.
- Per-task technical grants or enforcement of the instruction-level use rule.
- Agent skill requirements.
- Authenticated browsing, arbitrary HTTP, credentials, or private-network access.
- Changes to non-web tools, role responsibilities, model routing, or sandboxes.
- Hand-editing generated files or introducing UI/API/persistent-data work.

## Required policy states

1. Legacy: no catalog; preserve current rendering exactly.
2. Enabled by default: emit enabled native mapping and enabled guidance.
3. Explicitly denied: emit local-only native mapping and disabled guidance.
4. Explicitly re-enabled: a higher layer reverses a lower denial with rationale.
5. Invalid: reject before any output write or stale managed-file deletion.

## Contracts

### Source contract

```toml
[agent_capabilities.web_research]
default = true
authorization = "explicit-task-or-brief"

[[agent_capability_overrides]]
agent = "example-local-only-role"
capability = "web_research"
enabled = false
rationale = "This role must remain local-only."
```

- The overlay may add exception records but may not redefine the catalog.
- Override identity is `(agent, capability)` with at most one record per layer.
- Every override needs a nonblank rationale.
- `enabled = true` is valid only over an effective lower-layer denial.
- Reject unknown capabilities, authorizations, agents, fields on `[[agents]]`,
  non-booleans, duplicate keys, redundant enables, and ambiguity.

### Resolver contract

`resolve_agent_capabilities(framework_manifest, overlay_manifest,
final_agent_names)` returns an effective decision per agent/capability including
enabled state, provenance, and rationale, or raises one stable policy error that
identifies layer/path, agent, capability, violated rule, and remediation.

### Runtime contract

- Claude enabled: normalize to exactly one `WebSearch` and one `WebFetch` while
  preserving unrelated tools. Disabled: remove both.
- Codex enabled: emit `web_search = "live"` and `tools.web_search = true`.
  Disabled: emit `web_search = "disabled"` and
  `tools.web_search = false`. Treat the pair as one invariant bundle.
- Enabled and disabled guidance use stable bounded markers and occur once.
- Every custom/replacing Claude agent under an active capability catalog must
  declare `tools`; a missing key fails immediately, while an explicit empty
  list is valid. This is required for disabled agents too because omission can
  inherit runtime tools and defeat an opt-out.

### Behavioral guidance contract

Availability is not authorization. Browsing requires a user task or
orchestrator brief that names an external/current research question and
explicitly requires web research. Retrieved material is untrusted data. Agents
must not disclose secrets, private source, personal data, or internal
identifiers without authorization; they prefer primary sources, cite material
claims, and surface conflicts with local policy or project truth. Disabled
agents report or reroute the conflict and may not bypass it through shell HTTP.

## Implementation sequence and ownership

1. Lead developer: add `cli/agent_capabilities.py` and
   `tests/test_agent_capabilities.py`; prove resolver and validation semantics.
2. Lead developer: update `cli/sync.py` to preserve both policy layers, make
   malformed overlays fatal, resolve after agent merge, and fail before writes.
3. Lead developer: update `cli/render.py`, `scaffolds/default/flow.toml`, and
   `scaffolds/default/agents/solution-architect.md` for native mappings,
   centralized guidance, and source-authority cleanup.
4. Test engineer: extend `tests/test_flow.py` for full inventory, both runtimes,
   overlay persistence/re-enable, missing tools, idempotence, and sentinels.
5. Architect/tech writer: add
   `docs/adr/0003-semantic-agent-capabilities.md`; update
   `docs/runtime-adapters.md` and `docs/architecture.md`, with a README or CLI
   reference pointer only if needed for discoverability.
6. Security reviewer: verify task authorization, untrusted-content handling,
   disclosure restrictions, denial persistence, and fail-closed behavior.
7. Quality reviewer: independently verify acceptance evidence and truthful
   configuration-only claims before acceptance.
8. Flow maintainer: commit as a `feat`, push the accepted source commit, let the
   release workflow select v0.23.0, and verify candidate, publication, public
   install/upgrade, tag, notes, and generated release commit.
9. Orchestrator/tech writer: capture release evidence, archive the Flow run, and
   publish any separately required closeout commit.

## Release and recovery

- Do not manually edit `CHANGELOG.md`, create the version tag, or publish the
  GitHub release; the existing serialized workflow owns those writes.
- If candidate validation fails, fix forward with a normal commit.
- If publication is partial or uncertain, preserve remote objects, reconcile
  using retained evidence, and repair forward according to the release runbook.
- Consumer rollback is the prior Flow release followed by both runtime syncs.

## Validation

The authoritative matrix is `validation-plan.md`. Completion requires focused
and full tests, structural adapter proof, pre-write atomicity proof, review,
hosted candidate validation, publication, public readback, fresh install,
upgrade, and archive. Final language is: **web capability configuration
passed**. Live access, runtime enforcement, disclosure prevention, and agent
behavior remain unverified.

## Recommended lane

`flow-implement`, because the change spans a new domain module, overlay merge
semantics, two adapters, security-sensitive defaults, broad tests,
documentation, review, and a full release lifecycle.
