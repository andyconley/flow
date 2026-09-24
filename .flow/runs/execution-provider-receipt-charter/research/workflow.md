# Business-analyst role review

Evidence inventory: `scaffolds/default/standards/orchestration.md`, `cli/orchestration.py`, `cli/runstate.py`, `scaffolds/default/templates/agent-brief.md`, `.flow/PROJECT.md`. Archive retrieval returned no matches.

Observed: Flow checks declared capabilities, output artifact presence, reconciliation status, and claim provenance. It does not inspect artifact contents or prove the worker followed its brief.

Recommendation: An operator should be able to dispatch only confirmed capability, identify a unique attempt, compare its receipt with repository evidence, and decide accept/rework/escalate without worker chat. Include explicit partial/failed/interrupted outcomes and missing-validation reasons. Preserve observed/inferred/recommended/unverified claims.

Challenges and dispositions: The draft distinguishes terminal outcomes and makes unsuccessful/no-commit attempts diagnostic rather than successful handback. Exact serialization and retry mechanics remain solution/future work. Tests should cover completed, partial, unconfirmed capability, missing/mismatched evidence, and unauthorized changes.
