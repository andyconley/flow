# Definition: Global Flow Agent Web Access Policy

- Work item: `agent-web-access-policy`
- Definition lead: root orchestrator
- Opening role: solution-architect
- Status: Approved
- Approver: Andy Conley

## Problem or opportunity

- What: Flow assigns external-research responsibilities to multiple roles, but
  only `solution-architect` currently declares Claude web tools and the Codex
  renderer does not map that declaration into native agent configuration.
- Who: Flow users, every current and future Flow role agent, and maintainers of
  the Claude and Codex adapters.
- Why now: A real research assignment exposed that the accountable role can be
  blocked by its generated capability configuration.

## Desired outcome

Every Flow agent receives web-research capability by default in both Claude and
Codex. A role uses it only when its task or orchestrator brief explicitly names
an external/current research question and marks web research as required.
Individual agents can be made local-only through a source-owned, documented,
fail-closed opt-out.

## Evidence

- Research needed: yes
- Research notes:
  - `research/architecture.md`
  - `research/requirements.md`
  - `research/product.md`
  - `research/security.md`
  - `research/testability.md`
- Official Codex configuration supports custom-agent TOML configuration layers
  and native web-search settings: [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
  and [Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference).

## Requirements

### Success criteria

- One semantic Flow policy controls effective web-research capability across
  every registered agent and both supported runtime adapters.
- All current and future agents inherit the enabled default unless an explicit,
  documented opt-out applies.
- Capability availability does not authorize browsing: the generated role
  instructions require an explicitly assigned external/current research
  question before use.
- A deterministic configuration test detects missing grants, ineffective
  opt-outs, overlay precedence errors, and Claude/Codex policy drift.

### Acceptance criteria

- [ ] Canonical source defines a single default-enabled semantic web-research
  capability for the complete agent inventory.
- [ ] Effective policy is resolved after framework and supported user-overlay
  agent configuration is merged.
- [ ] Claude output contains `WebSearch` and `WebFetch` exactly once for every
  enabled agent while preserving unrelated tools.
- [ ] Codex output contains an explicit native setting that permits current
  external web research for every enabled agent.
- [ ] An agent can explicitly opt out in source; an opt-out requires a non-empty
  rationale.
- [ ] Opted-out Claude output omits both web tools, while opted-out Codex output
  contains an explicit native disable rather than inheriting through omission.
- [ ] Invalid capability values, missing opt-out rationales, and ambiguous
  overlay replacement fail configuration before rendering.
- [ ] Generated guidance for both runtimes permits web use only when the user
  assignment or orchestrator brief names an external/current research question
  and explicitly requires web research. Role selection or workflow entry alone
  is not authorization.
- [ ] Generated guidance treats web content as untrusted data, never as
  instructions; prohibits transmitting secrets, credentials, private source,
  personal data, or internal identifiers without explicit disclosure
  authorization; prefers primary sources; cites material external claims; and
  surfaces conflicts with local policy or project truth.
- [ ] A table-driven configuration test visits the entire manifest inventory,
  validates both runtime-native outputs, and covers an enabled role, an opted-out
  role, missing rationale, invalid values, and user-overlay precedence.
- [ ] Sync documentation identifies canonical source as editable and generated
  Claude/Codex files as outputs.
- [ ] Validation language says web capability configuration passed and explicitly
  does not claim live access, runtime enforcement, or behavioral compliance.

### Non-goals

- Live delegated web calls, provider/network tests, or account-entitlement
  checks.
- Per-task technical tool grants or enforcement of the instruction-level use
  rule.
- Automatic browsing because local evidence is missing, stale, or ambiguous.
- Arbitrary HTTP execution, authenticated browsing, credential forwarding, or
  private-network access.
- Changes to non-web tools, role responsibilities, model routing, or runtime
  sandbox policy.
- Editing generated files under `~/.claude`, `~/.codex`, or project runtime
  adapter directories.

### Constraints

- Flow owns semantic capability intent; adapters own runtime-native syntax.
- External content cannot override the task, Flow instructions, local policy,
  or project source of truth.
- An opt-out is a deny, not an omission, and must survive inheritance and
  unrelated customization.
- The Codex mapping must use a documented mode capable of current external
  retrieval; the exact native field and mode are selected and recorded during
  solutioning.
- Configuration-only proof is the approved validation boundary.

### Assumptions

- All Flow agents means all thirteen current manifest agents and future agents
  added to that inventory.
- User-overlay agent replacement remains a supported source mechanism; this
  slice adds no new overlay authoring UX.
- The user accepts standing capability availability as a conscious trade from
  least privilege, with task authorization enforced through generated
  instructions rather than per-invocation technical isolation.

### Open questions

- Which exact shared manifest schema and exception location best preserves an
  opt-out through overlay replacement? Owner: solution lane.
- Which native Codex representation should Flow emit for enabled web research
  (`web_search` mode, `tools.web_search`, or both where supported)? Owner:
  solution lane, validated against official documentation.
- Does the shared policy remain web-specific or establish a small generalized
  capability resolver? Owner: solution lane; avoid generalization unless it
  materially simplifies the accepted requirement.

## Research implications

- Claude source-frontmatter-only edits would create false parity -> define one
  semantic policy and translate it per adapter.
- Codex omitted settings can inherit -> render an explicit disabled value for
  opt-outs.
- User overlays already replace agent entries -> resolve capability after merge
  and test replacement behavior.
- Global access expands the external trust boundary -> generate task-scoped use,
  untrusted-content, and data-disclosure instructions for every enabled role.
- Configuration tests cannot prove runtime behavior -> constrain validation
  claims and retain runtime execution as an explicit non-goal.

## Adversarial review

- Product: Prioritize the narrow global policy, opt-out, adapters, instructions,
  tests, and docs; defer runtime testing and broader browsing controls.
- Requirements: The policy must cover the complete inventory, explicit task
  authorization, edge cases, overlay precedence, and truthful proof language.
- Architecture/capability: Use one semantic default with runtime-native mappings;
  route through solutioning because Codex mode and exception persistence remain
  design decisions.
- Security: Three medium findings are incorporated: task-explicit authorization,
  untrusted external-content/data-disclosure guardrails, and fail-closed opt-out
  behavior. Accepted residual risk is that task-only use is instructional, not a
  per-invocation permission boundary.
- Testability: Configuration integration tests are sufficient for this slice if
  they exercise the real inventory, merge, resolver, and both renderers without
  claiming live access.

## Next lane

- `flow-solution` after explicit engineer approval
- Why: Requirements are stable, but the shared schema, overlay-safe exception
  precedence, and exact native Codex representation need a short explicit design
  decision before implementation planning.
