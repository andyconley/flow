"""Observed telemetry, context propagation and live status wiring; no inference."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
import contextlib
import io
import time
from unittest.mock import patch

from poc import device_context, monitoring
from poc.artifacts import Artifacts
from poc.glg import summarize
from poc.runtime_env import environment
from poc.goose_job import GooseJob
from poc.contracts import task_input_digest


class MonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.home = self.root/'home'; self.home.mkdir()
        self.project = self.root/'project'; self.project.mkdir()
        self.database = self.root/'runtime/goose-home/data/sessions/sessions.db'
        self.database.parent.mkdir(parents=True)
        self.patch = patch('poc.monitoring.ROOT', self.root); self.patch.start(); self.addCleanup(self.patch.stop)
        roles = self.root/'role-bundle/recipes'; roles.mkdir(parents=True); (roles/'lead-developer.yaml').write_text('title: lead-developer')
        with sqlite3.connect(self.database) as c:
            c.execute('CREATE TABLE sessions(id TEXT,name TEXT,parent_session_id TEXT,working_dir TEXT,recipe_json TEXT,provider_name TEXT,model_config_json TEXT,input_tokens INT,output_tokens INT,total_tokens INT,accumulated_input_tokens INT,accumulated_output_tokens INT,accumulated_total_tokens INT,accumulated_cache_read_tokens INT,accumulated_cache_write_tokens INT,accumulated_cost REAL)')
            c.execute('CREATE TABLE usage_ledger(id INT,session_id TEXT,input_tokens INT,output_tokens INT,total_tokens INT,cache_read_tokens INT,cache_write_tokens INT,cost REAL,cost_source TEXT,is_compaction INT)')

    def session(self, identity, parent=None, tokens=100, provider='ollama', title=None, name=None):
        with sqlite3.connect(self.database) as c:
            c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,name or 'job-implement-1-0',parent,str(self.project),json.dumps({'title':title}),provider,json.dumps({'model_name':'configured-model'}),tokens,10,None if tokens is None else tokens+10,tokens,10,None if tokens is None else tokens+10,None,None,None))

    def test_parent_child_counts_once_and_cumulative_is_not_added_to_ledger(self):
        self.session('parent'); self.session('child','parent',40,title='lead-developer')
        self.session('unrelated',tokens=900,name='other-job')
        with sqlite3.connect(self.database) as c:
            c.execute("INSERT INTO usage_ledger VALUES(1,'parent',50,4,54,NULL,NULL,NULL,'unknown',0)")
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        result = monitoring.report(self.project, job_id='job')
        self.assertEqual(result['totals']['input_tokens'],140)
        self.assertEqual(len(result['sessions']),2)
        self.assertEqual({row['role'] for row in result['sessions']},{'implementation-coordinator','lead-developer'})
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(),before)
        self.assertIsNone(result['totals']['cache_read_tokens'])

    def test_missing_native_metrics_and_subscription_bill_stay_unknown(self):
        self.session('native',tokens=None,provider='codex-acp')
        value = monitoring.report(self.project,job_id='job')
        self.assertIsNone(value['totals']['input_tokens'])
        self.assertEqual(value['coverage']['missing_input_tokens'],1)
        self.assertIsNone(value['actual_billed_cost']); self.assertIsNone(value['reported_cost'])
        self.assertIsNone(value['sessions'][0]['native_context_occupancy'])

    def test_status_reads_actual_job_lineage_and_role_projection(self):
        self.session('root'); self.session('worker','root',40,title='lead-developer')
        snapshot = SimpleNamespace(values={'work_id':'work','job_id':'job','lifecycle_phase':'closed'},tasks=[],next=[])
        value = summarize(snapshot,Artifacts(self.project,'work'))
        self.assertEqual(value['usage']['totals']['input_tokens'],140)
        self.assertEqual(value['usage']['scope']['job_id'],'job')

    def test_status_retains_captured_launch_configuration_in_project_evidence(self):
        artifacts=Artifacts(self.project,'work')
        reference=artifacts.publish('results','implement-1',{'result':{'runtime':{'context_configuration':{'context_tokens':65536,'application_basis':'captured launch'},'goose_session_ids':['observed-worker']}}})
        snapshot=SimpleNamespace(values={'work_id':'work','job_id':'job','result_refs':{'implement-1':reference}},tasks=[],next=[])
        value=summarize(snapshot,artifacts)
        self.assertEqual(value['launch_context'][0]['configuration']['context_tokens'],65536)
        self.assertEqual(value['launch_context'][0]['session_ids'],['observed-worker'])

    def test_metric_observation_failure_does_not_change_task_outcome(self):
        record = {'status':'completed','exit':0}
        with patch('poc.monitoring.report',side_effect=RuntimeError('unavailable')):
            monitoring.attach(record,self.project,'name')
        self.assertEqual(record['status'],'completed'); self.assertFalse(record['usage']['available'])

    def test_absent_store_does_not_create_database_or_fake_zero(self):
        path = self.root/'absent/db'
        value = monitoring.report(database=path)
        self.assertFalse(value['available']); self.assertFalse(path.exists()); self.assertEqual(value['totals'],{})

    def test_context_uses_last_local_request_not_cumulative_and_native_is_unknown(self):
        self.session('local',tokens=64000); self.session('native',provider='claude-acp')
        with sqlite3.connect(self.database) as c:
            c.execute("UPDATE sessions SET accumulated_total_tokens=999999 WHERE id='local'")
        with patch('poc.monitoring.settings',return_value={'context_tokens':65536}):
            result = monitoring.context_report(self.project)
        local = next(r for r in result['observations'] if r['session_id']=='local')
        native = next(r for r in result['observations'] if r['session_id']=='native')
        self.assertLess(local['last_reported_request_percent'],100)
        self.assertIsNotNone(local['warning']); self.assertIsNone(native['last_reported_request_percent'])
        self.assertTrue(result['informational_only'])

    def test_actual_job_captures_profile_environment_and_warns_without_usage_gate(self):
        self.session('root',tokens=64000)
        user = self.home/'.flow/user'; user.mkdir(parents=True)
        (user/'runtime.toml').write_text('[profiles.ollama]\nkind="local"\nmodel="ollama_chat/configured-model"\nmax_input_tokens=65536\n')
        class Process:
            pid = 12345678
            returncode = 0
            def __init__(self): self.polls=0
            def poll(self): self.polls+=1; return None if self.polls==1 else 0
        class Scope:
            def __init__(self,pid): self.known={}
            def observe(self): return {}
        def prepare(workspace,run_dir,bundle,provider=None,model=None):
            return run_dir/'scope.sb',environment(workspace,provider,model)
        state = {'task':'approved','workspace':str(self.project),'project_context':'facts','job_id':'job','deadline':time.time()+10}
        state['inputs']=task_input_digest(state['task'],state['workspace'],state['project_context'])
        output=io.StringIO()
        with patch.dict(os.environ,{'HOME':str(self.home),'GOOSE_INPUT_LIMIT':''}), patch('poc.goose_job.ROOT',self.root), patch('poc.goose_job.ProcessScope',Scope), patch('poc.native_runtime.prepare',side_effect=prepare), patch('poc.goose_job.subprocess.Popen',return_value=Process()) as launch, patch('poc.goose_job.time.sleep'), contextlib.redirect_stderr(output):
            result=GooseJob(provider='ollama',model='configured-model',role_bundle=self.root/'role-bundle')._run(state,'implement','approved instructions')
        self.assertEqual(launch.call_args.kwargs['env']['GOOSE_INPUT_LIMIT'],'65536')
        self.assertEqual(result['context_configuration']['context_tokens'],65536)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['usage']['totals']['input_tokens'],64000)
        self.assertEqual(output.getvalue().count('Flow context observation:'),1)
        saved=json.loads((self.root/'artifacts/job/implement-1-0.json').read_text())
        self.assertEqual(saved['goose_session_ids'],['root'])

    def test_observed_estimate_does_not_become_an_actual_bill(self):
        self.session('root')
        with sqlite3.connect(self.database) as c:
            c.execute("INSERT INTO usage_ledger VALUES(1,'root',100,10,110,0,0,.25,'estimated',1)")
        result=monitoring.report(self.project,job_id='job')
        self.assertEqual(result['reported_cost'],.25); self.assertIsNone(result['actual_billed_cost'])
        self.assertEqual(result['sessions'][0]['cost_sources'],['estimated'])
        self.assertEqual(result['sessions'][0]['goose_compactions'],1)


class DeviceContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)/'home'; self.home.mkdir()
        self.project = Path(self.temp.name)/'project'; self.project.mkdir()
        user = self.home/'.flow/user'; user.mkdir(parents=True)
        (user/'runtime.toml').write_text('[profiles.ollama]\nkind="local"\nmodel="ollama_chat/gemma4-26b-dev:latest"\nmax_input_tokens=65536\nmax_output_tokens=8192\ncondenser_max_tokens=57344\n')
        env = patch.dict(os.environ,{'HOME':str(self.home),'GOOSE_INPUT_LIMIT':''}); env.start(); self.addCleanup(env.stop)

    def test_actual_runtime_environment_honors_existing_64k_profile(self):
        env = environment(project=self.project,provider='ollama',model='gemma4-26b-dev:latest')
        self.assertEqual(env['GOOSE_INPUT_LIMIT'],'65536'); self.assertEqual(env['GOOSE_MAX_TOKENS'],'8192')
        self.assertEqual(float(env['GOOSE_AUTO_COMPACT_THRESHOLD']),.875)
        # Ollama-only input option may be inherited; no local output/threshold override on a native coordinator.
        native = environment(project=self.project,provider='chatgpt_codex',model='current')
        self.assertEqual(native['GOOSE_INPUT_LIMIT'],'65536'); self.assertNotIn('GOOSE_MAX_TOKENS',native)

    def test_project_profile_and_explicit_environment_precedence(self):
        (self.project/'.flow').mkdir(); (self.project/'.flow/runtime.toml').write_text('[profiles.ollama]\nmax_input_tokens=131072\n')
        self.assertEqual(device_context.settings(self.project)['context_tokens'],131072)
        with patch.dict(os.environ,{'GOOSE_INPUT_LIMIT':'32768'}):
            self.assertEqual(environment(project=self.project)['GOOSE_INPUT_LIMIT'],'32768')

    def test_no_profile_has_no_arbitrary_8k_override(self):
        (self.home/'.flow/user/runtime.toml').unlink()
        self.assertNotIn('GOOSE_INPUT_LIMIT',environment(project=self.project))

    def test_ambiguous_profiles_do_not_choose_first_or_block_execution(self):
        with (self.home/'.flow/user/runtime.toml').open('a') as stream:
            stream.write('[profiles.other]\nkind="local"\nmodel="ollama/other"\nmax_input_tokens=16384\n')
        value = device_context.settings(self.project)
        self.assertIsNone(value['context_tokens']); self.assertTrue(value['warnings'])
        self.assertNotIn('GOOSE_INPUT_LIMIT',environment(project=self.project))

    def test_malformed_context_value_is_diagnostic_not_an_execution_gate(self):
        (self.home/'.flow/user/runtime.toml').write_text('[profiles.ollama]\nkind="local"\nmodel="ollama/test"\nmax_input_tokens=[1,2]\n')
        value=device_context.settings(self.project)
        self.assertIsNone(value['context_tokens']); self.assertTrue(value['warnings'])
        self.assertNotIn('GOOSE_INPUT_LIMIT',environment(project=self.project))

    def test_project_cannot_redeclare_user_owned_device_capacity(self):
        (self.home/'.flow/user/runtime.toml').unlink()
        (self.home/'.flow/user/flow.toml').write_text('[local_machine]\ncontext_tokens=65536\n')
        (self.project/'.flow').mkdir();(self.project/'.flow/runtime.toml').write_text('[local_machine]\ncontext_tokens=8192\n')
        self.assertEqual(device_context.settings(self.project)['context_tokens'],65536)
