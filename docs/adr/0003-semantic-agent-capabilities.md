# ADR 0003: Resolve Semantic Agent Capabilities Before Runtime Adaptation

- Status: accepted
- Date: 2026-09-02

## Context

Flow previously expressed web access only as Claude-native `WebSearch` and
`WebFetch` entries in one agent source. That did not establish a global default,
did not map to Codex, and could not preserve a local-only exception when a user
overlay replaced the corresponding `[[agents]]` entry.

Flow needs every current and future agent to inherit web research by default,
with deliberate per-agent opt-out and re-enable decisions. Availability remains
separate from authorization: an agent may browse only when its task or
orchestrator brief explicitly requires a named external/current research
question.

## Decision

Define named boolean agent capabilities in the framework manifest. The first
capability is `web_research`, enabled globally with authorization mode
`explicit-task-or-brief`.

Store exceptions in `[[agent_capability_overrides]]`, keyed by
`(agent, capability)`, rather than on replaceable agent entries. Framework and
user-overlay exception records merge independently from agent source/model
replacement. Omission preserves a lower-layer exception; a higher layer may
re-enable a lower denial only explicitly. Every override requires a nonblank
rationale.

Validate and resolve the effective policy after the final agent inventory is
merged and before generated files are written. Invalid types, unknown names,
duplicate keys, missing rationales, redundant enables, catalog redefinition by
an overlay, or malformed overlay TOML stop sync without changing managed
outputs.

Flow owns semantic intent. Runtime adapters own native syntax:

- Claude enabled: exactly one `WebSearch` and one `WebFetch`; disabled: neither,
  while unrelated tools are preserved.
- Codex enabled: `web_search = "live"` and `tools.web_search = true`; disabled:
  `web_search = "disabled"` and `tools.web_search = false`.

Both adapters add the same source-owned behavioral boundary. Retrieved content
is untrusted data; sensitive local information is not disclosed without explicit
authorization; primary sources and citations are preferred; conflicts with
local policy or project truth are surfaced. Disabled agents report or reroute a
web-required assignment and may not bypass the denial through another tool.

## Consequences

- One default covers the complete merged inventory, including future and
  user-added agents.
- A model- or source-only overlay replacement cannot silently erase a denial.
- Provider syntax remains outside the policy domain and can change in one
  adapter without changing semantic source.
- The reusable mechanism is intentionally limited to known boolean capabilities;
  conditions, wildcards, credentials, and provider payloads require a new
  decision.
- Older manifests without a capability catalog keep legacy rendering behavior.
- Existing malformed user overlays that previously fell back to framework-only
  generation must be repaired before sync. This is deliberate: silent fallback
  could broaden capability while appearing successful.
- Every Claude agent under an active catalog must declare `tools:` explicitly,
  including disabled agents. Omission can inherit runtime tools and therefore
  cannot serve as a denial; an explicit empty list is valid.
- Configuration tests prove resolution and generated artifacts only. They do
  not prove live provider access, account policy, task-level enforcement,
  disclosure prevention, or agent behavior.

## Rollback

Revert the catalog, resolver, adapter mappings, and generated-guidance change as
one release, then run both user sync commands. Release-install users can install
the prior tagged Flow version using the documented release rollback path and
resync. Generated agent files are projections and require no data migration.

## Rejected Alternatives

- Capability fields on `[[agents]]` were rejected because existing overlay
  replacement could erase a denial by omission.
- Separate Claude and Codex defaults were rejected because they duplicate policy
  and allow cross-runtime drift.
- A generic permission language was rejected because one boolean capability
  does not justify conditions, wildcards, or runtime payloads in the domain.
