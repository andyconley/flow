# Architecture Review: Agent Capability Defaults

- Work item: `agent-web-access-policy`
- Reviewer: architect
- Date: 2026-09-02
- Verdict: Recommend a small semantic capability catalog plus a separately
  merged exception ledger. Do not put capability state on replaceable agent
  records or runtime-specific defaults.

## Architecture Summary

### Context

Flow needs all current and future agents to inherit web research by default in
Claude and Codex, while preserving explicit local-only exceptions across user
overlay replacement. The policy must remain Flow-owned even though each runtime
uses different configuration syntax. The user also chose to make this the first
reusable capability default rather than a one-off web flag.

The durable decision is not merely that web is enabled. It is where semantic
agent capability policy lives, how exceptions compose with overlays, and where
runtime-specific translation occurs.

### Proposed Shape

Use a deliberately narrow capability model:

```toml
[agent_capabilities.web_research]
default = true
guidance_source = "agents/web-research-policy.md"

[[agent_capability_overrides]]
agent = "example-local-only-role"
capability = "web_research"
enabled = false
rationale = "This role handles material that must remain local."
```

The canonical release need not contain a built-in opt-out merely to exercise
the mechanism. The second block illustrates the supported source shape.

Keep this abstraction intentionally small:

- capabilities are named boolean grants with a framework-owned default;
- per-agent overrides are keyed by `(agent, capability)` and require a
  non-blank rationale;
- the catalog recognizes only capabilities with an implemented adapter mapping;
- no conditions, groups, wildcards, policy expressions, or arbitrary
  provider-specific payloads belong in this slice.

This gives future boolean capabilities a stable home without building a general
authorization engine before a second use case exists.

### Boundaries and Data Flow

```text
framework manifest ------+                         +--> Claude adapter
  capability catalog     |                         |    normalize tools list
  framework overrides    +--> overlay merge --> capability resolver
                         |                         |    + shared guidance
user overlay ------------+                         |
  agent replacements                               +--> Codex adapter
  keyed overrides                                        web_search = live|disabled
```

1. Load the framework manifest and tag provenance as today.
2. Replace or append `[[agents]]` through the existing name-based overlay rule.
3. Merge `[[agent_capability_overrides]]` separately by the composite key
   `(agent, capability)`. A user override for the same key replaces the
   framework override; an unrelated agent replacement does not touch it.
4. Validate the merged inventory, catalog, and exception ledger before either
   adapter renders anything.
5. Resolve one effective capability map for every final inventory agent:
   user override -> framework override -> framework default.
6. Pass the resolved semantic value and common guidance to each adapter. The
   resolver never emits `WebSearch`, `WebFetch`, or Codex TOML.
7. Render native configuration:
   - Claude preserves unrelated tools, removes duplicate web entries, and adds
     `WebSearch` and `WebFetch` exactly once when enabled; when disabled it
     removes both.
   - Codex emits the single authoritative top-level mode
     `web_search = "live"` when enabled and `web_search = "disabled"` when
     denied. Do not also emit a second boolean whose disagreement would create
     two authorities.
8. Append the same source-owned behavioral guidance to both generated role
   instruction bodies, with the effective status made explicit. The guidance
   governs task authorization and untrusted content; it is not part of the
   provider syntax.

The resolver should be a pure, testable module (for example,
`cli/capabilities.py`) rather than additional branching inside both renderers.
The current model-tier resolver remains separate: model selection and tool
capability are different policy domains even though both are consumed during
agent generation.

### Validation Rules

Fail before output generation when any of these conditions exists:

- an unknown capability appears in the catalog or an override;
- an override names an agent absent from the merged inventory;
- `default` or `enabled` is not a boolean;
- duplicate overrides exist for one `(agent, capability)` key at one source
  layer;
- any explicit override has a missing, empty, or whitespace-only rationale;
- capability fields appear directly on a replaceable `[[agents]]` record,
  creating a second policy authority;
- a user overlay tries to redefine the framework capability catalog or global
  default rather than expressing a per-agent exception.

Requiring a rationale for every explicit override is simpler and more auditable
than conditioning validation on direction. It covers both opt-out and deliberate
re-enablement of an inherited framework deny. A redundant explicit enable may
be accepted if it has a rationale, but the implementation should warn or reject
it if that helps keep the ledger clean; it must not change precedence.

For compatibility, a manifest with no capability catalog can retain today's
rendering behavior. Once the catalog exists, its supported capabilities become
authoritative: source frontmatter is input to normalization, not a competing
grant. This permits the existing `solution-architect` web entries to be removed
cleanly while avoiding a flag-day change for unrelated older/custom manifests.

### Change Surface

- New files/modules:
  - one pure capability validation/resolution module
  - one shared web-research guidance source
  - ADR covering semantic capabilities and adapter translation
- Modified files/modules:
  - `scaffolds/default/flow.toml` for catalog/default
  - `cli/sync.py` for overlay-ledger merge and resolver invocation
  - `cli/render.py` for native Claude/Codex mappings and guidance injection
  - `scaffolds/default/agents/solution-architect.md` to remove duplicate web
    authority
  - sync/configuration tests and maintainer documentation
- Data model / migration impact:
  - additive source-manifest schema only; no persistent user data migration
  - generated agent files are replaced by the next sync
  - existing overlays that only replace agents continue to work and inherit
    framework defaults/exceptions

## Options Critique

### Option A: Capability fields inside each `[[agents]]` record

- Benefit: Fewest new manifest concepts.
- Problem: The current user overlay replaces a same-name agent wholesale. A
  model-only replacement can therefore erase a framework deny. Special-casing
  selected fields to survive replacement would silently change the established
  replacement contract and make each agent record partly replaceable and partly
  inherited.
- Judgment: Reject. The apparent simplicity moves complexity into ambiguous
  merge behavior and weakens the fail-closed requirement.

### Option B: Capability catalog plus keyed override ledger

- Benefit: One default covers future inventory entries; exceptions have stable
  identity and provenance; agent replacement and security-policy replacement
  are independent operations; both adapters consume one resolved value.
- Cost: Adds a small schema and one composite-key merge path.
- Judgment: Recommend. It is the smallest design that preserves a deny through
  unrelated overlay changes without redefining existing agent replacement.

### Option C: Generic provider policy engine

- Shape: Allow arbitrary capability types, conditions, per-runtime payloads,
  inheritance expressions, or manifest-defined adapter mappings.
- Benefit: Maximum theoretical extensibility.
- Problem: Leaks integration syntax into the domain, makes validation open-ended,
  and creates an authorization framework with no demonstrated second complex
  use case.
- Judgment: Reject for now. Add another named boolean capability through the
  same resolver first; generalize value types or conditional grants only when
  real requirements force it.

### Option D: Separate Claude and Codex defaults

- Benefit: Mirrors provider configuration directly.
- Problem: Duplicates one policy, permits drift, and requires every exception to
  be expressed twice.
- Judgment: Reject. It violates the desired single semantic policy and
  `architecture.md / Domain and integration boundaries`.

## Architecture Dimensions

### Domain Boundaries

`web_research` is Flow's semantic capability. Provider keys are integration
details. The resolver owns defaulting, precedence, validation, and rationale;
renderers own only native serialization. This follows `architecture.md / Core
principles`, `Layering`, and `Domain and integration boundaries`.

### Interfaces and Data Flow

The only new inner interface is a deterministic map such as
`agent_name -> capability_name -> effective boolean + provenance + rationale`.
Both output builders receive that map. Keeping provenance in the result makes
diagnostics and review output possible without reparsing the source.

### State and Persistence

The manifest and optional user overlay remain the sources of truth. Generated
Claude Markdown and Codex TOML remain replaceable projections, never policy
state. There is no runtime database or migration. Sync remains atomic: invalid
policy prevents both adapter outputs from being written.

### Operational Shape

Resolution is local, deterministic, and proportional to the small agent and
capability inventories. It introduces no network dependency or runtime service.
Diagnostics should report effective capability and provenance, but configuration
tests—not live browsing—remain the accepted proof boundary.

### Decision Durability

The semantic-policy/adapter boundary and overlay exception precedence will
govern future capability additions, so this is a durable integration decision.
It should be recorded even though the implementation is reversible.

## Risks and Tradeoffs

- Global standing web capability broadens privilege. Owner: Andy Conley. Mitigation:
  retain the accepted instruction-level authorization rule, shared untrusted-input
  and disclosure guidance, and explicit local-only exceptions.
- An unrelated overlay could erase a deny if implementation attaches the deny
  to `[[agents]]`. Owner: implementation lead. Mitigation: separate keyed ledger,
  provenance-aware merge, and a replacement-without-capability regression test.
- Claude source frontmatter and the manifest could remain dual authorities.
  Owner: implementation lead. Mitigation: once the catalog is present, normalize
  web tools solely from resolved policy and remove the built-in manual entries.
- A future Codex version could change accepted web-search syntax. Owner: Flow
  maintainer. Mitigation: emit one documented mode, structurally test it, state
  the supported client contract, and update only the Codex adapter when it
  changes.
- Generic schema can grow into an authorization language. Owner: Flow architect.
  Mitigation: boolean values, explicit known-capability registry, no conditions
  or provider payloads, and a new ADR decision before expanding that boundary.
- Configuration success may be misreported as behavioral enforcement. Owner:
  test/release lead. Mitigation: evidence says configuration passed and lists
  live availability and task compliance as unverified.

## Applicable Standards

- `architecture.md / Core principles` — isolate deterministic policy from
  runtime rendering and make the long-lived choice explicit.
- `architecture.md / Domain and integration boundaries` — translate Flow-owned
  semantics at Claude and Codex boundaries.
- `patterns.md / Code-level defaults` — use an idiomatic Adapter boundary; do
  not construct a textbook framework around one capability.
- `security.md / Secure defaults` and `Secure review checklist` — make the scope
  expansion and every exception review-visible and fail closed on ambiguity.
- `testing.md / Testing philosophy` and `Test levels` — test the pure resolver
  and source-to-generated adapter integration without claiming live behavior.
- `solutioning-decisions.md / Impact, scope, and cost` — avoid runtime services,
  new policy expression languages, or unrelated diagnostics work.
- `solutioning-risks.md / The four-step pattern (ICOM)` — assign owners and
  concrete mitigations to the permission, overlay, compatibility, and proof
  risks.

## ADR Recommendation

- Needed: yes
- Title: Semantic Agent Capabilities and Runtime Adapter Mappings
- Decision to capture: Flow owns named boolean agent capabilities and their
  defaults; separately keyed overrides survive agent replacement and require a
  rationale; a pure resolver produces effective policy after overlay merge;
  Claude and Codex adapters translate that policy into native syntax; generated
  files are projections, not policy sources.
- Alternatives to record: per-agent embedded fields, separate runtime defaults,
  and a generic provider policy engine.

## Review Conclusion

The keyed-ledger design satisfies the global-default, overlay-safe deny, and
cross-runtime parity requirements without changing the established semantics of
agent replacement. It creates one reusable seam—the boolean capability
resolver—and stops there. Planning should treat the resolver/merge contract as
the first chunk, the two adapter mappings and shared guidance as the second, and
inventory-wide configuration tests plus ADR/docs as the third.
