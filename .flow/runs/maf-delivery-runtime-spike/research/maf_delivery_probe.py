"""Bounded, model-free MAF orchestration probe against Flow specialist files."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Never

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentResponse,
    Executor,
    Message,
    WorkflowContext,
    handler,
)
from agent_framework_orchestrations import ConcurrentBuilder


ROOT = Path(__file__).resolve().parents[4]
AGENTS = ROOT / "scaffolds/default/agents"
ENVELOPE = {
    "max_delegations": 6,
    "max_concurrent": 3,
    "max_replans": 2,
    "allowed_specialists": ["lead-developer", "test-engineer", "quality-reviewer"],
}


def authorize(roles: list[str], replans: int = 0) -> None:
    if len(roles) > ENVELOPE["max_delegations"]:
        raise ValueError("delegation cap")
    if len(roles) > ENVELOPE["max_concurrent"]:
        raise ValueError("concurrency cap")
    if replans > ENVELOPE["max_replans"]:
        raise ValueError("replan cap")
    if any(role not in ENVELOPE["allowed_specialists"] for role in roles):
        raise ValueError("specialist denied")


class StubSpecialist(Executor):
    def __init__(self, role: str, provider: str) -> None:
        super().__init__(id=role)
        self.role = role
        self.provider = provider

    @handler
    async def work(
        self,
        request: AgentExecutorRequest,
        ctx: WorkflowContext[Never, AgentExecutorResponse],
    ) -> None:
        assert request.should_respond
        source = AGENTS / f"{self.role}.md"
        definition = source.read_bytes()
        response = AgentResponse(messages=Message(role="assistant", contents=[self.role]), agent_id=self.role)
        await ctx.send_message(
            AgentExecutorResponse(
                executor_id=self.id,
                agent_response=response,
                full_conversation=request.messages + response.messages,
            )
        )


async def main() -> None:
    roles = ["lead-developer", "test-engineer", "quality-reviewer"]
    providers = ["codex-stub", "claude-stub", "ollama-stub"]
    authorize(roles)
    denials = {}
    for case, candidate, replans in [
        ("delegations", roles * 3, 0),
        ("concurrent", roles + [roles[0]], 0),
        ("replans", roles, 3),
        ("specialist", ["security-reviewer"], 0),
    ]:
        try:
            authorize(candidate, replans)
        except ValueError as exc:
            denials[case] = str(exc)
    assert len(denials) == 4
    specialists = [StubSpecialist(role, provider) for role, provider in zip(roles, providers)]
    workflow = ConcurrentBuilder(participants=specialists, name="flow-maf-delivery-probe").build()
    result = await workflow.run("bounded charter")
    output = result.get_outputs()
    assert len(output) == 1
    assert [message.text for message in output[0].messages] == roles
    print(json.dumps({
        "specialists": [
            {"role": role, "provider": provider, "definition_sha256": hashlib.sha256((AGENTS / f"{role}.md").read_bytes()).hexdigest()}
            for role, provider in zip(roles, providers)
        ],
        "definitions_available": len(list(AGENTS.glob("*.md"))),
        "outputs": [message.text for message in output[0].messages],
        "flow_denials": denials,
        "model_calls": 0,
        "provider_calls": 0,
        "receipt_independently_verified": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
