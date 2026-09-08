import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class DocumentationAuthorityTests(unittest.TestCase):
    def test_project_authority_surfaces_use_the_four_part_model(self):
        paths = [
            REPO_ROOT / "docs" / "architecture.md",
            REPO_ROOT / "docs" / "file-structure.md",
            REPO_ROOT / "scaffolds" / "default" / "FRAMEWORK.md",
            REPO_ROOT / "scaffolds" / "default" / "memory" / "STATE.md",
            REPO_ROOT / "scaffolds" / "default" / "commands" / "flow-help.md",
        ]
        combined = "\n".join(path.read_text() for path in paths)
        for phrase in (
            "archive envelopes",
            "ADRs",
            "transient",
            "companion",
        ):
            self.assertIn(phrase, combined)

        forbidden = (
            "Durable facts and decisions live in the active runtime memory provider",
            "They live in the active runtime's durable memory provider",
            "Durable facts and decisions → the active runtime's durable memory provider",
            "durable facts live in the runtime memory provider",
        )
        for path in paths:
            content = path.read_text()
            for phrase in forbidden:
                self.assertNotIn(phrase, content, f"stale authority wording in {path}")

    def test_archive_indexes_are_documented_as_derived(self):
        architecture = (REPO_ROOT / "docs" / "architecture.md").read_text()
        self.assertIn("Derived `.flow/.cache/archive/`", architecture)
        self.assertIn("transient merged query table", architecture)


if __name__ == "__main__":
    unittest.main()
