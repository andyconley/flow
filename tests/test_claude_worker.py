"""Focused bounds and completion checks for the installed Claude Code adapter."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from claude_worker import ClaudeWorkerError, _parse_result, call_claude


def result_json(**overrides):
    payload = {"type": "result", "subtype": "success", "is_error": False,
               "result": "Looks good.", "session_id": "session-1", "num_turns": 1,
               "usage": {"input_tokens": 8, "output_tokens": 2}}
    payload.update(overrides)
    return json.dumps(payload).encode()


class ClaudeWorkerTests(unittest.TestCase):
    def test_completed_turn_normalized(self):
        result = _parse_result(result_json(), "claude-test")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["provider"], "claude")
        self.assertEqual(result["model"], "claude-test")
        self.assertTrue(result["physical_call"])
        self.assertEqual(result["evidence_level"], "flow_observed_claude_cli_completed_turn")
        self.assertEqual(result["output"], "Looks good.")
        self.assertEqual(result["session_id"], "session-1")
        self.assertEqual(result["usage"]["output_tokens"], 2)
        import hashlib
        self.assertEqual(result["output_sha256"], hashlib.sha256(b"Looks good.").hexdigest())

    def test_incomplete_or_malformed_result_rejected(self):
        cases = [
            result_json(is_error=True),
            result_json(type="assistant"),
            result_json(subtype="error"),
            result_json(result=""),
            result_json(result=None),
            result_json(session_id=""),
            result_json(session_id=None),
            result_json(num_turns=0),
            result_json(num_turns=2),
            result_json(num_turns=True),
            result_json(num_turns="1"),
            result_json(usage={"input_tokens": -1}),
            result_json(usage={"input_tokens": True}),
            result_json(usage="not-a-dict"),
            b"not json",
            b"[]",
            json.dumps("just a string").encode(),
        ]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ClaudeWorkerError):
                _parse_result(raw, "claude-test")

    def test_output_over_limit_rejected(self):
        with self.assertRaises(ClaudeWorkerError):
            _parse_result(result_json(result="x" * 5000), "claude-test")

    def test_usage_may_be_absent(self):
        result = _parse_result(result_json(usage=None), "claude-test")
        self.assertIsNone(result["usage"])

    def test_provider_usage_metadata_is_ignored_and_token_counts_retained(self):
        result = _parse_result(
            result_json(usage={"input_tokens": 3, "cache": {"created": 1, "read": 0},
                               "service_tier": "standard", "iterations": []}),
            "claude-test")
        self.assertEqual(result["usage"], {"input_tokens": 3})

    def test_invalid_inputs_raise_value_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            with self.assertRaises(ValueError):
                call_claude(instructions="", task="Review", workspace=workspace,
                            model="claude-test", timeout_seconds=5)
            with self.assertRaises(ValueError):
                call_claude(instructions="Review charter", task="", workspace=workspace,
                            model="claude-test", timeout_seconds=5)
            with self.assertRaises(ValueError):
                call_claude(instructions="Review charter", task="Review",
                            workspace=workspace, model="", timeout_seconds=5)
            with self.assertRaises(ValueError):
                call_claude(instructions="Review charter", task="Review",
                            workspace=workspace, model="bad model", timeout_seconds=5)
            with self.assertRaises(ValueError):
                call_claude(instructions="Review charter", task="Review",
                            workspace=workspace, model="claude-test", timeout_seconds=0)
            with self.assertRaises(ValueError):
                call_claude(instructions="Review charter", task="Review",
                            workspace=workspace, model="claude-test", timeout_seconds=601)
            with self.assertRaises(ValueError):
                call_claude(instructions="Review charter", task="Review",
                            workspace=workspace, model="claude-test", timeout_seconds=True)
            with self.assertRaises(ValueError):
                call_claude(instructions="x" * 40000, task="Review",
                            workspace=workspace, model="claude-test", timeout_seconds=5)

    def test_missing_workspace_raises(self):
        with self.assertRaises(FileNotFoundError):
            call_claude(instructions="Review charter", task="Review",
                        workspace=Path("/nonexistent/flow-claude-worker-fixture"),
                        model="claude-test", timeout_seconds=5)

    def test_invocation_has_no_tools_and_one_turn(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "fixture"
            workspace.mkdir()
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\n"
                            "import json, os, sys\n"
                            "from pathlib import Path\n"
                            "Path('argv.json').write_text(json.dumps(sys.argv[1:]))\n"
                            "Path('prompt.txt').write_text(sys.stdin.read())\n"
                            "Path('env.json').write_text(json.dumps(dict(os.environ)))\n"
                            "print(json.dumps({'type': 'result', 'subtype': 'success', "
                            "'is_error': False, 'result': 'Reviewed the change.', "
                            "'session_id': 'test-session', 'num_turns': 1, "
                            "'usage': {'input_tokens': 5}}))\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with patch.dict(os.environ, {"FLOW_UNRELATED_SECRET": "do-not-pass",
                                        "ANTHROPIC_API_KEY": "do-not-pass",
                                        "CLAUDE_API_KEY": "do-not-pass"}):
                result = call_claude(instructions="Follow charter", task="Review a tiny change",
                                     workspace=workspace, model="claude-test", timeout_seconds=5,
                                     claude_bin=str(fake))
            argv = json.loads((workspace / "argv.json").read_text())
            child_env = json.loads((workspace / "env.json").read_text())
            self.assertEqual(result["output"], "Reviewed the change.")
            self.assertEqual(result["session_id"], "test-session")
            self.assertIn("-p", argv)
            self.assertIn("--output-format", argv)
            self.assertIn("json", argv)
            self.assertIn("--safe-mode", argv)
            self.assertIn("--no-session-persistence", argv)
            self.assertIn("--permission-mode", argv)
            self.assertIn("dontAsk", argv)
            self.assertIn("--tools", argv)
            self.assertEqual(argv[argv.index("--tools") + 1], "")
            self.assertIn("--model", argv)
            self.assertIn("claude-test", argv)
            self.assertNotIn("--bare", argv)
            self.assertNotIn("bypassPermissions", argv)
            self.assertIn("Follow charter", (workspace / "prompt.txt").read_text())
            self.assertNotIn("FLOW_UNRELATED_SECRET", child_env)
            self.assertNotIn("ANTHROPIC_API_KEY", child_env)
            self.assertNotIn("CLAUDE_API_KEY", child_env)
            self.assertIn("HOME", child_env)

    def test_manager_prompt_override_preserves_exact_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\n"
                            "import json, sys\n"
                            "from pathlib import Path\n"
                            "Path('received.txt').write_text(sys.stdin.read())\n"
                            "print(json.dumps({'type':'result','subtype':'success','is_error':False,"
                            "'result':'complete','session_id':'manager-test','num_turns':1}))\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            prompt = "Return only stock Magentic progress JSON."
            call_claude(instructions="unused", task="unused", workspace=root,
                        model="claude-test", timeout_seconds=5, claude_bin=str(fake),
                        prompt_override=prompt)
            self.assertEqual((root / "received.txt").read_text(), prompt)

    def test_nonzero_exit_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with self.assertRaises(ClaudeWorkerError):
                call_claude(instructions="Charter", task="Review", workspace=root,
                            model="claude-test", timeout_seconds=5, claude_bin=str(fake))

    def test_timeout_is_uncertain(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(4)\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with self.assertRaisesRegex(ClaudeWorkerError, "timed out"):
                call_claude(instructions="Charter", task="Review", workspace=root,
                           model="claude-test", timeout_seconds=1, claude_bin=str(fake))

    def test_blocked_prompt_write_obeys_timeout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\nimport time\ntime.sleep(4)\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with self.assertRaisesRegex(ClaudeWorkerError, "timed out"):
                call_claude(instructions="x" * 30000, task="Review", workspace=root,
                            model="claude-test", timeout_seconds=1, claude_bin=str(fake))

    def test_oversized_stdout_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / "claude-fake"
            fake.write_text("#!/usr/bin/env python3\n"
                            "import sys\n"
                            "sys.stdout.write('x' * (300 * 1024))\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            with self.assertRaisesRegex(ClaudeWorkerError, "exceeds limit"):
                call_claude(instructions="Charter", task="Review", workspace=root,
                           model="claude-test", timeout_seconds=5, claude_bin=str(fake))


if __name__ == "__main__":
    unittest.main()
