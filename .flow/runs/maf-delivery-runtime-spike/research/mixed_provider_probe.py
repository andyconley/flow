"""Historical mixed-provider prototype; do not rerun without a Codex cost guard.

The recorded run preceded review. This source preserves what ran but its Codex
subscription path cannot enforce the run's dollar cap. The entry point now
fails closed until that boundary is implemented and reviewed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Never

from agent_framework import Agent, AgentExecutorRequest, AgentExecutorResponse, AgentResponse, Executor, Message, WorkflowContext, handler
from agent_framework_ollama import OllamaChatClient
from agent_framework_orchestrations import ConcurrentBuilder
from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox


ROOT = Path(__file__).resolve().parents[4]
FIXTURE = Path("/private/tmp/flow-maf-live-20260919")
ROLES = ("lead-developer", "quality-reviewer", "test-engineer")
CHARter = "Read-only proof. Answer with only your provider name followed by -ready. No edits, delegation, or tool use beyond reading README.md."


def definition(role: str) -> str:
    return (ROOT / "scaffolds/default/agents" / f"{role}.md").read_text()


def codex_call() -> dict[str, object]:
    with Codex(CodexConfig(cwd=str(FIXTURE))) as client:
        if client.account().account.root.type != "chatgpt":
            raise RuntimeError("Codex is not using ChatGPT sign-in")
        thread = client.thread_start(
            ephemeral=True,
            cwd=str(FIXTURE),
            sandbox=Sandbox.read_only,
            approval_mode=ApprovalMode.deny_all,
            base_instructions=definition(ROLES[0]) + "\n" + CHARter,
        )
        turn = thread.turn(
            "Read README.md. Reply with exactly codex-ready.",
            sandbox=Sandbox.read_only,
            approval_mode=ApprovalMode.deny_all,
        ).run()
        return {"provider": "codex", "session_id": thread.id, "turn_id": turn.id, "status": str(turn.status), "item_count": len(turn.items), "usage": str(turn.usage)[:240], "error": bool(turn.error)}


def claude_call() -> dict[str, object]:
    command = [
        "claude", "-p", "Read README.md. Reply with exactly claude-ready.",
        "--output-format", "json", "--max-budget-usd", "3", "--no-session-persistence",
        "--tools", "Read", "--permission-mode", "dontAsk",
        "--append-system-prompt", definition(ROLES[1]) + "\n" + CHARter,
    ]
    process = subprocess.run(command, cwd=FIXTURE, capture_output=True, text=True, timeout=120)
    result = json.loads(process.stdout)
    if process.returncode or result.get("is_error"):
        raise RuntimeError("Claude provider failed")
    return {"provider": "claude", "session_id": result.get("session_id"), "cost_usd": result.get("total_cost_usd"), "turns": result.get("num_turns"), "answer_matches": result.get("result", "").strip() == "claude-ready"}


async def ollama_call() -> dict[str, object]:
    agent = Agent(client=OllamaChatClient(model="llama3.1:8b"), id="flow-test-engineer-1", name="test-engineer", instructions=definition(ROLES[2]) + "\n" + CHARter)
    result = await asyncio.wait_for(agent.run("Reply with exactly ollama-ready."), timeout=90)
    return {"provider": "ollama", "agent_id": agent.id, "model": "llama3.1:8b", "answer_matches": result.text.strip() == "ollama-ready"}


class ProviderExecutor(Executor):
    def __init__(self, provider: str, role: str) -> None:
        super().__init__(id=f"{provider}-{role}-1")
        self.provider = provider
        self.role = role
        self.result: dict[str, object] | None = None

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        assert request.should_respond
        if self.provider == "codex":
            self.result = await asyncio.to_thread(codex_call)
        elif self.provider == "claude":
            self.result = await asyncio.to_thread(claude_call)
        else:
            self.result = await ollama_call()
        response = AgentResponse(messages=Message(role="assistant", contents=[self.provider + "-complete"]), agent_id=self.id)
        await ctx.send_message(AgentExecutorResponse(executor_id=self.id, agent_response=response, full_conversation=request.messages + response.messages))


async def main() -> None:
    participants = [ProviderExecutor(provider, role) for provider, role in zip(("codex", "claude", "ollama"), ROLES)]
    assert len(participants) <= 3 and len(participants) <= 6
    workflow = ConcurrentBuilder(participants=participants, name="flow-maf-mixed-providers").build()
    result = await asyncio.wait_for(workflow.run(CHARter), timeout=150)
    outputs = result.get_outputs()
    assert len(outputs) == 1
    print(json.dumps({
        "workflow": workflow.name,
        "output_roles": [message.text for message in outputs[0].messages],
        "workers": [participant.result for participant in participants],
        "definition_sha256": {role: hashlib.sha256(definition(role).encode()).hexdigest() for role in ROLES},
        "charter_sha256": hashlib.sha256(CHARter.encode()).hexdigest(),
        "initial_dispatch_authorized": True,
        "runtime_delegation_tested": False,
        "checkpoint_in_this_workflow": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit("Disabled: Codex spend cannot be capped or accounted for under this spike's $10 rule")
