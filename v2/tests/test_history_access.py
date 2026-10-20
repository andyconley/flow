"""Real CLI discovery/handoff and compatibility reports; preserved bytes, no providers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from poc import history
from poc.glg import ROOT, storage
from poc.artifacts import Artifacts


class HistoryAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.project = self.root/'project'; self.project.mkdir()
        self.home = self.root/'home'; self.home.mkdir()
        self.environment = {**os.environ,'HOME':str(self.home)}
        self.run_dir = self.project/'.flow/runs/old-work'; self.run_dir.mkdir(parents=True)
        self.run = self.run_dir/'run.json'; self.run.write_text(json.dumps({'work_id':'old-work','state':'implementing','runtime':'openhands','approval':'legacy-only'}))
        (self.run_dir/'abstract.json').write_text(json.dumps({'work_id':'old-work','summary':'retained archive decision'}))
        self.digest = hashlib.sha256(self.run.read_bytes()).hexdigest()
        self.addCleanup(lambda: shutil.rmtree(storage(self.project,'new-work').parent,ignore_errors=True))

    def cli(self,*arguments,expected=0):
        result = subprocess.run([sys.executable,'-m','poc.glg','--project',str(self.project),*arguments],env=self.environment,capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,expected,result.stderr+result.stdout)
        return json.loads(result.stdout) if expected==0 and result.stdout.strip() else result

    def test_context_and_runs_expose_preserved_legacy_without_claiming_resume(self):
        value = self.cli('context')
        self.assertEqual(value['legacy_work'][0]['work_id'],'old-work')
        runs = self.cli('runs'); self.assertEqual(runs['current'],[])
        self.assertFalse(runs['legacy'][0]['native_v2_resume'])
        self.assertEqual(hashlib.sha256(self.run.read_bytes()).hexdigest(),self.digest)
        self.assertFalse((self.project/'.glg').exists())

    def test_legacy_status_is_read_only_and_native_resume_is_explicitly_refused(self):
        value = self.cli('--work','old-work','status','--legacy')
        self.assertEqual(value['record']['state'],'implementing'); self.assertFalse(value['approval_imported'])
        failure = self.cli('--work','old-work','resume',expected=2)
        self.assertIn('original runtime',failure.stderr)
        self.assertEqual(hashlib.sha256(self.run.read_bytes()).hexdigest(),self.digest)

    def test_handoff_creates_new_approval_boundary_with_controlled_historical_reference(self):
        brief = self.root/'brief.json'; brief.write_text(json.dumps({'goal':'successor','scope':['README'],'acceptance_criteria':['documented'],'check_command':[sys.executable,'-m','unittest']}))
        value = self.cli('--work','new-work','create','--legacy-run','old-work','--brief-file',str(brief))
        self.assertTrue(value['pending']); self.assertNotIn('approval_ref',value['references'])
        saved = json.loads((self.project/value['references']['brief_ref']['path']).read_text())['payload']
        reference = saved['historical_references'][0]
        self.assertEqual(reference['revision'],self.digest); self.assertFalse(reference['approval_imported'])
        self.assertEqual(hashlib.sha256(self.run.read_bytes()).hexdigest(),self.digest)
        self.assertFalse(list((self.project/'.glg/work/new-work/results').glob('*.json')))
        self.assertEqual(self.cli('runs')['current'][0]['work_id'],'new-work')

    def test_handoff_rejects_same_identity_and_symlink_escape(self):
        failure = self.cli('--work','old-work','create','--request','new','--legacy-run','old-work',expected=2)
        self.assertIn('distinct new',failure.stderr)
        self.assertFalse(storage(self.project,'old-work').exists())
        failure = self.cli('--work','old-work','resume',expected=2)
        self.assertIn('original runtime',failure.stderr)
        outside = self.root/'outside'; outside.mkdir(); (outside/'run.json').write_text('{}')
        (self.project/'.flow/runs/escaped').symlink_to(outside,target_is_directory=True)
        with self.assertRaisesRegex(ValueError,'escapes'):
            history.legacy_run(self.project,'escaped')

    def test_empty_checkpoint_from_rejected_creation_retains_legacy_guidance(self):
        from langgraph.checkpoint.sqlite import SqliteSaver
        path = storage(self.project,'old-work')/'workflow.sqlite'
        path.parent.mkdir(parents=True)
        with SqliteSaver.from_conn_string(str(path)) as saver:
            self.assertIsNone(saver.get({'configurable': {'thread_id': 'old-work'}}))
        before = self.run.read_bytes()
        for command in ['status', 'resume']:
            failure = self.cli('--work','old-work',command,expected=2)
            self.assertIn('No v2 checkpoint exists',failure.stderr)
            self.assertIn('original runtime',failure.stderr)
            self.assertNotIn('runtime_options',failure.stderr)
        self.assertEqual(self.run.read_bytes(),before)

    def test_archive_search_and_backlog_view_leave_history_and_ranked_text_unchanged(self):
        path = self.project/'docs/backlog.md'; path.parent.mkdir(); path.write_text('# Backlog\n\n1. Keep ranked work first\n')
        before = path.read_bytes(); abstract = self.run_dir/'abstract.json'; archived = abstract.read_bytes()
        value = self.cli('archive','search','decision')
        self.assertEqual(value['records'][0]['origin'],'legacy'); self.assertIsNone(value['records'][0]['current'])
        self.assertIn('historical',value['records'][0]['verification'])
        backlog = self.cli('backlog','list','--file','docs/backlog.md')
        self.assertEqual(backlog['documents'][0]['content'],before.decode()); self.assertFalse(backlog['writes'])
        self.assertEqual(path.read_bytes(),before); self.assertEqual(abstract.read_bytes(),archived)

    def test_archive_output_is_bounded_without_deleting_oversized_original(self):
        path = self.run_dir/'abstract.json'; path.write_text(json.dumps({'summary':'x'*20000}))
        value = self.cli('archive','list','--max-output-bytes','1024')
        self.assertLessEqual(len(json.dumps(value,indent=2).encode()),1024)
        self.assertTrue(path.exists()); self.assertEqual(Path(value['records'][0]['path']),path.resolve())
        self.assertIn('content_omitted',value['records'][0])

    def test_explicit_registry_is_read_without_invented_registration(self):
        path = self.project/'projects.json'; path.write_text('{"existing-project":"/example"}\n')
        before = path.read_bytes(); value = self.cli('projects','--file','projects.json')
        self.assertFalse(value['writes']); self.assertEqual(value['registry']['content'],before.decode())
        self.assertEqual(path.read_bytes(),before)

    def test_legacy_cost_bridge_uses_canonical_modules_not_untrusted_project_imports(self):
        marker = self.project/'untrusted-imported'
        (self.project/'paths.py').write_text('from pathlib import Path\nPath("untrusted-imported").write_text("bad")\nraise RuntimeError("untrusted import")\n')
        value = self.cli('cost','summary','--all','--json')
        self.assertIsInstance(value,dict); self.assertFalse(marker.exists())
        self.assertTrue((self.home/'.flow/usage.db').exists())

    def test_read_only_run_bridge_cannot_dispatch_legacy_execution(self):
        failure = self.cli('run','transition','old-work','implement',expected=2)
        self.assertIn('read-only',failure.stderr)
        self.assertEqual(hashlib.sha256(self.run.read_bytes()).hexdigest(),self.digest)

    def test_new_closure_followups_do_not_claim_current_or_rewrite_backlog(self):
        reference=Artifacts(self.project,'closed-work').publish('closures','closure',{'outcome':'ready','acceptance':'not-recorded','followups':['consider later']})
        value=history.backlog(self.project)
        followup=value['closure_followups'][0]
        self.assertEqual(followup['followups'],['consider later']); self.assertIsNone(followup['current'])
        self.assertEqual(followup['acceptance'],'not-recorded'); self.assertFalse(value['writes'])
        path=self.project/reference['path'];path.write_text(path.read_text()+'\n')
        observed=history.archives(self.project)
        self.assertTrue(any('diagnostic' in row for row in observed['records'] if row['origin']=='v2'))
        self.assertEqual(history.backlog(self.project)['closure_followups'],[])

    def test_search_decodes_unicode_without_changing_legacy_bytes(self):
        path=self.run_dir/'abstract.json';path.write_text(json.dumps({'summary':'décision retained'}))
        before=path.read_bytes();value=self.cli('archive','search','décision')
        self.assertEqual(value['matched'],1);self.assertEqual(path.read_bytes(),before)

    def test_corrupt_new_checkpoint_does_not_hide_preserved_legacy_history(self):
        target=storage(self.project,'corrupt-work')/'workflow.sqlite';target.parent.mkdir(parents=True)
        target.write_bytes(b'not a database')
        value=self.cli('context')
        self.assertEqual(value['legacy_work'][0]['work_id'],'old-work')
        self.assertFalse(value['work'][0]['native_v2_resume']);self.assertIn('diagnostic',value['work'][0])
        self.assertEqual(target.read_bytes(),b'not a database')
