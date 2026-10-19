"""Smoke-run boundary regressions; disposable state and no model calls."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

from poc import glg, native_runtime, runtime_env
from poc.role_renderer import bind_bundle
from poc.runtime_env import goose_binary

ROOT = Path(__file__).resolve().parents[1]
GOOSE = goose_binary()


class RuntimeSmokeRepairs(unittest.TestCase):
    @unittest.skipUnless(sys.platform == 'darwin', 'macOS sandbox execution probe')
    def test_sandbox_supports_linked_git_python_cache_and_shell_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); home = root/'home'; home.mkdir()
            repository = home/'repo'; repository.mkdir()
            workspace = repository/'.claude/worktrees/task.with spaces'
            git_env = {**os.environ, 'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_CONFIG_NOSYSTEM':'1'}
            def git(*args):
                subprocess.run(['git', '-C', str(repository), *args], env=git_env,
                               check=True, capture_output=True, text=True)
            git('init', '-q'); git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (repository/'example.py').write_text('value = 1\n')
            git('add', '.'); git('commit', '-qm', 'fixture')
            git('worktree', 'add', '-q', '-b', 'worker', str(workspace))
            run = root/'run'; run.mkdir()
            with patch.object(runtime_env, 'ROOT', root), patch.object(native_runtime, 'ROOT', root), \
                    patch.object(Path, 'home', return_value=home), \
                    patch.object(native_runtime, 'goose_binary', return_value=root/'goose'), \
                    patch.object(native_runtime, 'build'):
                runtime_env.setup()
                profile, env = native_runtime.prepare(workspace, run, ROOT/'role-bundle')
            script = '''import os, pathlib, py_compile, subprocess
subprocess.run(['git','status','--porcelain'],check=True,capture_output=True)
shell = subprocess.run(['/bin/zsh','-c',"cat <<'END'\\n"+'x'*10000+"\\nEND"],capture_output=True,text=True)
assert shell.returncode == 0, shell.stderr
(pathlib.Path.home()/'Library').mkdir()
py_compile.compile('example.py',doraise=True)
print('fixture succeeded')
'''
            probe = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(profile), sys.executable, '-c', script],
                                   cwd=workspace, env=env, capture_output=True, text=True)
            self.assertEqual(probe.returncode, 0, probe.stdout+probe.stderr)
            self.assertIn('fixture succeeded', probe.stdout)
            unrelated = home/'unrelated'; unrelated.write_text('keep private')
            denied = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(profile), sys.executable,
                                     '-c', 'from pathlib import Path; Path('+repr(str(unrelated))+').write_text("changed")'],
                                    cwd=workspace, env=env, capture_output=True, text=True)
            self.assertNotEqual(denied.returncode, 0)
            self.assertEqual(unrelated.read_text(), 'keep private')

    def test_status_reads_committed_checkpoint_under_writer_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); project = root/'project'; project.mkdir()
            args = ['--project', str(project), '--work', 'active']
            def invoke(*tail):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    glg.main([*args, *tail])
                return json.loads(output.getvalue())
            with patch.object(glg, 'ROOT', root):
                invoke('create', '--request', 'Shape an approved task')
                state = glg.storage(project, 'active')
                before = (state/'workflow.sqlite').read_bytes()
                with glg.locked(state):
                    with patch.object(glg.NativeHarness, '_job', side_effect=AssertionError('Status launched a worker')):
                        status = invoke('status')
                    self.assertTrue(status['operator_active'])
                    self.assertEqual(status['checkpoint_view'], 'latest_committed_snapshot')
                    self.assertEqual(status['phase'], 'shaping')
                    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                        invoke('resume')
                self.assertEqual((state/'workflow.sqlite').read_bytes(), before)
                self.assertFalse(invoke('status')['operator_active'])

    def test_native_runtime_owns_temp_root_without_guessing_workspace_slug(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); home = root/'home'; home.mkdir()
            workspace = root/'path-nexus/.claude/worktrees/a.b with spaces'; workspace.mkdir(parents=True)
            run = root/'run'; run.mkdir()
            with patch.object(runtime_env, 'ROOT', root), patch.object(native_runtime, 'ROOT', root), \
                    patch.object(Path, 'home', return_value=home), \
                    patch.object(native_runtime, 'goose_binary', return_value=root/'goose'), \
                    patch.object(native_runtime, 'build'):
                runtime_env.setup()
                profile, env = native_runtime.prepare(workspace, run, ROOT/'role-bundle')
            scratch = (run/'native-runtime/claude-tmp').resolve()
            self.assertEqual(env['CLAUDE_CODE_TMPDIR'], str(scratch))
            self.assertEqual(env['GOOSE_SUBAGENT_MAX_TURNS'], str(runtime_env.WORKER_MAX_TURNS))
            self.assertIn('--max-turns '+str(runtime_env.WORKER_MAX_TURNS),
                          (run/'native-runtime/claude').read_text())
            self.assertTrue(scratch.is_dir())
            self.assertIn('(allow file-write* (subpath "'+str(scratch)+'"))', profile.read_text())
            self.assertNotIn(str(workspace).replace('/', '-'), profile.read_text())
            self.assertNotIn('(allow file-write* (subpath "'+str(home)+'"))', profile.read_text())

    @unittest.skipUnless(GOOSE.is_file(), 'Qualified Goose needed for offline recipe rendering')
    def test_bound_recipes_render_omitted_parameters_without_template_injection(self):
        task = 'Preserve "quotes" and literal {{ not_a_variable }}\n{% not_a_directive %}\nUnicode Zoë'
        context = 'Project: {"nested":true}\nSecond line'
        originals = {p:p.read_bytes() for p in (ROOT/'role-bundle/recipes').glob('*.yaml')}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = bind_bundle(ROOT/'role-bundle', root/'bound', task, context)
            env = dict(os.environ, HOME=str(root), GOOSE_PATH_ROOT=str(root/'goose-home'), GOOSE_DISABLE_KEYRING='1')
            for role in ('lead-developer', 'quality-reviewer'):
                path = bundle/'recipes'/f'{role}.yaml'
                self.assertEqual({p['key']:p['default'] for p in yaml.safe_load(path.read_text())['parameters']},
                                 {'task':task, 'project_context':context})
                self.assertEqual(yaml.safe_load(path.read_text())['settings']['max_turns'],
                                 runtime_env.WORKER_MAX_TURNS)
                command = [str(GOOSE), 'run', '--recipe', str(path), '--render-recipe']
                result = subprocess.run(command, capture_output=True, text=True, env=env)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                rendered = yaml.safe_load(result.stdout)
                self.assertIn(task, rendered['instructions'])
                self.assertIn(context, rendered['instructions'])
                override = subprocess.run([*command, '--params', 'task=Refined assignment'], capture_output=True, text=True, env=env)
                self.assertEqual(override.returncode, 0, override.stdout+override.stderr)
                self.assertIn('Refined assignment', yaml.safe_load(override.stdout)['instructions'])
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
