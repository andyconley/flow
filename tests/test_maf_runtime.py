"""Focused contract tests for the optional managed MAF runtime boundary."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from maf_runtime import probe
import lifecycle


class MafRuntimeProbeTests(unittest.TestCase):
    def test_absent_managed_selection_is_not_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            result = probe(home=Path(temp))
        self.assertEqual(result["state"], "not_installed")
        self.assertEqual(result["source"], "managed")

    def test_explicit_invalid_override_never_falls_back(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"FLOW_MAF_PYTHON": "/missing/maf-python"}):
            result = probe(home=Path(temp))
        self.assertEqual(result["state"], "interpreter_missing")
        self.assertEqual(result["source"], "override")

    def test_cli_interpreter_without_maf_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            result = probe(python_path=os.sys.executable, home=Path(temp))
        self.assertIn(result["state"], {"package_missing", "runner_import_failed"})


class MafLifecycleTransactionTests(unittest.TestCase):
    def test_develop_conversion_restores_source_config_and_runtime_pointer_when_provision_fails(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            source.mkdir()
            (source / "prior.txt").write_text("prior source\n")
            config = root / "config.toml"
            config.write_bytes(b"mode = 'release'\n")
            pointer = root / "runtimes" / "maf" / "current.json"
            pointer.parent.mkdir(parents=True)
            pointer.write_bytes(b"{\"prior\":true}\n")
            clone = root / "clone"
            (clone / "cli").mkdir(parents=True)
            (clone / "cli" / "flow.py").write_text("# checkout marker\n")

            def write_config(value):
                config.write_text(repr(value))

            with patch.object(lifecycle, "SOURCE_DIR", source), \
                 patch.object(lifecycle, "FLOW_HOME", root), \
                 patch.object(lifecycle, "FLOW_CONFIG", config), \
                 patch.object(lifecycle, "_provision_maf_runtime", return_value=False), \
                 patch.object(lifecycle, "write_install_config", side_effect=write_config):
                self.assertEqual(lifecycle._convert_to_develop(clone), 1)

            self.assertEqual((source / "prior.txt").read_bytes(), b"prior source\n")
            self.assertEqual(config.read_bytes(), b"mode = 'release'\n")
            self.assertEqual(pointer.read_bytes(), b"{\"prior\":true}\n")


if __name__ == "__main__":
    unittest.main()
