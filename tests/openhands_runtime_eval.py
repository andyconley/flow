"""Deterministic self-hosted endpoint exercises actual SDK tools and persistence.

Not a model benchmark. No production provider, authentication, or run is used.
Run with the isolated OpenHands Python environment.
"""
import json
import os
import re
import sys
import tempfile
import threading
from argparse import Namespace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from openhands_config import OUTPUTS
import openhands_flow as flow
import runstate


class Endpoint(BaseHTTPRequestHandler):
    calls = []
    def log_message(self, *args):
        pass
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append(request)
        # Extract only the latest Flow task. Resume keeps prior SDK messages.
        text = next(m["content"] for m in reversed(request["messages"]) if m["role"] == "user")
        if isinstance(text, list):
            text = "\n".join(part.get("text", "") for part in text)
        paths = re.findall(r"^- \w+: (\.flow/runs/[^\n]+\.md)$", text, re.M)
        tool = next(t["function"]["name"] for t in request["tools"] if "editor" in t["function"]["name"].lower())
        root = Path(re.search(r"Project workspace: (.+)", text).group(1))
        pending = [root / p for p in paths if not (root / p).exists()]
        # Real SDK file editor creates files; our endpoint supplies model replies.
        if pending:
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": f"call_{len(self.calls)}", "type": "function", "function": {"name": tool, "arguments": json.dumps({"command": "create", "path": str(pending[0]), "file_text": "Verified SDK stage artifact.\n"})}}]}
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": "Stage complete; outputs written with the SDK file editor."}
            finish = "stop"
        response = {"id": f"flow_eval_{len(self.calls)}", "object": "chat.completion", "created": 1, "model": "flow-test-coder", "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}}
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Endpoint)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / ".flow").mkdir()
            (root / ".flow/runtime.toml").write_text(f'default_profile="test"\n[profiles.test]\nkind="local"\nmodel="openai/flow-test-coder"\nbase_url="http://127.0.0.1:{server.server_port}/v1"\n[roles.business-analyst]\ntools=["file_editor"]\n[roles.solution-architect]\ntools=["file_editor"]\n[roles.lead-developer]\ntools=["file_editor"]\n[roles.quality-reviewer]\ntools=["file_editor"]\n')
            (root / "task.md").write_text("Produce this stage's outputs with your file editor tool.")
            args = Namespace(project_root=root, work_id="sdk-evaluation", stage="define", role=None, profile=None, task_file=Path("task.md"), new_session=False, disposition=[])
            flow.initialize(args)
            result = flow.execute(args)
            assert result["session"]["status"] == "finished", result
            original_id = result["session"]["conversation_id"]
            resumed = flow.execute(args)
            assert resumed["session"]["conversation_id"] == original_id
            for stage in ("define", "solution", "plan", "implement", "review"):
                args.stage = stage
                if stage != "define":
                    result = flow.execute(args)
                    assert result["session"]["status"] == "finished", result
                args.disposition = ["risk=accepted"] if stage == "solution" else []
                flow.approve(args)
            args.disposition = ["memory=recorded", "capability_gaps=none"]
            flow.archive(args)
            assert runstate.verify(args.work_id, root)[0]
            # The SDK confirmation policy must not be silently approved by a
            # normal Flow continuation. Explicit confirmation uses SDK run().
            args.work_id = "sdk-confirmation"
            args.stage = "define"
            args.disposition = []
            runtime_file = root / ".flow/runtime.toml"
            runtime_file.write_text(runtime_file.read_text() + '\n[workspace]\nkind="local"\nconfirmation="always"\n')
            flow.initialize(args)
            pending = flow.execute(args)
            assert pending["session"]["status"] == "waiting_for_confirmation", pending
            assert pending["session"]["pending_actions"]
            output = root / ".flow/runs/sdk-confirmation/requirements.md"
            assert not output.exists(), "unconfirmed SDK action executed"
            calls_before = len(Endpoint.calls)
            pending_again = flow.execute(args)
            assert pending_again["session"]["status"] == "waiting_for_confirmation"
            assert len(Endpoint.calls) == calls_before, "unconfirmed continuation ran a model/tool"
            args.confirm_pending = True
            for _ in range(4):
                confirmed = flow.execute(args)
                if confirmed["session"]["status"] == "finished":
                    break
            assert output.exists() and confirmed["session"]["status"] == "finished", confirmed
            assert len(Endpoint.calls) > 10
            persistence = root / ".flow/runs/sdk-evaluation/openhands"
            assert list(persistence.rglob("base_state.json")), "SDK persistence missing"
            print(json.dumps({"status": "passed", "runtime": "OpenHands 1.54.0", "stages": list(OUTPUTS), "resume_same_id": True, "endpoint_calls": len(Endpoint.calls), "real_sdk_file_tools": True, "archived": True, "sdk_confirmation_preserved": True}))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
