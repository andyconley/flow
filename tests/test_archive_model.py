"""Pure archive schema and final-source selection contract tests."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))
import archive_extract as extract_module
import archive_model as model


SOURCE_ID = "8ac834b7-5c53-4133-a7f6-a8912f0d8f07"


class ArchiveModelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run_dir = self.root / ".flow" / "runs" / "one"
        self.run_dir.mkdir(parents=True)

    def archived_run(self, artifacts):
        value = {
            "schema_version": 1,
            "work_id": "one",
            "state": "archived",
            "gates": {"archive": "2026-09-06T00:00:00Z"},
            "artifacts": artifacts,
        }
        (self.run_dir / "run.json").write_text(json.dumps(value))
        return value

    def extract(self, text, role="archive", filename="archive.md"):
        path = self.run_dir / filename
        path.write_text(text)
        return extract_module.extract(
            self.root,
            self.archived_run({role: f".flow/runs/one/{filename}"}),
            SOURCE_ID,
        )

    def test_canonical_digest_is_order_independent_and_rejects_nonfinite_numbers(self):
        self.assertEqual(model.canonical_json({"b": 1, "a": "é"}), '{"a":"é","b":1}')
        self.assertEqual(model.digest({"a": 1, "b": 2}), model.digest({"b": 2, "a": 1}))
        with self.assertRaises(ValueError):
            model.canonical_json({"value": float("nan")})

    def test_strict_versions_and_sha256_values_are_required(self):
        generated = self.extract("## Work Closed\nKeep the decision.\n")
        envelope = {
            "schema_version": 1,
            "identity": {"source_id": SOURCE_ID, "work_id": "one"},
            "generated": generated,
            "declarations": {},
            "refinement": None,
            "provenance": {},
        }
        model.validate_envelope(envelope)
        for path, bad in (
            (("schema_version",), True),
            (("generated", "extractor_version"), True),
            (("generated", "source_digest"), "g" * 64),
        ):
            invalid = copy.deepcopy(envelope)
            cursor = invalid
            for part in path[:-1]:
                cursor = cursor[part]
            cursor[path[-1]] = bad
            with self.assertRaises(ValueError):
                model.validate_envelope(invalid)

    def test_conflict_alternatives_are_validated_recursively(self):
        source = {"source_id": SOURCE_ID, "work_id": "one", "path": "runs/one/archive.md", "selector": "heading:work closed:1", "digest": "a" * 64}
        field = {
            "state": "conflicted",
            "value": None,
            "sources": [source],
            "reason": "two selected passages differ",
            "alternatives": [
                {"state": "known", "value": "one", "sources": [source]},
                {"state": "unknown", "value": None, "sources": [], "reason": "not actually a value"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "alternatives"):
            model.validate_field(field)

    def test_archive_requires_work_closed_not_generic_decision_heading(self):
        with self.assertRaisesRegex(ValueError, "no decision/outcome heading"):
            self.extract("## Decision\nDo not treat this as final authority.\n")

    def test_scout_scope_precedes_handback_and_handback_is_fallback(self):
        generated = self.extract("## Scope\nUse the scout scope.\n\n## Handback\nDo not replace scope.\n", "scout_summary", "scout-summary.md")
        self.assertEqual(generated["fields"]["decision"]["value"], "Use the scout scope.")
        generated = self.extract("## Handback\nUse the scout handback.\n", "scout_summary", "scout-summary.md")
        self.assertEqual(generated["fields"]["decision"]["value"], "Use the scout handback.")

    def test_explicit_selection_must_resolve_exact_selector(self):
        path = self.run_dir / "archive.md"
        path.write_text("## Work Closed\nKeep the final decision.\n")
        run = self.archived_run({"archive": ".flow/runs/one/archive.md"})
        source = {
            "source_id": SOURCE_ID,
            "work_id": "one",
            "path": "runs/one/archive.md",
            "selector": "heading:missing:1",
            "digest": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
        }
        declarations = {"selections": [{"field": "decision", "actor": "reviewer", "reason": "explicit source", "source": source}]}
        with self.assertRaisesRegex(ValueError, "does not resolve"):
            extract_module.extract(self.root, run, SOURCE_ID, declarations)

    def test_explicit_selection_is_used_instead_of_being_ignored(self):
        path = self.run_dir / "archive.md"
        path.write_text("## Work Closed\nKeep the final decision.\n")
        run = self.archived_run({"archive": ".flow/runs/one/archive.md"})
        source = {
            "source_id": SOURCE_ID,
            "work_id": "one",
            "path": "runs/one/archive.md",
            "selector": "heading:work closed:1",
            "digest": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
        }
        declarations = {"selections": [{"field": "rationale", "actor": "reviewer", "reason": "the final outcome carries the reason", "source": source}]}
        generated = extract_module.extract(self.root, run, SOURCE_ID, declarations)
        self.assertEqual(generated["fields"]["rationale"]["state"], "known")
        self.assertEqual(generated["fields"]["rationale"]["value"], "Keep the final decision.")

    def test_explicit_selection_cannot_take_over_canonical_closure_time(self):
        source = {"source_id": SOURCE_ID, "work_id": "one", "path": "runs/one/archive.md", "selector": "heading:work closed:1", "digest": "a" * 64}
        with self.assertRaisesRegex(ValueError, "invalid explicit source selection"):
            model.validate_declarations(
                {"selections": [{"field": "closed_at", "actor": "reviewer", "reason": "not allowed", "source": source}]},
                {"source_id": SOURCE_ID, "work_id": "one"},
            )


if __name__ == "__main__":
    unittest.main()
