"""Transactional runtime/source activation in isolated install homes."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import lifecycle

class ActivationTests(unittest.TestCase):
    def test_provision_and_binding_failure_restore_previous_install(self):
        for failure in ('provision', 'binding', None):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                home = Path(temp)/'user'; flow = home/'.flow'; source = flow/'source'
                source.mkdir(parents=True); (source/'old').write_text('keep')
                staging = flow/'source.new'; staging.mkdir(); (staging/'new').write_text('candidate')
                config = flow/'config.toml'; config.write_text('[flow]\npython="prior"\n[install]\nmode="release"\nversion="old"\n')
                launcher = home/'.local/bin/flow'; launcher.parent.mkdir(parents=True); launcher.write_text('prior launcher'); launcher.chmod(0o755)
                pointer = flow/'runtimes/openhands/current.json'; pointer.parent.mkdir(parents=True); pointer.write_text('prior pointer')
                snapshots = {p:p.read_bytes() for p in (config,launcher,pointer)}
                def provision(command, **kwargs):
                    self.assertEqual(command[command.index('--home')+1], str(flow))
                    pointer.write_text('new pointer')
                    return subprocess.CompletedProcess(command, 1 if failure=='provision' else 0, sys.executable+'\n', 'dependency failure')
                with patch.multiple(lifecycle,FLOW_HOME=flow,SOURCE_DIR=source,FLOW_CONFIG=config), patch.object(lifecycle,'_stage_path',side_effect=lambda label:flow/f'source.{label}'), patch.object(lifecycle.subprocess,'run',side_effect=provision):
                    if failure=='binding':
                        with patch.object(lifecycle,'write_install_config',side_effect=OSError('binding failed')):
                            ok=lifecycle._activate_openhands_source(staging, {'mode':'release','version':'new'})
                    else:
                        ok=lifecycle._activate_openhands_source(staging, {'mode':'release','version':'new'})
                self.assertEqual(ok, failure is None)
                if failure:
                    self.assertTrue((source/'old').exists())
                    for p, before in snapshots.items(): self.assertEqual(p.read_bytes(),before)
                    self.assertEqual(launcher.stat().st_mode & 0o777,0o755)
                else:
                    self.assertTrue((source/'new').exists())
                    self.assertIn(sys.executable,launcher.read_text())
                    self.assertIn(sys.executable,config.read_text())
                    self.assertFalse((flow/'source.old').exists())

class PredecessorActivationBridgeTests(unittest.TestCase):
    """The predecessor may swap source before it knows about SDK activation."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / 'user'
        self.flow = self.home / '.flow'
        self.source = self.flow / 'source'
        (self.source / 'cli').mkdir(parents=True)
        (self.source / 'candidate').write_text('already installed new source')
        (self.source / 'cli/openhands_provision.py').write_text('# predecessor installed new provisioner\n')
        self.config = self.flow / 'config.toml'
        self.config.write_text('[flow]\npython="prior-python"\n[install]\nmode="release"\nversion="candidate"\n')
        self.launcher = self.home / '.local/bin/flow'
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text('prior launcher')
        self.launcher.chmod(0o755)
        self.pointer = self.flow / 'runtimes/openhands/current.json'
        self.pointer.parent.mkdir(parents=True)
        self.pointer.write_text('prior pointer')
        self.profile = self.flow / 'runtime.toml'
        self.profile.write_text('[profiles.custom]\nkind="local"\nmodel="local/custom"\n')
        self.patches = patch.multiple(lifecycle, FLOW_HOME=self.flow, SOURCE_DIR=self.source,
                                      FLOW_CONFIG=self.config,
                                      __file__=str(self.source / 'cli/lifecycle.py'))
        self.ready_patch = patch.object(lifecycle, "_openhands_runtime_ready", return_value=True)
        self.ready = self.ready_patch.start()
        self.addCleanup(self.ready_patch.stop)
        self.sync_patch = patch.object(lifecycle, '_sync_installed_adapters', return_value=0)
        self.sync = self.sync_patch.start()
        self.addCleanup(self.sync_patch.stop)
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.addCleanup(self.temp.cleanup)

    def provision(self, source):
        self.assertEqual(source, self.source)
        self.pointer.write_text('new verified pointer')
        return sys.executable

    def test_first_managed_invocation_binds_verified_runtime_and_repeat_skips(self):
        profile = self.profile.read_bytes()
        with patch.object(lifecycle, '_provision_openhands_interpreter', side_effect=self.provision) as provision:
            result = lifecycle.activate_managed_openhands_runtime()
            self.assertEqual(result['state'], 'succeeded')
            self.assertTrue(result['attempted'])
            self.assertEqual(result['interpreter'], sys.executable)
            config = lifecycle.read_install_config()
            self.assertEqual(config['openhands_runtime_activation_revision'], 1)
            self.assertEqual(config['openhands_runtime_activation_state'], 'succeeded')
            self.assertIn(sys.executable, self.launcher.read_text())
            self.assertIn(sys.executable, self.config.read_text())
            repeat = lifecycle.activate_managed_openhands_runtime()
            self.assertFalse(repeat['attempted'])
            provision.assert_called_once_with(self.source)
            self.sync.assert_called_once_with(quiet=True)
        self.assertEqual((self.source / 'candidate').read_text(), 'already installed new source')
        self.assertEqual(self.profile.read_bytes(), profile)

    def test_failure_restores_bindings_and_pointer_without_reverting_new_source_then_forced_retry(self):
        for failing_step in ('provision', 'binding'):
            with self.subTest(step=failing_step):
                snapshots = {path: path.read_bytes() for path in (self.config, self.launcher, self.pointer, self.profile)}
                def fail(source):
                    self.provision(source)
                    raise RuntimeError('offline dependency failure')
                provision_effect = fail if failing_step == 'provision' else self.provision
                with patch.object(lifecycle, '_provision_openhands_interpreter', side_effect=provision_effect):
                    if failing_step == 'binding':
                        def fail_binding(*args):
                            self.config.write_text('partial config')
                            self.launcher.write_text('partial launcher')
                            raise OSError('binding failed')
                        with patch.object(lifecycle, '_bind_openhands_launcher', side_effect=fail_binding):
                            result = lifecycle.activate_managed_openhands_runtime(force=True)
                    else:
                        result = lifecycle.activate_managed_openhands_runtime(force=True)
                self.assertTrue(result['attempted'])
                self.assertEqual(result['state'], 'failed')
                self.assertTrue(result['detail'])
                self.assertEqual(self.sync.call_count, 0 if failing_step == 'provision' else 1)
                for path, before in snapshots.items():
                    self.assertEqual(path.read_bytes(), before, path)
                self.assertEqual(self.launcher.stat().st_mode & 0o777, 0o755)
                self.assertTrue((self.source / 'candidate').is_file())
                with patch.object(lifecycle, '_provision_openhands_interpreter', side_effect=self.provision):
                    self.assertEqual(lifecycle.activate_managed_openhands_runtime(force=True)['state'], 'succeeded')

    def test_unmanaged_and_noninstalled_source_do_not_provision(self):
        with patch.object(lifecycle, '_provision_openhands_interpreter') as provision:
            with patch.object(lifecycle, '__file__', str(self.home / 'project/cli/lifecycle.py')):
                self.assertFalse(lifecycle.activate_managed_openhands_runtime()['attempted'])
            self.config.write_text('[flow]\npython="prior-python"\n')
            self.assertFalse(lifecycle.activate_managed_openhands_runtime()['attempted'])
            provision.assert_not_called()
            self.sync.assert_not_called()

    def test_adapter_conflict_is_reported_after_verified_binding(self):
        self.sync.return_value = 1
        with patch.object(lifecycle, '_provision_openhands_interpreter', side_effect=self.provision):
            result = lifecycle.activate_managed_openhands_runtime()
        self.assertEqual(result['state'], 'succeeded')
        self.assertTrue(result['adapter_conflicts'])
        self.assertIn(sys.executable, self.launcher.read_text())
        self.assertEqual(self.pointer.read_text(), 'new verified pointer')
        self.assertEqual(lifecycle.read_install_config()['openhands_runtime_activation_state'], 'succeeded')

    def copy_installed_cli(self):
        repository = Path(__file__).resolve().parents[1]
        shutil.copytree(repository / 'cli', self.source / 'cli', dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copytree(repository / 'scaffolds', self.source / 'scaffolds')
        shutil.copytree(repository / 'hooks', self.source / 'hooks')
        shutil.copytree(repository / 'runtime', self.source / 'runtime',
                        ignore=shutil.ignore_patterns('__pycache__', 'wheelhouse'))
    def test_installed_cli_reexecutes_and_refreshes_all_role_discovery_paths(self):
        self.copy_installed_cli()
        module = self.source / "cli/openhands_flow.py"
        with module.open("a") as handle:
            handle.write("\nimport sys\ndef execute(args):\n    return {'work_id': args.work_id, 'execution_python': sys.executable}\n")
        task = self.home / "task.md"
        task.write_text("Offline reexec fixture")
        # Provisioning itself is separately covered. This fixture supplies a
        # verified interpreter without network access or live model execution.
        (self.source / 'cli/openhands_provision.py').write_text(
            'VERSION = "1.54.0"\ndef ready(python): return True\nif __name__ == "__main__":\n    print(' + repr(sys.executable) + ')\n')
        environment = {**os.environ, 'HOME': str(self.home), 'PYTHONDONTWRITEBYTECODE': '1'}
        process = subprocess.run([sys.executable, str(self.source / 'cli/flow.py'),
                                  'workflow', 'execute', 'example', '--task-file', str(task), '--json'], env=environment,
                                 text=True, capture_output=True, timeout=60)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        # Pure JSON proves adapter progress was quiet before os.execv reran
        # the originally requested command under the activated interpreter.
        payload = json.loads(process.stdout)
        self.assertEqual(payload['execution_python'], sys.executable)
        self.assertEqual(payload['work_id'], 'example')
        for directory, suffix in (('.claude/agents', '.md'), ('.codex/agents', '.toml'),
                                  ('.agents/agents', '.md')):
            generated = list((self.home / directory).glob('*' + suffix))
            self.assertEqual(len(generated), 13, directory)
            self.assertTrue(all(path.is_symlink() for path in generated))
        self.assertIn(sys.executable, self.launcher.read_text())
        self.assertEqual(self.profile.read_text(), '[profiles.custom]\nkind="local"\nmodel="local/custom"\n')

    def test_installed_inspection_and_workflow_metadata_do_not_provision(self):
        self.copy_installed_cli()
        (self.source / 'cli/openhands_provision.py').write_text(
            'VERSION = "1.54.0"\ndef ready(python): return True\nif __name__ == "__main__":\n    raise RuntimeError("must not install during inspection")\n')
        # Resolve update diagnostics wholly offline against a nonexistent local
        # remote, rather than probing a live index or GitHub repository.
        self.config.write_text('[flow]\npython="prior-python"\n[install]\nmode="release"\nversion="candidate"\nremote="file:///nonexistent-flow-remote"\n')
        before = {path: path.read_bytes() for path in (self.config, self.launcher, self.pointer, self.profile)}
        environment = {**os.environ, 'HOME': str(self.home), 'PYTHONDONTWRITEBYTECODE': '1'}
        project = self.home / 'project'
        project.mkdir()
        commands = [
            (['workflow', 'runtime', '--json'], 0),
            (['workflow', 'init', 'inspection', '--project-root', str(project), '--json'], 0),
            (['workflow', 'status', 'inspection', '--project-root', str(project), '--json'], 0),
            (['runtime', 'readiness', '--json'], 1),
            (['update', '--check', '--json'], None),
        ]
        for arguments, exit_code in commands:
            with self.subTest(command=arguments):
                process = subprocess.run([sys.executable, '-S', str(self.source / 'cli/flow.py'), *arguments],
                                         env=environment, text=True, capture_output=True, timeout=60)
                if exit_code is not None:
                    self.assertEqual(process.returncode, exit_code, process.stdout + process.stderr)
                self.assertNotIn('must not install', process.stdout + process.stderr)
                payload = json.loads(process.stdout)
                if arguments[:2] in (['workflow', 'runtime'], ['runtime', 'readiness']):
                    self.assertFalse(payload['ready'])
                for path, content in before.items():
                    self.assertEqual(path.read_bytes(), content, path)
                self.assertFalse((self.flow / 'generated').exists())
        self.assertTrue((project / '.flow/runs/inspection/run.json').is_file())

    def test_invalid_update_json_is_rejected_before_activation(self):
        self.copy_installed_cli()
        (self.source / 'cli/openhands_provision.py').write_text(
            'VERSION = "1.54.0"\ndef ready(python): return True\nif __name__ == "__main__":\n    raise RuntimeError("must not install rejected flags")\n')
        before = {path: path.read_bytes() for path in (self.config, self.launcher, self.pointer, self.profile)}
        environment = {**os.environ, 'HOME': str(self.home), 'PYTHONDONTWRITEBYTECODE': '1'}
        process = subprocess.run([sys.executable, '-S', str(self.source / 'cli/flow.py'),
                                  'update', '--json'], env=environment, text=True,
                                 capture_output=True, timeout=60)
        self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
        self.assertIn('flow update --json requires --check', process.stderr)
        self.assertNotIn('must not install', process.stdout + process.stderr)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content, path)
        self.assertFalse((self.flow / 'generated').exists())

    def test_damaged_marked_runtime_is_revalidated_and_reprovisioned(self):
        with patch.object(lifecycle, '_provision_openhands_interpreter', side_effect=self.provision) as provision:
            lifecycle.activate_managed_openhands_runtime()
            self.ready.return_value = False
            repaired = lifecycle.activate_managed_openhands_runtime()
            self.assertTrue(repaired['attempted'])
            self.assertEqual(repaired['state'], 'succeeded')
            self.ready.assert_called_with(sys.executable)
            self.assertEqual(provision.call_count, 2)
            self.ready.return_value = True
            self.assertFalse(lifecycle.activate_managed_openhands_runtime()['attempted'])
            self.assertEqual(provision.call_count, 2)
