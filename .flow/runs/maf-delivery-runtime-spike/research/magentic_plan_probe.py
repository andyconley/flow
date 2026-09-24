"""Local Magentic manager plan-review probe; no worker dispatch."""

from __future__ import annotations

import asyncio
import json

from agent_framework import Agent
from agent_framework_ollama import OllamaChatClient
from agent_framework_orchestrations import MagenticBuilder, MagenticPlanReviewRequest


async def main() -> None:
    client = OllamaChatClient(model="llama3.1:8b")
    manager = Agent(client=client, id="local-manager", name="manager", instructions="Plan a tiny bounded read-only task. Delegate to at most two named specialists.")
    developer = Agent(client=client, id="developer-1", name="developer", description="Reads a file and reports its content.")
    tester = Agent(client=client, id="tester-1", name="tester", description="Checks the developer's answer.")
    workflow = MagenticBuilder(participants=[developer, tester], manager_agent=manager, enable_plan_review=True, max_round_count=2, max_reset_count=0, name="flow-magentic-plan-probe").build()
    result = await asyncio.wait_for(workflow.run("Read a one-line README and verify the answer. Plan first, then wait for Flow approval."), timeout=120)
    requests = result.get_request_info_events()
    assert len(requests) == 1
    request = requests[0].data
    assert isinstance(request, MagenticPlanReviewRequest)
    plan_text = request.plan.text
    print(json.dumps({"manager": "ollama:llama3.1:8b", "plan_review_pending": True, "plan_chars": len(plan_text), "worker_dispatches": 0, "flow_approval_given": False, "max_round_count": 2, "max_reset_count": 0}, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
