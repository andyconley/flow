"""Focused contract tests for the optional managed MAF runtime boundary."""

from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from maf_runtime import probe, provision, runtime_root
from tests.maf_env import managed_wheelhouse
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

    def test_full_metadata_but_missing_runner_symbols_is_refused_without_managed_pointer(self):
        """Top-level imports and metadata cannot stand in for runner surfaces."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            environment = root / "broken"
            venv.EnvBuilder(with_pip=False).create(environment)
            interpreter = environment / "bin" / "python"
            site = Path(subprocess.check_output([str(interpreter), "-c", "import site; print(site.getsitepackages()[0])"], text=True).strip())
            from maf_runtime import RESOLVED_PACKAGES
            for package, version in RESOLVED_PACKAGES.items():
                info = site / (package.replace("-", "_") + ".dist-info")
                info.mkdir()
                (info / "METADATA").write_text(f"Name: {package}\nVersion: {version}\n")
            for module in ("agent_framework", "agent_framework_orchestrations"):
                package = site / module
                package.mkdir()
                (package / "__init__.py").write_text("# deliberately missing delivery symbols\n")
            home = root / "home"
            result = probe(python_path=str(interpreter), home=home)
            self.assertIn(result["state"], {"package_missing", "runner_import_failed"})
            self.assertFalse((home / "runtimes" / "maf" / "current.json").exists())

    def test_clean_release_managed_wheelhouse_runtime_reaches_initialized_child_without_override(self):
        """Release proof: install the locked wheels, then run a real child pre-provider."""
        self.assertTrue(managed_wheelhouse().is_dir(),
                        "release-managed MAF wheelhouse is required for this acceptance oracle")
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "FLOW_MAF_WHEELHOUSE": str(managed_wheelhouse()),
            "FLOW_MAF_PYTHON": "",
        }, clear=False):
            home = Path(temp)
            installed = provision(home=home, base_python=sys.executable)
            self.assertEqual(installed["state"], "ready")
            selected = Path(installed["identity"]["interpreter"])
            self.assertTrue(str(selected).startswith(str(runtime_root(home).resolve())))
            self.assertEqual(probe(home=home)["state"], "ready")
            root = Path(__file__).resolve().parents[1]
            child = subprocess.Popen([str(selected), "-m", "runtime.maf_runner.delivery_lead"], cwd=root,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.addCleanup(lambda: child.poll() is None and child.kill())
            assert child.stdin and child.stdout
            envelope = {"execution_protocol_version": 8, "attempt_id": "release-smoke", "checkpoint_dir": temp,
                        "maf_runtime": installed["identity"], "roster": [{"instance_id": "release-worker"}]}
            child.stdin.write(json.dumps({"protocol_version": 8, "type": "start", "envelope": envelope,
                                          "task": "prove initialization only"}) + "\n")
            child.stdin.flush()
            self.assertEqual(json.loads(child.stdout.readline())["type"], "runtime_ready")
            self.assertEqual(json.loads(child.stdout.readline()), {"protocol_version": 8, "type": "runtime_initialized"})
            child.kill()
            child.wait(timeout=5)
            child.stdin.close()
            child.stdout.close()
            child.stderr.close()

    @unittest.skipUnless(managed_wheelhouse().is_dir(), "local locked wheelhouse unavailable")
    def test_invalid_digest_target_is_quarantined_before_rebuild(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
            "FLOW_MAF_WHEELHOUSE": str(managed_wheelhouse()),
        }, clear=False):
            home = Path(temp)
            first = provision(home=home, base_python=sys.executable)
            target = Path(first["identity"]["interpreter"]).parents[1]
            (target / "bin" / "python").unlink()
            repaired = provision(home=home, base_python=sys.executable)
            self.assertEqual(repaired["state"], "ready")
            self.assertTrue(Path(repaired["identity"]["interpreter"]).is_file())
            self.assertEqual(len(list(target.parent.glob(target.name + ".invalid-*"))), 1)


class MafLifecycleTransactionTests(unittest.TestCase):
    def test_first_upgrade_activation_bridge_provisions_once_and_stamps_config(self):
        config = {"mode": "release", "version": "v0.38.0"}
        with patch.object(lifecycle, "read_install_config", return_value=config), \
             patch.object(lifecycle, "_provision_maf_runtime", return_value=True) as provisioned, \
             patch.object(lifecycle, "write_install_config") as written:
            self.assertEqual(lifecycle.activate_managed_maf_runtime(), {"attempted": True, "state": "succeeded"})
        provisioned.assert_called_once()
        written.assert_called_once()
        stamped = written.call_args.args[0]
        self.assertEqual(stamped["maf_runtime_activation_revision"], 1)
        self.assertEqual(stamped["maf_runtime_activation_state"], "succeeded")

    def test_failed_bridge_is_recorded_once_and_explicit_repair_is_separate(self):
        config = {"mode": "release", "version": "v0.38.0"}
        with patch.object(lifecycle, "read_install_config", side_effect=[config, config]), \
             patch.object(lifecycle, "_provision_maf_runtime", return_value=False) as provisioned, \
             patch.object(lifecycle, "write_install_config") as written:
            self.assertEqual(lifecycle.activate_managed_maf_runtime(), {"attempted": True, "state": "failed"})
            # Simulate the persisted state read by a later command: it must not retry.
            config.update(written.call_args.args[0])
            self.assertEqual(lifecycle.activate_managed_maf_runtime(), {"attempted": False, "state": "failed"})
        provisioned.assert_called_once()

    def test_install_config_round_trips_structured_activation_marker(self):
        with tempfile.TemporaryDirectory() as raw:
            config_path = Path(raw) / "config.toml"
            marker = {"mode": "release", "maf_runtime_activation_revision": 1,
                      "maf_runtime_activation_state": "failed", "maf_runtime_activation_detail": 'needs "repair"'}
            with patch.object(lifecycle, "FLOW_CONFIG", config_path):
                lifecycle.write_install_config(marker)
                restored = lifecycle.read_install_config()
            self.assertEqual(restored["maf_runtime_activation_revision"], 1)
            self.assertEqual(restored["maf_runtime_activation_state"], "failed")
            self.assertEqual(restored["maf_runtime_activation_detail"], 'needs "repair"')

    def test_unsupported_runtime_records_truthful_activation_state(self):
        with tempfile.TemporaryDirectory() as raw:
            config_path = Path(raw) / "config.toml"
            with patch.object(lifecycle, "FLOW_CONFIG", config_path):
                lifecycle.write_install_config({"mode": "release", "maf_runtime_activation_state": "pending"})
                lifecycle.record_managed_maf_runtime_unavailable("unsupported_runtime")
                restored = lifecycle.read_install_config()
            self.assertEqual(restored["maf_runtime_activation_state"], "unsupported")
            self.assertEqual(restored["maf_runtime_activation_detail"], "unsupported_runtime")

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
