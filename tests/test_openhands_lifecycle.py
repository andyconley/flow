"""Transactional runtime/source activation in isolated install homes."""
import os
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
