"""Pure graph authority cases, independent of extraction and SQLite."""
from pathlib import Path
import sys
import unittest
import uuid

CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))

from archive_graph import resolve_graph


CHILD = "11111111-1111-4111-8111-111111111111"
PARENT = "22222222-2222-4222-8222-222222222222"
GRAND = "33333333-3333-4333-8333-333333333333"


def row(source_id, work_id, targets=(), *, closure="anchored", declarations="anchored"):
    identity = {"source_id": source_id, "work_id": work_id}
    return {
        "identity": identity,
        "qualified_id": source_id + ":" + work_id,
        "closure_status": closure,
        "declaration_status": declarations if targets else "none",
        "declarations": {
            "supersedes": [
                {"target": {"source_id": target_source, "work_id": target_work}, "whole_run": True}
                for target_source, target_work in targets
            ]
        },
    }


def source(source_id, records, state="ready"):
    return {"source_id": source_id, "records": records, "state": state}


class GraphAuthorityTests(unittest.TestCase):
    def test_chain_marks_every_replaced_ancestor_superseded(self):
        a = row(GRAND, "a")
        b = row(PARENT, "b", [(GRAND, "a")])
        c = row(CHILD, "c", [(PARENT, "b")])
        result = resolve_graph([source(CHILD, [c]), source(PARENT, [b]), source(GRAND, [a])])
        self.assertEqual(result["records"][a["qualified_id"]]["status"], "superseded")
        self.assertEqual(result["records"][b["qualified_id"]]["status"], "superseded")
        self.assertEqual(result["records"][c["qualified_id"]]["status"], "current")

    def test_fanout_does_not_invent_precedence_between_replacements(self):
        old = row(PARENT, "old")
        first = row(CHILD, "first", [(PARENT, "old")])
        second = row(CHILD, "second", [(PARENT, "old")])
        result = resolve_graph([source(CHILD, [first, second]), source(PARENT, [old])])
        self.assertEqual(result["records"][old["qualified_id"]]["status"], "superseded")
        self.assertEqual(result["records"][first["qualified_id"]]["status"], "current")
        self.assertEqual(result["records"][second["qualified_id"]]["status"], "current")
        self.assertEqual(
            result["records"][old["qualified_id"]]["superseded_by"],
            sorted([first["qualified_id"], second["qualified_id"]]),
        )

    def test_cycle_is_unknown_and_never_suppresses_members(self):
        a = row(CHILD, "a", [(CHILD, "b")])
        b = row(CHILD, "b", [(CHILD, "a")])
        result = resolve_graph([source(CHILD, [a, b])])
        self.assertEqual(result["records"][a["qualified_id"]]["status"], "unknown")
        self.assertEqual(result["records"][b["qualified_id"]]["status"], "unknown")
        self.assertIn("supersession_cycle", [d["code"] for d in result["diagnostics"]])

    def test_missing_target_is_unknown_not_a_guessed_current_record(self):
        declaring = row(CHILD, "new", [(PARENT, "missing")])
        result = resolve_graph([source(CHILD, [declaring]), source(PARENT, [])])
        self.assertEqual(result["records"][declaring["qualified_id"]]["status"], "unknown")
        self.assertIn("invalid_supersession", [d["code"] for d in result["diagnostics"]])

    def test_child_to_parent_is_scoped_but_parent_to_child_is_rejected(self):
        parent = row(PARENT, "parent")
        child = row(CHILD, "child", [(PARENT, "parent")])
        allowed = resolve_graph([source(CHILD, [child]), source(PARENT, [parent])])
        self.assertEqual(allowed["records"][parent["qualified_id"]]["status"], "superseded")

        downward_parent = row(PARENT, "parent", [(CHILD, "child")])
        plain_child = row(CHILD, "child")
        rejected = resolve_graph([source(CHILD, [plain_child]), source(PARENT, [downward_parent])])
        self.assertEqual(rejected["records"][downward_parent["qualified_id"]]["status"], "unknown")
        self.assertEqual(rejected["records"][plain_child["qualified_id"]]["status"], "unknown")

    def test_partial_child_context_only_marks_permitted_affected_scope_unknown(self):
        child = row(CHILD, "child")
        parent = row(PARENT, "parent")
        grand = row(GRAND, "grand")
        result = resolve_graph([
            source(CHILD, [child], state="partial"),
            source(PARENT, [parent]),
            source(GRAND, [grand]),
        ])
        self.assertEqual(result["records"][child["qualified_id"]]["status"], "unknown")
        self.assertEqual(result["records"][parent["qualified_id"]]["status"], "unknown")
        self.assertEqual(result["records"][grand["qualified_id"]]["status"], "unknown")

    def test_unverified_closure_never_becomes_current(self):
        unclosed = row(PARENT, "torn", closure="unverified")
        result = resolve_graph([source(PARENT, [unclosed])])
        self.assertEqual(result["records"][unclosed["qualified_id"]]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
