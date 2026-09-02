# Agent Web Access Policy Requirements

## Problem Statement

- **What:** Flow currently grants web research capabilities unevenly across role agents. That prevents some otherwise appropriate roles from completing a task that explicitly requires current or external evidence, and makes the capability policy hard to reason about across Claude and Codex.
- **Who:** Flow users assigning work to any Flow role; role agents that need external research; and maintainers who generate or validate Claude and Codex adapters.
- **Why now:** The policy was surfaced by a real task in which `solution-architect` could perform SAFe research while other roles could not. The user approved a global default, with an explicit per-agent opt-out and configuration-level verification.

## Users and Workflows

- **Primary personas:**
  - A Flow user who assigns a role an explicitly web-research task.
  - A Flow agent that must distinguish local-corpus reasoning from external research.
  - A Flow maintainer who changes source scaffolds and regenerates adapters.
- **Current workflow:** A user assigns a role; the role may be blocked if its generated definition lacks web tools. Capability differences vary by role and adapter, and editing generated Claude output is not durable.
- **Future workflow:**
  1. The maintainer declares web research as the default capability for every supported Flow agent in the canonical source.
  2. Adapter generation produces equivalent Claude and Codex capability declarations from that source.
  3. A role uses web research only when its assigned task explicitly requires external/current research.
  4. A maintainer can opt an individual agent out in source when that role must remain local-only; the opt-out overrides the global default in every generated adapter.
  5. Configuration tests verify the source policy and generated adapter artifacts without attempting a live delegated web-research run.

## Scope

- **In scope:**
  - A global default that makes web research available to every Flow agent.
  - Claude and Codex adapter parity for the policy.
  - A durable, source-level, per-agent opt-out.
  - Role instructions that limit use to tasks explicitly requiring web research.
  - Configuration-level tests and documentation of the policy.
- **Out of scope:**
  - Editing generated files in `~/.claude/agents/` or other generated runtime locations.
  - A per-user agent override layer, unless existing supported overlay behavior is verified separately.
  - Live delegated web-research smoke tests, network reliability testing, or source-quality evaluation.
  - Giving agents unrestricted authority to browse merely because a task might benefit from it.
  - Changes to non-web tools, model routing, role responsibilities, or runtime sandboxing.
- **Constraints:**
  - Canonical scaffolds are the source of truth; generated outputs are regenerated through Flow sync rather than hand-edited.
  - `WebSearch` and `WebFetch` are the required named web capabilities where the target runtime uses those names.
  - The policy applies globally across all Flow roles, not only product-manager or the originally affected roles.
  - Configuration tests are the agreed verification level for this change; they must not claim to prove live tool invocation.

## Requirements

### Goals

1. Every supported Flow role has web research capability by default in both Claude and Codex generated surfaces.
2. Every role retains a clear behavioral rule: use web research only when the assigned task explicitly requires external or current research.
3. A source-level opt-out can make a named agent local-only, and that opt-out takes precedence over the global default in every adapter.
4. Generated capability declarations are deterministic, reviewable, and traceable to canonical source configuration.
5. Tests make capability drift visible before a release without needing a live browser or delegated-agent execution.

### Non-goals

1. The policy does not require agents to browse whenever local evidence is incomplete, ambiguous, or merely old; the task must explicitly require external/current research.
2. The policy does not guarantee that a particular host, account, network, or agent invocation can successfully access the web at runtime.
3. The policy does not establish a user-overlay override mechanism whose support has not been confirmed.

### User Stories

1. As a Flow user, I can assign any role a task that explicitly requires current external research and expect that role's generated Claude and Codex definition to declare web research capability.
2. As a Flow user, I can assign a local-analysis task to a web-capable role and expect it to remain local unless I explicitly ask for web research.
3. As a Flow maintainer, I can mark a specific agent as web-disabled in canonical source and know the generated Claude and Codex forms will not grant it `WebSearch` or `WebFetch`.
4. As a reviewer, I can run configuration checks that identify a missing default grant, an ignored opt-out, or Claude/Codex parity drift.

### Acceptance Criteria

1. Canonical Flow source defines one global default that applies web research capability to every supported Flow agent unless that agent explicitly opts out.
2. For every non-opted-out agent, generated Claude output declares both `WebSearch` and `WebFetch` in the role's tool/capability configuration.
3. For every non-opted-out agent, the generated Codex surface exposes an equivalent web-research capability according to the Codex adapter's supported representation; it must not silently omit web access while Claude grants it.
4. An explicit source opt-out for an agent results in neither `WebSearch` nor `WebFetch` being granted for that agent in Claude, and in no equivalent web capability in Codex.
5. The opt-out is documented as an intentional exception, including the role name and rationale, so a local-only policy cannot be accidental or invisible.
6. Role guidance says web access is used only when the assigned task explicitly requires external/current research. A role with available web tools must not treat availability as an implicit instruction to browse.
7. Configuration tests inventory all supported agent sources and fail if any non-opted-out agent lacks the required default web grant in canonical source or either generated adapter.
8. Configuration tests fail if an opted-out agent receives web capability in any generated adapter.
9. Configuration tests fail if the global default, opt-out semantics, or adapter rendering would leave Claude and Codex with different effective policy for the same agent.
10. Validation records that it checked configuration and generated artifacts only; documentation must state that this is not a live delegated web-access test.
11. The documented regeneration procedure uses Flow sync for both supported adapters and does not direct users to modify generated runtime files.

## Edge Cases and Exceptions

- **Explicit task wording:** “Research current external practice,” “find recent guidance,” or an equivalent explicit request permits web use. “Could benefit from research,” a broad ambiguity, or an unverified local claim alone does not.
- **Mixed evidence:** When a task explicitly requires web research, the role may combine web results with the local corpus; it must still distinguish sourced external facts from local evidence and inference.
- **Opted-out role receives a web-required task:** The role remains local-only. It should report the capability conflict or the orchestrator should route the research portion to an eligible role; it must not bypass the opt-out.
- **Adapter cannot represent the policy:** Sync or configuration validation must fail clearly, or explicitly report the capability as unavailable. It must never label web access as present based only on source intent.
- **Unsupported or offline runtime:** Configuration may be correct while runtime use is unavailable. This is a runtime limitation, not a reason to weaken the source policy or claim a successful smoke test.
- **New role added later:** It receives the global default automatically unless it is added with a documented opt-out; inventory tests must cover it.
- **Generated-output drift:** A hand edit to generated output is not an accepted fix. The source and sync/rendering path must be corrected.

## Risks and Open Questions

- **Risks:**
  - Global availability may encourage unnecessary browsing unless the explicit-task-use rule is prominent and consistently applied.
  - Claude and Codex may not expose identical configuration syntax, which could create false parity if only source files are inspected.
  - A global source-scaffold change affects all users of the framework, including those with roles intended to be deliberately local-only.
  - Configuration tests cannot detect a provider outage, permissions issue, or unavailable runtime tool.
- **Assumptions:**
  - Flow has canonical agent scaffolds that can express defaults and per-agent exceptions, or can be extended to do so.
  - `flow sync claude --user` and the corresponding Codex sync are the supported regeneration paths.
  - The desired opt-out is an intentional source-level exception, not an unverified user-overlay feature.
  - “All Flow agents” means every agent supported by the current canonical Flow agent inventory and any future agent included by that inventory.
- **Open questions:**
  - What exact source field and adapter mapping should encode the global default and opt-out while preserving backward compatibility?
  - What is the authoritative Codex-generated artifact to inspect, given that current adapters may represent roles differently from Claude?
  - Should an opted-out agent's instructions contain a standard remediation message directing the orchestrator to an eligible research role?
  - Should adding an opt-out require a rationale format or review gate beyond the documented exception requirement?

## Delivery Slices

1. Define and document the source-level global default, per-agent opt-out, explicit-task-use rule, and adapter parity contract.
2. Implement source and adapter rendering for Claude and Codex, then add inventory and generated-output configuration tests.
3. Regenerate supported user/runtime surfaces, validate the configuration results, and document runtime-test boundaries and opt-out operations.
