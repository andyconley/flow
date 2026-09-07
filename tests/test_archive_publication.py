"""Failure-focused proof for archive-owned canonical publication."""
import copy
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))
import archive_model as model
import archive_store as store
import archive_service as service


class ArchivePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        (self.root / ".flow" / "runs" / "one").mkdir(parents=True)
        self.run_dir = self.root / ".flow" / "runs" / "one"
        self.source = self.run_dir / "archive.md"
        self.source.write_text("## Work Closed\nKeep the durable decision.\n")
        run = {
            "schema_version": 1,
            "work_id": "one",
            "state": "archived",
            "gates": {"archive": "2026-09-06T00:00:00Z"},
            "artifacts": {"archive": ".flow/runs/one/archive.md"},
        }
        event = {"event": "archive", "at": run["gates"]["archive"], "to": "archived", "dispositions": {}}
        (self.run_dir / "run.json").write_text(json.dumps(run))
        (self.run_dir / "events.jsonl").write_text(json.dumps(event) + "\n")
        with store.writer_lock(self.root):
            self.source_id = store.ensure_identity(self.root)

    def envelope(self):
        run = service.load_run(self.root, "one")
        return service.build_envelope(self.root, run, self.source_id, None, "backfill")

    def publish(self, value):
        with store.writer_lock(self.root):
            self.assertTrue(store.write_envelope(self.root, "one", value, "absent"))

    def test_external_base_change_rejects_publication_and_leaves_editor_bytes(self):
        old = self.envelope()
        self.publish(old)
        path = self.run_dir / "abstract.json"
        preview_digest = store.file_digest(path)
        editor_value = copy.deepcopy(old)
        editor_value["provenance"]["editor_note"] = "external edit"
        path.write_bytes(store.encode(editor_value))

        replacement = copy.deepcopy(old)
        replacement["provenance"]["last_action"] = "rescan"
        with store.writer_lock(self.root), self.assertRaisesRegex(ValueError, "base changed"):
            store.write_envelope(self.root, "one", replacement, preview_digest)

        self.assertEqual(path.read_bytes(), store.encode(editor_value))

    def test_failed_refinement_history_publication_preserves_current_envelope(self):
        original = self.envelope()
        self.publish(original)
        current = self.run_dir / "abstract.json"
        before = current.read_bytes()
        replacement = copy.deepcopy(original)
        decision = copy.deepcopy(original["generated"]["fields"]["decision"])
        replacement["refinement"] = {
            "revision": "one",
            "actor": "reviewer",
            "reason": "first source-backed refinement",
            "base_generated_digest": model.digest(original["generated"]),
            "patches": {"decision": decision},
        }
        with store.writer_lock(self.root):
            store.write_envelope(self.root, "one", replacement, store.file_digest(current))
        refined_bytes = current.read_bytes()

        def fail_history(path, data, root):
            if "abstract-history" in str(path):
                raise OSError("history volume unavailable")
            return real_atomic_write(path, data, root)

        real_atomic_write = store.atomic_write
        with patch.object(store, "atomic_write", side_effect=fail_history), store.writer_lock(self.root):
            with self.assertRaisesRegex(OSError, "history volume unavailable"):
                store.write_envelope(self.root, "one", original, store.file_digest(current))

        self.assertNotEqual(before, refined_bytes)
        self.assertEqual(current.read_bytes(), refined_bytes)
        self.assertFalse((self.run_dir / "abstract-history").exists())

    def test_identity_initialization_writes_a_complete_readable_uuid(self):
        identity = self.root / ".flow" / "identity.json"
        identity.unlink()
        with store.writer_lock(self.root):
            source_id = store.ensure_identity(self.root)
        value = json.loads(identity.read_text())
        self.assertEqual(value, {"schema_version": 1, "source_id": source_id})
        self.assertEqual(store.read_identity(self.root), source_id)

    def test_archive_scout_closure_survives_prepare_failure(self):
        args = argparse.Namespace(
            work_id="scout",
            event="archive-scout",
            artifact=["scout_summary=.flow/runs/scout/scout-summary.md"],
            disposition=["capability_gaps=n/a", "memory=n/a"],
            note=None,
            json=True,
        )
        scout = self.root / ".flow" / "runs" / "scout"
        scout.mkdir()
        (scout / "scout-summary.md").write_text("## Scope\nKeep closure independent.\n")
        with (
            patch("fsutil.repo_root", return_value=self.root),
            patch.object(service, "ensure_identity", side_effect=OSError("identity storage unavailable")),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(service.archive_transition(args), 0)

        report = json.loads(output.getvalue())
        self.assertTrue(report["ok"])
        self.assertIn("prepare: identity storage unavailable", str(report["enrichment_diagnostics"]))
        self.assertEqual(json.loads((scout / "run.json").read_text())["state"], "archived")

    def test_archive_run_map_race_reports_gap_without_publishing(self):
        import runstate
        scout = self.root / ".flow" / "runs" / "scout"
        scout.mkdir()
        (scout / "scout-summary.md").write_text("## Scope\nOriginal decision.\n")
        (scout / "alternate.md").write_text("## Scope\nReplacement decision.\n")
        args = argparse.Namespace(work_id="scout", event="archive-scout", artifact=["scout_summary=.flow/runs/scout/scout-summary.md"], disposition=["capability_gaps=n/a", "memory=n/a"], note=None, json=True)
        real_transition = runstate.apply_transition

        def race(*args, **kwargs):
            result = real_transition(*args, **kwargs)
            changed = copy.deepcopy(result[1])
            changed["artifacts"]["scout_summary"] = ".flow/runs/scout/alternate.md"
            (scout / "run.json").write_text(json.dumps(changed))
            return result

        with patch("fsutil.repo_root", return_value=self.root), patch.object(runstate, "apply_transition", side_effect=race), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(service.archive_transition(args), 0)
        report = json.loads(output.getvalue())
        self.assertTrue(report["ok"])
        self.assertIn("canonical run changed", str(report["enrichment_diagnostics"]))
        self.assertFalse((scout / "abstract.json").exists())
        self.assertEqual(service.backfill(self.root, apply=True, yes=True)["state"], "complete")
        self.assertIn("Replacement", service.load_envelope(self.root, "scout")["generated"]["fields"]["decision"]["value"])

    def test_refinement_evidence_race_rejects_publication(self):
        value = self.envelope()
        self.publish(value)
        abstract = self.run_dir / "abstract.json"
        before = abstract.read_bytes()
        data = {"schema_version": 1, "actor": "reviewer", "reason": "source evidence", "base_generated_digest": model.digest(value["generated"]), "patches": {"decision": value["generated"]["fields"]["decision"]}}
        original_lock = store.writer_lock

        @contextlib.contextmanager
        def race(root):
            self.source.write_text("## Work Closed\nChanged during consent.\n")
            with original_lock(root):
                yield

        with patch.object(service, "writer_lock", side_effect=race), self.assertRaises(ValueError):
            service.mutate(self.root, "one", "refine", data, store.file_digest(abstract), apply=True, yes=True)
        self.assertEqual(abstract.read_bytes(), before)

    def test_archive_snapshot_race_retains_external_refinement_bytes(self):
        scout = self.root / ".flow" / "runs" / "scout"
        scout.mkdir()
        source = scout / "scout-summary.md"
        source.write_text("## Scope\nKeep closure independent.\n")
        provisional = {
            "work_id": "scout",
            "state": "archived",
            "gates": {"archive-scout": "2026-09-06T00:00:00Z"},
            "artifacts": {"scout_summary": ".flow/runs/scout/scout-summary.md"},
        }
        (scout / "run.json").write_text(json.dumps(provisional))
        initial = service.build_envelope(self.root, provisional, self.source_id, None, "archive")
        initial["refinement"] = {
            "revision": "reviewed",
            "actor": "reviewer",
            "reason": "preserve source-backed scope",
            "base_generated_digest": model.digest(initial["generated"]),
            "patches": {"decision": copy.deepcopy(initial["generated"]["fields"]["decision"])},
        }
        abstract = scout / "abstract.json"
        abstract.write_bytes(store.encode(initial))
        # An incomplete pre-archive run is valid input to archive-scout.
        (scout / "run.json").write_text(json.dumps({"work_id": "scout", "artifacts": provisional["artifacts"]}))
        args = argparse.Namespace(work_id="scout", event="archive-scout", artifact=["scout_summary=.flow/runs/scout/scout-summary.md"], disposition=["capability_gaps=n/a", "memory=n/a"], note=None, json=True)
        original_build = service.build_envelope
        external = copy.deepcopy(initial)
        external["refinement"]["revision"] = "external"
        external["refinement"]["reason"] = "editor changed refinement after snapshot"

        def edit_between_snapshot_and_publish(*args):
            abstract.write_bytes(store.encode(external))
            return original_build(*args)

        with patch("fsutil.repo_root", return_value=self.root), patch.object(service, "build_envelope", side_effect=edit_between_snapshot_and_publish), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(service.archive_transition(args), 0)

        report = json.loads(output.getvalue())
        self.assertIn("archive base changed", str(report["enrichment_diagnostics"]))
        self.assertEqual(abstract.read_bytes(), store.encode(external))


if __name__ == "__main__":
    unittest.main()
