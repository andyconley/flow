"""Source discovery and consistent-observation authority cases."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))

import archive_model as model
import archive_sources as sources


SOURCE_ID = "44444444-4444-4444-8444-444444444444"
PARENT_ID = "55555555-5555-4555-8555-555555555555"


class SourceObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        self.root.mkdir()
        self.overlay(self.root, SOURCE_ID)

    def overlay(self, root, source_id):
        (root / ".flow" / "runs").mkdir(parents=True, exist_ok=True)
        (root / ".flow" / "PROJECT.md").write_text("# Project\n")
        (root / ".flow" / "identity.json").write_text(json.dumps({"schema_version": 1, "source_id": source_id}))

    def closed_run(self, work, *, envelope=None, event=True):
        directory = self.root / ".flow" / "runs" / work
        directory.mkdir(exist_ok=True)
        closed_at = "2026-09-06T00:00:00Z"
        run = {"schema_version": 1, "work_id": work, "state": "archived", "gates": {"archive": closed_at}, "artifacts": {}}
        (directory / "run.json").write_text(json.dumps(run))
        if event:
            (directory / "events.jsonl").write_text(json.dumps({"event": "archive", "to": "archived", "at": closed_at, "dispositions": {}}) + "\n")
        if envelope is not None:
            (directory / "abstract.json").write_text(json.dumps(envelope))
        return directory

    def test_duplicate_uuid_context_is_ambiguous_and_not_nearest_wins(self):
        child = self.root / "child"
        self.overlay(child, SOURCE_ID)
        context = sources.discover_context(child)
        self.assertEqual([entry["state"] for entry in context], ["ambiguous", "ambiguous"])
        self.assertEqual([entry["source_id"] for entry in context], [SOURCE_ID, SOURCE_ID])

    def test_source_partial_when_canonical_run_is_malformed(self):
        directory = self.root / ".flow" / "runs" / "bad"
        directory.mkdir()
        (directory / "run.json").write_text("not json")
        observed = sources.assess_source(self.root)
        self.assertEqual(observed["state"], "partial")
        self.assertEqual(observed["diagnostics"][0]["code"], "invalid_run")
        self.assertEqual(observed["inventory"], ["bad"])

    def test_repeated_source_changes_become_unstable(self):
        first = {"fingerprint": "one", "diagnostics": [], "state": "ready"}
        second = {"fingerprint": "two", "diagnostics": [], "state": "ready"}
        third = {"fingerprint": "three", "diagnostics": [], "state": "ready"}
        fourth = {"fingerprint": "four", "diagnostics": [], "state": "ready"}
        with patch.object(sources, "_observe", side_effect=[first, second, third, fourth]):
            observed = sources.assess_source(self.root)
        self.assertEqual(observed["state"], "unstable")
        self.assertEqual(observed["diagnostics"][-1]["code"], "source_changed_during_capture")

    def test_anchored_controls_without_generated_prose_remain_graph_evidence(self):
        target = self.closed_run("target")
        evidence_path = self.root / ".flow" / "runs" / "control" / "evidence.md"
        evidence_path.parent.mkdir()
        evidence_path.write_text("# Decision\nReplace target.\n")
        pointer = {
            "source_id": SOURCE_ID,
            "work_id": "control",
            "path": "runs/control/evidence.md",
            "selector": "heading:decision:1",
            "digest": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
        }
        declarations = {"supersedes": [{"target": {"source_id": SOURCE_ID, "work_id": "target"}, "whole_run": True, "rationale": "replacement", "actor": "engineer", "evidence": [pointer]}]}
        envelope = {"schema_version": 1, "identity": {"source_id": SOURCE_ID, "work_id": "control"}, "declarations": declarations, "refinement": None, "provenance": {"origin": "declaration"}}
        control = self.closed_run("control", envelope=envelope)
        event = json.loads((control / "events.jsonl").read_text())
        event["dispositions"]["archive_declarations"] = model.declaration_digest(envelope["identity"], declarations)
        (control / "events.jsonl").write_text(json.dumps(event) + "\n")
        observed = sources.assess_source(self.root)
        rows = {row["work_id"]: row for row in observed["records"]}
        self.assertEqual(rows["control"]["closure_status"], "anchored")
        self.assertEqual(rows["control"]["declaration_status"], "anchored")
        self.assertFalse(rows["control"]["content_current"])
        from archive_graph import resolve_graph
        graph = resolve_graph([observed])
        self.assertEqual(graph["records"][rows["target"]["qualified_id"]]["status"], "superseded")

    def test_compact_observation_preserves_fingerprint_and_authority(self):
        import archive_service
        directory = self.closed_run("one")
        (directory / "archive.md").write_text("## Work Closed\n" + "SQLite durable decision. " * 2000 + "\n")
        run = json.loads((directory / "run.json").read_text())
        run["artifacts"] = {"archive": ".flow/runs/one/archive.md"}
        (directory / "run.json").write_text(json.dumps(run))
        self.assertEqual(archive_service.backfill(self.root, apply=True, yes=True)["state"], "complete")
        full = sources.assess_source(self.root)
        compact = sources.assess_source(self.root, compact=True)
        from archive_graph import resolve_graph
        self.assertEqual(full["fingerprint"], compact["fingerprint"])
        self.assertEqual(resolve_graph([full]), resolve_graph([compact]))
        self.assertTrue(compact["records"][0]["content_current"])
        self.assertNotIn("envelope", compact["records"][0])
        self.assertNotIn("run", compact["records"][0])
        self.assertLess(len(json.dumps(compact)), len(json.dumps(full)) / 5)

    def test_missing_closure_event_is_not_a_closed_authority_record(self):
        self.closed_run("torn", event=False)
        observed = sources.assess_source(self.root)
        record = observed["records"][0]
        self.assertEqual(record["closure_status"], "unverified")
        from archive_graph import resolve_graph
        self.assertEqual(resolve_graph([observed])["records"][record["qualified_id"]]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
