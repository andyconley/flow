# Brief: Implementation Architecture and Quality Review

## Review question

Does the implementation match the approved capability boundary, overlay
precedence, native mappings, compatibility contract, acceptance criteria, and
release-ready evidence standard?

## Evidence inventory

### Requirements and plan

- `.flow/runs/agent-web-access-policy/requirements.md`
- `.flow/runs/agent-web-access-policy/acceptance-criteria.md`
- `.flow/runs/agent-web-access-policy/solution.md`
- `.flow/runs/agent-web-access-policy/plan.md`
- `.flow/runs/agent-web-access-policy/implementation-handoff.md`
- `.flow/runs/agent-web-access-policy/validation-plan.md`

### Changed product surface

- `cli/agent_capabilities.py`
- `cli/sync.py`
- `cli/render.py`
- `scaffolds/default/flow.toml`
- `scaffolds/default/agents/solution-architect.md`
- `tests/test_agent_capabilities.py`
- `tests/test_flow.py`
- `docs/adr/0003-semantic-agent-capabilities.md`
- `docs/runtime-adapters.md`
- `docs/architecture.md`

## Required output

Write `.flow/runs/agent-web-access-policy/reviews/quality.md`. Report findings
by severity with exact evidence, acceptance traceability, and a release verdict.
Do not edit implementation files.
