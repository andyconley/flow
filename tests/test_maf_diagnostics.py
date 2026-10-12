"""Replacement runtime readiness is strict without starting any provider."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
import runtime_smoke

class OpenHandsDiagnosticTests(unittest.TestCase):
    def test_missing_or_wrong_package_is_unready(self):
        for packages in ({"openhands-sdk": None}, {"openhands-sdk": "1.0.0"}):
            with self.subTest(packages=packages), patch("openhands_runtime.probe", return_value={"ready": False, "packages": packages}):
                self.assertFalse(runtime_smoke.smoke_payload("openhands")["ok"])
    def test_ready_is_reported_without_provider_startup(self):
        with patch("openhands_runtime.probe", return_value={"ready": True, "packages": {"openhands-sdk": "1.54.0"}}):
            self.assertTrue(runtime_smoke.smoke_payload("openhands")["ok"])
    def test_command_exit_matches_readiness(self):
        for ready in (False, True):
            with self.subTest(ready=ready), patch("openhands_runtime.probe", return_value={"ready": ready, "packages": {}}):
                self.assertEqual(runtime_smoke.cmd_smoke(SimpleNamespace(target="openhands", json=True)), 0 if ready else 1)
