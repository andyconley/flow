"""Generated help tables keep literal pipes inside their cells."""

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "regenerate_flow_help", REPO_ROOT / "scripts" / "regenerate-flow-help.py")
regenerate_flow_help = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(regenerate_flow_help)


class RenderTableTests(unittest.TestCase):
    def test_pipes_are_escaped_in_both_columns(self):
        table = regenerate_flow_help.render_table(
            [("`flow sync all|claude|codex`", "Pick one | or all")], ("Command", "Use when"))
        self.assertEqual(table.splitlines()[2],
                         r"| `flow sync all\|claude\|codex` | Pick one \| or all |")

    def test_every_row_has_exactly_two_cells(self):
        data = regenerate_flow_help.read_toml(regenerate_flow_help.FLOW_TOML)
        for name, build in regenerate_flow_help.BUILDERS.items():
            for row in build(data).splitlines():
                with self.subTest(table=name, row=row):
                    unescaped = row.replace(r"\|", "")
                    self.assertEqual(unescaped.count("|"), 3)


if __name__ == "__main__":
    unittest.main()
