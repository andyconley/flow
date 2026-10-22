"""Deterministic readiness checks; never sign in or invoke a model."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
import yaml
from poc.provider_preflight import check, planned, PreflightError


class ProviderPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root/'roles'; (self.bundle/'recipes').mkdir(parents=True)
        self.home = self.root/'private-home'; self.home.mkdir()
        self.env = {'HOME':str(self.home), 'CODEX_HOME':str(self.home/'codex'),
                    'CODEX_PATH':'/fixture/codex', 'FLOW_V2_CLAUDE_BINARY':'/fixture/claude',
                    'CLAUDE_CONFIG_DIR':str(self.home/'claude'), 'PATH':'/fixture/bin'}
        self.profile = self.root/'worker.sb'
    def recipe(self, name, provider, model):
        (self.bundle/'recipes'/(name+'.yaml')).write_text(yaml.safe_dump({'settings':{'goose_provider':provider,'goose_model':model}}))
    def test_all_bound_roles_and_coordinator_checked_before_dispatch(self):
        self.recipe('implement', 'codex-acp', 'gpt')
        self.recipe('review', 'claude-acp', 'opus')
        self.recipe('research', 'claude-acp', 'sonnet')
        def run(command, **kwargs):
            self.assertEqual(command[:3], ['/usr/bin/sandbox-exec','-f',str(self.profile)])
            self.assertIs(kwargs['env'], self.env)
            self.assertLessEqual(kwargs['timeout'], 5)
            self.assertTrue(command[-2:] == ['login','status'] or command[-3:] == ['auth','status','--json'])
            return subprocess.CompletedProcess(command, 0, json.dumps({'loggedIn':True}))
        with patch('poc.provider_preflight.subprocess.run', side_effect=run) as calls:
            result = check(self.bundle, 'chatgpt_codex', 'gpt', self.profile, self.env, time.time()+60)
        self.assertTrue(result['passed']); self.assertEqual(len(result['providers']),4)
        self.assertEqual(calls.call_count,2)  # account checks dedup; models remain explicit
    def test_auth_uses_workspace_and_claude_only_real_home(self):
        self.recipe('worker', 'codex-acp', 'gpt')
        self.recipe('review', 'claude-acp', 'opus')
        workspace=self.root/'approved';workspace.mkdir()
        env={**self.env,'FLOW_V2_CLAUDE_USER_HOME':'/fixture/real-user'}
        before=dict(env)
        def run(command, **kwargs):
            self.assertEqual(kwargs['cwd'],workspace)
            self.assertEqual(command[:3],['/usr/bin/sandbox-exec','-f',str(self.profile)])
            effective=kwargs['env']
            self.assertEqual(effective['HOME'], '/fixture/real-user' if command[3]=='/fixture/claude' else env['HOME'])
            self.assertEqual(effective['CLAUDE_CONFIG_DIR'],env['CLAUDE_CONFIG_DIR'])
            self.assertEqual(effective['CODEX_HOME'],env['CODEX_HOME'])
            return subprocess.CompletedProcess(command,0,'{"loggedIn":true}')
        with patch('poc.provider_preflight.subprocess.run',side_effect=run) as calls:
            check(self.bundle,'chatgpt_codex','gpt',self.profile,env,workspace=workspace)
        self.assertEqual(calls.call_count,2)
        self.assertEqual(env,before)
        self.assertFalse((self.home/'codex/auth.json').exists())

    def test_unsigned_review_provider_blocks_even_when_implementation_signed_in(self):
        self.recipe('implement', 'codex-acp', 'gpt'); self.recipe('review','claude-acp','opus')
        with patch('poc.provider_preflight.subprocess.run', return_value=subprocess.CompletedProcess([],0,'{"loggedIn":false}')):
            with self.assertRaisesRegex(PreflightError, 'CLAUDE_CONFIG_DIR') as error:
                check(self.bundle,'codex-acp','gpt',self.profile,self.env)
        self.assertEqual(error.exception.status,'permission_required')
        self.assertFalse((self.home/'codex').exists())
    def test_unknown_missing_and_expired_fail_closed(self):
        self.recipe('unknown','other','model')
        with self.assertRaisesRegex(PreflightError,'No safe readiness'):
            check(self.bundle,'other','model',self.profile,self.env)
        with patch('poc.provider_preflight.subprocess.run') as calls:
            with self.assertRaisesRegex(PreflightError,'budget exhausted'):
                check(self.bundle,'codex-acp','gpt',self.profile,self.env,0)
            calls.assert_not_called()
        (self.bundle/'recipes/unknown.yaml').write_text('settings: {}')
        with self.assertRaisesRegex(PreflightError,'explicit provider/model'):
            planned(self.bundle,'codex-acp','gpt')
    def test_stage_time_revalidation_does_not_cache_signed_in_status(self):
        self.recipe('review','claude-acp','opus')
        with patch('poc.provider_preflight.subprocess.run', side_effect=[subprocess.CompletedProcess([],0,'{"loggedIn":true}'),subprocess.CompletedProcess([],1,'')]) as calls:
            check(self.bundle,'claude-acp','opus',self.profile,self.env)
            with self.assertRaises(PreflightError):
                check(self.bundle,'claude-acp','opus',self.profile,self.env)
        self.assertEqual(calls.call_count,2)
    def test_local_codex_is_explicit_and_never_copies_auth(self):
        home=Path(self.env['CODEX_HOME']);home.mkdir()
        config=home/'config.toml';config.write_text('model_provider="local"\n[model_providers.local]\nrequires_openai_auth=false\nbase_url="http://127.0.0.1:11434/v1"\n')
        before=config.read_bytes()
        with patch('poc.provider_preflight.subprocess.run') as run:
            result=check(self.bundle,'codex-acp','gpt-oss',self.profile,self.env)
            run.assert_not_called()
        self.assertIn('inference availability',result['providers'][0]['readiness'])
        self.assertEqual(config.read_bytes(),before);self.assertFalse((home/'auth.json').exists())
        config.write_text(config.read_text().replace('127.0.0.1','example.com'))
        with self.assertRaisesRegex(PreflightError,'loopback'):
            check(self.bundle,'codex-acp','gpt-oss',self.profile,self.env)

    def test_failed_preflight_never_publishes_native_intent_or_launches(self):
        from poc import goose_job
        from poc.contracts import task_input_digest, digest_tree
        self.recipe('review','claude-acp','opus')
        (self.root/'runtime').mkdir()
        workspace=self.root/'workspace';workspace.mkdir()
        (workspace/'file').write_text('original')
        before=digest_tree(workspace)
        state={'task':'approved','workspace':str(workspace),'project_context':'','job_id':'preflight'}
        state['inputs']=task_input_digest('approved',workspace)
        job=goose_job.GooseJob(provider='codex-acp',role_bundle=self.bundle)
        with patch.object(goose_job,'ROOT',self.root), patch('poc.knowledge_tools.require_ready'), \
                patch('poc.native_runtime.prepare',return_value=(self.profile,self.env)), \
                patch('poc.provider_preflight.subprocess.run',return_value=subprocess.CompletedProcess([],1,'')) as readiness, \
                patch('poc.goose_job.subprocess.Popen') as launch:
            result=job._run_impl(state,'implement','approved prompt')
            retried=job._run_impl(state,'implement','approved prompt')
        self.assertEqual(readiness.call_args.kwargs['cwd'],str(workspace))
        self.assertEqual(retried['status'],'permission_required')
        self.assertEqual(result['status'],'permission_required');self.assertFalse(result['submitted'])
        launch.assert_not_called()
        self.assertFalse((self.root/'artifacts/preflight/implement-1-0.json').exists())
        self.assertEqual(before,digest_tree(workspace))

    def test_ollama_checks_effective_endpoint_and_model_inside_native_scope(self):
        self.recipe('local','ollama','tiny')
        self.env['OLLAMA_HOST']='http://127.0.0.1:11435'
        result=subprocess.CompletedProcess([],0,'{"models":[{"name":"tiny:latest"}]}')
        with patch('poc.provider_preflight.subprocess.run',return_value=result) as run:
            check(self.bundle,'ollama','tiny',self.profile,self.env)
        self.assertEqual(run.call_args.args[0][:4],['/usr/bin/sandbox-exec','-f',str(self.profile),'/usr/bin/curl'])
        self.assertEqual(run.call_args.args[0][-1],'http://127.0.0.1:11435/api/tags')
        self.assertIs(run.call_args.kwargs['env'],self.env)
        with patch('poc.provider_preflight.subprocess.run',return_value=subprocess.CompletedProcess([],0,'{"models":[]}')):
            with self.assertRaisesRegex(PreflightError,'no pull or provider switching'):
                check(self.bundle,'ollama','tiny',self.profile,self.env)

    def test_selected_worker_digest_is_rechecked_and_exact_failure_preserved(self):
        from poc.implementation_profiles import fingerprint
        selected={'name':'fast','provider':'ollama','model':'gpt-oss:20b','endpoint':'http://127.0.0.1:11434','context_tokens':32768,'output_tokens':-1,'condenser_max_tokens':28672,'model_digest':'a'*64}
        selected['sha256']=fingerprint(selected)
        self.recipe('lead-developer','ollama','gpt-oss:20b')
        env={**self.env,'FLOW_V2_IMPLEMENTATION_PROFILE':json.dumps(selected),'FLOW_V2_LOCAL_PREFLIGHT_SCOPE':'/fixture/readiness-only.sb'}
        for digest,passes in [('a'*64,True),('b'*64,False)]:
            def run(command,**kwargs):
                self.assertEqual(command[2],'/fixture/readiness-only.sb')
                return subprocess.CompletedProcess(command,0,json.dumps({'models':[{'name':'gpt-oss:20b','digest':digest}]}))
            with patch('poc.provider_preflight.subprocess.run',side_effect=run):
                if passes:self.assertTrue(check(self.bundle,'ollama','gpt-oss:20b',self.profile,env)['passed'])
                else:
                    with self.assertRaisesRegex(PreflightError,'digest changed'):check(self.bundle,'ollama','gpt-oss:20b',self.profile,env)

    def test_cloud_alias_cannot_replace_previously_local_worker(self):
        from poc.implementation_profiles import fingerprint
        selected={'name':'fast','provider':'ollama','model':'gpt-oss:20b','endpoint':'http://127.0.0.1:11434','context_tokens':32768,'output_tokens':-1,'condenser_max_tokens':28672,'model_digest':'a'*64}
        selected['sha256']=fingerprint(selected)
        self.recipe('lead-developer','ollama','gpt-oss:20b')
        env={**self.env,'FLOW_V2_IMPLEMENTATION_PROFILE':json.dumps(selected)}
        tags={'models':[{'name':'gpt-oss:20b','digest':'a'*64,'remote_host':'https://cloud.invalid'}]}
        with patch('poc.provider_preflight.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(tags))):
            with self.assertRaisesRegex(PreflightError,'cloud alias'):check(self.bundle,'ollama','gpt-oss:20b',self.profile,env)
