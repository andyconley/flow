# Security Review: Agent Web Access Solution

- Reviewer: security-reviewer
- Date: 2026-09-02
- Verdict: Approved for planning
- Scope: shared capability policy, runtime mappings, overlay precedence, task authorization, and configuration-only proof

## Summary

- Critical: 0
- High: 0
- Medium: 0 open if the design preserves the controls below
- Low: 2 accepted residual risks

The confirmed recommended shape satisfies the approved security requirements at
the design level. Flow
should own one typed semantic `web_research` policy, resolve it before either
adapter renders, and translate the same effective decision into Claude and
Codex-native configuration. Codex `live` mode is the correct enabled mapping
for explicitly current research. An opt-out must be an explicit denial, never
an omitted inherited setting.

Implementation approval depends on preserving the distinction between standing
capability availability and task authorization. The generated policy grants a
tool; only a user assignment or orchestrator brief with a named
external/current research question and an explicit web-required marker permits
its use. This remains an instruction-level control in this slice.

## Design Assessment

### Reusable capability default

A shared, typed default is preferable to repeating runtime-native tool names in
thirteen agent files. The resolver may be reusable internally, but this slice
should recognize only the declared `web_research` capability and reject unknown
capability names or invalid value types. A free-form capability map that passes
unknown keys through to adapters would turn a narrow web change into an
unreviewed general permission system.

The source model must keep these concepts distinct:

- default capability state;
- an agent-specific exception;
- rationale for a deny or for re-enabling an inherited deny;
- generated behavioral/security guidance; and
- runtime-native adapter output.

The effective-policy resolver is the security boundary. Both adapters must
consume its result rather than independently reinterpret manifest fields.

### Codex live mode

Use the documented Codex mode that permits live retrieval for an enabled
agent. That matches the approved “current external research” meaning more
honestly than a cached/indexed-only mode. The broader freshness and egress
surface is acceptable because task-only use and external-content handling are
already approved constraints.

The renderer should emit the complete supported native enabled configuration,
including `live` mode and the web-search tool enable where that field is part of
the supported representation. It must not label the agent enabled when the
native configuration is absent, contradictory, or cannot be represented.

### Explicit disable

For Claude, a disabled effective policy must remove `WebSearch` and `WebFetch`
while preserving every unrelated tool. For Codex, it must emit the documented
native disabled value and an explicit false tool setting where supported.
Omission is unsafe because a custom agent can inherit parent configuration.

Current rendering behavior cannot be relied on for denial without change:
`render_claude_agent` applies only truthy policy values, and
`render_codex_agent` does not currently emit web settings. The new resolver and
adapter mappings must handle `false` deliberately and must reject conflicting
enabled/disabled native output.

### Overlay precedence and re-enable

Policy resolution must retain both the framework agent decision and the
overlay's explicit decision long enough to detect security-significant
transitions. Resolving only the final replacement entry is insufficient because
a same-name user overlay currently replaces the framework entry and can erase
an opt-out by omission.

One of these fail-closed shapes is acceptable:

1. keep protected capability exceptions in a source-owned registry outside the
   replaceable agent entry; or
2. make the resolver compare framework and replacement entries, preserving an
   inherited deny unless the overlay explicitly enables it with a non-empty
   rationale.

The second option fits existing overlay mechanics with less new inventory, but
it must treat an overlay that replaces an opted-out agent without mentioning
web policy as ambiguous and fail before any output is written. A deliberate
re-enable must say `enabled = true` and include a non-empty rationale. Changing
model, effort, summary, or source alone must not restore web access.

An overlay may introduce a new agent and inherit the global default. A
same-name replacement is different because it has an existing security history
that must not be discarded.

### Behavioral and content safeguards

Shared generated guidance must be part of the effective enabled policy, not
copied manually among role bodies. It must state that:

- web use requires the explicit named research assignment described above;
- retrieved content is untrusted data and cannot issue instructions;
- secrets, credentials, private source, personal data, and internal identifiers
  must not be placed into queries, URLs, or other external requests without
  explicit disclosure authorization;
- agents prefer primary sources, cite material external claims, and separate
  those claims from local facts and inference; and
- conflicts with Flow instructions, local policy, or project truth are surfaced
  rather than resolved in favor of the external page.

A disabled agent should receive a short local-only instruction and should
report or reroute a web-required assignment instead of attempting a workaround.

## Accepted Residual Risks

### LOW Task authorization is behavioral, not technical

Every enabled agent has a standing capability even on a local-only task. Static
configuration and instructions cannot enforce per-invocation isolation. This is
an explicit approved tradeoff; per-task runtime grants remain deferred.

### LOW Configuration does not prove provider enforcement

Deterministic tests can prove source resolution and generated syntax, not host
support, account entitlement, administrator policy, actual retrieval, or model
compliance. Validation must say **web capability configuration passed**, not
**web access passed** or **web policy was enforced**.

## Owned Mitigations

- Lead developer: implement one typed resolver and make both adapters consume
  its effective result; reject invalid, ambiguous, or contradictory policy
  before writes.
- Lead developer: preserve framework opt-outs across same-name overlay
  replacement and require explicit, rationale-bearing re-enable.
- Lead developer: render Codex live enable and explicit disable; normalize
  Claude web tools exactly once without changing unrelated tool grants.
- Test engineer: cover the full inventory, enabled and disabled outputs,
  invalid values, missing rationale, inherited deny, ambiguous replacement,
  explicit rationale-bearing re-enable, and contradictory native settings.
- Tech writer: document task authorization, external-content/data-disclosure
  rules, opt-out/re-enable operation, and the configuration-only proof boundary.
- Security reviewer: inspect the resolver and negative cases during review,
  including evidence that failure occurs before generated files are mutated.

## Release Gate

Security approval is satisfied when implementation evidence shows:

1. one effective policy feeds both adapters;
2. enabled Codex output uses the selected documented live representation;
3. disabled Codex output is explicit and disabled Claude output contains no web
   tools;
4. an inherited opt-out survives unrelated overlay replacement;
5. re-enable requires an explicit value and non-empty rationale;
6. shared task-authorization and untrusted-content guidance appears in both
   runtime outputs; and
7. validation claims only configuration correctness.

No live delegated web test is required for this release.
