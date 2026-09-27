"""Stable optional-warning and strict-readiness behavior for MAF diagnostics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
import runtime_smoke


class MafDiagnosticTests(unittest.TestCase):
    def test_maf_smoke_is_strict_for_every_unready_state(self):
        states = ("not_installed", "interpreter_missing", "identity_mismatch", "lock_mismatch",
                  "package_missing", "version_mismatch", "runner_import_failed", "protocol_incompatible", "probe_timeout")
        for state in states:
            with self.subTest(state=state), patch("maf_runtime.probe", return_value={"state": state, "remedy": "repair"}):
                payload = runtime_smoke.smoke_payload("maf")
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["targets"][0]["static"][0]["detail"], state + ": repair")

    def test_maf_smoke_passes_only_ready(self):
        with patch("maf_runtime.probe", return_value={"state": "ready", "remedy": "none"}):
            self.assertTrue(runtime_smoke.smoke_payload("maf")["ok"])

    def test_command_exit_is_nonzero_for_unready_and_zero_for_ready(self):
        with patch("maf_runtime.probe", return_value={"state": "not_installed", "remedy": "repair"}):
            self.assertEqual(runtime_smoke.cmd_smoke(SimpleNamespace(target="maf", json=True)), 1)
        with patch("maf_runtime.probe", return_value={"state": "ready", "remedy": "none"}):
            self.assertEqual(runtime_smoke.cmd_smoke(SimpleNamespace(target="maf", json=True)), 0)


if __name__ == "__main__":
    unittest.main()
