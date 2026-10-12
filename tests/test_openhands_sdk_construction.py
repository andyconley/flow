"""Pinned SDK construction tests; no model calls or provider authentication."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from openhands_config import select
from openhands_runtime import build_agent, probe

@unittest.skipUnless(probe()["ready"], "isolated pinned SDK required")
class SpecialistConstructionTests(unittest.TestCase):
    def test_repeated_and_different_project_factories_keep_own_profiles(self):
        from openhands.sdk.subagent import get_agent_factory
        keys = []
        with tempfile.TemporaryDirectory() as d:
            for name in ("first", "second"):
                root = Path(d) / name
                (root / ".flow").mkdir(parents=True)
                (root / ".flow/runtime.toml").write_text(f'default_profile="local"\n[profiles.local]\nkind="local"\nmodel="openai/{name}"\nbase_url="http://localhost:8000/v1"\n[roles.lead-developer]\ntools=["task","file_editor"]\nspecialists=["test-engineer"]\n[roles.test-engineer]\nspecialists=["quality-reviewer"]\ntools=["task","file_editor"]\n')
                first = build_agent(select(root, "implement"), root)
                repeated = build_agent(select(root, "implement"), root)
                key = first.agent_context.system_message_suffix.split("subagent_type=")[-1].split()[0]
                keys.append(key)
                child = get_agent_factory(key).factory_func(first.llm)
                self.assertEqual(child.llm.model, f"openai/{name}")
                self.assertIn("quality-reviewer: use task", child.agent_context.system_message_suffix)
                self.assertEqual(first.agent_context.system_message_suffix, repeated.agent_context.system_message_suffix)
            self.assertNotEqual(*keys)

    def test_waiting_resume_preserves_last_outcome(self):
        from argparse import Namespace
        from contextlib import contextmanager
        from types import SimpleNamespace
        from unittest.mock import patch
        from uuid import uuid4
        from openhands.sdk.conversation.state import ConversationExecutionStatus
        import openhands_flow as flow
        import runstate
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / ".flow").mkdir()
            (root / ".flow/runtime.toml").write_text('default_profile="local"\n[profiles.local]\nkind="local"\nmodel="openai/test"\nbase_url="http://localhost:8000/v1"\n')
            (root / "task.md").write_text("Continue after inspecting pending actions")
            args = Namespace(project_root=root, work_id="waiting", stage="define", role=None,
                             profile=None, task_file=Path("task.md"), new_session=False)
            flow.initialize(args)
            payload = runstate.status("waiting", root)
            selection = select(root, "define")
            payload["sessions"] = {"define:business-analyst": {"conversation_id": str(uuid4()),
                "binding": selection.fingerprint(), "response": "previous response", "metrics": {"cost": 0.2}}}
            runstate._write_run("waiting", payload, root)
            @contextmanager
            def waiting(*_, **__):
                yield SimpleNamespace(state=SimpleNamespace(execution_status=ConversationExecutionStatus.WAITING_FOR_CONFIRMATION,
                                                            active_branch=lambda: []))
            with patch("openhands_runtime.conversation", waiting):
                result = flow.execute(args)
            self.assertEqual(result["session"]["response"], "previous response")
            self.assertEqual(result["session"]["metrics"], {"cost": 0.2})
            stored = runstate.status("waiting", root)["sessions"]["define:business-analyst"]
            self.assertEqual(stored["response"], "previous response")

    def test_unavailable_metrics_property_preserves_original_failure_and_outcome(self):
        from argparse import Namespace
        from contextlib import contextmanager
        from types import SimpleNamespace
        from unittest.mock import patch
        from openhands.sdk.conversation.state import ConversationExecutionStatus
        import openhands_flow as flow
        import runstate
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            (root / ".flow").mkdir()
            (root / ".flow/runtime.toml").write_text('default_profile="local"\n[profiles.local]\nkind="local"\nmodel="openai/test"\nbase_url="http://localhost:8000/v1"\n')
            (root / "task.md").write_text("Report continuity when remote metrics are unavailable")
            args = Namespace(project_root=root, work_id="metrics-failure", stage="define", role=None,
                             profile=None, task_file=Path("task.md"), new_session=False)
            flow.initialize(args)
            class Session:
                state = SimpleNamespace(execution_status=ConversationExecutionStatus.FINISHED)
                def send_message(self, *_):
                    pass
                def run(self):
                    raise RuntimeError("original execution failure")
                @property
                def conversation_stats(self):
                    raise ConnectionError("metrics endpoint unavailable")
            @contextmanager
            def unavailable(*_, **__):
                yield Session()
            with patch("openhands_runtime.conversation", unavailable):
                with self.assertRaisesRegex(RuntimeError, "original execution failure"):
                    flow.execute(args)
            stored = runstate.status(args.work_id, root)["sessions"]["define:business-analyst"]
            self.assertEqual(stored["status"], "error")
            self.assertEqual(stored["error_type"], "RuntimeError")
            self.assertEqual(stored["metrics_error_type"], "ConnectionError")
            self.assertIn("elapsed_seconds", stored)
            self.assertTrue((root / ".flow/runs/metrics-failure/define-business-analyst-outcome.json").exists())

    def test_configured_effective_context_controls_sdk_and_summary_headroom(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".flow").mkdir()
            (root / ".flow/runtime.toml").write_text('default_profile="local"\n[profiles.local]\nkind="local"\nmodel="openai/test"\nbase_url="http://localhost:8000/v1"\nmax_input_tokens=65536\nmax_output_tokens=8192\ncondenser_max_tokens=57344\n')
            agent = build_agent(select(root, "define"), root)
            self.assertEqual(agent.llm.effective_max_input_tokens, 65536)
            self.assertEqual(agent.llm.effective_max_output_tokens, 8192)
            self.assertEqual(agent.condenser._effective_max_tokens(agent.llm), 57344)
