# Research: Product policy for agent web access

- Owner role: product-manager
- Date: 2026-09-02
- Confidence: High for the observed Flow policy and requested outcome; Medium for downstream adoption effects because no usage telemetry is available.

## Question

Should Flow make web research available to every built-in role, limit its use to tasks that explicitly require external research, and provide a per-agent opt-out? What is the smallest policy worth shipping, and how should it be proven without runtime web smoke tests?

## Method and sources

- User decision: enable the capability globally for all Flow agents, use it only when the task explicitly requires it, support an opt-out for agents that should not have it, and cover both Claude and Codex.
- `scaffolds/default/agents/solution-architect.md`: the only current built-in role with `WebSearch` and `WebFetch` in its declared tools.
- Other built-in agent frontmatter under `scaffolds/default/agents/`: local corpus tools only.
- `scaffolds/default/standards/research-evidence.md`: assigns named external-evidence questions to product, business analysis, SRE, support, security, UX, and other roles; research is optional but must answer a named question and change a requirement or decision.
- `scaffolds/default/standards/definition.md`: requires product, requirements, and solution perspectives for definition, and durable evidence for capability work.

## Findings

1. **The present capability allocation conflicts with Flow's role model.**
   The research standard gives several roles responsibility for questions that can require current external evidence, while only the solution architect can access it. In an explicitly research-dependent task, that prevents the accountable role from independently fulfilling its stated remit or forces an unnecessary handoff.

2. **Global availability is justified; global browsing is not.**
   All roles should be able to perform an explicitly requested research task, including product comparison, policy/security research, support documentation lookup, and operational-vendor research. That is a capability baseline, not a default work pattern. The agent instructions should retain a clear rule: use web access only when the user explicitly asks for external/current research or when a selected Flow workflow requires a named research question. Local artifacts remain the primary source whenever they answer the question.

3. **A per-agent opt-out is a necessary policy control, but must be narrow and source-owned.**
   The opt-out should let Flow intentionally keep a role local-only when its purpose, trust boundary, cost profile, or environment warrants it. It should be declared in the Flow source for that role and render consistently to both harnesses. It should not create an unverified user-overlay override mechanism or invite per-run circumvention of a deliberate local-only restriction.

4. **This is a priority-now, small foundation change.**
   The requested work is a direct unblocker for definition and planning tasks whose assigned role needs external evidence. The change has a low implementation surface if it stays at policy, generated capability declarations, synchronization, and configuration tests. Its value is broad because it removes role-dependent dispatch failures across every Flow workflow.

5. **Configuration proof is sufficient for this slice, with an explicit residual risk.**
   The agreed acceptance boundary is source-to-generated configuration verification, not delegated live web calls. This avoids flaky, network-dependent release tests and keeps the change proportional. It does not prove credentials, host availability, or tool execution at runtime; that residual risk should be recorded rather than silently implied away.

## Product Decision Summary

### Opportunity

- Problem: Flow assigns research accountability to many roles, but only one built-in role currently declares the tools needed for web research. Explicitly research-dependent tasks can therefore be blocked or rerouted away from the accountable role.
- Users: Flow users delegating definition, planning, review, operational, security, support, and product work; the roles assigned to produce evidence-backed conclusions.
- Why now: The gap was observed during real work, the user has chosen a global policy, and it is a prerequisite for reliable role-based research in both supported harnesses.

### Recommendation

- Prioritize: global web-capability availability for all built-in Flow agents, rendered for Claude and Codex; constrain use in role/workflow instructions to explicitly requested or named research.
- Why: It aligns capability with existing role accountability without changing the default local-corpus-first operating model.
- Policy distinction: **availability** is global; **authorization to browse** is task-specific; **opt-out** is a deliberate source-level exception.

### Scope

- Minimum useful slice:
  - Define a single source-of-truth policy for all built-in agents.
  - Render `WebSearch` and `WebFetch` (or the harness-equivalent declarations) for every non-opted-out built-in role in both Claude and Codex outputs.
  - Add concise instruction language: do not browse unless the task explicitly requires external/current research or a Flow workflow has a named research question; prefer local/primary evidence first; cite external sources when used.
  - Add a source-level per-agent opt-out whose generated outputs omit web tools and preserve the local-only instruction.
  - Add deterministic configuration tests covering: every default role is enabled, an opted-out fixture is disabled, and both generated harness outputs match the source policy.
  - Regenerate the user-facing Claude and Codex agent outputs through Flow sync as part of verification.
- Deferred scope:
  - A user-overlay agent override until its supported merge/render semantics are established.
  - Runtime/delegated web smoke tests, credential probing, and network availability monitoring.
  - Automatic web research based on agent discretion, query allowlists/blocklists, quotas, or central logging.

### Risks and Tradeoffs

- Risks:
  - Broad availability can increase latency, cost, and source-quality variance if agents treat it as a default rather than a task-specific capability.
  - External sources can be stale, adversarial, paywalled, or conflict with local project truth.
  - Claude and Codex may differ in tool names or runtime availability even when their rendered configuration looks correct.
  - A poorly specified opt-out could yield inconsistent generated artifacts or let users assume a non-existent overlay override works.
- Mitigations:
  - Make explicit-task-only usage and local-first evidence part of each enabled role's instructions and the research standard.
  - Require the existing named-question, source-quality, confidence, and requirement-impact discipline for web research.
  - Test source-to-rendered declarations deterministically for both harnesses; document runtime execution as outside this slice.
  - Keep opt-out source-owned and test it with a fixture before documenting any user-level customization path.
- Tradeoffs:
  - This chooses flexibility and role accountability over the stronger default isolation of local-only roles.
  - It accepts that configuration success is not proof of live provider availability; the user explicitly prefers this smaller, non-flaky acceptance boundary.
- Assumptions:
  - Both harness renderers can represent equivalent web-search and web-fetch capability declarations.
  - The source scaffold, rather than generated `~/.claude/agents/*.md`, remains the canonical editable layer.
  - Existing guidance can make "explicitly requires" sufficiently observable in task prompts and Flow research workflows; edge cases can be refined from later capability-gap evidence.

### Success

- Success metrics:
  - 100% of built-in default roles have the web-capability policy represented in canonical source and in both generated harness outputs, except roles deliberately marked opted out.
  - Configuration tests demonstrate no role is accidentally omitted, no opted-out role receives the tools, and no harness renders a divergent declaration.
  - Role guidance contains the explicit-task-only and local-first rules wherever web tools are available.
- Launch or acceptance criteria:
  - Source policy and per-agent opt-out semantics are documented.
  - A configuration test covers default-enabled and opted-out cases for Claude and Codex output.
  - `flow sync claude --user` and the equivalent Codex sync complete successfully; generated outputs are inspected or tested for the expected declarations.
  - No runtime web smoke test is required for this release; the resulting limitation is stated in release/handback evidence.

## Implication for requirements

- Add a global capability-baseline requirement with a source-level per-agent opt-out.
- Add an explicit-use requirement: availability does not authorize browsing absent an explicit task need or named Flow research question.
- Add dual-harness source-to-rendered configuration acceptance criteria.
- Add no-runtime-smoke-test as a deliberate non-goal and residual-risk statement, not as a claim that runtime access was validated.

## Open follow-ups

- Define the exact canonical opt-out syntax and merge precedence through solutioning; do not promise a user-overlay override until proven.
- Decide whether explicit currentness needs a standard prompt phrase beyond "explicitly requires external/current research." 
