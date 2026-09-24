# Research: Does Microsoft routing change the first execution contract?

- Owner role: coordinator
- Date: 2026-09-19
- Confidence: High for cited product behavior; medium for Flow fit, which still needs a later design/evaluation

## Question

What should the first execution contract preserve for a later Microsoft or equivalent model router?

## Method and sources

- Microsoft Foundry Model Router documentation: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router
- Microsoft Foundry Model Router concepts: https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-router-how-it-works
- Microsoft Agent Framework runtime routing: https://learn.microsoft.com/en-us/agent-framework/concepts/agents/runtime-model-routing
- Flow's historical `docs/agent-model-routing-research.md` and current `flow.toml` semantic tiers.

## Findings

- Foundry Model Router selects an eligible underlying model for a request from a configured pool. Its response can identify the underlying model. Model/tool compatibility and the deployed subset constrain eligibility. This is model selection within Foundry, not Flow worker dispatch or worktree evidence.
- Microsoft Agent Framework describes routing between inference providers when the caller manages conversation history. Service-managed opaque conversation IDs limit portability. Its cited routing client is experimental and currently .NET-only.
- Flow already has semantic model tiers and native Claude/Codex agent mappings, but the current execution definition has no general assignment-level router.

## Implication for requirements

- Keep provider identity, router/deployment, requested profile/model, and observed underlying model distinct. Record unknown when the actual model is unavailable.
- Do not add Foundry or Agent Framework as a dependency of the first Codex worker path. Evaluate them, and local Ollama routing, after the single-worker execution receipt works.

## Open follow-ups

- Later routing design: evaluate portability, tool compatibility, privacy, cost, model eligibility, and per-assignment observability against Flow's local-first goal.
