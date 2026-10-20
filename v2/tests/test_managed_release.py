"""Real release layout/migration/rollback, with tiny verified assets and no network."""
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from poc import managed,goose_artifact

ROOT=Path(__file__).resolve().parents[1]


class ManagedReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.home=self.root/'home';self.home.mkdir()
        self.bundle=self.root/'bundle';self.bundle.mkdir();source=self.root/'code';(source/'v2').mkdir(parents=True)
        for name in ('poc','skills','role-bundle'):
            shutil.copytree(ROOT/name,source/'v2'/name,ignore=shutil.ignore_patterns('__pycache__'))
        vendor=source/'v2/vendor';(vendor/'artifacts').mkdir(parents=True)
        (vendor/'fixture.patch').write_text('fixture patch')
        lock={'patch':'fixture.patch','patch_sha256':managed.sha(vendor/'fixture.patch')}
        (vendor/'goose.lock.json').write_text(json.dumps(lock))
        binary=b'#!/bin/sh\necho fixture\n';archive=self.bundle/'goose-macos-arm64.gz';archive.write_bytes(gzip.compress(binary,mtime=0))
        metadata={'source_lock':lock,'platform':'Darwin','architecture':'arm64','minimum_macos':'15.0',
                  'archive':archive.name,'archive_size':archive.stat().st_size,'archive_sha256':managed.sha(archive),
                  'binary_size':len(binary),'binary_sha256':hashlib.sha256(binary).hexdigest()}
        (self.bundle/'goose-macos-arm64.json').write_text(json.dumps(metadata))
        with tarfile.open(self.bundle/'flow-code.tar.gz','w:gz') as target:target.add(source/'v2',arcname='v2')
        with tarfile.open(self.bundle/'python-wheels.tar.gz','w:gz') as target:
            item=tarfile.TarInfo('requirements.lock');item.size=0;target.addfile(item,io.BytesIO(b''))
        self.manifest={'schema_version':1,'version':'v0.51.0','source_sha':'a'*40,'supported_targets':['Darwin-arm64'],'minimum_macos':'15.0',
            'assets':{name:{'size':(self.bundle/name).stat().st_size,'sha256':managed.sha(self.bundle/name)} for name in managed.ASSETS}}
        self.no_platform=patch.object(goose_artifact,'check_platform');self.no_platform.start();self.addCleanup(self.no_platform.stop)
        self.env=patch.dict(os.environ,{'HOME':str(self.home)},clear=False);self.env.start();self.addCleanup(self.env.stop)

    def prepare(self,release,root):
        v2=release/'v2';(v2/'.venv/bin').mkdir(parents=True)
        (v2/'.venv/bin/python').symlink_to(sys.executable)
        state=root/'state';state.mkdir(exist_ok=True)
        for name in ('artifacts','workspaces'):
            target=state/name;target.mkdir(exist_ok=True);(v2/name).symlink_to(target)
        (v2/'runtime').mkdir();goose_artifact.extract(v2)

    def install(self,manifest=None):
        return managed.install_release(self.home,manifest or self.manifest,bundle=self.bundle,preparer=self.prepare)

    def test_fresh_install_survives_bootstrap_deletion_and_reuses_verified_release(self):
        result=self.install();release=Path(result['runtime'])
        shutil.rmtree(self.root/'code')
        command=self.home/'.local/bin/flow'
        run=subprocess.run([str(command),'--version'],env={**os.environ,'HOME':str(self.home)},capture_output=True,text=True,check=True)
        self.assertIn('v0.51.0',run.stdout)
        self.assertIn('/.flow/v2/current/v2',command.read_text())
        self.assertNotIn(str(self.root/'code'),command.read_text())
        self.assertFalse(self.install()['changed'])
        self.assertEqual((self.home/'.flow/v2/current').resolve(),release)

    def test_legacy_upgrade_preserves_overlay_configuration_and_history_and_rolls_back(self):
        legacy=self.home/'.local/bin/flow';legacy.parent.mkdir(parents=True)
        legacy.write_text('#!/bin/sh\nexec "'+str(self.home)+'/.flow/runtime/bin/python" "'+str(self.home)+'/.flow/source/cli/flow.py" "$@"\n');legacy.chmod(0o755)
        original=legacy.read_bytes()
        config=self.home/'.flow/config.toml';config.parent.mkdir();config.write_text('user configuration')
        history=self.home/'.flow/archive/record.json';history.parent.mkdir();history.write_text('history')
        custom=self.home/'.claude/skills/session-hygiene/SKILL.md';custom.parent.mkdir(parents=True);custom.write_text('user command')
        receipt=self.home/'.claude/flow.managed.toml';receipt.write_text('[managed]\ngenerator="flow"\n[[files]]\npath=".claude/skills/session-hygiene/SKILL.md"\nsource="~/.flow/user/commands/session-hygiene.md"\nkind="skill"\nsync_mode="replace"\nsha256="'+managed.sha(custom)+'"\n')
        self.install()
        self.assertEqual(config.read_text(),'user configuration');self.assertEqual(history.read_text(),'history');self.assertEqual(custom.read_text(),'user command')
        managed.rollback(self.home)
        self.assertEqual(legacy.read_bytes(),original);self.assertEqual(custom.read_text(),'user command');self.assertEqual(history.read_text(),'history')

    def test_real_update_switches_version_and_rollback_preserves_state(self):
        first=self.install();state=self.home/'.flow/v2/state/artifacts';(state/'history').write_text('retained')
        second={**self.manifest,'version':'v0.52.0','source_sha':'b'*40}
        updated=self.install(second)
        self.assertNotEqual(updated['runtime'],first['runtime'])
        self.assertEqual((self.home/'.flow/v2/current').resolve(),Path(updated['runtime']))
        managed.rollback(self.home)
        self.assertEqual((self.home/'.flow/v2/current').resolve(),Path(first['runtime']))
        self.assertEqual((state/'history').read_text(),'retained')

    def test_corrupt_assets_preparation_failures_and_user_edits_never_replace_working_install(self):
        first=self.install();current=(self.home/'.flow/v2/current').resolve();launcher=(self.home/'.local/bin/flow').read_bytes()
        next_version={**self.manifest,'version':'v0.52.0'}
        (self.bundle/'goose-macos-arm64.gz').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):self.install(next_version)
        self.assertEqual((self.home/'.flow/v2/current').resolve(),current)
        self.assertEqual((self.home/'.local/bin/flow').read_bytes(),launcher)
        surface=self.home/'.claude/skills/flow-define/SKILL.md';surface.write_text('post-install user edit')
        with self.assertRaisesRegex(ValueError,'User edits prevent rollback'):managed.rollback(self.home)
        self.assertEqual(surface.read_text(),'post-install user edit')

    def test_failed_preparation_does_not_create_a_current_selection(self):
        def fail(*args):raise RuntimeError('fixture dependency failure')
        with self.assertRaisesRegex(RuntimeError,'dependency failure'):
            managed.install_release(self.home,self.manifest,bundle=self.bundle,preparer=fail)
        self.assertFalse((self.home/'.flow/v2/current').exists())
        self.assertFalse((self.home/'.local/bin/flow').exists())

    def test_source_bound_history_and_opaque_native_stores_survive_checkout_removal(self):
        old=self.root/'old-checkout/v2';store=old/'runtime/goose-home';store.mkdir(parents=True)
        (store/'opaque-native-state').write_text('fixture native state')
        history=old/'artifacts/glg-state/project-key/old-work';history.mkdir(parents=True)
        (history/'retained-record').write_text('historical evidence')
        receipt=self.home/'.flow-v2/install.json';receipt.parent.mkdir()
        receipt.write_text(json.dumps({'source':str(old),'files':{},'selection':'side-by-side'}))
        self.install()
        state=self.home/'.flow/v2/state'
        self.assertTrue(store.is_symlink())
        self.assertEqual((state/'goose-home/opaque-native-state').read_text(),'fixture native state')
        imported=json.loads((state/'imported-work.json').read_text())
        self.assertIn('glg-state/project-key/old-work',imported['work_paths'])
        shutil.rmtree(self.root/'old-checkout')
        self.assertEqual((state/'goose-home/opaque-native-state').read_text(),'fixture native state')
        self.assertEqual((state/'artifacts/glg-state/project-key/old-work/retained-record').read_text(),'historical evidence')

    def test_active_operator_and_archive_traversal_are_rejected(self):
        root=self.home/'.flow/v2';root.mkdir(parents=True)
        with (root/'operator.lock').open('w') as stream:
            fcntl.flock(stream,fcntl.LOCK_SH|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'Flow is in use'):self.install()
        path=self.root/'bad.tar.gz'
        with tarfile.open(path,'w:gz') as archive:
            item=tarfile.TarInfo('../escape');item.size=1;archive.addfile(item,io.BytesIO(b'x'))
        with self.assertRaisesRegex(ValueError,'Unsafe release'):managed.unpack(path,self.root/'extracted')
        self.assertFalse((self.root/'escape').exists())

    def test_unsupported_platform_has_no_fallback(self):
        with patch.object(managed.platform,'system',return_value='Linux'):
            with self.assertRaisesRegex(ValueError,'No local-build or legacy fallback'):managed.supported()
