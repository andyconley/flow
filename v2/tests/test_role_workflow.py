"""Real LangGraph/SQLite and existing Goose adapter; no native inference."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from poc.workflow import build
from poc.contracts import digest_tree
from poc.goose_job import GooseJob

ROOT=Path(__file__).resolve().parents[1]


class Harness:
    def __init__(self, reviews=(), permission_at=None):
        self.implementations=0;self.reviews=0;self.results=list(reviews);self.permission_at=permission_at
    def implement(self,s):
        self.implementations+=1
        if self.permission_at=='implement' and not s.get('resume_epoch'):
            return {'status':'scope_required','reason':'approved scope needs owner decision'}
        return {'status':'completed'}
    def review(self,s):
        self.reviews+=1
        if self.permission_at=='review' and not s.get('resume_epoch'):
            return {'outcome':'permission_required','reason':'test needs permission'}
        approved=self.results.pop(0) if self.results else True
        return {'passed':approved,'candidate':digest_tree(s['workspace']),'findings':[] if approved else ['Fix the defect']}
    def reconcile(self,s):return {'status':'blocked','reason':'unresolved external intent'}


class RoleWorkflowTests(unittest.TestCase):
    def setUp(self):
        # Mock provider tests own their store; installed consumer HOME is seeded
        # but deliberately unprovisioned. Keep real readiness behavior elsewhere.
        fixture = tempfile.TemporaryDirectory(prefix='flow-mock-knowledge-')
        self.addCleanup(fixture.cleanup)
        env = patch.dict(os.environ, FLOW_KNOWLEDGE_HOME=fixture.name)
        env.start(); self.addCleanup(env.stop)

    def graph(self,tmp,h):
        saver=SqliteSaver.from_conn_string(str(Path(tmp)/'checkpoints.sqlite'));cp=saver.__enter__()
        self.addCleanup(saver.__exit__,None,None,None)
        # Keep checkpoint files outside the candidate workspace.
        workspace=Path(tmp)/'workspace';workspace.mkdir(exist_ok=True)
        graph=build(h,lambda p:{'passed':True,'tests':5}).compile(checkpointer=cp)
        return graph,{'task':'approved coding change','workspace':str(workspace),'inputs':'approved','approved':'approved','job_id':'test'}

    def test_success_and_completed_resume_do_not_repeat_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness();g,s=self.graph(tmp,h);config={'configurable':{'thread_id':'one'}}
            self.assertEqual(g.invoke(s,config)['phase'],'reviewed-and-ready')
            self.assertEqual(g.invoke(None,config)['phase'],'reviewed-and-ready')
            self.assertEqual((h.implementations,h.reviews),(1,1))

    def test_review_correction_then_fresh_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness([False,True]);g,s=self.graph(tmp,h)
            result=g.invoke(s,{'configurable':{'thread_id':'correct'}})
            self.assertEqual(result['phase'],'reviewed-and-ready')
            self.assertEqual(result['corrections'],1)
            self.assertEqual((h.implementations,h.reviews),(2,2))

    def test_initial_plus_three_corrections_then_concise_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness([False]*4);g,s=self.graph(tmp,h)
            result=g.invoke(s,{'configurable':{'thread_id':'exhaust'}})
            self.assertEqual(result['phase'],'blocked')
            self.assertEqual((h.implementations,h.reviews),(4,4))
            self.assertEqual(result['corrections'],3)
            self.assertIn('recommendation',result)

    def test_review_permission_pause_reopen_sqlite_resume_only_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(permission_at='review');workspace=Path(tmp)/'workspace';workspace.mkdir()
            config={'configurable':{'thread_id':'pause'}}
            with SqliteSaver.from_conn_string(str(Path(tmp)/'db')) as cp:
                g=build(h,lambda p:{'passed':True}).compile(checkpointer=cp)
                result=g.invoke({'task':'task','workspace':str(workspace),'inputs':'x','approved':'x'},config)
                self.assertIn('__interrupt__',result)
                self.assertEqual((h.implementations,h.reviews),(1,1))
            with SqliteSaver.from_conn_string(str(Path(tmp)/'db')) as cp:
                g=build(h,lambda p:{'passed':True}).compile(checkpointer=cp)
                result=g.invoke(Command(resume='resume'),config)
            self.assertEqual(result['phase'],'reviewed-and-ready')
            self.assertEqual((h.implementations,h.reviews),(1,2))
            self.assertNotIn('corrections',result)

    def test_scope_pause_before_automatic_correction(self):
        with tempfile.TemporaryDirectory() as tmp:
            h=Harness(permission_at='implement');g,s=self.graph(tmp,h);config={'configurable':{'thread_id':'scope'}}
            self.assertIn('__interrupt__',g.invoke(s,config))
            self.assertEqual((h.implementations,h.reviews),(1,0))
            self.assertEqual(g.invoke(Command(resume='stop'),config)['phase'],'blocked')
            self.assertEqual(h.implementations,1)

    def test_role_adapter_uses_catalog_and_structured_real_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=GooseJob(provider='chatgpt_codex',model='gpt-5.6-sol',role_bundle=ROOT/'role-bundle')
            g,s=self.graph(tmp,job);counter={'implement':0,'review':0};prompts=[]
            def execute(state,kind,prompt,provider_override=None):
                counter[kind]+=1;prompts.append(prompt)
                report={'outcome':'completed' if kind=='implement' else 'approve','findings':[],'test_results':{'passed':True},'candidate_revision':state.get('candidate')}
                path=Path(tmp)/(kind+'.jsonl')
                path.write_text(json.dumps({'message':{'role':'assistant','content':[{'type':'text','text':json.dumps(report)}]}})+'\n')
                return {'status':'completed','output':str(path)}
            with patch.object(job,'_run',side_effect=execute):
                result=g.invoke(s,{'configurable':{'thread_id':'adapter'}})
            self.assertEqual(result['phase'],'reviewed-and-ready')
            self.assertEqual(counter,{'implement':1,'review':1})
            self.assertIn('quality-reviewer',prompts[0]);self.assertIn('FRESH session',prompts[1])
            self.assertNotIn('READ-ONLY',prompts[1]);self.assertIn('normal broad',prompts[1])

    def test_adapter_propagates_permission_instead_of_inferring_failure(self):
        job=GooseJob(role_bundle=ROOT/'role-bundle')
        with patch.object(job,'_run',return_value={'status':'permission_required','reason':'actual denied operation'}):
            result=job.review({'task':'task','workspace':'workspace'})
        self.assertEqual(result['outcome'],'permission_required')

    def test_existing_intent_record_prevents_duplicate_subprocess(self):
        from poc.contracts import task_input_digest
        class Process:
            pid=123;returncode=0
            def poll(self):return 0
            def wait(self,timeout=None):return 0
        class Scope:
            def __init__(self,pid):self.known={}
            def observe(self):return {}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runtime').mkdir();(root/'artifacts').mkdir()
            workspace=root/'workspace';workspace.mkdir()
            state={'task':'task','workspace':str(workspace),'project_context':'context','inputs':task_input_digest('task',workspace,'context'),'job_id':'one'}
            job=GooseJob(provider='chatgpt_codex',role_bundle=ROOT/'role-bundle')
            with patch('poc.goose_job.ROOT',root),patch('poc.goose_job.ProcessScope',Scope),patch('poc.goose_job.subprocess.Popen',return_value=Process()) as launch,patch('poc.native_runtime.prepare',return_value=(root/'common.sb',{'PATH':'/usr/bin'})):
                first=job._run(state,'implement','prompt')
                second=job._run(state,'implement','prompt')
            self.assertEqual(launch.call_count,1)
            self.assertEqual(first['status'],'completed');self.assertEqual(first,second)
            command=launch.call_args.args[0]
            self.assertNotIn('developer',command);self.assertIn('summon',command)
            sources=json.loads(launch.call_args.kwargs['env']['FLOW_V2_ROLE_SOURCES'])
            self.assertIn('lead-developer',sources);self.assertIn('quality-reviewer',sources)
            self.assertEqual(len(sources),13)

    def test_actual_checker_permission_error_pauses_and_resumes_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace=Path(tmp)/'workspace';workspace.mkdir();h=Harness();calls=[]
            def check(path):
                calls.append(path)
                if len(calls)==1:raise PermissionError('test fixture inaccessible')
                return {'passed':True}
            with SqliteSaver.from_conn_string(str(Path(tmp)/'db')) as cp:
                g=build(h,check).compile(checkpointer=cp);config={'configurable':{'thread_id':'checker'}}
                self.assertIn('__interrupt__',g.invoke({'workspace':str(workspace),'inputs':'x','approved':'x'},config))
                result=g.invoke(Command(resume='resume'),config)
            self.assertEqual(result['phase'],'reviewed-and-ready')
            self.assertEqual((h.implementations,h.reviews,len(calls)),(1,1,2))

    def test_expired_total_budget_submits_nothing(self):
        from poc.contracts import task_input_digest
        state={'task':'task','workspace':'workspace','project_context':'','deadline':0}
        state['inputs']=task_input_digest('task','workspace')
        job=GooseJob(role_bundle=ROOT/'role-bundle')
        with patch('poc.goose_job.subprocess.Popen') as launch:
            result=job._run(state,'implement','prompt')
        self.assertEqual(result['status'],'blocked');launch.assert_not_called()

    def test_entrypoint_writes_minimal_handoff_and_completed_resume_is_idle(self):
        import contextlib
        import io
        import sys
        from poc import role_run
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);workspace=root/'workspace';workspace.mkdir()
            contract=root/'task.json';contract.write_text(json.dumps({'task':'approved task','workspace':str(workspace),'project_context':'context','check_command':[sys.executable,'-c','print("check passed")']}))
            h=Harness()
            with patch.object(role_run,'ROOT',root),patch.object(role_run,'setup'),patch.object(role_run,'GooseJob',return_value=h),contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys,'argv',['role_run','--job','example','--task-file',str(contract),'--approved']):role_run.main()
                with patch.object(sys,'argv',['role_run','--job','example','--task-file',str(contract),'--resume']):role_run.main()
            handoff=json.loads((root/'artifacts/example/handoff.json').read_text())
            self.assertEqual(set(handoff),{'task','workspace','candidate_revision','outcome','findings','test_results'})
            self.assertEqual(handoff['outcome'],'reviewed-and-ready')
            self.assertTrue(handoff['test_results']['passed'])
            self.assertEqual((h.implementations,h.reviews),(1,1))
