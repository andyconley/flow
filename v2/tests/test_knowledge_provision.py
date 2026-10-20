import contextlib,io,json,os,shutil,subprocess,sys,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from poc import knowledge as k
from poc import knowledge_provision as p

class ProvisionTests(unittest.TestCase):
 def test_plan_has_no_download_and_declares_costs(self):
  with tempfile.TemporaryDirectory() as t,patch.object(p,'online') as online,contextlib.redirect_stdout(io.StringIO()) as out:
   self.assertEqual(0,k.main(['--home',t,'setup']));online.assert_not_called();data=json.loads(out.getvalue());self.assertEqual(6*1024**3,data['minimum_free_bytes']);self.assertGreater(data['embedding_bytes'],66000000);self.assertIn('No Ollama',data['network'])
 def test_hash_size_network_and_redirect_failures_leave_no_published_artifact(self):
  with tempfile.TemporaryDirectory() as t:
   dest=Path(t)/'asset';row={'size':3,'sha256':k.digest(b'yes')}
   for body in (b'bad',b'oversized'):
    with patch.object(p,'open_official',return_value=io.BytesIO(body)),self.assertRaises(ValueError):p.download('https://files.pythonhosted.org/fixture',dest,row)
    self.assertFalse(dest.exists());self.assertFalse(list(Path(t).glob('*.partial')))
   with patch.object(p,'open_official',side_effect=urllib.error.URLError('offline')),self.assertRaises(urllib.error.URLError):p.download('https://files.pythonhosted.org/fixture',dest,row)
   self.assertFalse(dest.exists())
  self.assertFalse(p.allowed('https://example.com/model'));self.assertFalse(p.allowed('https://huggingface.co@evil.example/file'));self.assertFalse(p.allowed('http://pypi.org/file'))
  with self.assertRaises(ValueError):p.OfficialRedirect().redirect_request(None,None,302,'',{},'https://evil.example/file')
 def wheel_fixture(self,root):
  lock=root/'pins';lock.write_text('six==1.17.0\n');body=b'fixture wheel bytes';name='six-1.17.0-py2.py3-none-any.whl';row={'filename':name,'packagetype':'bdist_wheel','yanked':False,'url':'https://files.pythonhosted.org/fixture/'+name,'size':len(body),'digests':{'sha256':k.digest(body)}}
  return lock,body,name,{'urls':[row]}
 def test_official_wheel_selection_hashes_resume_and_offline_tamper_failure(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);lock,body,name,metadata=self.wheel_fixture(root);dest=root/'wheels'
   with patch.object(p,'fetch_json',return_value=metadata) as meta,patch.object(p,'open_official',return_value=io.BytesIO(body)):
    hashed=p.wheels(dest,lock);self.assertIn('--hash=sha256:'+k.digest(body),hashed.read_text());self.assertIn('/six/1.17.0/json',meta.call_args.args[0])
   with patch.object(p,'fetch_json') as net:p.wheels(dest,lock,offline=True);net.assert_not_called()
   (dest/name).write_bytes(b'corrupt')
   with patch.object(p,'fetch_json') as net,self.assertRaisesRegex(ValueError,'checksum'):p.wheels(dest,lock,offline=True)
   net.assert_not_called()
 def test_empty_offline_wheelhouse_fails_without_network(self):
  with tempfile.TemporaryDirectory() as t,patch.object(p,'fetch_json') as net:
   root=Path(t);lock=root/'pins';lock.write_text('six==1.17.0\n')
   with self.assertRaisesRegex(ValueError,'No network attempted'):p.wheels(root/'wheels',lock,offline=True)
   net.assert_not_called()
 def test_unsupported_binary_pin_is_actionable_no_source_build(self):
  with tempfile.TemporaryDirectory() as t,patch.object(p,'fetch_json',return_value={'urls':[]}):
   root=Path(t);lock=root/'pins';lock.write_text('six==1.17.0\n')
   with self.assertRaisesRegex(ValueError,'No compatible official binary wheel'):p.wheels(root/'wheels',lock)
 def exercise_online(self,root,model_ok=True):
  hashed=root/'fixture.hashed';hashed.write_text('fixture')
  def run(args,**kw):
   if args[1:3]==['-m','venv']:
    exe=Path(args[-1])/'bin/python';exe.parent.mkdir(parents=True);exe.write_text('fixture')
   return subprocess.CompletedProcess(args,0)
  def embed(cache,manifest):cache.mkdir(parents=True);return cache
  health={'checks':{'dependencies':{'ok':True},'embedding_cache':{'ok':True},'local_model':{'ok':model_ok,'digest':'observed-digest'}}}
  with patch.object(p,'require_host'),patch.object(p,'wheels',return_value=hashed),patch.object(p,'embeddings',side_effect=embed),patch.object(p.subprocess,'run',side_effect=run) as calls,patch('poc.knowledge_health.doctor',return_value=health),patch.object(p.shutil,'disk_usage',return_value=type('Usage',(),{'free':p.MIN_FREE+1})()):
   with k.locked(root):result=p.online(root,sys.executable,'explicit:local','http://127.0.0.1:11435')
  return result,calls
 def test_online_full_setup_preserves_notes_and_never_changes_agent_or_pulls_model(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'notes').mkdir();(root/'notes/manual.md').write_text('Private manual note.\n');(root/'agent-provider').write_text('unchanged');result,calls=self.exercise_online(root)
   self.assertTrue(result['configured']);self.assertFalse(result['agent_provider_changed']);self.assertEqual('Private manual note.\n',(root/'notes/manual.md').read_text());self.assertEqual('unchanged',(root/'agent-provider').read_text());self.assertEqual('explicit:local',k.read(root/'settings.json')['model']);self.assertTrue(list((root/'backups').glob('*.zip')))
   self.assertTrue(any('--require-hashes' in c.args[0] and '--no-index' in c.args[0] for c in calls.call_args_list));self.assertTrue(all('ollama' not in c.args[0] for c in calls.call_args_list))
 def test_missing_model_retains_assets_and_previous_configuration(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);k.write(root/'settings.json',{'manual':'preserved'});result,calls=self.exercise_online(root,False)
   self.assertFalse(result['configured']);self.assertTrue(result['assets_ready']);self.assertEqual({'manual':'preserved'},k.read(root/'settings.json'));self.assertEqual('explicit:local',result['required_model_setup']['model']);self.assertTrue(list((root/'provisioning').glob('*/installed.json')))
 def test_low_disk_prevents_all_acquisition(self):
  with tempfile.TemporaryDirectory() as t,patch.object(p,'require_host'),patch.object(p.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()),patch.object(p,'wheels') as wheels:
   with self.assertRaisesRegex(ValueError,'no download started'):p.online(Path(t),sys.executable,'local','http://localhost:11434')
   wheels.assert_not_called()

 def test_only_exact_allowlisted_source_builds_are_accepted(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);lock=root/'pins';lock.write_text('pybars3==0.9.7\n');pin=k.read(k.SHARED/'source-builds.lock.json')['sources']['pybars3'];wheel=root/'pybars3-0.9.7-py3-none-any.whl';wheel.write_bytes(b'fixture derived wheel')
   item={'filename':pin['filename'],'packagetype':'sdist','url':pin['url'],'size':pin['size'],'digests':{'sha256':pin['sha256']}}
   with patch.object(p,'fetch_json',return_value={'urls':[item]}),patch.object(p,'build_source',return_value=wheel) as build:
    p.wheels(root/'wheels',lock);build.assert_called_once();receipt=k.read(root/'wheels/verified.json');self.assertEqual(pin,receipt['files'][wheel.name]['source'])
   item['digests']['sha256']='changed'
   with patch.object(p,'fetch_json',return_value={'urls':[item]}),patch.object(p,'build_source') as build,self.assertRaisesRegex(ValueError,'source release changed'):p.wheels(root/'new-wheels',lock)
   build.assert_not_called()
 def test_source_builder_has_no_unsandboxed_retry(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);pin=k.read(k.SHARED/'source-builds.lock.json')['sources']['pybars3'];tools=root/('build-tools-'+k.digest((k.SHARED/'build-requirements.lock').read_bytes())[:16]);(tools/'runtime/bin').mkdir(parents=True);(tools/'runtime/bin/python').touch();k.write(tools/'ready.json',{'python':str(tools/'runtime/bin/python')});hashed=root/'pins';hashed.write_text('fixture');commands=[]
   def run(args,**kw):
    commands.append(args)
    if args[0]=='/usr/bin/sandbox-exec':raise subprocess.CalledProcessError(1,args)
    return subprocess.CompletedProcess(args,0)
   with patch.object(p.sys,'platform','darwin'),patch.object(p,'download'),patch.object(p,'wheels',return_value=hashed),patch.object(p.subprocess,'run',side_effect=run),self.assertRaises(subprocess.CalledProcessError):p.build_source(root,'pybars3',pin)
   sandbox=[c for c in commands if c[0]=='/usr/bin/sandbox-exec'];self.assertEqual(1,len(sandbox));self.assertIn('(deny network*)',sandbox[0][2]);self.assertIn('--no-build-isolation',sandbox[0]);self.assertIn('--no-index',sandbox[0])
 def test_missing_model_candidate_is_discoverable_without_changing_active_config(self):
  from poc.knowledge_health import hint
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);result,_=self.exercise_online(root,False);self.assertFalse(result['configured']);candidate=k.read(root/'provisioned-runtime.json');self.assertTrue(Path(candidate['python']).is_file());self.assertFalse((root/'settings.json').exists());self.assertTrue(hint(root)['python_present']);self.assertFalse(hint(root)['configured'])
 def test_acquisition_failure_remains_visible_without_forced_retry(self):
  with tempfile.TemporaryDirectory() as t,patch.object(p,'online',side_effect=ValueError('fixture offline failure')),contextlib.redirect_stderr(io.StringIO()):
   root=Path(t);self.assertEqual(1,k.main(['--home',str(root),'setup','--download']));self.assertEqual('failed',k.status(root)['provisioning']['acquisition']['state']);self.assertFalse((root/'settings.json').exists())

 def test_cli_success_enqueues_indexing_and_preserves_existing_extraction_selection(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);k.write(root/'settings.json',{'model':'already:chosen','ollama':'http://127.0.0.1:11435'})
   with patch.object(p,'online',return_value={'configured':True,'assets_ready':True}) as online,patch.object(k,'trigger',return_value={'pending':True}) as trigger,contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(0,k.main(['--home',str(root),'setup','--download']))
   self.assertEqual('already:chosen',online.call_args.args[2]);self.assertEqual('http://127.0.0.1:11435',online.call_args.args[3]);trigger.assert_called_once_with(root);self.assertEqual('ready',k.read(root/'provisioning-status.json')['state'])
 def test_ordinary_status_and_note_write_never_acquire(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);note=root/'input';note.write_text('Manual note.\n')
   with patch.object(p,'online') as acquire,patch.object(k,'trigger',return_value={'pending':True}),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(0,k.main(['--home',str(root),'status']));self.assertEqual(0,k.main(['--home',str(root),'write','a.md','--from-file',str(note)]))
   acquire.assert_not_called()
