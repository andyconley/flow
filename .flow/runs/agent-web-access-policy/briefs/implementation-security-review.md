# Brief: Implementation Security Review

## Review question

Does the implementation safely expand web capability while preserving explicit
authorization, disclosure, untrusted-content, opt-out, overlay, and pre-write
failure boundaries?

## Evidence inventory

### Requirements and design

- `.flow/runs/agent-web-access-policy/requirements.md`
- `.flow/runs/agent-web-access-policy/acceptance-criteria.md`
- `.flow/runs/agent-web-access-policy/solution.md`
- `.flow/runs/agent-web-access-policy/plan.md`
- `.flow/runs/agent-web-access-policy/validation-plan.md`

### Implementation

- `cli/agent_capabilities.py`
- `cli/sync.py`
- `cli/render.py`
- `scaffolds/default/flow.toml`
- `scaffolds/default/agents/solution-architect.md`

### Proof and documentation

- `tests/test_agent_capabilities.py`
- `tests/test_flow.py`
- `docs/adr/0003-semantic-agent-capabilities.md`
- `docs/runtime-adapters.md`
- `docs/architecture.md`

## Required output

Write `.flow/runs/agent-web-access-policy/reviews/security.md`. Classify every
finding, identify evidence paths/lines, state release impact, and distinguish
verified configuration behavior from unverified runtime behavior. Do not edit
implementation files.
