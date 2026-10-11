"""Real SDK ACP transport/resume/mode test with a disposable protocol peer.

This is not live native-provider acceptance; no subscription or credentials are used.
"""
import json
import os
import sys
import tempfile
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
import openhands_flow as flow
import openhands_runtime as runtime


def main():
    fixture = Path(__file__).resolve().parent / "fixtures/openhands_acp_server.py"
    spec = SimpleNamespace(npx_command=lambda: (sys.executable, str(fixture)))
    original = runtime.build_native_agent
    def bounded(selection, root):
        agent = original(selection, root)
        return agent.model_copy(update={"acp_prompt_timeout": 5})
    with patch.object(runtime, "build_native_agent", side_effect=bounded), patch('openhands.sdk.settings.acp_install_catalog.ACP_INSTALL_CATALOG', {"codex": spec, "claude-code": spec}):
        for kind, expected_mode in (("codex", "agent"), ("claude", "default")):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                (root / ".flow").mkdir()
                (root / ".flow/runtime.toml").write_text(f'default_profile="native"\n[profiles.native]\nkind="{kind}"\npermission_requests="stock-openhands"\n')
                (root / "task.md").write_text("Run only the disposable fixture proof operation.")
                args = Namespace(project_root=root, work_id="acp-test", stage="define", role=None, profile=None,
                                 task_file=Path("task.md"), new_session=False, disposition=[])
                flow.initialize(args)
                first = flow.execute(args)
                assert first["session"]["status"] == "finished", first
                assert (root / "fixture-mode.txt").read_text() == expected_mode, first
                assert f"mode={expected_mode}" in first["session"]["response"], first
                second = flow.execute(args)
                assert second["session"]["conversation_id"] == first["session"]["conversation_id"]
                assert (root / "native-fixture-proof.txt").read_text() == "2"
    print(json.dumps({"status": "passed", "stock_sdk_acp_transport": True, "providers": ["codex", "claude"],
                      "explicit_modes": ["agent", "default"], "resume": True, "credential_copy": False,
                      "live_native_validation": "pending_access_decision"}))

if __name__ == "__main__":
    main()
