"""Prove the explicit legacy-v8 charter migration is narrow and atomic."""

from __future__ import annotations

import copy
import contextlib
import hashlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_gateway import provider_selection_probe  # noqa: E402
import flow  # noqa: E402
from runstate import approve_job_charter_v9_migration  # noqa: E402
from tests.test_chartered_delivery_gateway import CharteredFixture  # noqa: E402
from tests.test_delivery_selection import _envelope  # noqa: E402


class V8V9JobCharterMigrationTests(CharteredFixture):
    """A real-shaped v8 run whose manifest already cites its charter.

    The test fixture deliberately omits only the v9 artifact registration.  It
    retains the sealed Delivery authority used by the migrator rather than
    mocking lifecycle reads, so each refusal can prove no authority projection
    was modified.
    """

    def setUp(self) -> None:
        super().setUp()
        self.state["artifacts"].pop("job_charter")
        self.manifest["assignments"][0]["input_evidence"] = [
            ".flow/runs/sample/job-charter.json"
        ]
        self._write_inputs()
        self.state["approved_artifact_digests"] = {
            "orchestration_manifest": hashlib.sha256(
                (self.run / "orchestration.json").read_bytes()).hexdigest(),
        }
        self._write_delivery_authority()
        self.replacement = self.run / "successor-job-charter.json"
        self.replacement.write_text(self._json(self._successor_charter()))

    @staticmethod
    def _json(value: dict) -> str:
        import json
        return json.dumps(value, indent=2, sort_keys=True) + "\n"

    def _successor_charter(self) -> dict:
        successor = copy.deepcopy(self.charter)
        common = {
            "minimum_tier": "working", "locality": "any",
            "input_bytes": 100, "output_bytes": 100, "context_tokens": 100,
        }
        successor["logical_assignments"] = [
            {"assignment_id": "magentic-manager", "role": "delivery-lead",
             "instructions": "Coordinate the sealed logical work.", "depends_on": [],
             "requirements": {**common, "operation": "manage",
                              "required_capabilities": ["structured_output"],
                              "risk_class": "standard", "independence_required": False}},
            {"assignment_id": "editor", "role": "lead-developer",
             "instructions": "Edit only the approved path.", "depends_on": [],
             "requirements": {**common, "operation": "edit",
                              "required_capabilities": ["structured_edit"],
                              "risk_class": "standard", "independence_required": False}},
            {"assignment_id": "verifier", "role": "test-engineer",
             "instructions": "Collect independent bounded verification evidence.",
             "depends_on": ["editor"],
             "requirements": {**common, "operation": "verify",
                              "required_capabilities": ["evidence_collection"],
                              "risk_class": "high", "independence_required": True}},
        ]
        return successor

    def _migrate(self, replacement: str | None = None, *, approved: bool = True):
        return approve_job_charter_v9_migration(
            "sample", replacement or self.replacement.relative_to(self.root).as_posix(),
            "explicit user approval for deterministic v9 selection",
            approved_by_user=approved, root=self.root,
        )

    def _tree(self) -> dict[str, tuple[str, bytes | str]]:
        result: dict[str, tuple[str, bytes | str]] = {}
        for path in sorted(self.run.rglob("*")):
            if path.is_dir() or path.name == ".delivery.lock":
                continue
            relative = path.relative_to(self.run).as_posix()
            if path.is_symlink():
                result[relative] = ("symlink", os.readlink(path))
            else:
                result[relative] = ("file", path.read_bytes())
        return result

    def _assert_refused_atomically(self, expected: str) -> None:
        before = self._tree()
        ok, _payload, errors = self._migrate()
        self.assertFalse(ok)
        self.assertTrue(any(expected in error for error in errors), errors)
        self.assertEqual(self._tree(), before)

    def test_valid_legacy_manifest_link_migrates_and_provider_selection_probe_accepts_v9_artifact(self) -> None:
        original = (self.run / "job-charter.json").read_bytes()
        ok, payload, errors = self._migrate()
        self.assertTrue(ok, errors)
        registered = payload["artifacts"]["job_charter"]
        registered_path = self.root / registered
        self.assertEqual(registered_path.read_bytes(), self.replacement.read_bytes())
        self.assertNotEqual(registered_path.read_bytes(), original)
        self.assertEqual(payload["approved_artifact_digests"]["job_charter"],
                         hashlib.sha256(self.replacement.read_bytes()).hexdigest())
        self.assertEqual(payload["delivery"]["owner_generation"], 2)
        self.assertEqual(len(payload["job_charter_migrations"]), 1)
        record = payload["job_charter_migrations"][0]
        self.assertEqual(record["predecessor_digest"], hashlib.sha256(original).hexdigest())
        self.assertEqual(record["successor_digest"], hashlib.sha256(self.replacement.read_bytes()).hexdigest())
        self.assertTrue((self.root / record["predecessor_snapshot"]).is_file())

        inputs = copy.deepcopy(_envelope()["selection_inputs"])
        for candidate in inputs["catalog"]:
            candidate["capabilities"].append("evidence_collection")
        with patch("delivery_gateway.flow_owned_v9_selection_inputs",
                   return_value=(inputs["catalog"], inputs["policy"], inputs["availability"])):
            probe = provider_selection_probe("sample", root=self.root)
        self.assertEqual({row["assignment_id"] for row in probe["decisions"]},
                         {"magentic-manager", "editor", "verifier"})
        self.assertTrue(all(row["decision"]["selected_binding"] is not None for row in probe["decisions"]))

    def test_repeat_is_an_idempotent_noop_without_duplicate_history(self) -> None:
        ok, payload, errors = self._migrate()
        self.assertTrue(ok, errors)
        before = self._tree()
        ok, repeated, errors = self._migrate()
        self.assertTrue(ok, errors)
        self.assertEqual(repeated, payload)
        self.assertEqual(self._tree(), before)

    def test_missing_explicit_approval_is_refused_without_mutation(self) -> None:
        before = self._tree()
        ok, _payload, errors = self._migrate(approved=False)
        self.assertFalse(ok)
        self.assertIn("explicit user approval is required", errors)
        self.assertEqual(self._tree(), before)

    def test_missing_manifest_link_is_refused_atomically(self) -> None:
        self.manifest["assignments"][0]["input_evidence"] = []
        self._write_inputs()
        self.state["approved_artifact_digests"]["orchestration_manifest"] = hashlib.sha256(
            (self.run / "orchestration.json").read_bytes()).hexdigest()
        self._write_delivery_authority()
        self._assert_refused_atomically("does not uniquely link")

    def test_symlinked_successor_is_refused_atomically(self) -> None:
        target = self.run / "safe-successor.json"
        target.write_text(self._json(self._successor_charter()))
        self.replacement.unlink()
        self.replacement.symlink_to(target.name)
        self._assert_refused_atomically("must be a bounded current-run regular file")

    def test_out_of_run_successor_path_is_refused_atomically(self) -> None:
        outside = self.root / "outside-successor.json"
        outside.write_text(self._json(self._successor_charter()))
        before = self._tree()
        ok, _payload, errors = approve_job_charter_v9_migration(
            "sample", outside.relative_to(self.root).as_posix(), "explicit approval",
            approved_by_user=True, root=self.root,
        )
        self.assertFalse(ok)
        self.assertTrue(any("current-run relative path" in error for error in errors), errors)
        self.assertEqual(self._tree(), before)

    def test_malformed_successor_schema_is_refused_atomically(self) -> None:
        malformed = self._successor_charter()
        malformed.pop("logical_assignments")
        self.replacement.write_text(self._json(malformed))
        self._assert_refused_atomically("requires complete logical_assignments")

    def test_authority_expansion_is_refused_atomically(self) -> None:
        widened = self._successor_charter()
        widened["write_paths"] = ["target.py", "other.py"]
        self.replacement.write_text(self._json(widened))
        self._assert_refused_atomically("changes approved v8 field: write_paths")

    def test_stale_manifest_digest_is_refused_atomically(self) -> None:
        self.state["approved_artifact_digests"]["orchestration_manifest"] = "0" * 64
        self._write_delivery_authority()
        self._assert_refused_atomically("differs from its approved digest")

    def test_active_execution_blocks_migration_without_mutating_run_state(self) -> None:
        execution = self.run / "execution"
        execution.mkdir()
        import sqlite3
        db = sqlite3.connect(execution / "ledger.sqlite")
        try:
            db.execute("CREATE TABLE attempts (status TEXT)")
            db.execute("INSERT INTO attempts VALUES ('started')")
            db.commit()
        finally:
            db.close()
        self._assert_refused_atomically("started execution attempt")

    def test_cli_help_exposes_explicit_approval_and_successor_contract(self) -> None:
        output = io.StringIO()
        with patch.object(sys, "argv", ["flow", "run", "migrate-job-charter-v9", "--help"]), \
                contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exited:
            flow.main()
        self.assertEqual(exited.exception.code, 0)
        help_text = output.getvalue()
        self.assertIn("--replacement", help_text)
        self.assertIn("--reason", help_text)
        self.assertIn("--approved-by-user", help_text)


if __name__ == "__main__":
    unittest.main()
