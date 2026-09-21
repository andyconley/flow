"""Shaper MCP core must preserve Flow's lifecycle and read boundaries."""

import json
import tempfile
import unittest
from pathlib import Path

from shaper_gateway import current_state, run_evidence, submit_charter
from runstate import status


class ShaperGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".flow").mkdir()
        (self.root / ".flow" / "PROJECT.md").write_text("# Fixture\n")

    def submit(self):
        return submit_charter(self.root, goal="Build a safe launcher",
                              outcomes="One verified job", constraints="Use an isolated worktree",
                              execution_envelope="Up to six direct worker calls")

    def test_submission_is_proposed_definition_not_execution(self):
        result = self.submit()
        self.assertEqual(result["state"], "defining")
        self.assertFalse(result["execution_started"])
        run = status(result["work_id"], self.root)
        self.assertEqual(run["last_event"], "start-definition")
        self.assertNotIn("approve-definition", run["gates"])
        path = self.root / result["submission"]
        self.assertEqual(json.loads(path.read_text())["status"], "proposed")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(current_state(self.root)["runs"]), 1)

    def test_evidence_is_allowlisted_and_bounded(self):
        result = self.submit()
        self.assertIn("Build a safe launcher", run_evidence(
            self.root, result["work_id"], "shaper-submission.json")["content"])
        with self.assertRaises(ValueError):
            run_evidence(self.root, result["work_id"], "run.json")
        with self.assertRaises(ValueError):
            run_evidence(self.root, "../escape", "HANDOFF.md")
        with self.assertRaises(ValueError):
            current_state(self.root, 1000)

    def test_invalid_charter_creates_no_run(self):
        with self.assertRaises(ValueError):
            submit_charter(self.root, goal=" ", outcomes="yes", constraints="yes",
                           execution_envelope="yes")
        self.assertEqual(current_state(self.root)["runs"], [])

    def test_symlinked_artifact_is_rejected(self):
        result = self.submit()
        path = self.root / ".flow" / "runs" / result["work_id"] / "HANDOFF.md"
        path.symlink_to(self.root / ".flow" / "PROJECT.md")
        with self.assertRaises(FileNotFoundError):
            run_evidence(self.root, result["work_id"], "HANDOFF.md")

    def test_symlinked_run_directory_is_rejected_before_read(self):
        runs = self.root / ".flow" / "runs"
        runs.mkdir()
        (runs / "foreign").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            current_state(self.root)
        with self.assertRaises(FileNotFoundError):
            run_evidence(self.root, "foreign", "HANDOFF.md")

    def test_symlinked_run_storage_cannot_receive_submission(self):
        target = self.root / "outside"
        target.mkdir()
        (self.root / ".flow" / "runs").symlink_to(target, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.submit()
        self.assertEqual(list(target.iterdir()), [])

    def test_run_projection_symlink_and_large_inventory_are_rejected(self):
        runs = self.root / ".flow" / "runs"
        run_dir = runs / "linked"
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").symlink_to(self.root / ".flow" / "PROJECT.md")
        with self.assertRaises(ValueError):
            current_state(self.root)
        (run_dir / "run.json").unlink()
        for index in range(201):
            (runs / f"legacy-{index}").mkdir()
        with self.assertRaises(ValueError):
            current_state(self.root)


if __name__ == "__main__":
    unittest.main()
