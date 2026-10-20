import hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from poc import knowledge as k

class KnowledgeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.root=self.base/'local';self.shared=self.base/'shared';(self.shared/'cards').mkdir(parents=True)
  self.publish({'a.md':'---\ntitle: A\n---\nFirst authored rule.\n','b.md':'---\ntitle: B\n---\nSecond authored rule.\n'},'1')
  with k.locked(self.root):k.reconcile_shared(self.root,self.shared)
 def publish(self,files,version):
  for p in (self.shared/'cards').glob('*.md'):p.unlink()
  for n,b in files.items():(self.shared/'cards'/n).write_text(b)
  k.write(self.shared/'manifest.json',{'schema':1,'version':version,'files':{n:k.digest(b.encode()) for n,b in files.items()}})
 def build(self,p):
  self.assertTrue(list((self.root/'backups').glob('*before-enrichment.zip')))
  for n in (p/'notes').glob('*.md'):n.write_text(n.read_text()+k.START+'\n## Relations\n\n'+k.END+'\n')
  return {'passed':True,'unresolved_edges':0}
 def run_build(self):return k.process(self.root,self.build)
 def test_initial_repeat_manual_change_and_remove(self):
  self.run_build();first=k.read(self.root/'CURRENT.json');self.run_build();self.assertEqual(first,k.read(self.root/'CURRENT.json'))
  (self.root/'notes/a.md').write_text('Manual edited rule.\n');self.assertTrue(k.status(self.root)['pending']);self.run_build();self.assertEqual('Manual edited rule.\n',(k.snapshot(self.root)/'notes/a.md').read_text().split(k.START)[0])
  (self.root/'notes/b.md').unlink();self.run_build();self.assertFalse((k.snapshot(self.root)/'notes/b.md').exists())
 def test_failed_build_keeps_previous_snapshot_and_authored_notes(self):
  self.run_build();first=k.read(self.root/'CURRENT.json');(self.root/'notes/a.md').write_text('Changed locally.\n')
  def fail(p):
   (p/'notes/a.md').write_text('DELETED AUTHORSHIP');raise RuntimeError('injected')
  with self.assertRaisesRegex(RuntimeError,'injected'):k.process(self.root,fail)
  self.assertEqual(first,k.read(self.root/'CURRENT.json'));self.assertEqual('Changed locally.\n',(self.root/'notes/a.md').read_text());self.assertEqual('failed',k.status(self.root)['state'])
  k.write(self.root/'status.json',{'state':'running'});self.run_build();self.assertEqual('ready',k.status(self.root)['state'])
 def test_fetch_three_way_preserves_edits_deletions_and_conflicts(self):
  (self.root/'notes/a.md').write_text('Unpromoted manual edit.\n');(self.root/'notes/b.md').unlink()
  self.publish({'a.md':'Changed shared.\n','b.md':'Changed shared B.\n','c.md':'New.\n'},'2')
  with k.locked(self.root):r=k.reconcile_shared(self.root,self.shared)
  self.assertEqual(['a.md','b.md'],r['conflicts']);self.assertEqual('Unpromoted manual edit.\n',(self.root/'notes/a.md').read_text());self.assertFalse((self.root/'notes/b.md').exists());self.assertTrue((self.root/'notes/c.md').exists())
 def test_clean_fetch_deletion_and_seed_repeat(self):
  self.publish({'a.md':'New shared.\n'},'2')
  with k.locked(self.root):k.reconcile_shared(self.root,self.shared);k.reconcile_shared(self.root,self.shared)
  self.assertFalse((self.root/'notes/b.md').exists());self.assertEqual('New shared.\n',(self.root/'notes/a.md').read_text())
 def test_generated_edits_fail_closed_and_no_feedback(self):
  self.run_build();fp=k.fingerprint(self.root)
  self.assertEqual(fp,k.fingerprint(self.root));self.assertNotIn(k.START,(self.root/'notes/a.md').read_text())
  p=self.root/'notes/a.md';p.write_text(p.read_text()+k.START+'\nMANUAL\n'+k.END+'\n')
  # Generated output cannot trigger a feedback loop, but attempted processing checks ownership.
  self.assertNotEqual(fp,k.fingerprint(self.root));(self.root/'notes/b.md').write_text('Edited other input.\n')
  with self.assertRaisesRegex(ValueError,'Manual edit'):self.run_build()
 def test_midbuild_edit_and_invalid_inventory_cannot_publish(self):
  self.run_build();first=k.read(self.root/'CURRENT.json');(self.root/'notes/a.md').write_text('Start\n')
  def race(p):
   (self.root/'notes/a.md').write_text('External edit during build\n');return self.build(p)
  with self.assertRaisesRegex(ValueError,'Inputs changed'):k.process(self.root,race)
  self.assertEqual(first,k.read(self.root/'CURRENT.json'));self.assertEqual('External edit during build\n',(self.root/'notes/a.md').read_text())
  (self.root/'notes/b.md').unlink();(self.root/'notes/b.md').symlink_to('/etc/hosts')
  with self.assertRaisesRegex(ValueError,'Symlink'):k.inventory(self.root/'notes')
 def test_authored_deletion_by_whole_file_writer_refused(self):
  def bad(p):(p/'notes/a.md').write_text('lost');return {'passed':True}
  with self.assertRaisesRegex(ValueError,'authored'):k.process(self.root,bad)
 def test_code_and_settings_versions_reconcile(self):
  self.run_build();k.write(self.root/'settings.json',{'model':'updated local model'});self.assertTrue(k.status(self.root)['pending'])
 def test_agent_extension_and_cli_dispatch(self):
  from poc.knowledge_tools import attach
  with patch.dict(os.environ,FLOW_KNOWLEDGE_HOME=str(self.root)):
   k.write(self.root/'settings.json',{'python':'/safe path/python'});self.run_build();
   with patch('poc.knowledge_tools.require_ready'):cmd,env=attach(['goose','run'],{})
  self.assertIn('--with-extension',cmd);self.assertIn("'/safe path/python'",cmd[-1]);self.assertEqual(str(self.root),env['FLOW_KNOWLEDGE_HOME'])
 def test_unchanged_shared_fetch_leaves_local_edits_and_deletions_unconflicted(self):
  (self.root/'notes/a.md').write_text('Local edit.\n');(self.root/'notes/b.md').unlink()
  with k.locked(self.root):result=k.reconcile_shared(self.root,self.shared)
  self.assertEqual([],result['conflicts']);self.assertEqual('Local edit.\n',(self.root/'notes/a.md').read_text());self.assertFalse((self.root/'notes/b.md').exists())
 def test_current_publication_recovers_status_after_crash_before_ready_write(self):
  self.run_build();current=k.read(self.root/'CURRENT.json');k.write(self.root/'status.json',{'state':'running',**current})
  self.assertEqual('ready',k.status(self.root)['state']);self.assertFalse(k.status(self.root)['pending'])
  with patch.dict(os.environ,FLOW_KNOWLEDGE_READONLY='1'):
   self.assertEqual('ready',k.status(self.root)['state']);self.assertFalse(k.status(self.root)['pending'])
  with patch.object(k.subprocess,'Popen') as launch:k.trigger(self.root);launch.assert_not_called()
 def test_export_and_restore_are_runtime_independent(self):
  import contextlib,io
  with patch.object(k,'trigger',return_value={'pending':True}),contextlib.redirect_stdout(io.StringIO()) as out:
   self.assertEqual(0,k.main(['--home',str(self.root),'export']))
  export=Path(json.loads(out.getvalue())['export']);self.assertTrue((export/'manifest.json').exists())
  archive=next((self.root/'backups').glob('*before-export.zip'));original=k.inventory(self.root/'notes')
  (self.root/'notes/a.md').write_text('Local edit to restore explicitly.\n')
  with patch.object(k,'trigger',return_value={'pending':True}),contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,k.main(['--home',str(self.root),'restore',str(archive)]))
  self.assertEqual(original,k.inventory(self.root/'notes'));self.assertTrue(list((self.root/'backups').glob('*before-restore.zip')))
 def test_failed_fingerprint_does_not_spin_or_block_known_good(self):
  self.run_build();old=k.read(self.root/'CURRENT.json');(self.root/'notes/a.md').write_text('A real edit.\n')
  k.write(self.root/'status.json',{'state':'failed','fingerprint':k.fingerprint(self.root),'error':'injected'})
  with patch.object(k.subprocess,'Popen') as launch:
   state=k.trigger(self.root);launch.assert_not_called()
  self.assertTrue(state['pending']);self.assertEqual(old,k.read(self.root/'CURRENT.json'));self.assertTrue(k.snapshot(self.root).exists())
if __name__=='__main__':unittest.main()
