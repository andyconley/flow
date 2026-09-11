import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "architecture_evidence" / "adapters" / "tach.py"
SPEC = importlib.util.spec_from_file_location("architecture_evidence_tach", MODULE_PATH)
tach = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(tach)


class TachAdapterTests(unittest.TestCase):
    def _source(self, root: Path) -> Path:
        source = root / "source"
        cli = source / "cli"
        cli.mkdir(parents=True)
        (cli / "alpha.py").write_text(
            "import beta\nfrom beta import value\n", encoding="utf-8"
        )
        (cli / "beta.py").write_text("value = 1\n", encoding="utf-8")
        return source

    def _fake_run(self, missing_source=False):
        def run(arguments, *, cwd, environment, timeout):
            if arguments[1:] == ["--version"]:
                return tach.subprocess.CompletedProcess(
                    arguments, 0, "tach 0.35.0\n", ""
                )
            if arguments[1] == "map":
                output = Path(arguments[arguments.index("-o") + 1])
                output.write_text(
                    json.dumps({"cli/alpha.py": ["cli/beta.py"]}) + "\n",
                    encoding="utf-8",
                )
                return tach.subprocess.CompletedProcess(arguments, 0, "", "")
            if arguments[1:3] == ["report", "cli/alpha.py"]:
                stdout = "[ Dependencies ]\n"
                if not missing_source:
                    stdout += (
                        "alpha.py:1: Import 'beta'\nalpha.py:2: Import 'beta.value'\n"
                    )
                return tach.subprocess.CompletedProcess(arguments, 0, stdout, "")
            return tach.subprocess.CompletedProcess(
                arguments, 0, "No dependencies found.\n", ""
            )

        return run

    def test_collects_map_and_all_exact_source_lines_without_touching_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._source(root)
            executable = root / "tach"
            executable.write_bytes(b"fake tach")
            before = {
                path.relative_to(source): path.read_bytes()
                for path in source.rglob("*")
                if path.is_file()
            }
            with mock.patch.object(tach, "_run", side_effect=self._fake_run()):
                graph, metadata, gaps = tach.collect_graph(
                    source,
                    {"tach_executable": str(executable), "source_roots": ["cli"]},
                    root / "raw",
                )
            edge = graph["edges"][0]
            self.assertEqual(edge["from"], "python:alpha")
            self.assertEqual(edge["to"], "python:beta")
            self.assertEqual(
                edge["sources"],
                [
                    {"path": "cli/alpha.py", "start_line": 1, "end_line": 1},
                    {"path": "cli/alpha.py", "start_line": 2, "end_line": 2},
                ],
            )
            self.assertEqual(gaps, [])
            self.assertEqual(metadata["capabilities"]["dynamic_imports"], "unsupported")
            self.assertEqual(metadata["tool_version"], "0.35.0")
            self.assertTrue((root / "raw" / "tach-map.json").is_file())
            report = root / "raw" / "tach-reports" / "cli__alpha.py.txt"
            self.assertIn(
                "alpha.py:1: Import 'beta'", report.read_text(encoding="utf-8")
            )
            self.assertNotIn("--raw", metadata["command_contract"]["report"])
            after = {
                path.relative_to(source): path.read_bytes()
                for path in source.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)
            self.assertFalse((source / "tach.toml").exists())
            self.assertFalse((source / "cli" / "pyproject.toml").exists())

    def test_missing_map_to_report_join_is_required_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._source(root)
            executable = root / "tach"
            executable.write_bytes(b"fake tach")
            with mock.patch.object(
                tach, "_run", side_effect=self._fake_run(missing_source=True)
            ):
                graph, _, gaps = tach.collect_graph(
                    source,
                    {"tach_executable": str(executable), "source_roots": ["cli"]},
                    root / "raw",
                )
            self.assertEqual(graph["edges"][0]["sources"], [])
            self.assertTrue(
                any(
                    gap.startswith("tach:missing-source:python:alpha:python:beta")
                    for gap in gaps
                )
            )

    def test_rejects_relative_executable_and_unsafe_source_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self._source(root)
            with self.assertRaisesRegex(ValueError, "absolute file"):
                tach.collect_graph(
                    source,
                    {"tach_executable": "tach", "source_roots": ["cli"]},
                    root / "raw",
                )
            executable = root / "tach"
            executable.write_bytes(b"fake tach")
            with self.assertRaisesRegex(ValueError, "unsafe source root"):
                tach.collect_graph(
                    source,
                    {"tach_executable": str(executable), "source_roots": ["../cli"]},
                    root / "raw-two",
                )


if __name__ == "__main__":
    unittest.main()
