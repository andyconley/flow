import contextlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from poc import knowledge as k
from poc.knowledge_health import doctor
class KnowledgeHealthTests(unittest.TestCase):
 def test_seeded_status_shows_supported_setup_and_diagnostics(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);k.write(root/'base.json',{'files':{}})
   result=k.status(root)['provisioning'];self.assertFalse(result['configured']);self.assertFalse(result['python_present']);self.assertTrue(result['diagnostics'].endswith(' doctor'));self.assertIn(str(root),result['diagnostics']);self.assertIn('--download',result['setup']);self.assertIn('--wheelhouse',result['offline_setup'])
 def test_missing_dependencies_and_model_are_independent_visible_failures(self):
  with tempfile.TemporaryDirectory() as t,patch('poc.knowledge_health.subprocess.run',return_value=subprocess.CompletedProcess([],1,stdout='',stderr='No module named basic_memory')),patch.object(k,'local_model_digest',side_effect=ValueError('Configured local model not installed')):
   data=doctor(Path(t),python=sys.executable,cache='/absent/cache',model='missing:fixture')
   self.assertFalse(data['ok']);self.assertFalse(data['checks']['dependencies']['ok']);self.assertIn('basic_memory',data['checks']['dependencies']['detail']);self.assertFalse(data['checks']['local_model']['ok']);self.assertFalse(data['downloads_attempted']);self.assertIn(str(k.SHARED/'requirements.lock'),data['commands']['dependency_lock'])
 def test_local_cache_probe_cannot_download_and_cli_preserves_notes(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'notes').mkdir();(root/'notes/a.md').write_text('Authored.\n');before=k.inventory(root/'notes')
   success=subprocess.CompletedProcess([],0,stdout='',stderr='')
   with patch('poc.knowledge_health.subprocess.run',return_value=success) as run,patch.object(k,'local_model_digest',return_value='digest'),contextlib.redirect_stdout(io.StringIO()) as output:
    self.assertEqual(0,k.main(['--home',str(root),'doctor','--python',sys.executable,'--cache','/fixture/cache','--model','fixture:local']))
   self.assertTrue(json.loads(output.getvalue())['ok']);self.assertEqual(2,run.call_count);self.assertIn('local_files_only=True',run.call_args.args[0][-1]);self.assertIn('lazy_load=False',run.call_args.args[0][-1]);self.assertIn('/fixture/cache',json.loads(output.getvalue())['commands']['configure']);self.assertIn('fixture:local',json.loads(output.getvalue())['commands']['configure']);self.assertIn(str(root),json.loads(output.getvalue())['commands']['configure']);self.assertEqual('1',run.call_args.kwargs['env']['HF_HUB_OFFLINE']);self.assertEqual(before,k.inventory(root/'notes'));self.assertFalse((root/'settings.json').exists())
if __name__=='__main__':unittest.main()
