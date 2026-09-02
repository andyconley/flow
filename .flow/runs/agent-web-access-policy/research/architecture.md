# Research: Cross-runtime agent web capability policy

- Owner role: solution-architect
- Date: 2026-09-02
- Confidence: High for the current Flow generation path and user-overlay behavior; Medium for host-level enforcement because configuration tests cannot prove a runtime exposes or honors a tool.

## Question

How should Flow represent a global web-research default with a per-agent opt-out, generate equivalent Claude and Codex agent configurations, and prove the configuration without a live delegated web test?

## Method and sources

- Inspected `scaffolds/default/flow.toml` and all source agents under `scaffolds/default/agents/`.
- Traced `merge_user_overlay`, `runtime_policy_for_agent`, `desired_claude_outputs`, and `desired_codex_outputs` in `cli/sync.py`.
- Traced `parse_frontmatter`, `render_claude_agent`, and `render_codex_agent` in `cli/render.py`.
- Inspected generated-surface checks in `cli/runtime_smoke.py`, agent-policy diagnostics in `cli/diagnostics.py`, and sync/overlay tests in `tests/test_flow.py`.
- Checked Flow's `Architecture Standard` (`Core principles`, `Domain and integration boundaries`, `ADR convention`), `Testing Standard` (`Testing philosophy`, `Test levels`), `Security Standard` (`Secure defaults`, `Secure review checklist`), and `Research Evidence Standard` (`Research questions`, `Source quality`).
- Checked official Codex documentation for custom-agent configuration and web search. Custom agent TOML files are configuration layers and may use supported session keys; the configuration reference defines `tools.web_search` and the `web_search` mode: https://learn.chatgpt.com/docs/agent-configuration/subagents and https://learn.chatgpt.com/docs/config-file/config-reference#configtoml

## Current architecture

1. `scaffolds/default/flow.toml` is already the shared inventory for the thirteen built-in agents. Each `[[agents]]` entry selects a source body and model tier.
2. Claude generation preserves the source Markdown frontmatter, then overlays manifest-derived runtime policy. Consequently, `tools:` in `solution-architect.md` reaches `.claude/agents/solution-architect.md`.
3. Codex generation parses the same frontmatter only to obtain `description`; it intentionally renders a native TOML configuration containing the body, model, and reasoning effort. It drops `tools:`. Adding `WebSearch` and `WebFetch` to every Markdown file would therefore change Claude only and would create false cross-runtime parity.
4. The shared manifest has semantic model tiers but no shared capability policy. `[claude.agent_defaults]` currently controls only generation mode and is not applied as a general frontmatter-default layer.
5. User-level agent overrides are supported today. `merge_user_overlay` replaces a same-name framework `[[agents]]` entry or appends a new one, and tests cover both cases. The absence of `~/.flow/user/agents/` on a particular machine means no overrides have been authored; it does not mean the capability is unsupported. This does not need to become part of the first delivery slice, but documentation should not claim that user-level agent overrides are unavailable.

## Applicable rules

- `architecture.md / Core principles` — one semantic policy should drive both adapters so a durable capability decision does not emerge accidentally from runtime-specific files.
- `architecture.md / Domain and integration boundaries` — Flow should own the concept `web research`; adapter code should translate it into Claude and Codex native configuration rather than treating Claude tool names as the domain model.
- `testing.md / Testing philosophy` — tests should exercise the accepted effective policy: default grant, explicit opt-out, and adapter parity.
- `testing.md / Test levels` — this boundary is best covered by deterministic unit tests for policy resolution plus an adapter integration test over generated files; a real network call is outside the agreed scope.
- `security.md / Secure defaults` — a capability expansion must be review-visible, and an opt-out must result in an explicit denial where omission would inherit broader parent settings.
- `security.md / Secure review checklist` — review should treat this as a permission/scope expansion even though use remains task-authorized.
- `research-evidence.md / Research questions` and `Source quality` — capability availability and permission to use it are separate. The role should browse only for a named, explicitly assigned external/current research question and should continue to prefer primary, durable sources.

## Options

### Option A: Repeat native tool declarations in every agent source

- Shape: add Claude `WebSearch` and `WebFetch` to all source frontmatter; teach the Codex renderer to infer an equivalent from those names. An opt-out is represented by omitting the tools from one file.
- Advantages: small visible edits; preserves the current `solution-architect` precedent.
- Disadvantages: there is no actual global default, so every new agent can drift; Claude-native names become the cross-runtime domain model; omission is ambiguous and cannot enforce a Codex opt-out when the parent has web enabled.
- Reversibility: High.
- Assessment: Does not satisfy the approved single-default or reliable opt-out requirements.

### Option B: Add a shared semantic capability default and render it per runtime

- Shape: add a shared manifest policy such as `[agent_defaults.capabilities] web_research = true`. Allow `web_research = false` plus a required rationale on an individual `[[agents]]` entry. Resolve the effective value after framework/user-overlay merge, then have each adapter translate that value into native output.
- Claude mapping: preserve all non-web tools, add `WebSearch` and `WebFetch` exactly once when enabled, and remove both when opted out.
- Codex mapping: emit a supported custom-agent config override. Enabled agents should explicitly enable the web-search tool and select the intended mode; opted-out agents must explicitly disable it rather than omit it, because omitted custom-agent settings inherit from the parent session.
- Advantages: one auditable policy, automatic coverage for new inventory entries, deterministic opt-out precedence, and honest runtime translation.
- Disadvantages: introduces a small capability-resolution concept and requires renderers, docs, diagnostics/tests, and old `solution-architect` source frontmatter to be reconciled.
- Reversibility: High; the field and adapter mappings can be removed without changing role bodies.

### Option C: Declare separate defaults under `[claude]` and `[codex]`

- Shape: add runtime-native defaults and per-agent overrides independently in each adapter section.
- Advantages: closely follows each runtime's syntax and avoids a new shared abstraction.
- Disadvantages: duplicates the policy, permits Claude/Codex drift by construction, and makes a single logical opt-out require two declarations.
- Reversibility: High.
- Assessment: Viable plumbing, but weaker than the requested parity contract.

## Recommendation

Use Option B. Treat `web_research` as a shared Flow capability and keep `WebSearch`/`WebFetch` and Codex web-search settings inside their adapter boundaries. This mirrors the existing semantic-model-tier design: Flow owns intent; each runtime renderer owns syntax.

The effective-policy precedence should be explicit:

1. a per-agent explicit value wins;
2. otherwise the shared global default applies;
3. if an opt-out is declared, a non-empty rationale is required;
4. the resolved value is calculated after user-overlay merge so framework and overlay agents follow the same deterministic rule.

The behavioral rule should also be generated or otherwise shared, rather than copied independently into thirteen bodies: capability availability does not authorize browsing. Use it only when the assigned task explicitly requires external or current research; otherwise stay with the local corpus. If the generated instruction is centralized, both adapters receive identical wording and future agents cannot miss it.

Codex parity should be defined semantically, not as literal `WebSearch` plus `WebFetch` names. Official Codex documentation exposes web research through native web-search configuration, not Claude's two tool names. Configuration should select a mode that actually permits the approved current/external-research use case. If Flow selects `live`, that choice is a visible scope expansion and should be called out in the implementation review. An opted-out Codex agent needs explicit `web_search = "disabled"` (and, if the adapter also emits `tools.web_search`, an explicit false value); omission alone is not a denial.

No ADR is necessary if this remains a reversible extension of the established shared-policy/adapter pattern. Create one only if implementation introduces a general capability framework intended to govern multiple future permissions, because that becomes a longer-lived runtime integration strategy (`architecture.md / ADR convention`).

## Smallest sound configuration validation

Add one table-driven source-to-generated integration test built on the actual manifest inventory and existing fake-home sync harness:

1. Load the framework manifest and assert the shared default is enabled.
2. Generate both Claude and Codex desired outputs for every registered agent.
3. For every default-enabled agent, assert Claude contains `WebSearch` and `WebFetch` exactly once and Codex parses to the enabled native web-search configuration.
4. In the same test (or a tightly paired resolver unit test), clone the manifest in memory, set one representative agent to explicit opt-out with a rationale, regenerate both adapters, and assert Claude contains neither web tool while Codex contains an explicit disabled setting.
5. Assert every manifest agent was visited so a newly registered role is covered automatically.
6. Assert an opt-out without a rationale fails configuration validation rather than silently rendering.

This proves the source default, opt-out precedence, full inventory coverage, and cross-adapter rendering without touching the user's real generated files or requiring network access. Existing sync freshness tests remain useful but are not sufficient by themselves: they prove generated files match their source, not that the source expresses the correct capability policy.

The validation record must say **configuration passed**, not **web access passed**. Host policy, account entitlements, administrator settings, runtime version, and actual delegated tool invocation remain untested.

## Adversarial concerns

- **Opt-out by omission is unsafe in Codex.** Custom-agent files inherit omitted session settings from the parent. The negative case must render an explicit disable.
- **Literal-name parity is misleading.** Codex has a native web-search configuration rather than Claude's `WebSearch`/`WebFetch` pair. Tests should compare effective capability, not identical text.
- **The existing `solution-architect` declaration becomes duplicate authority.** Once the manifest owns the default, either remove the source-level web entries or have rendering normalize them. Leaving both makes policy changes ambiguous.
- **Global availability includes future agents.** That is the intended benefit, but also means a newly added sensitive/local-only role is web-enabled unless its author declares and explains an opt-out. The inventory test should make the default visible in review.
- **User overlays already alter agents.** A same-name override replaces the entire manifest entry. Effective defaults must be applied after merge; otherwise an overlay can accidentally lose or bypass the policy. An explicit overlay opt-out is technically feasible today, even if authoring UX and documentation are deferred.
- **Instruction text is not a hard technical control.** “Only when explicitly required” governs model behavior, while tool configuration governs availability. Configuration tests cannot prove compliance with that behavioral rule.
- **External content expands the trust boundary.** Web content can be stale or adversarial. Existing source-quality and input-validation disciplines still apply; results must be cited and distinguished from local project truth.
- **Configuration does not prove runtime support.** The agreed test level will not detect host-level tool removal, administrative policy, account limits, or a client that ignores a custom-agent field. Do not upgrade that residual risk into a success claim.
- **`live` versus cached/indexed is a real semantic choice.** “Current external research” is not guaranteed by a cached-only mode. The implementation plan should name the selected Codex mode and its consequence rather than merely setting a boolean.

## Implication for requirements

- Confirm the requirement that Flow owns one semantic `web_research` default and adapters own runtime-native syntax.
- Refine Codex acceptance criteria from literal `WebSearch`/`WebFetch` names to an explicit enabled/disabled native configuration with current/external access semantics.
- Add that an opt-out without a non-empty rationale is invalid and that Codex opt-out must be explicit, not inherited through omission.
- Correct the assumption that user-level agent overrides are unverified: source, documentation, and tests show they are supported. Keep overlay authoring changes out of scope if desired, but do not document them as unavailable.
- Preserve the configuration-only validation boundary and its explicit non-claim about runtime invocation.
- Route to `flow-solution` only if the Codex mode (`live` versus another supported mode) or a generalized capability framework remains undecided; otherwise the recommended shared-default mapping is concrete enough for `flow-plan`.

## Open follow-ups

- Engineer/owner: choose the Codex web-search mode that satisfies “current external research”; `live` is the direct semantic match but expands access most broadly.
- Requirements owner: decide whether a user-overlay agent may opt out through the same field in this slice or whether only framework entries receive documented authoring support. The merge path already supports the underlying entry override.
- Implementation planner: decide whether capability checks extend `flow runtime smoke`/`flow doctor` now or remain focused tests. The smallest accepted slice needs tests; changing diagnostics is useful but not required.
