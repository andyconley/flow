"""Distribution fixtures: real Git transport and installed code, no private publishing."""
import contextlib,io,json,os,shutil,socket,subprocess,sys,tarfile,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from poc import knowledge as k
from poc.knowledge_tools import require_ready,KnowledgeUnavailable

class DistributionTests(unittest.TestCase):
 def test_corpus_only_changes_run_offline_workflow(self):
  import yaml
  workflow=yaml.safe_load((k.REPO/'.github/workflows/flow-v2.yml').read_text());events=workflow.get('on',workflow.get(True))
  for event in ('pull_request','push'):self.assertIn('knowledge/**',events[event]['paths'])

 def test_unprovisioned_installed_store_blocks_before_provider(self):
  from poc.goose_job import GooseJob
  from poc.contracts import task_input_digest
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);k.write(root/'base.json',{'version':'seeded','files':{}})
   with patch.dict(os.environ,FLOW_KNOWLEDGE_HOME=str(root)):
    with self.assertRaisesRegex(KnowledgeUnavailable,'not provisioned'):require_ready()
    state={'job_id':'knowledge-readiness-fixture','task':'fixture','workspace':t,'inputs':task_input_digest('fixture',t,'')}
    with patch('poc.goose_job.subprocess.Popen') as launch:
     result=GooseJob()._run(state,'implement','fixture');launch.assert_not_called()
    self.assertEqual('knowledge_preflight',result['source']);self.assertFalse(result['submitted'])
 def test_invalid_shared_version_cannot_escape_local_home(self):
  with tempfile.TemporaryDirectory() as t:
   shared=Path(t)/'shared';(shared/'cards').mkdir(parents=True);(shared/'cards/a.md').write_text('Shared.\n')
   k.write(shared/'manifest.json',{'schema':1,'version':'../../escape','files':{'a.md':k.digest(b'Shared.\n')}})
   with self.assertRaisesRegex(ValueError,'version'):k.reconcile_shared(Path(t)/'local',shared)
 @unittest.skipUnless(os.environ.get('FLOW_TEST_GIT_REMOTE')=='1','explicit loopback Git integration test')
 def test_real_remote_fetch_update_conflicts_and_runtime_independence(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);work=root/'upstream';work.mkdir();bare=root/'corpus.git';local=root/'installed/state/knowledge'
   def git(*args,cwd=work):return subprocess.check_output(['git',*args],cwd=cwd,text=True,stderr=subprocess.DEVNULL).strip()
   git('init','-q');git('config','user.name','Flow fixture');git('config','user.email','fixture@invalid.local');git('checkout','-b','fixture')
   def publish(files,version):
    folder=work/'knowledge/cards';folder.mkdir(parents=True,exist_ok=True)
    for p in folder.glob('*.md'):p.unlink()
    for n,text in files.items():(folder/n).write_text(text)
    k.write(work/'knowledge/manifest.json',{'schema':1,'version':version,'files':{n:k.digest(text.encode()) for n,text in files.items()}})
    git('add','.');git('commit','-qm',version)
    if bare.exists():git('fetch',str(work),'fixture:fixture',cwd=bare)
    else:git('clone','--bare',str(work),str(bare))
   publish({'a.md':'Authored A.\n','b.md':'Authored B.\n'},'1')
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   daemon=subprocess.Popen(['git','daemon','--export-all','--reuseaddr','--listen=127.0.0.1','--port='+str(port),'--base-path='+str(root),str(bare)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    for _ in range(40):
     try:
      with socket.create_connection(('127.0.0.1',port),timeout=.1):break
     except OSError:time.sleep(.05)
    url='git://127.0.0.1:'+str(port)+'/corpus.git'
    env={'GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'url.'+url+'.insteadOf','GIT_CONFIG_VALUE_0':'https://github.com/andyconley/flow.git'}
    with patch.dict(os.environ,env):
     with k.locked(local):first=k.reconcile_shared(local,k.fetch_shared(local,'fixture'))
     self.assertEqual('1',first['version']);self.assertEqual('Authored A.\n',(local/'notes/a.md').read_text())
     runtime=root/'installed/current';runtime.write_text('v-fixture-runtime');before=runtime.read_bytes()
     (local/'notes/a.md').write_text('Unpromoted authored local edit.\n');(local/'notes/b.md').unlink()
     publish({'a.md':'Changed shared A.\n','b.md':'Changed shared B.\n','c.md':'New shared C.\n'},'2')
     with k.locked(local):second=k.reconcile_shared(local,k.fetch_shared(local,'fixture'))
     self.assertEqual(['a.md','b.md'],second['conflicts']);self.assertEqual('Unpromoted authored local edit.\n',(local/'notes/a.md').read_text());self.assertFalse((local/'notes/b.md').exists());self.assertTrue((local/'notes/c.md').exists());self.assertEqual(before,runtime.read_bytes())
     receipt=k.read(local/'fetch-receipt.json');self.assertEqual(git('rev-parse','fixture'),receipt['commit'])
     with self.assertRaises(subprocess.CalledProcessError):k.fetch_shared(local,'missing-ref')
     self.assertEqual(before,runtime.read_bytes());self.assertEqual('Unpromoted authored local edit.\n',(local/'notes/a.md').read_text())
   finally:daemon.terminate();daemon.wait(timeout=5)

class FreshInstallKnowledgeTests(unittest.TestCase):
 def test_real_install_seed_and_local_update_without_runtime_change(self):
  from tests.test_managed_release import ManagedReleaseTests
  from poc import managed,goose_artifact
  fixture=ManagedReleaseTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  source=fixture.root/'code';shutil.copytree(k.SHARED,source/'knowledge')
  for name in ('adapters.package.json','adapters.package-lock.json'):shutil.copyfile(k.REPO/'v2'/name,source/'v2'/name)
  archive=fixture.bundle/'flow-code.tar.gz'
  with tarfile.open(archive,'w:gz') as tar:
   tar.add(source/'v2',arcname='v2');tar.add(source/'knowledge',arcname='knowledge')
  fixture.manifest['assets'][archive.name]={'size':archive.stat().st_size,'sha256':managed.sha(archive)}
  real_run=subprocess.run;steps=[]
  def provision(args,**kwargs):
   args=list(map(str,args));steps.append(args)
   if args[1:3]==['-m','venv']:return real_run([args[0],'-m','venv','--without-pip',args[-1]],check=True)
   if 'pip' in args or args[0]=='npm':return subprocess.CompletedProcess(args,0)
   if 'poc.goose_artifact' in args:
    goose_artifact.extract(Path(kwargs['cwd']));return subprocess.CompletedProcess(args,0)
   return real_run(args,**kwargs)
  with patch.object(managed.subprocess,'run',side_effect=provision):result=managed.install_release(fixture.home,fixture.manifest,bundle=fixture.bundle,knowledge_mode='defer')
  local=fixture.home/'.flow/v2/state/knowledge';self.assertEqual(21,len(k.inventory(local/'notes')));self.assertTrue((local/'base.json').exists());self.assertFalse((local/'settings.json').exists())
  launcher=fixture.home/'.local/bin/flow';version=real_run([str(launcher),'--version'],capture_output=True,text=True,env={**os.environ,'HOME':str(fixture.home)},check=True).stdout
  with patch.dict(os.environ,FLOW_KNOWLEDGE_HOME=str(local)):
   with self.assertRaisesRegex(KnowledgeUnavailable,'not provisioned'):require_ready()
  note=next((local/'notes').glob('*.md'));note.write_text(note.read_text()+'\nUnpromoted fixture edit.\n');before=note.read_bytes()
  with k.locked(local):k.reconcile_shared(local,source/'knowledge')
  self.assertEqual(before,note.read_bytes());self.assertEqual(version,real_run([str(launcher),'--version'],capture_output=True,text=True,env={**os.environ,'HOME':str(fixture.home)},check=True).stdout)
  self.assertTrue(any('--no-index' in step for step in steps));self.assertTrue(list((local/'backups').glob('*.zip')))

class ReadinessBoundaryTests(unittest.TestCase):
 def test_missing_bm_dependency_does_not_fall_back(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);py=root/'python';py.write_text('#!/bin/sh\necho BM_DEPENDENCY_MISSING >&2\nexit 3\n');py.chmod(0o755)
   k.write(root/'settings.json',{'python':str(py)});k.write(root/'CURRENT.json',{'generation':'good'});k.write(root/'generations/good/receipt.json',{'audit':{'passed':True}})
   with patch.dict(os.environ,FLOW_KNOWLEDGE_HOME=str(root)):
    with self.assertRaisesRegex(KnowledgeUnavailable,'BM_DEPENDENCY_MISSING'):require_ready()
 def test_readonly_status_delegates_reconciliation_without_model_calls(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);k.write(root/'status.json',{'state':'ready','fingerprint':'x'});k.write(root/'CURRENT.json',{'generation':'g','fingerprint':'x'})
   with patch.dict(os.environ,FLOW_KNOWLEDGE_READONLY='1'),patch.object(k,'fingerprint',side_effect=AssertionError('must not extract from native worker')):
    state=k.status(root)
   self.assertFalse(state['pending']);self.assertEqual('Flow supervisor',state['reconciliation_owner'])
 def test_local_codex_network_permission_requires_explicit_credential_free_loopback(self):
  from poc import native_runtime as n
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);cfg=root/'runtime/codex-home/config.toml';cfg.parent.mkdir(parents=True)
   def save(url,auth):cfg.write_text('model_provider="fixture"\n[model_providers.fixture]\nbase_url='+json.dumps(url)+'\nrequires_openai_auth='+str(auth).lower()+'\n')
   with patch.object(n,'ROOT',root):
    save('http://127.0.0.1:11435/v1',False);self.assertEqual(11435,n.local_codex_endpoint())
    save('http://127.0.0.1:11435/v1',True);self.assertIsNone(n.local_codex_endpoint())
    save('https://example.com/v1',False);self.assertIsNone(n.local_codex_endpoint())

class ProvisioningBehaviorTests(unittest.TestCase):
 @unittest.skipUnless(os.environ.get('FLOW_TEST_SETUP')=='1','explicit offline provisioning integration')
 def test_empty_wheelhouse_and_missing_model_block_without_data_loss(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t)/'store';wheels=Path(t)/'wheels';wheels.mkdir()
   with k.locked(root):k.reconcile_shared(root)
   before=k.inventory(root/'notes')
   with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):code=k.main(['--home',str(root),'setup','--python',sys.executable,'--wheelhouse',str(wheels)])
   self.assertEqual(1,code);self.assertEqual(before,k.inventory(root/'notes'));self.assertFalse((root/'settings.json').exists())
   with patch.dict(os.environ,FLOW_KNOWLEDGE_HOME=str(root)):
    with self.assertRaises(KnowledgeUnavailable):require_ready()
   with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,k.main(['--home',str(root),'export']))
   self.assertTrue(list((root/'exports').glob('*/manifest.json')))
   with contextlib.redirect_stderr(io.StringIO()):
    code=k.main(['--home',str(root),'configure','--python',sys.executable,'--cache',str(Path(t)/'cache'),'--model','fixture-model-that-is-not-installed:never','--ollama','http://127.0.0.1:11435'])
   self.assertEqual(1,code);self.assertEqual(before,k.inventory(root/'notes'));self.assertFalse((root/'settings.json').exists())

if __name__=='__main__':unittest.main()
