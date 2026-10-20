"""Prerequisite diagnostics use PATH and fail before touching an installation."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from poc import managed


class PrerequisiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.bin=self.root/'bin';self.bin.mkdir()
        self.home=self.root/'home';old=self.home/'.flow/v2/releases/old';old.mkdir(parents=True)
        (old/'retained').write_text('old code')
        (self.home/'.flow/v2/current').symlink_to(old)
        (self.home/'.flow/v2/install.json').write_text('existing receipt')
        self.executable('node','v24.12.0');self.executable('npm','11.6.2')
        for mock in (patch.dict(os.environ,{'PATH':str(self.bin),'FLOW_V2_NODE':'/ignored/override'}),
                     patch.object(managed.platform,'system',return_value='Darwin'),
                     patch.object(managed.platform,'machine',return_value='arm64'),
                     patch.object(managed.platform,'mac_ver',return_value=('15.0',(),'')),
                     patch.object(managed.sys,'version_info',(3,12,0))):
            mock.start();self.addCleanup(mock.stop)

    def executable(self,name,version,code=0):
        path=self.bin/name
        path.write_text('#!/bin/sh\nprintf "%s\\n" '+repr(version)+(' >&2' if code else '')+'\nexit '+str(code)+'\n')
        path.chmod(0o755)
        return path

    def snapshot(self):
        return {str(p.relative_to(self.home)):(str(p.readlink()) if p.is_symlink() else p.read_bytes())
                for p in self.home.rglob('*') if p.is_symlink() or p.is_file()}

    def fails_before_mutation(self,*expected):
        before=self.snapshot()
        for action in (['install'],['update'],['update','--check']):
            with self.subTest(action=action),patch.object(managed,'latest') as latest, \
                    patch.object(managed,'install_release') as install,patch.object(managed,'lock') as lock, \
                    contextlib.redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit) as failure:
                    managed.main([*action,'--home',str(self.home)])
                self.assertEqual(failure.exception.code,1)
                for text in expected:self.assertIn(text,error.getvalue())
                latest.assert_not_called();install.assert_not_called();lock.assert_not_called()
                self.assertEqual(self.snapshot(),before)

    def test_supported_24_reports_path_versions_without_polluting_json(self):
        manifest={'schema_version':1,'version':'v0.51.1','source_sha':'b'*40,
                  'supported_targets':['Darwin-arm64'],'minimum_macos':'15.0',
                  'assets':{name:{'size':1,'sha256':'a'*64} for name in managed.ASSETS}}
        for version in ('v24.0.0','v24.99.3'):
            self.executable('node',version)
            with patch.object(managed,'latest',return_value=(manifest,{})), \
                    contextlib.redirect_stdout(io.StringIO()) as output,contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(managed.main(['update','--check','--json']),0)
                self.assertEqual(json.loads(output.getvalue())['latest'],'v0.51.1')
                for value in (version,str(self.bin/'node'),'exactly 24.x','npm 11.6.2',str(self.bin/'npm')):
                    self.assertIn(value,error.getvalue())

    def test_missing_node_is_actionable_before_install_or_update(self):
        (self.bin/'node').unlink()
        self.fails_before_mutation('node: missing executable on PATH','exactly 24.x','nvm use 24','nvm install 24','does not install or switch')

    def test_rejects_22_25_and_newer_with_detected_version_and_path(self):
        for version in ('v22.15.0','v25.0.0','v26.1.0'):
            self.executable('node',version)
            self.fails_before_mutation(version,str(self.bin/'node'),'required exactly 24.x','nvm use 24')

    def test_malformed_node_version_is_readable(self):
        for version in ('','v24','not a version'):
            self.executable('node',version)
            self.fails_before_mutation('unrecognized version output',repr(version),str(self.bin/'node'),'exactly 24.x')

    def test_broken_node_reports_exit_stderr_and_remediation(self):
        self.executable('node','fixture loader failure',7)
        self.fails_before_mutation('cannot read version','exit 7','fixture loader failure',str(self.bin/'node'),'nvm use 24')

    def test_unreadable_or_hung_node_is_actionable(self):
        for error in (PermissionError('fixture permission denied'),subprocess.TimeoutExpired('node --version',10),
                      UnicodeDecodeError('utf-8',b'\xff',0,1,'invalid start byte')):
            with patch.object(managed.subprocess,'run',side_effect=error):
                self.fails_before_mutation('cannot read version',str(self.bin/'node'),'exactly 24.x','then retry')

    def test_missing_broken_and_malformed_npm_fail_before_preparation(self):
        (self.bin/'npm').unlink()
        self.fails_before_mutation('Node.js v24.12.0',str(self.bin/'node'),'npm: missing executable on PATH','Repair or reinstall npm')
        self.executable('npm','fixture npm failure',9)
        self.fails_before_mutation('Node.js v24.12.0',str(self.bin/'npm'),'exit 9','fixture npm failure','npm --version succeeds')
        self.executable('npm','not a version')
        self.fails_before_mutation('Node.js v24.12.0','unrecognized version output','Repair or reinstall npm')

    def test_rollback_does_not_require_node_or_npm(self):
        (self.bin/'node').unlink();(self.bin/'npm').unlink()
        with patch.object(managed,'supported',side_effect=AssertionError('must bypass')), \
                patch.object(managed,'rollback',return_value={'restored':'previous'}) as rollback, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(managed.main(['rollback','--home',str(self.home)]),0)
            rollback.assert_called_once_with(self.home)
