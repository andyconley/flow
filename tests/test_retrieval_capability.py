"""Capability receipt and advisory proof without requiring a second Python build."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "cli"
sys.path.insert(0, str(CLI))
import archive_preflight as preflight
import diagnostics


class _NoFtsConnection:
    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def execute(self, statement):
        if "fts5" in statement:
            raise sqlite3.OperationalError("no such module: fts5")


class RetrievalCapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "home"
        self.home.mkdir()
        self.receipt = self.home / ".flow" / "retrieval-capabilities.json"

    def test_injected_fts5_failure_keeps_plain_sqlite_usable_and_names_runtime(self):
        with sqlite3.connect(":memory:") as database:
            database.execute("CREATE TABLE ordinary_store (id INTEGER PRIMARY KEY)")
            database.execute("INSERT INTO ordinary_store VALUES (1)")
            self.assertEqual(database.execute("SELECT count(*) FROM ordinary_store").fetchone()[0], 1)
        with patch.object(preflight.sqlite3, "connect", return_value=_NoFtsConnection()):
            result = preflight.probe(persist=False)

        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["capability"], "FTS5")
        self.assertEqual(result["runtime"], preflight.runtime_identity())
        self.assertIn("no such module: fts5", result["detail"])

    def test_missing_and_runtime_mismatched_receipts_require_doctor_without_probe(self):
        with patch.object(preflight, "receipt_path", return_value=self.receipt):
            self.assertEqual(preflight.current()["state"], "preflight_required")
            self.receipt.parent.mkdir(parents=True)
            stale = {"schema_version": 1, "state": "available", "runtime": preflight.runtime_identity()}
            stale["runtime"] = {**stale["runtime"], "python": "0.0.0"}
            self.receipt.write_text(json.dumps(stale))
            with patch.object(preflight, "probe", side_effect=AssertionError("query must not probe")):
                result = preflight.current()

        self.assertEqual(result["state"], "preflight_required")
        self.assertIn("run flow doctor", result["remedy"])

    def test_doctor_unavailable_fts5_is_informational_when_other_diagnostics_are_clean(self):
        root = self.home / "project"
        (root / ".flow").mkdir(parents=True)
        unavailable = {"state": "unavailable", "capability": "FTS5", "runtime": preflight.runtime_identity(), "remedy": "select a compatible interpreter"}
        original_diagnostic = diagnostics.diagnostic

        def clean_telemetry(identifier, status, severity, category, summary, **kwargs):
            if identifier.startswith("telemetry."):
                return original_diagnostic(identifier, "ok", "info", "ok", summary, **kwargs)
            return original_diagnostic(identifier, status, severity, category, summary, **kwargs)

        with (
            patch.object(diagnostics, "repo_root", return_value=root),
            patch.object(diagnostics, "FLOW_HOME", self.home / ".flow"),
            patch.object(diagnostics, "HOME", self.home),
            patch.object(diagnostics, "SCAFFOLD_DIR", self.home / "no-scaffold"),
            patch.object(diagnostics, "_doctor_diagnostics", return_value=[]),
            patch.object(diagnostics, "diagnostic", side_effect=clean_telemetry),
            patch.object(preflight, "probe", return_value=unavailable),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            code = diagnostics.doctor(as_json=True, check=True)

        payload = json.loads(output.getvalue())
        retrieval = next(row for row in payload["diagnostics"] if row["id"] == "retrieval.fts5")
        self.assertEqual(code, 0)
        self.assertEqual(retrieval["severity"], "info")
        self.assertEqual(retrieval["status"], "warning")
        self.assertEqual(payload["warnings"], 0)

    def test_isolated_develop_install_probes_the_selected_interpreter(self):
        env = {**__import__("os").environ, "HOME": str(self.home), "FLOW_PYTHON": sys.executable}
        result = subprocess.run([str(ROOT / "install-flow.sh"), "--develop"], cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = self.home / ".flow" / "retrieval-capabilities.json"
        value = json.loads(receipt.read_text())
        self.assertEqual(value["runtime"]["executable"], str(Path(sys.executable).resolve()))
        self.assertIn("Python:", result.stdout)

    def test_isolated_install_succeeds_and_persists_unavailable_receipt_when_fts5_is_injected_missing(self):
        injection = self.home / "injection"
        injection.mkdir()
        (injection / "sitecustomize.py").write_text(
            "import sqlite3\n"
            "_connect = sqlite3.connect\n"
            "class Connection:\n"
            "    def __init__(self, *args, **kwargs): self._inner = _connect(*args, **kwargs)\n"
            "    def __enter__(self): self._inner.__enter__(); return self\n"
            "    def __exit__(self, *args): return self._inner.__exit__(*args)\n"
            "    def execute(self, statement, *args):\n"
            "        if 'VIRTUAL TABLE probe USING fts5' in statement: raise sqlite3.OperationalError('no such module: fts5 (test injection)')\n"
            "        return self._inner.execute(statement, *args)\n"
            "    def __getattr__(self, name): return getattr(self._inner, name)\n"
            "def connect(*args, **kwargs): return Connection(*args, **kwargs)\n"
            "sqlite3.connect = connect\n"
        )
        env = {
            **__import__("os").environ,
            "HOME": str(self.home),
            "FLOW_PYTHON": sys.executable,
            "PYTHONPATH": str(injection),
        }
        install = subprocess.run([str(ROOT / "install-flow.sh"), "--develop"], cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)

        self.assertEqual(install.returncode, 0, install.stderr)
        receipt = json.loads((self.home / ".flow" / "retrieval-capabilities.json").read_text())
        self.assertEqual(receipt["state"], "unavailable")
        self.assertEqual(receipt["runtime"]["executable"], str(Path(sys.executable).resolve()))
        self.assertIn("no such module: fts5", receipt["detail"])
        self.assertIn("retrieval FTS5: unavailable", install.stdout)
        self.assertIn(receipt["runtime"]["python"], install.stdout)
        self.assertIn(receipt["runtime"]["sqlite"], install.stdout)
        self.assertIn(preflight.remedy(), install.stdout)

        plain_sqlite = subprocess.run(
            [sys.executable, "-c", "import sqlite3; db=sqlite3.connect(':memory:'); db.execute('create table plain_store (id integer)'); db.execute('insert into plain_store values (1)'); print(db.execute('select count(*) from plain_store').fetchone()[0])"],
            env=env,
            text=True,
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(plain_sqlite.returncode, 0, plain_sqlite.stderr)
        self.assertEqual(plain_sqlite.stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()
