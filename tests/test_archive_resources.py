"""Resource behavior for the streamed transient archive query corpus."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))
import archive_preflight as preflight
import archive_query as query
import archive_service as service
import archive_store as store
from archive_sources import assess_source


class ArchiveResourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        (self.root / ".flow" / "runs").mkdir(parents=True)
        (self.root / ".flow" / "PROJECT.md").write_text("# Project\n")
        with store.writer_lock(self.root):
            store.ensure_ignore(self.root)
            self.source_id = store.ensure_identity(self.root)
        self.available = patch.object(preflight, "current", return_value={"state": "available"})
        self.available.start()
        self.addCleanup(self.available.stop)

    def add_run(self, work, decision=None):
        directory = self.root / ".flow" / "runs" / work
        directory.mkdir()
        (directory / "archive.md").write_text(
            "## Work Closed\n" + (decision or "Keep SQLite storage per overlay for " + work + ".") + "\n\n"
            "## Rationale\n" + ("durable local evidence " * 120) + "\n"
        )
        at = "2026-09-06T00:00:00Z"
        run = {"schema_version": 1, "work_id": work, "state": "archived", "gates": {"archive": at}, "artifacts": {"archive": ".flow/runs/" + work + "/archive.md"}}
        event = {"event": "archive", "at": at, "to": "archived", "dispositions": {"archive_enrichment": "1"}}
        (directory / "run.json").write_text(json.dumps(run))
        (directory / "events.jsonl").write_text(json.dumps(event) + "\n")

    def test_large_corpus_streams_projection_and_cleans_transient_database(self):
        for number in range(24):
            self.add_run(f"work-{number:02d}")
        result = service.backfill(self.root, apply=True, yes=True)
        self.assertEqual(result["state"], "complete", result)
        self.assertEqual(query.rebuild(self.root)["state"], "complete")
        _, rows = store.read_projection(self.root)
        expected = [row["qualified_id"] for row in query.rank(rows, "SQLite")[:5]]
        temporary_before = set(Path(tempfile.gettempdir()).glob("flow-archive-query-*.sqlite3"))
        with patch.object(query, "read_projection", side_effect=AssertionError("search must stream projection rows")):
            actual = query.search(self.root, "SQLite", max_output_bytes=1_000_000)
        temporary_after = set(Path(tempfile.gettempdir()).glob("flow-archive-query-*.sqlite3"))
        self.assertEqual(actual["state"], "complete")
        self.assertEqual([hit["qualified_id"] for hit in actual["hits"]], expected)
        self.assertEqual(actual["total_matches"], 24)
        self.assertEqual(temporary_after, temporary_before)

    def test_unknown_rows_do_not_change_eligible_bm25_or_final_lookup_checks(self):
        self.add_run("first", "SQLite retained decision.")
        self.add_run("second", "SQLite storage decision with extra terms.")
        self.add_run("unknown", "SQLite " + ("storage " * 300))
        self.assertEqual(service.backfill(self.root, apply=True, yes=True)["state"], "complete")
        self.assertEqual(query.rebuild(self.root)["state"], "complete")
        _, rows = store.read_projection(self.root)
        source = assess_source(self.root, compact=True)
        source["distance"] = 0
        graph = {"records": {row["qualified_id"]: {"status": "unknown" if row["work_id"] == "unknown" else "current", "supersedes": [], "superseded_by": []} for row in rows}}
        expected = [row["qualified_id"] for row in query.rank([row for row in rows if row["work_id"] != "unknown"], "SQLite")]
        with query._stream_ranked([source], graph, "SQLite", None, None, None, False, 5) as (ordered, total, uncertain):
            actual = list(ordered)
        self.assertEqual([row["qualified_id"] for row in actual], expected)
        self.assertEqual(total, 2)
        self.assertEqual(uncertain, 1)
        with self.assertRaisesRegex(ValueError, "projection changed"):
            store.projection_record(self.root, "first", "not-the-current-fingerprint", query.VERSIONS)

    def test_verified_prefix_assesses_each_display_source_twice_not_each_row(self):
        for number in range(6):
            self.add_run(f"work-{number}")
        self.assertEqual(service.backfill(self.root, apply=True, yes=True)["state"], "complete")
        self.assertEqual(query.rebuild(self.root)["state"], "complete")
        source = assess_source(self.root, compact=True)
        source["distance"] = 0
        graph = {"records": {row["qualified_id"]: {"status": "current", "supersedes": [], "superseded_by": []} for row in source["records"]}}
        real_assess = query.assess_source
        calls = []

        def counted(root, compact=False):
            calls.append((Path(root), compact))
            return real_assess(root, compact=compact)

        with patch.object(query, "assess_source", side_effect=counted):
            with query._stream_ranked([source], graph, "SQLite", None, None, None, False, 5) as (ordered, total, uncertain):
                rows = list(ordered)
        self.assertEqual((len(rows), total, uncertain), (5, 6, 0))
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(root.resolve() == self.root.resolve() and compact for root, compact in calls))

    def test_zero_match_source_change_rejects_query_counts(self):
        self.add_run("first")
        self.assertEqual(service.backfill(self.root, apply=True, yes=True)["state"], "complete")
        self.assertEqual(query.rebuild(self.root)["state"], "complete")
        source = assess_source(self.root, compact=True)
        source["distance"] = 0
        graph = {"records": {row["qualified_id"]: {"status": "current", "supersedes": [], "superseded_by": []} for row in source["records"]}}
        with self.assertRaisesRegex(ValueError, "verifying query counts"):
            with query._stream_ranked([source], graph, "unmatchedtoken", None, None, None, False, 5) as (ordered, total, uncertain):
                self.assertEqual(total, 0)
                (self.root / ".flow" / "runs" / "first" / "archive.md").write_text("## Work Closed\nChanged evidence.\n")
                self.assertEqual(list(ordered), [])

    def test_huge_top_k_with_tiny_budget_loads_only_first_nonfitting_payload(self):
        for number in range(24):
            self.add_run(f"work-{number:02d}")
        self.assertEqual(service.backfill(self.root, apply=True, yes=True)["state"], "complete")
        self.assertEqual(query.rebuild(self.root)["state"], "complete")
        real_record = query.projection_record
        loads = 0

        def counted(*args, **kwargs):
            nonlocal loads
            loads += 1
            return real_record(*args, **kwargs)

        with patch.object(query, "projection_record", side_effect=counted):
            result = query.search(self.root, "SQLite", top_k=1_000_000, max_output_bytes=1200)
        self.assertEqual(result["shown"], 0)
        self.assertEqual(result["total_matches"], 24)
        self.assertEqual(result["reason"], "no_hit_fits")
        self.assertEqual(loads, 1)


if __name__ == "__main__":
    unittest.main()
