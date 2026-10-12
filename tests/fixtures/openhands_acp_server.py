"""Deterministic ACP peer for testing the stock SDK bridge, never a runtime provider."""
import asyncio
from pathlib import Path
from acp import run_agent
from acp.schema import (InitializeResponse, Implementation, AgentCapabilities,
    NewSessionResponse, LoadSessionResponse, SessionModeState, SessionMode,
    SetSessionModeResponse, PromptResponse, ToolCallUpdate, PermissionOption,
    AgentMessageChunk, TextContentBlock)

class FixtureAgent:
    def on_connect(self, connection):
        self.connection = connection
        self.mode = "default"
    async def initialize(self, protocol_version, client_capabilities=None, client_info=None, **kwargs):
        return InitializeResponse(protocol_version=protocol_version,
            agent_info=Implementation(name="flow-acp-fixture", version="1.0"),
            agent_capabilities=AgentCapabilities(load_session=True), auth_methods=[])
    def modes(self):
        return SessionModeState(current_mode_id=self.mode,
            available_modes=[SessionMode(id=m, name=m) for m in ("agent", "default", "plan", "read-only")])
    async def new_session(self, cwd, mcp_servers=None, **kwargs):
        self.cwd = Path(cwd)
        return NewSessionResponse(session_id="fixture-session", modes=self.modes())
    async def load_session(self, cwd, session_id, mcp_servers=None, **kwargs):
        self.cwd = Path(cwd)
        return LoadSessionResponse(modes=self.modes())
    async def set_session_mode(self, session_id, mode_id, **kwargs):
        assert mode_id in ("agent", "default", "plan", "read-only")
        self.mode = mode_id
        return SetSessionModeResponse()
    async def prompt(self, session_id, prompt, **kwargs):
        try:
            permission = await self.connection.request_permission(session_id=session_id,
                tool_call=ToolCallUpdate(tool_call_id="fixture-edit", title="Write disposable fixture proof", kind="edit", status="pending"),
                options=[PermissionOption(option_id="allow-once", name="Allow once", kind="allow_once"),
                         PermissionOption(option_id="reject-once", name="Reject once", kind="reject_once")])
            assert permission.outcome.option_id == "allow-once"
            target = self.cwd / "native-fixture-proof.txt"
            count = int(target.read_text()) + 1 if target.exists() else 1
            target.write_text(str(count))
            (self.cwd / "fixture-mode.txt").write_text(self.mode)
            await self.connection.session_update(session_id=session_id,
                update=AgentMessageChunk(session_update="agent_message_chunk", content=TextContentBlock(type="text", text=f"Fixture mode={self.mode}; stock SDK auto-approved allow-once; turn={count}")))
            return PromptResponse(stop_reason="end_turn")
        except Exception:
            import traceback
            traceback.print_exc()
            raise
    async def cancel(self, session_id, **kwargs):
        return None
    async def authenticate(self, method_id, **kwargs):
        raise AssertionError("fixture must never authenticate")

if __name__ == "__main__":
    asyncio.run(run_agent(FixtureAgent()))
