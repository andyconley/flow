"""Guarded editing adapter invocation and terminal result checks."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from claude_edit_worker import ClaudeEditError, _result, call_claude_edit


class ClaudeEditWorkerTests(unittest.TestCase):
    def test_result_rejects_failed_and_overbound_turns(self):
        good = {"type": "result", "subtype": "success", "is_error": False,
                "result": "Edited two files.", "session_id": "one", "num_turns": 2,
                "usage": {"input_tokens": 3}}
        self.assertEqual(_result(json.dumps(good).encode(), "claude-test")["num_turns"], 2)
        for change in ({"is_error": True}, {"num_turns": 9}, {"session_id": ""},
                       {"result": "x" * 9000}):
            with self.subTest(change=change), self.assertRaises(ClaudeEditError):
                _result(json.dumps({**good, **change}).encode(), "claude-test")

    def test_cli_has_only_file_tools_and_no_ambient_secret(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\n"
                            "import json, os, sys\n"
                            "from pathlib import Path\n"
                            "Path('argv.json').write_text(json.dumps(sys.argv[1:]))\n"
                            "Path('env.json').write_text(json.dumps(dict(os.environ)))\n"
                            "Path('prompt.txt').write_text(sys.stdin.read())\n"
                            "print(json.dumps({'type':'result','subtype':'success',"
                            "'is_error':False,'result':'Edited.','session_id':'test',"
                            "'num_turns':2,'usage':{'input_tokens':3}}))\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "do-not-pass", "FLOW_SECRET": "do-not-pass"}):
                result = call_claude_edit(instructions="Fix defect", task="Edit only two files",
                                          workspace=workspace, model="claude-test", timeout_seconds=5,
                                          claude_bin=str(fake))
            argv = json.loads((workspace / "argv.json").read_text())
            child_env = json.loads((workspace / "env.json").read_text())
            self.assertEqual(result["output"], "Edited.")
            for flag in ("--restricted", "--safe-mode", "--strict-mcp-config",
                         "--no-session-persistence", "--disable-slash-commands"):
                self.assertIn(flag, argv)
            self.assertEqual(argv[argv.index("--tools") + 1], "Read,Glob,Grep,Edit")
            self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits")
            self.assertNotIn("ANTHROPIC_API_KEY", child_env)
            self.assertNotIn("FLOW_SECRET", child_env)
            self.assertIn("Edit only two files", (workspace / "prompt.txt").read_text())

    def test_symlink_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "real").mkdir()
            (root / "link").symlink_to(root / "real")
            with self.assertRaises(ValueError):
                call_claude_edit(instructions="Fix", task="Edit", workspace=root / "link",
                                 model="claude-test", timeout_seconds=5)


if __name__ == "__main__":
    unittest.main()
