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

from claude_edit_worker import ClaudeEditError, _result, _stream_result, call_claude_edit


class ClaudeEditWorkerTests(unittest.TestCase):
    def test_stream_result_requires_one_success(self):
        good = {"type": "result", "subtype": "success", "is_error": False,
                "result": "Edited.", "session_id": "one", "num_turns": 9,
                "usage": {"input_tokens": 3}}
        stream = b'{"type":"system","subtype":"init"}\n' + json.dumps(good).encode() + b'\n'
        self.assertEqual(_stream_result(stream, "claude-test")["output"], "Edited.")
        self.assertEqual(_stream_result(stream, "claude-test")["num_turns"], 9)
        with self.assertRaises(ClaudeEditError):
            _stream_result(stream + json.dumps(good).encode() + b'\n', "claude-test")

    def test_live_events_are_preserved_on_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            trace = root / "claude-implementer.debug.log"
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\n"
                            "import json, sys\n"
                            "from pathlib import Path\n"
                            "Path(sys.argv[sys.argv.index('--debug-file') + 1]).write_text('started\\n')\n"
                            "sys.stdin.read()\n"
                            "print(json.dumps({'type':'system','subtype':'init'}), flush=True)\n"
                            "print(json.dumps({'type':'result','subtype':'success',"
                            "'is_error':False,'result':'Edited.','session_id':'test',"
                            "'num_turns':1,'usage':{'input_tokens':3}}), flush=True)\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            result = call_claude_edit(instructions="Fix", task="Edit", workspace=workspace,
                                      model="claude-test", timeout_seconds=5,
                                      claude_bin=str(fake), trace_path=trace)
            events = root / "claude-implementer.events.ndjson"
            self.assertEqual(result["output"], "Edited.")
            self.assertIn('"subtype": "init"', events.read_text())
            self.assertEqual(stat.S_IMODE(events.stat().st_mode), 0o600)

    def test_result_rejects_failed_and_invalid_turns(self):
        good = {"type": "result", "subtype": "success", "is_error": False,
                "result": "Edited two files.", "session_id": "one", "num_turns": 2,
                "usage": {"input_tokens": 3}}
        self.assertEqual(_result(json.dumps(good).encode(), "claude-test")["num_turns"], 2)
        self.assertEqual(_result(json.dumps(good).encode(), "claude-test")["evidence_level"],
                         "flow_observed_claude_cli_completed_turn")
        self.assertEqual(_result(json.dumps({**good, "num_turns": 9}).encode(), "claude-test")["num_turns"], 9)
        for change in ({"is_error": True}, {"num_turns": 0}, {"session_id": ""},
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

    def test_debug_trace_survives_timeout_without_session_persistence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            trace = root / "claude-implementer.debug.log"
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\n"
                            "import sys, time\n"
                            "from pathlib import Path\n"
                            "Path(sys.argv[sys.argv.index('--debug-file') + 1]).write_text('tool: Read started\\n')\n"
                            "sys.stdin.read()\n"
                            "time.sleep(4)\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with self.assertRaisesRegex(ClaudeEditError, "timed out"):
                call_claude_edit(instructions="Fix", task="Edit", workspace=workspace,
                                 model="claude-test", timeout_seconds=1, claude_bin=str(fake),
                                 trace_path=trace)
            self.assertEqual(trace.read_text(), "tool: Read started\n")
            self.assertEqual(stat.S_IMODE(trace.stat().st_mode), 0o600)
            self.assertTrue((root / "claude-implementer.events.ndjson").exists())

    def _stream_fake(self, root: Path, *, trace_bytes: int = 0, payload_bytes: int = 0) -> Path:
        """A stream-json Claude stand-in: optional trace, optional bulk events, one result."""
        fake = root / "claude-fake"
        fake.write_text("#!/usr/bin/env python3\n"
                        "import json, sys\n"
                        "from pathlib import Path\n"
                        "Path('argv.json').write_text(json.dumps(sys.argv[1:]))\n"
                        f"Path(sys.argv[sys.argv.index('--debug-file') + 1]).write_bytes(b'x' * {trace_bytes})\n"
                        "sys.stdin.read()\n"
                        f"left = {payload_bytes}\n"
                        "while left > 0:\n"
                        "    line = json.dumps({'type':'user','tool_result':'r' * min(left, 60000)})\n"
                        "    print(line, flush=True)\n"
                        "    left -= len(line) + 1\n"
                        "print(json.dumps({'type':'result','subtype':'success',"
                        "'is_error':False,'result':'Edited.','session_id':'test',"
                        "'num_turns':4,'usage':{'input_tokens':3}}), flush=True)\n")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def _stream_call(self, root: Path, fake: Path) -> dict:
        workspace = root / "workspace"
        workspace.mkdir(exist_ok=True)
        return call_claude_edit(instructions="Fix", task="Edit", workspace=workspace,
                                model="claude-test", timeout_seconds=20, claude_bin=str(fake),
                                trace_path=root / "claude-implementer.debug.log")

    def test_stream_over_one_mebibyte_completes_and_is_logged_whole(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._stream_call(root, self._stream_fake(root, payload_bytes=3 * 1024 * 1024))
            events = (root / "claude-implementer.events.ndjson").read_bytes()
            self.assertEqual(result["output"], "Edited.")
            self.assertGreater(len(events), 3 * 1024 * 1024)
            self.assertEqual(sum(b'"type": "result"' in line for line in events.splitlines()), 1)

    def test_stream_over_event_cap_is_uncertain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = self._stream_fake(root, payload_bytes=512 * 1024)
            with patch("claude_edit_worker.MAX_EVENT_BYTES", 256 * 1024), \
                    self.assertRaisesRegex(ClaudeEditError, "output exceeds limit"):
                self._stream_call(root, fake)
            self.assertEqual((root / "claude-implementer.events.ndjson").stat().st_size, 256 * 1024)

    def test_stream_mode_omits_partial_messages(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._stream_call(root, self._stream_fake(root))
            argv = json.loads((root / "workspace" / "argv.json").read_text())
            self.assertEqual(argv[argv.index("--output-format") + 1], "stream-json")
            self.assertIn("--verbose", argv)
            self.assertNotIn("--include-partial-messages", argv)

    def test_debug_trace_is_truncated_not_fatal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = self._stream_call(root, self._stream_fake(root, trace_bytes=2 * 1024 * 1024))
            trace = root / "claude-implementer.debug.log"
            self.assertEqual(result["output"], "Edited.")
            self.assertEqual(trace.stat().st_size, 1024 * 1024)
            self.assertEqual(stat.S_IMODE(trace.stat().st_mode), 0o600)

if __name__ == "__main__":
    unittest.main()
