"""Focused bounds and completion checks for the installed Codex adapter."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from codex_worker import CodexWorkerError, _parse_events, call_codex


def stream(*events):
    return ("\n".join(json.dumps(item) for item in events) + "\n").encode()


class CodexWorkerTests(unittest.TestCase):
    def test_completed_turn_normalized(self):
        result = _parse_events(stream(
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}},
            {"type": "turn.completed", "usage": {"input_tokens": 8, "output_tokens": 2}},
        ), "gpt-test")
        self.assertEqual(result["output"], "Done")
        self.assertEqual(result["thread_id"], "thread-1")
        self.assertEqual(result["usage"]["output_tokens"], 2)

    def test_incomplete_or_ambiguous_turn_rejected(self):
        cases = [
            stream({"type": "thread.started", "thread_id": "thread-1"}),
            stream({"type": "turn.completed"}),
            stream({"type": "thread.started", "thread_id": "thread-1"},
                   {"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}},
                   {"type": "turn.failed"}, {"type": "turn.completed"}),
            b"not json\n",
        ]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(CodexWorkerError):
                _parse_events(raw, "gpt-test")

    def test_invocation_is_sandboxed_and_one_turn(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "fixture"
            workspace.mkdir()
            fake = root / "codex-fake"
            fake.write_text("#!/usr/bin/env python3\n"
                            "import json, os, sys\n"
                            "from pathlib import Path\n"
                            "Path('argv.json').write_text(json.dumps(sys.argv[1:]))\n"
                            "Path('prompt.txt').write_text(sys.stdin.read())\n"
                            "Path('env.json').write_text(json.dumps(dict(os.environ)))\n"
                            "print(json.dumps({'type':'thread.started','thread_id':'test-thread'}))\n"
                            "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'changed fixture'}}))\n"
                            "print(json.dumps({'type':'turn.completed','usage':{'input_tokens':5}}))\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"FLOW_UNRELATED_SECRET": "do-not-pass",
                                        "OPENAI_API_KEY": "do-not-pass",
                                        "CODEX_API_KEY": "do-not-pass"}):
                result = call_codex(instructions="Follow charter", task="Make a tiny change",
                                    workspace=workspace, model="gpt-test", timeout_seconds=5,
                                    codex_bin=str(fake))
            argv = json.loads((workspace / "argv.json").read_text())
            child_env = json.loads((workspace / "env.json").read_text())
            self.assertEqual(result["output"], "changed fixture")
            self.assertIn("workspace-write", argv)
            self.assertIn("--ignore-user-config", argv)
            self.assertIn("--ephemeral", argv)
            self.assertIn("features.multi_agent=false", argv)
            self.assertEqual(argv[-1], "-")
            self.assertIn("Follow charter", (workspace / "prompt.txt").read_text())
            self.assertNotIn("FLOW_UNRELATED_SECRET", child_env)
            self.assertNotIn("OPENAI_API_KEY", child_env)
            self.assertNotIn("CODEX_API_KEY", child_env)
            self.assertIn("HOME", child_env)
            self.assertEqual(child_env["PYTHONDONTWRITEBYTECODE"], "1")

    def test_timeout_is_uncertain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "codex-fake"
            fake.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(4)\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with self.assertRaisesRegex(CodexWorkerError, "timed out"):
                call_codex(instructions="Charter", task="Task", workspace=root,
                           model="gpt-test", timeout_seconds=1, codex_bin=str(fake))


if __name__ == "__main__":
    unittest.main()
