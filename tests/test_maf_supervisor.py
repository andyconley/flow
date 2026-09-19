"""Failure-boundary tests for the optional MAF child protocol; no MAF import or model call."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))
from maf_supervisor import MafProtocolError, run_maf  # noqa: E402


class SupervisorProtocolTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        task = "Return a stub result."
        charter_sources = {
            "requirements": {"path": ".flow/runs/test/requirements.md", "sha256": "a" * 64},
            "acceptance": {"path": ".flow/runs/test/acceptance-criteria.md", "sha256": "b" * 64},
        }
        charter_digest = hashlib.sha256(
            json.dumps(
                {"requirements": charter_sources["requirements"]["sha256"], "acceptance": charter_sources["acceptance"]["sha256"]},
                sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
            ).encode()
        ).hexdigest()
        self.envelope = {
            "schema_version": 1, "work_id": "test", "attempt_id": "attempt-1",
            "charter_digest": charter_digest, "charter_sources": charter_sources, "run_protocol_revision": 2,
            "manifest_digest": "c" * 64, "assignment_id": "test-role",
            "definition_digest": "c" * 64, "instance_id": "test-engineer-1", "role": "test-engineer",
            "provider": "local-stub", "model": "stub", "task": task,
            "task_digest": hashlib.sha256(task.encode()).hexdigest(), "instructions": "Return one line.",
            "limits": {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "paid_budget_usd": 0},
            "checkpoint_dir": str(self.root / "checkpoint"),
        }

    def script(self, body: str) -> str:
        path = self.root / "fake-child"
        path.write_text(f"#!{sys.executable}\n" + body)
        os.chmod(path, 0o700)
        return str(path)

    def assert_protocol_rejected(self, body: str, message: str) -> None:
        executable = self.script(body)
        with self.assertRaisesRegex(MafProtocolError, message):
            run_maf(self.envelope, lambda _: self.fail("no proposal expected"), python_path=executable, timeout_s=2)

    def test_partial_line_obeys_deadline(self):
        executable = self.script("import sys,time\nsys.stdin.readline()\nsys.stdout.write('{')\nsys.stdout.flush()\ntime.sleep(1)\n")
        with self.assertRaisesRegex(MafProtocolError, "timed out"):
            run_maf(self.envelope, lambda _: self.fail("no proposal expected"), python_path=executable, timeout_s=0.1)

    def test_nonzero_exit_after_finished_is_not_accepted(self):
        executable = self.script('''import hashlib,json,sys
start=json.loads(sys.stdin.readline())
e=start["envelope"]
def dig(v):
 return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
aid=dig({"attempt_id":e["attempt_id"],"charter_digest":e["charter_digest"],"definition_digest":e["definition_digest"],"instance_id":e["instance_id"],"kind":"delegate","sequence":1})
proposal={"protocol_version":1,"type":"propose_action","schema_version":1,"kind":"delegate","attempt_id":e["attempt_id"],"action_id":aid,"role":e["role"],"instance_id":e["instance_id"],"provider":e["provider"],"model":e["model"],"task_digest":e["task_digest"],"envelope_digest":dig(e),"sequence":1}
print(json.dumps(proposal),flush=True)
sys.stdin.readline()
print(json.dumps({"protocol_version":1,"type":"workflow_finished","attempt_id":e["attempt_id"],"checkpoint_id":None,"summary":"done"}),flush=True)
sys.exit(7)
''')
        seen = []
        with self.assertRaisesRegex(RuntimeError, "exited 7"):
            run_maf(self.envelope, lambda action: seen.append(action) or {"status": "completed", "output": "stub"}, python_path=executable, timeout_s=2)
        self.assertEqual(len(seen), 1)

    def test_rejects_invalid_protocol_version_before_callback(self):
        self.assert_protocol_rejected(
            "import sys\nsys.stdin.readline()\nprint('{\\\"protocol_version\\\":2,\\\"type\\\":\\\"workflow_finished\\\"}', flush=True)\n",
            "unsupported protocol message",
        )

    def test_rejects_malformed_and_oversized_child_json(self):
        with self.subTest("malformed"):
            self.assert_protocol_rejected(
                "import sys\nsys.stdin.readline()\nsys.stdout.write('{not-json}\\n');sys.stdout.flush()\n",
                "invalid JSON",
            )
        with self.subTest("oversized"):
            self.assert_protocol_rejected(
                "import sys\nsys.stdin.readline()\nsys.stdout.write('x'*262145);sys.stdout.flush()\n",
                "oversized unterminated",
            )

    def test_rejects_finish_before_proposal_and_foreign_attempt(self):
        with self.subTest("premature finish"):
            self.assert_protocol_rejected(
                "import json,sys\nstart=json.loads(sys.stdin.readline())\nprint(json.dumps({'protocol_version':1,'type':'workflow_finished','attempt_id':start['envelope']['attempt_id'],'checkpoint_id':None,'summary':'premature'}),flush=True)\n",
                "without one action proposal",
            )
        with self.subTest("foreign attempt"):
            self.assert_protocol_rejected(
                '''import json,sys
start=json.loads(sys.stdin.readline())
e=start["envelope"]
print(json.dumps({"protocol_version":1,"type":"propose_action","schema_version":1,"kind":"delegate","attempt_id":"foreign-attempt","action_id":"foreign","role":e["role"],"instance_id":e["instance_id"],"provider":e["provider"],"model":e["model"],"task_digest":e["task_digest"],"envelope_digest":"foreign","sequence":1}),flush=True)
''',
                "not bound to the envelope",
            )

    def test_eof_and_crash_before_terminal_record_are_rejected(self):
        with self.subTest("eof"):
            self.assert_protocol_rejected(
                "import sys\nsys.stdin.readline()\n",
                "closed stdout before workflow_finished",
            )
        with self.subTest("crash"):
            self.assert_protocol_rejected(
                "import sys\nsys.stdin.readline()\nraise RuntimeError('child crash')\n",
                "closed stdout before workflow_finished",
            )

    def test_rejects_a_second_proposal_after_flow_handles_the_first(self):
        executable = self.script('''import hashlib,json,sys
start=json.loads(sys.stdin.readline())
e=start["envelope"]
def dig(v):
 return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
aid=dig({"attempt_id":e["attempt_id"],"charter_digest":e["charter_digest"],"definition_digest":e["definition_digest"],"instance_id":e["instance_id"],"kind":"delegate","sequence":1})
proposal={"protocol_version":1,"type":"propose_action","schema_version":1,"kind":"delegate","attempt_id":e["attempt_id"],"action_id":aid,"role":e["role"],"instance_id":e["instance_id"],"provider":e["provider"],"model":e["model"],"task_digest":e["task_digest"],"envelope_digest":dig(e),"sequence":1}
print(json.dumps(proposal),flush=True)
sys.stdin.readline()
print(json.dumps(proposal),flush=True)
''')
        seen = []
        with self.assertRaisesRegex(MafProtocolError, "more than one action"):
            run_maf(self.envelope, lambda action: seen.append(action) or {"status": "completed"}, python_path=executable, timeout_s=2)
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
