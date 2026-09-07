"""Acceptance regressions for archive-retrieval corrections AR-01 through AR-04."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch


CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))

import archive_model as model
import archive_preflight as preflight
import archive_query as query
import archive_service as service
import archive_store as store
import archive_sources as sources
import runstate
from archive_graph import resolve_graph


SOURCE_ID = "44444444-4444-4444-8444-444444444444"


class ArchiveAcceptanceRepairTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = (Path(self.temporary.name) / "project").resolve()
        self.root.mkdir()
        (self.root / ".flow" / "runs").mkdir(parents=True)
        (self.root / ".flow" / "PROJECT.md").write_text("# Project\n")
        with store.writer_lock(self.root):
            store.ensure_ignore(self.root)
            self.source_id = store.ensure_identity(self.root)
        available = patch.object(preflight, "current", return_value={"state": "available"})
        available.start()
        self.addCleanup(available.stop)

    def archived_run(self, work_id="closed"):
        directory = self.root / ".flow" / "runs" / work_id
        directory.mkdir()
        (directory / "archive.md").write_text(
            "## Work Closed\nKeep SQLite storage per overlay.\n\n## Rationale\nLocal ownership.\n"
        )
        at = "2026-09-06T00:00:00Z"
        (directory / "run.json").write_text(json.dumps({
            "schema_version": 1, "work_id": work_id, "state": "archived",
            "gates": {"archive": at},
            "artifacts": {"archive": f".flow/runs/{work_id}/archive.md"},
        }))
        (directory / "events.jsonl").write_text(json.dumps({
            "event": "archive", "to": "archived", "at": at,
            "dispositions": {"archive_enrichment": "1"},
        }) + "\n")
        return directory

    def indexed(self):
        self.assertEqual(service.backfill(self.root, apply=True, yes=True)["state"], "complete")
        self.assertEqual(query.rebuild(self.root)["state"], "complete")

    def test_malformed_identity_shapes_are_contained_for_closure_and_search(self):
        malformed = {
            "array": [], "string": "not-an-identity", "null": None,
            "empty-object": {}, "source-array": {"schema_version": 1, "source_id": []},
            "source-object": {"schema_version": 1, "source_id": {}},
            "source-null": {"schema_version": 1, "source_id": None},
            "source-number": {"schema_version": 1, "source_id": 1},
            "source-invalid-string": {"schema_version": 1, "source_id": "not-a-uuid"},
        }
        for name, identity in malformed.items():
            with self.subTest(name=name):
                root = (Path(self.temporary.name) / name).resolve()
                scout = root / ".flow" / "runs" / "scout"
                scout.mkdir(parents=True)
                (root / ".flow" / "PROJECT.md").write_text("# Project\n")
                (root / ".flow" / "identity.json").write_text(json.dumps(identity))
                (scout / "scout-summary.md").write_text("## Scope\nKeep SQLite.\n")
                args = argparse.Namespace(
                    work_id="scout", event="archive-scout",
                    artifact=["scout_summary=.flow/runs/scout/scout-summary.md"],
                    disposition=["capability_gaps=n/a", "memory=n/a"], note=None, json=True,
                )
                with patch("fsutil.repo_root", return_value=root), contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(service.archive_transition(args), 0)
                report = json.loads(output.getvalue())
                self.assertTrue(report["ok"])
                self.assertIn("prepare:", report["enrichment_diagnostics"][0])
                self.assertEqual(json.loads((scout / "run.json").read_text())["state"], "archived")
                result = query.search(root, "SQLite")
                self.assertEqual(result["state"], "unavailable")
                self.assertTrue(result["unavailable_sources"])
                self.assertEqual(result["unavailable_sources"][0]["diagnostics"][0]["code"], "identity_unavailable")

    def test_nonarchived_lifecycle_activity_does_not_stale_an_archived_projection(self):
        self.archived_run()
        self.indexed()
        self.assertEqual(query.search(self.root, "SQLite")["state"], "complete")

        ok, _, errors = runstate.apply_transition("definition", "start-definition", root=self.root)
        self.assertTrue(ok, errors)
        ok, _, errors = runstate.apply_transition("definition", "pause", root=self.root)
        self.assertTrue(ok, errors)

        result = query.search(self.root, "SQLite")
        self.assertEqual(result["state"], "complete")
        self.assertEqual([hit["work_id"] for hit in result["hits"]], ["closed"])

    def test_new_archived_run_and_archived_run_removal_stale_the_projection(self):
        self.archived_run("existing")
        self.indexed()
        summary = self.root / ".flow" / "runs" / "new" / "scout-summary.md"
        summary.parent.mkdir()
        summary.write_text("## Scope\nNew archived authority.\n")
        ok, _, errors = runstate.apply_transition(
            "new", "archive-scout",
            artifacts={"scout_summary": ".flow/runs/new/scout-summary.md"},
            dispositions={"capability_gaps": "n/a", "memory": "n/a"}, root=self.root,
        )
        self.assertTrue(ok, errors)
        self.assertEqual(query.search(self.root, "SQLite")["state"], "unavailable")

        # Rebuild, then remove canonical archived evidence: this also must be stale.
        self.assertEqual(query.rebuild(self.root)["state"], "complete")
        for path in sorted((self.root / ".flow" / "runs" / "existing").rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
        (self.root / ".flow" / "runs" / "existing").rmdir()
        self.assertEqual(query.search(self.root, "SQLite")["state"], "unavailable")

    def _control_observation(self, *, anchored=True):
        target = self.archived_run("target")
        self.assertEqual(service.backfill(self.root, apply=True, yes=True)["state"], "complete")
        control = self.root / ".flow" / "runs" / "control"
        control.mkdir()
        evidence_path = control / "evidence.md"
        evidence_path.write_text("# Decision\nReplace target.\n")
        at = "2026-09-06T00:00:00Z"
        (control / "run.json").write_text(json.dumps({
            "schema_version": 1, "work_id": "control", "state": "archived",
            "gates": {"archive": at}, "artifacts": {},
        }))
        pointer = {
            "source_id": self.source_id, "work_id": "control", "path": "runs/control/evidence.md",
            "selector": "heading:decision:1", "digest": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        }
        declarations = {"supersedes": [{
            "target": {"source_id": self.source_id, "work_id": "target"}, "whole_run": True,
            "rationale": "replacement", "actor": "engineer", "evidence": [pointer],
        }]}
        envelope = {
            "schema_version": 1, "identity": {"source_id": self.source_id, "work_id": "control"},
            "declarations": declarations,
            # The malformed generated shape is intentionally not graph authority.
            "generated": {"extractor_version": 1, "source_digest": "0" * 64, "fields": []},
            "refinement": None, "provenance": {"origin": "test"},
        }
        (control / "abstract.json").write_text(json.dumps(envelope))
        digest = model.declaration_digest(envelope["identity"], declarations)
        (control / "events.jsonl").write_text(json.dumps({
            "event": "archive", "to": "archived", "at": at,
            "dispositions": {"archive_declarations": digest if anchored else "0" * 64},
        }) + "\n")
        return sources.assess_source(self.root)

    def test_malformed_prose_keeps_anchored_control_and_historical_link(self):
        observed = self._control_observation(anchored=True)
        rows = {row["work_id"]: row for row in observed["records"]}
        graph = resolve_graph([observed])
        target_id = rows["target"]["qualified_id"]
        control_id = rows["control"]["qualified_id"]
        self.assertFalse(rows["control"]["content_current"])
        self.assertEqual(rows["control"]["declaration_status"], "anchored")
        self.assertEqual(graph["records"][target_id]["status"], "superseded")
        self.assertEqual(graph["records"][target_id]["superseded_by"], [control_id])

    def test_malformed_superseder_is_graph_authority_but_not_a_search_payload(self):
        self._control_observation(anchored=True)
        self.assertEqual(query.rebuild(self.root)["state"], "complete")
        current = query.search(self.root, "SQLite")
        self.assertEqual(current["state"], "partial")
        self.assertEqual(current["hits"], [])
        self.assertTrue(any(row["code"] == "invalid_abstract_content" for row in current["diagnostics"]))
        history = query.search(self.root, "SQLite", include_superseded=True)
        self.assertEqual(history["state"], "partial")
        self.assertEqual([hit["work_id"] for hit in history["hits"]], ["target"])
        self.assertEqual(history["hits"][0]["superseded_by"], [self.source_id + ":control"])

    def test_malformed_prose_does_not_make_an_unanchored_control_authoritative(self):
        observed = self._control_observation(anchored=False)
        rows = {row["work_id"]: row for row in observed["records"]}
        graph = resolve_graph([observed])
        self.assertEqual(rows["control"]["declaration_status"], "unverified")
        self.assertEqual(graph["records"][rows["target"]["qualified_id"]]["status"], "unknown")

    def test_sqlite_storage_errors_use_temporary_storage_remedy_but_missing_fts_does_not(self):
        self.archived_run()
        self.indexed()

        cases = [
            ("full-code", "database or disk is full", getattr(sqlite3, "SQLITE_FULL", 13)),
            ("extended-ioerr", "disk I/O error", getattr(sqlite3, "SQLITE_IOERR", 10) | (7 << 8)),
            ("full-message-fallback", "database or disk is full", None),
            ("ioerr-message-fallback", "disk I/O error", None),
        ]
        for name, message, code in cases:
            with self.subTest(name=name):
                error = sqlite3.OperationalError(message)
                if code is not None:
                    error.sqlite_errorcode = code
                with patch.object(query, "_stream_ranked", side_effect=error):
                    result = query.search(self.root, "SQLite")
                self.assertEqual(result["reason"], "temporary_storage_unavailable")
                self.assertIn("TMPDIR", result["remedy"])

        with patch.object(query, "_stream_ranked", side_effect=sqlite3.OperationalError("no such module: fts5")):
            result = query.search(self.root, "SQLite")
        self.assertEqual(result["reason"], "fts5_failed_after_preflight")


if __name__ == "__main__":
    unittest.main()
