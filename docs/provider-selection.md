# Provider selection policy

Flow protocol v9 separates shaping from delivery binding. Shaper artifacts state
logical operation, tier, capabilities, locality, limits, risk, and independence;
they do not select a provider, model, candidate, or ranked roster.

## Authority and precedence

| Field | Merge rule | Lower-layer authority |
|---|---|---|
| candidate allowlist | intersection | narrow only |
| disabled candidates | union | disable only |
| byte, token, and cost ceilings | minimum | lower only |
| provider preference | deterministic order | reorder surviving hosted providers; Ollama remains first |
| adapter operations and capabilities | code/framework ceiling | none |
| provider family | catalog fact | none |
| independence waiver | absent by default | approved run amendment with sealed user approval only |

Framework policy is followed by administrator, project, and approved run policy.
The result records field provenance and a canonical digest. Mere presence in
Ollama `/api/tags` never grants a capability.

## Selection order

The selector excludes candidates using controlled reason codes, then assigns a
total rank tuple to every survivor. A qualifying local Ollama candidate comes
first. Hosted candidates follow the configured order, Claude then Codex by
default, followed by cost class and stable candidate ID. Input ordering has no
effect on canonical output or the decision digest.

Unknown, stale, or unavailable readiness is ineligible. Previous candidates may
be excluded only by positive no-send evidence. Provider-family filtering occurs
after base eligibility for high-risk verification.

## Compatibility

Protocol v8 retains its concrete roster, provider choice, receipts, inspection,
resume, and recovery behavior. Protocol v9 selection types and evidence are
additive; v8 records are not migrated or interpreted through v9 policy.
