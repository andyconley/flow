"""Contract preparation and provider routes for chartered Delivery Lead jobs."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_gateway import (ContractError, _default_worker_adapter,
                              _run_chartered_test, prepare_chartered_delivery)


class CharteredPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.run = self.root / ".flow" / "runs" / "sample"
        self.run.mkdir(parents=True)
        self.worktree = self.root / "worktree"
        self.worktree.mkdir()
        subprocess.run(["git", "init", "-q", str(self.worktree)], check=True)
        subprocess.run(["git", "-C", str(self.worktree), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.worktree), "config", "user.name", "Test"], check=True)
        (self.worktree / "target.py").write_text("old\n")
        subprocess.run(["git", "-C", str(self.worktree), "add", "target.py"], check=True)
        subprocess.run(["git", "-C", str(self.worktree), "commit", "-qm", "source"], check=True)
        self.commit = subprocess.check_output(["git", "-C", str(self.worktree), "rev-parse", "HEAD"], text=True).strip()
        self.charter = {"task": "Edit target.py", "read_paths": ["target.py"], "write_paths": ["target.py"],
                        "test": {"argv": ["/opt/homebrew/bin/python3.12", "-m", "unittest", "discover", "-s", "tests", "-p", "test_target.py"], "timeout_seconds": 30},
                        "producer_instance_ids": ["editor"], "verifier_instance_ids": ["verifier"],
                        "baseline": {"kind": "clean", "diff_sha256": hashlib.sha256(b"").hexdigest()}}
        self.manifest = {"assignments": [
            {"id": "magentic-manager", "lane": "implement", "role": "delivery-lead", "execution": {"provider": "claude", "model": "manager"}},
            {"id": "editor", "lane": "implement", "role": "lead-developer", "execution": {"provider": "codex", "model": "editor-model"}, "read_only": False, "write_scopes": ["target.py"]},
            {"id": "verifier", "lane": "implement", "role": "test-engineer", "execution": {"provider": "ollama", "model": "local-model"}, "read_only": True, "write_scopes": []}]}
        (self.run / "requirements.md").write_text("requirements")
        (self.run / "acceptance.md").write_text("acceptance")
        self.state = {"state": "implementing", "protocol_revision": 2, "artifacts": {
            "job_charter": ".flow/runs/sample/job-charter.json", "orchestration_manifest": ".flow/runs/sample/orchestration.json",
            "requirements": ".flow/runs/sample/requirements.md", "acceptance_criteria": ".flow/runs/sample/acceptance.md"}}
        self._write_inputs()

    def _write_inputs(self):
        (self.run / "job-charter.json").write_text(json.dumps(self.charter))
        (self.run / "orchestration.json").write_text(json.dumps(self.manifest))

    def prepare(self):
        with patch("delivery_gateway.run_status", return_value=self.state), patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role):
            return prepare_chartered_delivery("sample", self.worktree, self.commit, root=self.root)

    def test_clean_job_pins_roster_and_contract(self):
        envelope, task, attempt_dir, ledger = self.prepare()
        self.assertEqual(envelope["execution_protocol_version"], 6)
        self.assertEqual(envelope["job_contract"]["task"], task)
        self.assertEqual([r["capabilities"] for r in envelope["roster"]], [["read", "edit"], ["read"]])
        self.assertTrue((attempt_dir / "job-charter.snapshot.json").is_file())
        self.assertEqual(ledger.snapshot(envelope["attempt_id"])["status"], "started")

    def test_rejects_unapproved_charter_or_provider_permission_mismatch(self):
        self.state["artifacts"].pop("job_charter")
        with self.assertRaisesRegex(ContractError, "approved job charter"):
            self.prepare()
        self.manifest["assignments"][0]["input_evidence"] = [".flow/runs/sample/job-charter.json"]
        self._write_inputs()
        self.assertEqual(self.prepare()[0]["execution_protocol_version"], 6)
        self.state["artifacts"]["job_charter"] = ".flow/runs/sample/job-charter.json"
        self.manifest["assignments"][1]["read_only"] = True
        self._write_inputs()
        with self.assertRaisesRegex(ContractError, "permissions"):
            self.prepare()

    def test_rejects_unsafe_test_and_dirty_baseline(self):
        self.charter["test"]["argv"] = ["sh", "-c", "true"]
        self._write_inputs()
        with self.assertRaisesRegex(ContractError, "test argv"):
            self.prepare()
        self.charter["test"]["argv"] = ["/opt/homebrew/bin/python3.12", "-m", "unittest", "discover", "-s", "tests", "-p", "test_target.py"]
        self._write_inputs()
        (self.worktree / "target.py").write_text("changed\n")
        with self.assertRaisesRegex(ContractError, "not clean"):
            self.prepare()


class ProviderRouteTests(unittest.TestCase):
    def test_codex_and_claude_direct_routes(self):
        with tempfile.TemporaryDirectory() as dirname:
            workspace = Path(dirname)
            roster = [{"assignment_id": "editor", "instructions": "do task", "model": "pinned"}]
            envelope = {"execution_protocol_version": 6, "roster": roster}
            action = {"assignment_id": "editor", "provider": "codex", "task": "edit"}
            with patch("delivery_gateway.call_codex", return_value={"provider": "codex"}) as codex:
                self.assertEqual(_default_worker_adapter(action, envelope=envelope, workspace=workspace)["provider"], "codex")
                codex.assert_called_once()
            action["provider"] = "claude"
            with patch("delivery_gateway.call_claude_edit", return_value={"provider": "claude"}) as claude:
                self.assertEqual(_default_worker_adapter(action, envelope=envelope, workspace=workspace)["provider"], "claude")
                claude.assert_called_once()


if __name__ == "__main__":
    unittest.main()
