"""Offline install/update contracts; no package index, models or live home."""
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import openhands_provision as op


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("FLOW_PYTHON", None)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.home = self.root / 'home'
        requirements = self.source / 'runtime/openhands/requirements.txt'
        requirements.parent.mkdir(parents=True)
        requirements.write_text('openhands-sdk==1.54.0\n')

    def test_custom_pinned_interpreter_is_reused_without_install(self):
        with patch.object(op, 'ready', return_value=True), patch.object(op.subprocess, 'run') as run:
            self.assertEqual(op.provision(self.source, self.home, '/custom/python'), '/custom/python')
            run.assert_not_called()

    def test_fresh_provision_repeat_and_pointer(self):
        built = set()
        def run(command, **kwargs):
            if command[1:3] == ['-m', 'venv']:
                Path(command[3]).mkdir(parents=True)
            elif command[1:4] == ['-m', 'pip', 'install']:
                built.add(command[0])
        with patch.object(op, 'ready', side_effect=lambda p: p in built), patch.object(op, 'compatible', return_value=True), patch.object(op.subprocess, 'run', side_effect=run) as runner:
            python = op.provision(self.source, self.home, '/base/python')
            self.assertEqual(json.loads((self.home/'runtimes/openhands/current.json').read_text())['interpreter'], python)
            self.assertEqual(op.provision(self.source, self.home, '/base/python'), python)
            self.assertEqual(runner.call_count, 2)

    def test_failed_dependency_install_preserves_previous_pointer(self):
        pointer = self.home/'runtimes/openhands/current.json'
        pointer.parent.mkdir(parents=True)
        before = '{"interpreter":"/prior/python"}'
        pointer.write_text(before)
        with patch.object(op, 'ready', return_value=False), patch.object(op, 'compatible', return_value=True), patch.object(op.subprocess, 'run', side_effect=RuntimeError('index unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'index unavailable'):
                op.provision(self.source, self.home, '/base/python')
        self.assertEqual(pointer.read_text(), before)
        self.assertEqual(list(pointer.parent.glob('1.54.0-*')), [])

    def test_missing_supported_python_is_clear_failure(self):
        with patch.object(op, 'ready', return_value=False), patch.object(op, 'compatible', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'Python 3.12'):
                op.provision(self.source, self.home, '/old/python')

    def test_configured_custom_interpreter_has_precedence(self):
        self.home.mkdir()
        (self.home/'config.toml').write_text('[flow]\npython = "/configured/python"\n')
        with patch.object(op, 'ready', side_effect=lambda p: p == '/configured/python'):
            self.assertEqual(op.provision(self.source, self.home, '/base/python'), '/configured/python')

    def test_shell_fresh_and_repeat_bind_verified_launcher(self):
        repo = Path(__file__).resolve().parents[1]
        shim = self.root / 'pinned-python'
        shim.write_text('#!/bin/sh\nif [ "$1" = "-c" ]; then\n case "$2" in\n *"from openhands.sdk"*) exit 0;;\n esac\nfi\nexec ' + sys.executable + ' "$@"\n')
        shim.chmod(0o755)
        env = dict(os.environ, HOME=str(self.root / 'fake-user'), FLOW_PYTHON=str(shim), FLOW_PYTHON_CANDIDATES=str(shim), PYTHONDONTWRITEBYTECODE='1')
        for _ in range(2):
            result = subprocess.run(['bash', str(repo/'install-flow.sh'), '--develop'], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        launcher = Path(env['HOME'])/'.local/bin/flow'
        self.assertIn(str(shim), launcher.read_text())
        self.assertIn(str(shim), (Path(env['HOME'])/'.flow/config.toml').read_text())

    def test_shell_provision_failure_preserves_installed_bindings(self):
        repo = Path(__file__).resolve().parents[1]
        fixture = self.root/'candidate'
        (fixture/'cli').mkdir(parents=True)
        (fixture/'install-flow.sh').write_text((repo/'install-flow.sh').read_text())
        (fixture/'cli/openhands_provision.py').write_text('raise SystemExit("dependency index unavailable")\n')
        user = self.root/'fake-user'
        source = user/'.flow/source'
        source.mkdir(parents=True)
        (source/'sentinel').write_text('old source')
        config = user/'.flow/config.toml'
        config.write_text('[flow]\npython = "/old/python"\n')
        pointer = user/'.flow/runtimes/openhands/current.json'
        pointer.parent.mkdir(parents=True)
        pointer.write_text('{"interpreter":"/old/python"}')
        launcher = user/'.local/bin/flow'
        launcher.parent.mkdir(parents=True)
        launcher.write_text('old launcher')
        env = dict(os.environ, HOME=str(user), FLOW_PYTHON=sys.executable, FLOW_PYTHON_CANDIDATES=sys.executable)
        result = subprocess.run(['bash', str(fixture/'install-flow.sh'), '--release'], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('previous source, config and launcher are unchanged', result.stderr)
        self.assertEqual((source/'sentinel').read_text(), 'old source')
        self.assertEqual(launcher.read_text(), 'old launcher')
        self.assertIn('/old/python', config.read_text())
        self.assertEqual(pointer.read_text(), '{"interpreter":"/old/python"}')


if __name__ == '__main__':
    unittest.main()
