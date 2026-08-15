# Agent Model Routing Research

Status: historical research note for the shipped Codex agent model-policy work

Implementation note: the core recommendation has shipped. Flow now uses shared
`[[agents]]` entries, semantic model tiers, generated Claude agents, generated
Codex agents, and generated routing tables. Keep this document as the research
record and failure-mode background, not as the current implementation plan.

## Problem

Flow should route command and agent work to models that are appropriate for the
task's risk, ambiguity, and cost profile. The goal is not simply to pin models.
The goal is to preserve premium reasoning for judgment-heavy passes while using
more efficient models for bounded exploration, inventory, drafting, and
mechanical validation.

## Codex findings

Codex has a native custom-agent surface that Flow can target. Local Codex
clients can load custom agent TOML files from user-level and project-level
locations. Those files can define the agent name, description, developer
instructions, model, reasoning effort, sandbox mode, and other supported Codex
configuration keys.

This means Flow does not need to wrap Codex through the Agents SDK to get
role-specific model control. Flow can remain a runtime adapter and generate
Codex-native agent configuration.

Recommended Codex shape, now implemented in the core adapter:

- Use shared `[[agents]]` entries in `flow.toml`.
- Generate `.codex/agents/<agent>.toml` for project-level sync and
  `~/.codex/agents/<agent>.toml` for user-level sync.
- Preserve the Flow agent body as Codex `developer_instructions`.
- Emit `model`, `model_reasoning_effort`, and optional sandbox/tool settings
  into each generated agent file.
- Update generated Codex command skills so agent-heavy commands explicitly
  delegate bounded work to the named Codex agents.
- Track generated agent files in `.codex/flow.managed.toml` so drift checks and
  stale cleanup remain honest.

Preferred policy model:

- Define semantic tiers such as `judgment`, `working`, and `mechanical`.
- Provide default mappings to concrete Codex models and reasoning effort.
- Let user and project Flow overlays override the tier mapping or an individual
  agent's assignment.
- Let commands define composition; let agents define model/effort defaults.

Initial default tier mapping proposal, now represented in `flow.toml`:

```toml
[codex.model_tiers.judgment]
model = "gpt-5.6-sol"
model_reasoning_effort = "medium"

[codex.model_tiers.working]
model = "gpt-5.6-terra"
model_reasoning_effort = "medium"

[codex.model_tiers.mechanical]
model = "gpt-5.6-luna"
model_reasoning_effort = "low"
```

Initial role mapping proposal, now represented in shared `[[agents]]` entries:

- `judgment`: `architect`, `solution-architect`, `security-reviewer`,
  `quality-reviewer`
- `working`: `business-analyst`, `data-engineer`, `lead-developer`,
  `product-manager`, `sre`, `test-engineer`, `ux-specialist`
- `mechanical`: `support-lead`, `tech-writer`, and future inventory or
  summarization helpers when the task is bounded

## Open implementation questions

- Whether Codex should get its own `[[codex.agents]]` declarations or whether
  Flow should introduce a shared `[[agents]]` source that both runtime adapters
  consume.
- Whether Flow should translate existing Claude `opus` / `sonnet` / `haiku`
  metadata directly into Codex tiers as a compatibility bridge.
- Whether generated command skills should include a compact routing table or
  only name the agents they expect the orchestrator to use.
- Whether Flow should generate `.codex/config.toml` with `[agents]` defaults, or
  avoid runtime config writes until there is a concrete need beyond per-agent
  files.

## Claude findings

Claude Code already has a mature custom-subagent surface, and Flow already emits
that surface. `flow sync claude` generates `.claude/agents/*.md` from the Flow
agent source files. Those files use YAML frontmatter plus a Markdown body, which
matches Claude Code's native subagent format.

Claude Code's subagent frontmatter supports more than Flow currently uses:

- `name`
- `description`
- `tools`
- `disallowedTools`
- `model`
- `permissionMode`
- `maxTurns`
- `skills`
- `mcpServers`
- `hooks`
- `memory`
- `background`
- `effort`
- `isolation`
- `color`
- `initialPrompt`

The current Flow agent files already use the main fields needed for role
routing:

- `architect`, `solution-architect`, `security-reviewer`, and
  `quality-reviewer` use `model: opus`.
- Most working roles use `model: sonnet`.
- `support-lead` uses `model: haiku`.
- Agents also declare tool lists such as `Read`, `Write`, `Grep`, and `Glob`.

Claude Code resolves subagent model selection in this order:

1. `CLAUDE_CODE_SUBAGENT_MODEL`
2. per-invocation `model`
3. the subagent definition's `model` frontmatter
4. the main conversation's model

That means Flow's current Claude model pins are real, but not absolute. They can
still be overridden by environment or invocation-level controls.

Claude Code also supports `effort` per subagent. That gives Claude a stronger
parity story with Codex than Flow currently expresses. Flow should treat
`model` and `effort` as the shared policy dimensions across runtimes, even
though each runtime serializes them differently.

## Claude recommendation

Keep Claude's generated subagent Markdown as the target surface. Do not move
Claude through an SDK or wrapper. Claude Code's native files already provide
the role-specific model, effort, tool, and permission controls Flow needs.

Enhance the manifest layer instead of replacing the adapter:

- Introduce shared semantic routing tiers (`judgment`, `working`,
  `mechanical`) that apply to both Claude and Codex.
- Keep Claude's current `opus` / `sonnet` / `haiku` behavior as the default
  concrete mapping for those tiers.
- Add optional `effort` to Flow agent source files or manifest entries.
- Let runtime-specific overrides remain possible:
  - Claude can use aliases such as `opus`, `sonnet`, `haiku`, and `fable`, or
    full model IDs.
  - Codex can use concrete GPT model IDs and `model_reasoning_effort`.
- Preserve user and project overlay behavior: same-name agents override,
  new-name agents append, and managed manifests track generated files.

Initial Claude tier mapping proposal:

```toml
[claude.model_tiers.judgment]
model = "opus"
effort = "medium"

[claude.model_tiers.working]
model = "sonnet"
effort = "medium"

[claude.model_tiers.mechanical]
model = "haiku"
effort = "low"
```

Do not automatically route every high-value task to `fable`. Claude's own model
guidance frames Fable as useful for larger, ambiguous, long-running work. Flow
should reserve it as an opt-in `deep-judgment` tier or project/user override,
not the framework default.

## Cross-runtime proposal

The most consistent Flow shape is:

```toml
[[agents]]
name = "architect"
source = "agents/architect.md"
summary = "Boundaries, integrations, ADR decisions"
model_tier = "judgment"

[[agents]]
name = "support-lead"
source = "agents/support-lead.md"
summary = "Operator-facing notes, troubleshooting"
model_tier = "mechanical"
```

Runtime adapters then resolve the shared agent into native files:

- Claude: `.claude/agents/architect.md`
  - YAML frontmatter keeps `model`, `effort`, `tools`, and other Claude-native
    fields.
- Codex: `.codex/agents/architect.toml`
  - TOML fields include `model`, `model_reasoning_effort`, `sandbox_mode`, and
    `developer_instructions`.

If introducing shared `[[agents]]` is too large for the first slice, preserve
the existing `[[claude.agents]]` source for now and add `[[codex.agents]]` as a
parallel declaration. Then follow with a manifest unification slice.

Recommended staged implementation:

1. **Parity slice**: generate Codex custom agents from the existing Flow agent
   library and keep Claude generation unchanged.
2. **Policy slice**: add semantic model tiers and resolve them for both
   runtimes.
3. **Effort slice**: add explicit effort defaults and agent-level overrides for
   Claude and Codex.
4. **Composition slice**: update command skills to name expected agents and
   delegation boundaries consistently across runtimes.
5. **Optional deep-work slice**: add an opt-in `deep-judgment` tier for Fable or
   higher-effort frontier models where a project actually wants that cost.

## Research links

- Codex subagents and custom agents:
  https://learn.chatgpt.com/docs/agent-configuration/subagents
- Codex skills:
  https://learn.chatgpt.com/docs/build-skills
- Codex config basics:
  https://learn.chatgpt.com/docs/config-file/config-basic
- Codex model guidance:
  https://learn.chatgpt.com/docs/models
- OpenAI reasoning effort guidance:
  https://developers.openai.com/api/docs/guides/reasoning
- Claude Code subagents:
  https://code.claude.com/docs/en/sub-agents
- Claude Code skills:
  https://code.claude.com/docs/en/skills
- Claude Code model configuration:
  https://code.claude.com/docs/en/model-config
- Claude Code Agent SDK:
  https://code.claude.com/docs/en/agent-sdk/overview
- LangChain multi-agent architecture:
  https://www.langchain.com/blog/choosing-the-right-multi-agent-architecture
- LangChain multi-agent benchmarks:
  https://www.langchain.com/blog/benchmarking-multi-agent-architectures
- AutoGen model clients:
  https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/components/model-clients.html
- CrewAI LLM configuration:
  https://docs.crewai.com/v1.15.12/en/concepts/llms
- Agentic routing research:
  https://arxiv.org/abs/2607.11399

## External fit assessment

Flow's implementation direction is correct for the framework's intent, but the
current implementation is incomplete.

What is correct today:

- Claude generation already targets the native subagent surface. Flow emits
  `.claude/agents/*.md`, and Claude Code subagents are designed for focused
  system prompts, scoped tools, independent context, and model-based cost
  control.
- Flow's source agent files already contain role-specific model assignments:
  `opus` for judgment-heavy review and architecture, `sonnet` for most working
  roles, and `haiku` for support-oriented work.
- Flow's managed-manifest sync model is aligned with native-runtime config:
  generated files are tracked, stale generated files can be removed, and
  unmanaged files are preserved.
- Keeping Flow as an adapter that emits native runtime surfaces is consistent
  with both Claude and Codex. Neither runtime needs an SDK wrapper for the
  first-order problem of per-agent model routing.

What is not correct yet:

- Codex generation does not emit `.codex/agents/*.toml`, even though Codex has
  native custom-agent files with model and reasoning-effort controls.
- Flow has duplicated runtime agent catalogs: Claude has `[[claude.agents]]`,
  while Codex has only `[[codex.commands]]`. That creates drift from Flow's
  stated source-of-truth model.
- Flow lacks a shared semantic policy layer. Today the policy is encoded in
  Claude-specific model aliases inside the agent Markdown. That works for
  Claude, but does not translate cleanly to Codex, future runtimes, or user
  cost preferences.
- Flow lacks explicit effort policy. Both Claude and Codex expose an effort
  dimension, and model choice without effort is only half the routing decision.
- Flow command skills describe composition, but the Codex side does not yet bind
  those composition rules to concrete custom agents.

Broader-world comparison:

- Claude Code's own docs frame subagents as a way to preserve context, limit
  tools, reuse configurations, specialize behavior, and control cost by routing
  simpler work to cheaper models.
- Codex's docs now expose the same core idea: custom agents are TOML config
  layers that can set `model` and `model_reasoning_effort`, with inheritance
  from spawn values, `[agents]` defaults, and the parent session.
- LangChain's multi-agent architecture guidance distinguishes skills from
  subagents: skills are lighter and useful for progressive disclosure, while
  subagents are better when parallel execution and isolated context matter.
  Flow's heavy commands (`solution`, `plan`, `implement`, `review`) are exactly
  the class where subagents are warranted; lightweight commands (`status`,
  `help`, `scout`) should avoid unnecessary delegation.
- Cost-routing writeups and recent routing research agree on the same operating
  principle: do not run every step on the frontier model. Use stronger models
  for orchestration, judgment, and ambiguous reasoning; use cheaper models for
  bounded subtasks. Research also warns that routing should account for
  execution feedback and over-selection cost, which argues for starting with a
  simple static policy and logging outcomes before trying dynamic routing.

Verdict:

The proposed direction is right:

1. Generate native Codex agents.
2. Keep Claude on native Markdown agents.
3. Add shared semantic tiers.
4. Resolve tiers per runtime.
5. Add effort as a first-class policy dimension.
6. Keep SDK-based orchestration out of scope for now.

The first implementation slice should not attempt dynamic routing. It should
make the static policy explicit, generated, inspectable, and overrideable. That
matches Flow's adapter-first architecture and gives future routing work a clean
source of truth.

## Failure-mode research

There are public reports that both Claude and Codex subagent model routing can
fail or vary by client/runtime version. Flow should still target native agent
surfaces, but the implementation needs verification and fallback behavior.

Claude reported failures:

- `model:` frontmatter ignored. A Claude Code issue reports that a subagent with
  `model: sonnet` still inherited the parent Opus model unless the spawning
  Agent tool call explicitly passed `model: "sonnet"`. The report says this
  makes cost-optimized tiering impossible through agent definitions alone.
- Custom project agents unavailable in the VS Code extension. Another issue
  reports that `.claude/agents/*.md` custom agents worked in the CLI but were
  rejected by the VS Code extension, which only recognized built-in agents. The
  documented workaround of spawning a generic agent and telling it to read the
  custom file does not enforce frontmatter tool restrictions.
- The official Claude docs also include caveats that matter for Flow: model
  resolution can be overridden by `CLAUDE_CODE_SUBAGENT_MODEL` and per-invocation
  `model`, blocked model aliases can fall back, subagents inherit extended
  thinking rather than having independent thinking settings, and some behavior
  depends on Claude Code version.

Codex reported failures:

- Custom agent `model` and `model_reasoning_effort` ignored. An OpenAI Codex
  issue reports valid `.toml` custom agent roles being callable but still
  inheriting the parent model/effort rather than the configured Spark/Mini agent
  settings.
- Named custom agents unavailable in tool-backed Codex sessions. Another issue
  reports valid `.codex/agents/*.toml` files on disk, but the exposed
  `spawn_agent` tool did not provide a way to invoke those named custom agents.
  The report frames this as a docs/runtime mismatch between app/CLI behavior and
  tool-backed sessions.
- Community reports around the GPT-5.6/multi-agent-v2 transition describe
  spawned subagents unexpectedly inheriting parent model and effort, burning
  quota when users expected cheaper Terra/Luna/Spark workers.
- A Windows desktop issue reports named TOML configs no longer working and
  spawned agents using default configuration, with forked agents explicitly
  inheriting parent agent type, model, and reasoning effort.

Implications for Flow:

- Do not promise hard enforcement based only on generated files. Phrase the
  feature as Flow's intended native runtime configuration, with verification
  support.
- Add `flow doctor` checks that report whether expected generated agent files
  exist, whether their model/effort fields are present, and which runtime
  surfaces are likely unsupported or stale.
- Add a small manual verification command or documented smoke test for each
  runtime:
  - Claude: spawn a known cheap test agent and confirm transcript/metadata shows
    its configured model.
  - Codex: spawn a known cheap test agent and confirm logs/session metadata show
    its configured model and reasoning effort.
- For Claude command skills, consider including explicit per-agent model names
  in delegation instructions as a workaround for frontmatter-ignore bugs. This
  duplicates policy, so generate it from the same source rather than hand-writing
  it.
- For Codex command skills, include both the named custom agent and the expected
  model/effort in delegation instructions, and warn that some tool-backed
  sessions may require generic subagents plus injected developer instructions
  until named agent invocation is consistently exposed.
- Prefer static, inspectable routing first. Dynamic routing should wait until
  Flow can collect actual evidence about whether the runtime honored the
  configured model.

Net assessment after failure research:

The architecture is still correct, but the implementation should include a
"trust but verify" layer. Native custom-agent generation is the right source of
truth. Runtime model enforcement is not stable enough to treat as guaranteed
without diagnostics, transcript/log checks, and generated fallback hints.
