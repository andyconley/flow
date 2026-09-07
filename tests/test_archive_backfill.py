"""Backfill consent and source-race proof against temporary overlays."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))
import archive_service as service
import archive_store as store


class ArchiveBackfillTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.run_dir = self.root / ".flow" / "runs" / "one"
        self.run_dir.mkdir(parents=True)
        self.source = self.run_dir / "archive.md"
        self.source.write_text("## Work Closed\nKeep original source evidence.\n")
        run = {"schema_version": 1, "work_id": "one", "state": "archived", "gates": {"archive": "2026-09-06T00:00:00Z"}, "artifacts": {"archive": ".flow/runs/one/archive.md"}}
        event = {"event": "archive", "at": run["gates"]["archive"], "to": "archived", "dispositions": {"archive_enrichment": "1"}}
        (self.run_dir / "run.json").write_text(json.dumps(run))
        (self.run_dir / "events.jsonl").write_text(json.dumps(event) + "\n")

    def tree(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}

    def test_preview_and_apply_without_yes_do_not_initialize_identity_or_write_cache(self):
        before = self.tree()
        preview = service.backfill(self.root)
        refused = service.backfill(self.root, apply=True)

        self.assertEqual(preview["state"], "preview")
        self.assertTrue(preview["identity_needed"])
        self.assertEqual(refused["state"], "invalid_request")
        self.assertEqual(before, self.tree())
        self.assertFalse((self.root / ".flow" / "identity.json").exists())

    def test_source_changed_between_generation_and_lock_is_reported_without_abstract_write(self):
        original_extract = service.extract
        calls = 0

        def edit_after_proposal(root, run, source_id, declarations):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.source.write_text("## Work Closed\nExternal editor changed the source.\n")
            return original_extract(root, run, source_id, declarations)

        with patch.object(service, "extract", side_effect=edit_after_proposal):
            result = service.backfill(self.root, apply=True, yes=True)

        self.assertEqual(result["state"], "partial")
        self.assertIn("sources changed during generation", str(result["errors"]))
        self.assertFalse((self.run_dir / "abstract.json").exists())


if __name__ == "__main__":
    unittest.main()
