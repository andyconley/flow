"""A real child reaches the identity handshake before any MAF/provider route."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class MafChildHandshakeTests(unittest.TestCase):
    def test_delivery_child_echoes_runtime_identity_before_optional_imports(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as checkpoint:
            child = subprocess.Popen([sys.executable, "-m", "runtime.maf_runner.delivery_lead"], cwd=root,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            assert child.stdin and child.stdout
            envelope = {"execution_protocol_version": 8, "attempt_id": "handshake", "checkpoint_dir": checkpoint,
                        "maf_runtime": {"runtime_digest": "a" * 64}}
            child.stdin.write(json.dumps({"protocol_version": 8, "type": "start", "envelope": envelope, "task": "never dispatch"}) + "\n")
            child.stdin.flush()
            first = json.loads(child.stdout.readline())
            self.assertEqual(first, {"protocol_version": 8, "type": "runtime_ready", "runtime_digest": "a" * 64})
            child.kill()
            child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()
            child.stderr.close()


if __name__ == "__main__":
    unittest.main()
