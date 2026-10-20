"""Project interpreter selection must not depend on GUI-host PATH."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from poc import native_runtime, runtime_env
from poc.project_python import check_command, select


class ProjectPythonTests(unittest.TestCase):
    def test_venv_and_explicit_interpreter_are_consistent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            python = root/'.venv/bin/python'; python.parent.mkdir(parents=True)
            python.symlink_to(sys.executable)
            with patch.dict(os.environ, {'PATH':'/usr/bin:/bin'}):
                self.assertEqual(select(root, ['python3','-m','pytest']), python)
                self.assertEqual(check_command(root, ['python3','-m','pytest']), [str(python),'-m','pytest'])
                self.assertEqual(check_command(root, [sys.executable,'-m','unittest']), [sys.executable,'-m','unittest'])
                self.assertEqual(check_command(root, ['./.venv/bin/python','-V']), [str(python),'-V'])
                self.assertEqual(check_command(root, ['make','test']), ['make','test'])

    def test_missing_project_python_never_uses_ambient_python(self):
        with tempfile.TemporaryDirectory() as directory:
            for command in (['python3','-m','pytest'], ['./.venv/bin/python','-m','pytest']):
                with self.assertRaises(ValueError):
                    check_command(directory, command)
            self.assertIsNone(select(directory))

    def test_native_wrappers_use_selected_python_and_preserve_global_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); project = root/'project'; project.mkdir()
            python = project/'.venv/bin/python'; python.parent.mkdir(parents=True)
            # A tiny executable makes interpreter selection observable without
            # depending on packages in an arbitrary developer environment.
            python.write_text('#!/bin/sh\nprintf "project-python:%s" "$1"\n'); python.chmod(0o755)
            (project/'.venv/pyvenv.cfg').write_text('fixture')
            with patch.object(native_runtime, 'ROOT', root), patch.object(runtime_env, 'ROOT', root), \
                    patch.object(native_runtime, 'build'), patch.object(native_runtime, 'goose_binary', return_value=root/'goose'), \
                    patch.object(native_runtime, 'environment', return_value={'PATH':'/usr/bin:/bin'}):
                (root/'runtime').mkdir(); (root/'runtime/scope.sb').write_text('(version 1)')
                run = root/'run'; run.mkdir()
                profile, env = native_runtime.prepare(project, run, root/'roles', check_command=['python3','-m','pytest'])
            self.assertEqual(env['FLOW_V2_PROJECT_PYTHON'], str(python))
            for name in ('python', 'python3'):
                result = subprocess.run([str(run/'native-runtime/bin'/name), 'probe'],
                                        env=env, text=True, capture_output=True, check=True)
                self.assertEqual(result.stdout, 'project-python:probe')
            for shell in ('/bin/zsh','/bin/bash'):
                if not Path(shell).exists():
                    continue
                result = subprocess.run([shell,'-lc','python3 probe'],env=env,
                                        text=True,capture_output=True,check=True)
                self.assertEqual(result.stdout,'project-python:probe')
            self.assertIn(str(project/'.venv'), profile.read_text())
            self.assertEqual(python.read_text(), '#!/bin/sh\nprintf "project-python:%s" "$1"\n')
