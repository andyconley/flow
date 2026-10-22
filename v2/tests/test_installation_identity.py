"""Selected manifest is authoritative; retained legacy/dirty clones stay untouched."""
import contextlib,io,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from poc import managed,entry

class InstallationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=Path(self.temp.name).resolve()
        self.root=self.home/'.flow/v2';self.release=self.root/'releases/v0.54.0-fixture';self.release.mkdir(parents=True)
        (self.release/'v2').mkdir();(self.release/'release-manifest.json').write_text(json.dumps({'version':'v0.54.0','source_sha':'a'*40}))
        self.root.joinpath('current').symlink_to(self.release)
        self.legacy=self.home/'.flow/config.toml';self.legacy.write_text('[install]\nversion="v0.49.1"\nmode="release"\nsecret="never print me"\n')
        (self.home/'.flow/source').mkdir()
    def test_selection_ignores_stale_legacy_and_receipt_without_rewriting(self):
        self.root.joinpath('install.json').write_text('{"version":"v0.40.0"}')
        before=self.legacy.read_bytes();r=managed.installation_status(self.home,self.release/'v2')
        self.assertEqual(r['version'],'v0.54.0');self.assertEqual(r['mode'],'managed-release');self.assertEqual(r['source_sha'],'a'*40)
        self.assertEqual(r['legacy_config']['version'],'v0.49.1');self.assertEqual(r['retained_legacy_source']['kind'],'directory')
        self.assertTrue(r['invocation']['matches_selected']);self.assertNotIn('never print me',json.dumps(r));self.assertEqual(self.legacy.read_bytes(),before)
    def test_status_is_read_only_offline_and_disambiguates_invoked_checkout(self):
        checkout=self.home/'independent-checkout/v2';checkout.mkdir(parents=True)
        before=sorted(str(p) for p in self.home.rglob('*'));out=io.StringIO()
        with patch.object(entry,'ROOT',checkout),patch('poc.knowledge.trigger',side_effect=AssertionError('status must not provision')),patch('poc.managed.latest',side_effect=AssertionError('status must not fetch')),patch('poc.managed.subprocess.run',side_effect=AssertionError('status must not run Git')),contextlib.redirect_stdout(out):
            self.assertEqual(entry.main(['installation','status','--home',str(self.home),'--json']),0)
        r=json.loads(out.getvalue());self.assertEqual(r['invocation']['mode'],'source-checkout');self.assertFalse(r['invocation']['matches_selected']);self.assertEqual(before,sorted(str(p) for p in self.home.rglob('*')))
    def test_version_and_doctor_label_selected_release_without_provisioning(self):
        with patch.object(entry,'ROOT',self.release/'v2'),patch.dict(os.environ,{'HOME':str(self.home)}),patch('poc.knowledge.trigger',side_effect=AssertionError('identity must not provision')),patch('poc.goose_artifact.selected_binary',return_value=self.release/'v2/runtime/goose'):
            out=io.StringIO()
            with contextlib.redirect_stdout(out):self.assertEqual(entry.main(['--version']),0)
            self.assertIn('Flow v0.54.0',out.getvalue());self.assertIn('managed-release',out.getvalue())
            out=io.StringIO()
            with contextlib.redirect_stdout(out):self.assertEqual(entry.main(['doctor','--json']),0)
            r=json.loads(out.getvalue());self.assertEqual(r['installation']['version'],'v0.54.0');self.assertTrue(r['installation']['invocation']['matches_selected'])

    def test_broken_or_malformed_selection_never_uses_legacy_version(self):
        manifest=self.release/'release-manifest.json'
        for text in ['bad json','[]','{"version":"v0.54.0"}']:
            manifest.write_text(text);r=managed.installation_status(self.home);self.assertEqual(r['mode'],'invalid-selection');self.assertEqual(r['version'],'unknown')
        self.root.joinpath('current').unlink();self.root.joinpath('current').symlink_to(self.root/'missing')
        self.assertEqual(managed.installation_status(self.home)['mode'],'invalid-selection')
    def test_no_pointer_and_malformed_legacy_stay_explicit(self):
        self.root.joinpath('current').unlink();self.legacy.write_text('bad toml')
        r=managed.installation_status(self.home);self.assertEqual(r['mode'],'no-managed-release');self.assertIsNone(r['version']);self.assertIn('preserved unchanged',r['legacy_config']['read_status'])
    def test_old_release_invocation_is_not_labeled_selected(self):
        old=self.root/'releases/old';(old/'v2').mkdir(parents=True);(old/'release-manifest.json').write_text('{}')
        self.assertEqual(managed.installation_status(self.home,old/'v2')['invocation']['mode'],'unselected-release')
    def test_pointer_switch_during_status_cannot_mix_version_and_source(self):
        newer=self.root/'releases/newer';newer.mkdir();(newer/'release-manifest.json').write_text(json.dumps({'version':'v0.55.0','source_sha':'b'*40}))
        pointer=self.root/'current';real_resolve=Path.resolve;switched=[]
        def resolve(path,*args,**kwargs):
            target=real_resolve(path,*args,**kwargs)
            if path==pointer and not switched:
                pointer.unlink();pointer.symlink_to(newer);switched.append(True)
            return target
        with patch.object(Path,'resolve',resolve):r=managed.installation_status(self.home)
        self.assertEqual(r['version'],'v0.54.0');self.assertEqual(r['runtime'],str(self.release));self.assertEqual(pointer.resolve(),newer)

    def test_preparation_child_logs_use_stderr_not_json_stdout(self):
        release=self.home/'staged';v2=release/'v2';v2.mkdir(parents=True)
        for name in ['adapters.package.json','adapters.package-lock.json']:(v2/name).write_text('{}')
        (self.home/'staged-state').mkdir()
        real_run=subprocess.run
        def progress(command,**kwargs):
            return real_run([sys.executable,'-c','import sys; print("child progress"); print("child diagnostic",file=sys.stderr)'],stdout=kwargs.get('stdout'),stderr=kwargs.get('stderr'),check=True)
        out=io.StringIO()
        with tempfile.TemporaryFile(mode='w+') as err,contextlib.redirect_stdout(out),contextlib.redirect_stderr(err),patch('poc.managed.subprocess.run',side_effect=progress):
            managed.prepare_release(release,self.home/'staged-state');err.seek(0);text=err.read()
        self.assertEqual(out.getvalue(),'');self.assertEqual(text.count('child progress'),5);self.assertEqual(text.count('child diagnostic'),5)

class IdentityLifecycleTests(unittest.TestCase):
    def setUp(self):
        from test_managed_release import ManagedReleaseTests
        fixture=ManagedReleaseTests('test_real_update_switches_version_and_rollback_preserves_state');fixture.setUp();self.addCleanup(fixture.doCleanups)
        for name in ['home','bundle','manifest','prepare','install']:setattr(self,name,getattr(fixture,name))
    def test_update_rollback_report_pointer_and_preserve_dirty_separate_clone(self):
        clone=self.home/'personal/flow';clone.mkdir(parents=True);subprocess.run(['git','init','-q',str(clone)],check=True)
        (clone/'docs').mkdir();(clone/'docs/backlog.md').write_text('staged edit');subprocess.run(['git','-C',str(clone),'add','docs/backlog.md'],check=True)
        (clone/'docs/backlog.md').write_text('unstaged local edit');(clone/'.environment').write_text('private untracked fixture')
        legacy=self.home/'.flow/config.toml';legacy.parent.mkdir();legacy.write_text('[install]\nversion="v0.49.1"\nmode="release"\n');(self.home/'.flow/source').mkdir()
        tracked={str(p.relative_to(clone)):p.read_bytes() for p in clone.rglob('*') if p.is_file()};first=self.install()
        manifest={**self.manifest,'version':'v0.54.0','source_sha':'b'*40};out=io.StringIO();err=io.StringIO();real_install=managed.install_release
        def install(home,target,**kwargs):
            print('Python preparation progress')
            return real_install(home,target,bundle=self.bundle,preparer=self.prepare,knowledge_mode='defer')
        previous=Path.cwd()
        try:
            os.chdir(clone)
            with patch.object(managed,'supported'),patch.object(managed,'latest',return_value=(manifest,{})),patch.object(managed,'install_release',side_effect=install),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
                self.assertEqual(managed.main(['update','--home',str(self.home),'--knowledge','defer','--json']),0)
        finally:os.chdir(previous)
        r=json.loads(out.getvalue());self.assertEqual(r['installation']['version'],'v0.54.0');self.assertIn('Python preparation progress',err.getvalue());self.assertIn('not the v2 version authority',err.getvalue());self.assertIn('git pull or stashing',err.getvalue())
        out=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(io.StringIO()):self.assertEqual(managed.main(['rollback','--home',str(self.home)]),0)
        self.assertEqual(json.loads(out.getvalue())['installation']['runtime'],first['runtime']);self.assertEqual(managed.installation_status(self.home)['version'],'v0.51.0')
        self.assertIn('v0.49.1',legacy.read_text());self.assertEqual(tracked,{str(p.relative_to(clone)):p.read_bytes() for p in clone.rglob('*') if p.is_file()})

    def test_check_only_separates_available_and_active_without_installing(self):
        self.install();available={**self.manifest,'version':'v0.54.0','source_sha':'b'*40};out=io.StringIO();err=io.StringIO()
        with patch.object(managed,'supported'),patch.object(managed,'latest',return_value=(available,{})),patch.object(managed,'install_release',side_effect=AssertionError('check must not install')),contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            self.assertEqual(managed.main(['update','--check','--json','--home',str(self.home)]),0)
        r=json.loads(out.getvalue());self.assertEqual(r['latest'],'v0.54.0');self.assertEqual(r['installation']['version'],'v0.51.0');self.assertIn('CHECK ONLY',err.getvalue())

    def test_first_rollback_keeps_legacy_version_and_reports_no_managed_release(self):
        config=self.home/'.flow/config.toml';config.parent.mkdir();config.write_text('[install]\nversion="v0.49.1"\nmode="release"\n');before=config.read_bytes()
        launcher=self.home/'.local/bin/flow';launcher.parent.mkdir(parents=True);launcher.write_text('#!/bin/sh\nexec "'+str(self.home)+'/.flow/runtime/bin/python" "'+str(self.home)+'/.flow/source/cli/flow.py" "$@"\n');launcher.chmod(0o755)
        self.install();out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):self.assertEqual(managed.main(['rollback','--home',str(self.home)]),0)
        self.assertIn('Use flow --version',err.getvalue());self.assertNotIn('Use flow installation status',err.getvalue())
        r=json.loads(out.getvalue());self.assertEqual(r['installation']['mode'],'no-managed-release');self.assertIsNone(r['installation']['version']);self.assertEqual(config.read_bytes(),before);self.assertIn('pre-v2',r['installation']['next_action'])
