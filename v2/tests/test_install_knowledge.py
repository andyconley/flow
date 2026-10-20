"""Install/update consent and knowledge transaction tests; no acquisition/models."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from poc import install_knowledge as gate, knowledge as k, managed
from tests import test_managed_release as fixtures


class KnowledgeGateFixture:
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'knowledge'
        self.health=patch.object(gate,'doctor',return_value={'ok':True});self.doctor=self.health.start();self.addCleanup(self.health.stop)
        self.online_patch=patch.object(gate,'online',return_value={'configured':True});self.online=self.online_patch.start();self.addCleanup(self.online_patch.stop)
        self.process_patch=patch.object(k,'process',return_value={'state':'ready','pending':False,'snapshot':'audited'});self.process=self.process_patch.start();self.addCleanup(self.process_patch.stop)
        self.output=contextlib.redirect_stderr(io.StringIO());self.output.__enter__();self.addCleanup(self.output.__exit__,None,None,None)
    def configured(self):
        k.write(self.root/'settings.json',{'python':sys.executable,'model':'preserve-extraction','ollama':'http://127.0.0.1:11435'})
        with k.locked(self.root):k.reconcile_shared(self.root)


class KnowledgeGateTests(KnowledgeGateFixture, unittest.TestCase):
    def test_noninteractive_missing_never_reads_or_downloads(self):
        with self.assertRaisesRegex(ValueError,'requires consent'):
            gate.provision(self.root,interactive=False,choose=lambda:self.fail('must not read'))
        self.online.assert_not_called();self.process.assert_not_called()
    def test_interactive_download_and_decline_are_explicit(self):
        self.assertEqual('ready',gate.provision(self.root,interactive=True,choose=lambda:'download')['state'])
        self.online.assert_called_once();self.process.assert_called_once()
        self.root=Path(self.tmp.name)/'declined'
        with self.assertRaisesRegex(ValueError,'canceled'):gate.provision(self.root,interactive=True,choose=lambda:'no')
        self.assertFalse((self.root/'settings.json').exists())
    def test_interactive_defer_visible_without_acquisition(self):
        result=gate.provision(self.root,interactive=True,choose=lambda:'defer')
        self.assertFalse(result['ready']);self.assertEqual('deferred',result['state'])
        self.assertIn('flow update',result['resume']);self.assertTrue(list((self.root/'notes').glob('*.md')))
        self.online.assert_not_called();self.process.assert_not_called()
    def test_healthy_assets_reused_without_consent_or_download(self):
        self.configured();before=(self.root/'settings.json').read_bytes()
        (self.root/'notes/local.md').write_text('Unpromoted private edit.\n')
        result=gate.provision(self.root,interactive=False,choose=lambda:self.fail('must not prompt'))
        self.assertTrue(result['reused_assets']);self.online.assert_not_called()
        self.assertEqual(before,(self.root/'settings.json').read_bytes());self.assertEqual('Unpromoted private edit.\n',(self.root/'notes/local.md').read_text())
    def test_offline_reuses_or_fails_without_network(self):
        with self.assertRaisesRegex(ValueError,'Offline knowledge assets'):gate.provision(self.root,'offline')
        self.online.assert_not_called();self.configured()
        self.assertEqual('ready',gate.provision(self.root,'offline')['state']);self.online.assert_not_called()
    def test_broken_config_download_preserves_extraction_selection(self):
        self.configured();self.doctor.return_value={'ok':False}
        gate.provision(self.root,'download')
        self.online.assert_called_once_with(self.root,sys.executable,'preserve-extraction','http://127.0.0.1:11435')
    def test_missing_model_fails_without_claiming_ready_or_processing(self):
        self.online.return_value={'configured':False,'assets_ready':True,'required_model_setup':{'commands':['fixture Ollama requirement']}}
        with self.assertRaisesRegex(ValueError,'chat weights were not downloaded'):gate.provision(self.root,'download')
        self.process.assert_not_called()
    def test_failed_or_pending_snapshot_is_not_install_success(self):
        self.process.return_value={'state':'failed','pending':True}
        with self.assertRaisesRegex(ValueError,'did not become ready'):gate.provision(self.root,'download')


class KnowledgeTransactionFixture:
    def setUp(self):
        self.fixture=fixtures.ManagedReleaseTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.store=self.fixture.home/'.flow/v2/state/knowledge'
    def run_install(self,runner,version=None):
        manifest=self.fixture.manifest if version is None else {**self.fixture.manifest,'version':version,'source_sha':'b'*40}
        return managed.install_release(self.fixture.home,manifest,bundle=self.fixture.bundle,preparer=self.fixture.prepare,knowledge_mode='download',knowledge_runner=runner)
    def seed(self,text):
        (self.store/'notes').mkdir(parents=True,exist_ok=True);(self.store/'notes/local.md').write_text(text)
        k.write(self.store/'settings.json',{'python':'preserve-runtime','ollama':'http://127.0.0.1:11435'})
        k.write(self.store/'CURRENT.json',{'generation':'known-good'})


class KnowledgeTransactionTests(KnowledgeTransactionFixture, unittest.TestCase):
    def test_failure_before_activation_restores_authority_and_preserves_assets(self):
        self.seed('User authored.\n');before=(self.store/'settings.json').read_bytes()
        def fail(release,root,mode):
            (self.store/'notes/local.md').write_text('Failed attempt.\n');k.record_install_write(self.store/'notes/local.md',b'Failed attempt.\n')
            k.write(self.store/'settings.json',{'python':'failed'})
            (self.store/'provisioning/assets').mkdir(parents=True);(self.store/'provisioning/assets/verified').write_text('retained')
            raise ValueError('fixture failed acquisition')
        with self.assertRaisesRegex(ValueError,'failed acquisition'):self.run_install(fail)
        self.assertFalse((self.fixture.home/'.flow/v2/current').exists())
        self.assertEqual('User authored.\n',(self.store/'notes/local.md').read_text());self.assertEqual(before,(self.store/'settings.json').read_bytes())
        self.assertEqual('known-good',k.read(self.store/'CURRENT.json')['generation'])
        self.assertTrue((self.store/'provisioning/assets/verified').exists());self.assertTrue(list((self.fixture.home/'.flow/v2/backups').glob('knowledge-unselected-*/notes/local.md')))
        self.assertFalse(k.read(self.store/'last-install-failure.json')['runtime_activated'])
    def test_existing_update_failure_keeps_runtime_launcher_and_provider(self):
        self.seed('User authored.\n');first=self.run_install(lambda *a:{'state':'ready'})
        launcher=(self.fixture.home/'.local/bin/flow').read_bytes()
        provider=self.fixture.home/'.flow/v2/state/codex-home/config.toml';provider.parent.mkdir(parents=True,exist_ok=True);provider.write_text('model_provider="local"\n')
        def fail(*args):
            k.write(self.store/'CURRENT.json',{'generation':'bad'});raise ValueError('fixture snapshot failure')
        with self.assertRaisesRegex(ValueError,'snapshot failure'):self.run_install(fail,'v0.53.0')
        self.assertEqual(Path(first['runtime']),(self.fixture.home/'.flow/v2/current').resolve());self.assertEqual(launcher,(self.fixture.home/'.local/bin/flow').read_bytes())
        self.assertEqual('model_provider="local"\n',provider.read_text());self.assertEqual('known-good',k.read(self.store/'CURRENT.json')['generation'])
    def test_noop_update_still_completes_deferred_provisioning(self):
        calls=[]
        def run(release,root,mode):calls.append((release,mode));return {'state':'ready'}
        self.run_install(run);result=self.run_install(run)
        self.assertFalse(result['changed']);self.assertEqual(2,len(calls));self.assertEqual('ready',result['knowledge']['state'])
    def test_rollback_restores_prior_knowledge_and_rejects_new_manual_edits(self):
        self.seed('Before.\n');first=self.run_install(lambda *a:{'state':'ready'})
        def update(*args):(self.store/'notes/local.md').write_text('Shared update.\n');k.record_install_write(self.store/'notes/local.md',b'Shared update.\n');return {'state':'ready'}
        self.run_install(update,'v0.53.0');managed.rollback(self.fixture.home)
        self.assertEqual('Before.\n',(self.store/'notes/local.md').read_text())
        self.run_install(update,'v0.53.0');(self.store/'notes/local.md').write_text('Manual edit.\n')
        with self.assertRaisesRegex(ValueError,'Knowledge edits prevent rollback'):managed.rollback(self.fixture.home)
        self.assertEqual('Manual edit.\n',(self.store/'notes/local.md').read_text())


class KnowledgeConcurrencyTests(KnowledgeTransactionFixture, unittest.TestCase):
    def test_failed_install_preserves_unexpected_manual_edits_and_deletions(self):
        self.seed('Before.\n')
        (self.store/'notes/deleted.md').write_text('Before deletion.\n')
        def fail(*args):
            (self.store/'notes/local.md').write_text('Installer change.\n');k.record_install_write(self.store/'notes/local.md',b'Installer change.\n')
            (self.store/'notes/local.md').write_text('Manual edit during download.\n')
            (self.store/'notes/deleted.md').unlink()
            (self.store/'manual.json').write_text('{"user":"keep"}')
            raise ValueError('controlled failure')
        with self.assertRaisesRegex(ValueError,'controlled failure'):self.run_install(fail)
        self.assertEqual('Manual edit during download.\n',(self.store/'notes/local.md').read_text())
        self.assertFalse((self.store/'notes/deleted.md').exists());self.assertTrue((self.store/'manual.json').exists())
        self.assertIn('notes/local.md',k.read(self.store/'last-install-failure.json')['preserved_conflicts'])
    def test_install_excludes_other_managed_writers(self):
        def run(*args):
            env={**os.environ,'PYTHONPATH':str(k.REPO/'v2')}
            for key in ('FLOW_INSTALL_KNOWLEDGE_FD','FLOW_INSTALL_WRITE_RECEIPT','FLOW_INSTALL_KNOWLEDGE_ROOT'):env.pop(key,None)
            probe=subprocess.run([sys.executable,'-c','from pathlib import Path; from poc.knowledge import locked;\nwith locked(Path('+repr(str(self.store))+'),True):pass'],env=env,capture_output=True,text=True,timeout=5)
            self.assertNotEqual(0,probe.returncode);self.assertIn('BlockingIOError',probe.stderr)
            return {'state':'ready'}
        self.run_install(run)
    def test_added_configuration_blocks_rollback(self):
        self.seed('Before.\n');self.run_install(lambda *a:{'state':'ready'})
        (self.store/'new-config.json').write_text('{"keep":true}')
        with self.assertRaisesRegex(ValueError,'Knowledge edits prevent rollback'):managed.rollback(self.fixture.home)
        self.assertTrue((self.store/'new-config.json').exists())
    def test_manual_edit_at_restore_boundary_is_rechecked(self):
        self.seed('Before.\n');self.run_install(lambda *a:{'state':'ready'})
        real=managed.restore_knowledge
        def race(*args,**kwargs):
            (self.store/'notes/local.md').write_text('Manual boundary edit.\n')
            return real(*args,**kwargs)
        with patch.object(managed,'restore_knowledge',side_effect=race):
            with self.assertRaisesRegex(ValueError,'Knowledge edits prevent rollback'):managed.rollback(self.fixture.home)
        self.assertEqual('Manual boundary edit.\n',(self.store/'notes/local.md').read_text())

class KnowledgeAuditBoundaryTests(KnowledgeTransactionFixture, unittest.TestCase):
    def test_audit_uses_intended_bytes_even_if_manual_edit_precedes_record(self):
        self.seed('Before.\n');replace=Path.replace
        def boundary(path,target):
            result=replace(path,target)
            if Path(target)==self.store/'settings.json':Path(target).write_text('{"manual":"preserve"}')
            return result
        def fail(*args):
            with patch.object(Path,'replace',boundary):k.write(self.store/'settings.json',{'installer':'temporary'})
            raise ValueError('boundary failure')
        with self.assertRaisesRegex(ValueError,'boundary failure'):self.run_install(fail)
        self.assertEqual({'manual':'preserve'},k.read(self.store/'settings.json'))
    def test_same_version_provision_refreshes_rollback_poststate(self):
        self.seed('Original authority.\n')
        def defer(*args):k.write(self.store/'install-status.json',{'state':'deferred'});return {'state':'deferred'}
        self.run_install(defer)
        receipt=self.fixture.home/'.flow/v2/install.json';baseline=k.read(receipt)['knowledge_backup']
        def complete(*args):k.write(self.store/'install-status.json',{'state':'ready'});return {'state':'ready'}
        self.assertFalse(self.run_install(complete)['changed'])
        self.assertEqual(baseline,k.read(receipt)['knowledge_backup'])
        managed.rollback(self.fixture.home)
        self.assertEqual('Original authority.\n',(self.store/'notes/local.md').read_text())
        self.assertFalse((self.store/'install-status.json').exists())

class KnowledgeSuccessfulManualTests(KnowledgeTransactionFixture, unittest.TestCase):
    def test_success_does_not_let_later_rollback_erase_during_install_manual_edit(self):
        self.seed('Before.\n')
        def edit(*args):
            (self.store/'notes/local.md').write_text('Manual while installing.\n')
            (self.store/'new-user-config.json').write_text('{"manual":true}')
            return {'state':'ready'}
        self.run_install(edit);managed.rollback(self.fixture.home)
        self.assertEqual('Manual while installing.\n',(self.store/'notes/local.md').read_text())
        self.assertTrue((self.store/'new-user-config.json').exists())


class KnowledgeCLISelectionTests(unittest.TestCase):
    def test_policies_are_forwarded_and_metadata_checks_never_provision(self):
        manifest={'version':'v-fixture','source_sha':'a'*40,'supported_targets':['Darwin-arm64']}
        for flags,expected in [([], 'ask'),(['--knowledge','download'],'download'),(['--knowledge','defer'],'defer'),(['--non-interactive'],'offline'),(['--json'],'offline')]:
            with self.subTest(flags=flags),patch.object(managed,'supported'),patch.object(managed,'latest',return_value=(manifest,{})),patch.object(managed,'install_release',return_value={'knowledge':{'state':'fixture'}}) as install,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0,managed.main(['update',*flags]))
                self.assertEqual(expected,install.call_args.kwargs['knowledge_mode'])
        with patch.object(managed,'supported'),patch.object(managed,'latest',return_value=(manifest,{})),patch.object(managed,'validate'),patch.object(managed,'install_release') as install,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0,managed.main(['update','--check','--json']))
            install.assert_not_called()

class KnowledgeBusyTests(KnowledgeTransactionFixture, unittest.TestCase):
    def test_busy_writer_rejects_update_before_snapshot_or_mutation(self):
        self.seed('Before.\n')
        import fcntl
        self.store.mkdir(parents=True,exist_ok=True)
        with (self.store/'lock').open('a') as stream:
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.run_install(lambda *args:self.fail('must not run'))
        self.assertEqual('Before.\n',(self.store/'notes/local.md').read_text())
        self.assertFalse((self.store/'last-install-failure.json').exists())


class KnowledgeFailureBoundaryTests(KnowledgeTransactionFixture, unittest.TestCase):
    def test_uncertain_execution_preserves_state_and_blocks_retry(self):
        self.seed('Before.\n')
        def uncertain(*args):
            k.write(self.store/'settings.json',{'staged':'retain-for-inspection'})
            failure=managed.KnowledgeCancellationUncertain('fixture survivor');failure.processes={'root_pid':123,'known':{'123':{'birth':'fixture'}}}
            raise failure
        with self.assertRaises(managed.KnowledgeCancellationUncertain):self.run_install(uncertain)
        self.assertEqual({'staged':'retain-for-inspection'},k.read(self.store/'settings.json'))
        marker=self.fixture.home/'.flow/v2/knowledge-provision-uncertain.json'
        self.assertTrue(marker.exists());self.assertTrue(Path(k.read(marker)['audit']).exists())
        self.assertIn('123',k.read(marker)['processes']['known'])
        with self.assertRaisesRegex(ValueError,'No retry attempted'):self.run_install(lambda *a:self.fail('must not retry'))
    def test_finalization_failure_happens_before_runtime_activation(self):
        self.seed('Before.\n');first=self.run_install(lambda *a:{'state':'ready'})
        def change(*args):k.write(self.store/'CURRENT.json',{'generation':'new'});return {'state':'ready'}
        with patch.object(managed,'finalize_knowledge',side_effect=OSError('fixture disk failure')):
            with self.assertRaisesRegex(OSError,'disk failure'):self.run_install(change,'v0.53.0')
        self.assertEqual(Path(first['runtime']),(self.fixture.home/'.flow/v2/current').resolve())
        self.assertEqual('known-good',k.read(self.store/'CURRENT.json')['generation'])
        self.assertFalse(k.read(self.store/'last-install-failure.json')['runtime_activated'])


class KnowledgeActivationWindowTests(KnowledgeTransactionFixture, unittest.TestCase):
    def test_manual_edit_during_surface_activation_is_not_owned_by_rollback(self):
        from poc import install as surfaces
        self.seed('Before.\n');original=surfaces.install
        def activate(action,*args,**kwargs):
            result=original(action,*args,**kwargs)
            if action=='activate':(self.store/'notes/local.md').write_text('Manual activation-time edit.\n')
            return result
        with patch.object(surfaces,'install',side_effect=activate):self.run_install(lambda *a:{'state':'ready'})
        with self.assertRaisesRegex(ValueError,'Knowledge edits prevent rollback'):managed.rollback(self.fixture.home)
        self.assertEqual('Manual activation-time edit.\n',(self.store/'notes/local.md').read_text())


class KnowledgeBootstrapConsentTests(KnowledgeGateFixture, unittest.TestCase):
    def test_piped_bootstrap_uses_controlling_terminal_not_script_stdin(self):
        terminal=io.StringIO('defer\n')
        with patch.object(gate.sys.stdin,'isatty',return_value=False),patch.object(gate,'open',return_value=terminal,create=True) as opened:
            self.assertEqual('deferred',gate.provision(self.root)['state'])
        opened.assert_called_once_with('/dev/tty','r');self.online.assert_not_called()
    def test_unattended_missing_terminal_fails_without_input(self):
        with patch.object(gate.sys.stdin,'isatty',return_value=False),patch.object(gate,'open',side_effect=OSError('no controlling terminal'),create=True):
            with self.assertRaisesRegex(ValueError,'requires consent'):gate.provision(self.root)
        self.online.assert_not_called()


class KnowledgePriorManualEditTests(KnowledgeTransactionFixture, unittest.TestCase):
    def test_same_version_update_does_not_accept_earlier_edits_for_rollback(self):
        self.seed('Before.\n');(self.store/'notes/deleted.md').write_text('Retain user deletion.\n')
        self.run_install(lambda *a:{'state':'ready'})
        (self.store/'notes/local.md').write_text('User edit before no-op update.\n')
        (self.store/'notes/deleted.md').unlink()
        (self.store/'added-config.json').write_text('{"user":true}')
        self.assertFalse(self.run_install(lambda *a:{'state':'ready'})['changed'])
        with self.assertRaisesRegex(ValueError,'Knowledge edits prevent rollback'):managed.rollback(self.fixture.home)
        self.assertEqual('User edit before no-op update.\n',(self.store/'notes/local.md').read_text())
        self.assertFalse((self.store/'notes/deleted.md').exists());self.assertTrue((self.store/'added-config.json').exists())


if __name__=='__main__':unittest.main()
