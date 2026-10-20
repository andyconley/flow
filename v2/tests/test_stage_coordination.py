"""Persisted stage execution and approvals with simulated Goose, never inference."""
import tempfile
from pathlib import Path
import unittest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from poc.artifacts import Artifacts,ArtifactError
from poc.project_context import resolve
from poc.work_lifecycle import build


class StageCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.project=self.root/'project';self.project.mkdir()
        self.artifacts=Artifacts(self.project,'stages');self.calls=[];self.mode='success'
        outer=self
        class Harness:
            def shape(self,state,stage,assignment):
                outer.calls.append(stage)
                if outer.mode=='permission':return {'status':'permission_required','reason':'fixture permission'}
                if outer.mode=='write':(outer.project/'unapproved.py').write_text('partial effect')
                if outer.mode=='crash':raise RuntimeError('crash after intent')
                result={'status':'completed','content':stage+' substantive specialist evidence'}
                if stage=='plan':result['brief']={'goal':'Approved goal','scope':['feature'],'acceptance_criteria':['tests'], 'check_command':['/usr/bin/true']}
                return result
            def implement(self,*args):raise AssertionError('Stage approval started implementation')
        self.h=Harness();self.cfg={'configurable':{'thread_id':'stages'}}
        self.cm=SqliteSaver.from_conn_string(str(self.root/'state.sqlite'));self.saver=self.cm.__enter__();self.addCleanup(self.cm.__exit__,None,None,None)
        self.graph=build(self.artifacts,self.h,lambda _:None).compile(checkpointer=self.saver)
        self.context=self.artifacts.publish('contexts','project',resolve(self.project))
        self.graph.invoke({'work_id':'stages','job_id':'stages','workspace':str(self.project),'request':'Research this',
                           'context_ref':self.context,'lifecycle_phase':'shaping','budget_seconds':60},self.cfg)

    def assign(self,stage):
        reference=self.artifacts.publish('assignments',stage,{'stage':stage,'question':'Research '+stage,
            'context_ref':self.context,'brief_ref':None,'authority':'Research only'})
        self.graph.invoke(Command(resume={'action':'assign','assignment_ref':reference}),self.cfg)
        return reference

    def run_stage(self,stage,reference):
        return self.graph.invoke(Command(resume={'action':'run-stage','stage':stage,'actor':'Andy','assignment_ref':reference}),self.cfg)

    def test_full_shaping_is_runtime_owned_and_brief_stays_unapproved(self):
        for stage in ('define','solution','plan'):
            reference=self.assign(stage)
            self.assertEqual(len(self.calls),('define','solution','plan').index(stage))
            result=self.run_stage(stage,reference)
            self.assertEqual(self.calls[-1],stage)
            record=self.artifacts.read(result['shaping_refs'][stage])['payload']
            self.assertEqual(record['origin'],'goose-langgraph')
            self.assertEqual(record['assignment_ref'],reference)
            self.graph.invoke(Command(resume={'action':'approve-stage','stage':stage,'actor':'Andy'}),self.cfg)
            self.graph.invoke(None,self.cfg)
        state=self.graph.get_state(self.cfg).values
        self.assertEqual(self.calls,['define','solution','plan'])
        self.assertEqual(state['lifecycle_phase'],'awaiting-approval')
        self.assertIn('brief_ref',state);self.assertNotIn('approval_ref',state)
        self.assertEqual(self.artifacts.read(state['brief_ref'])['payload']['goal'],'Approved goal')

    def test_exact_assignment_and_actor_are_required_before_dispatch(self):
        reference=self.assign('define')
        with self.assertRaises(ArtifactError):
            self.graph.invoke(Command(resume={'action':'run-stage','stage':'define','actor':'Andy',
                'assignment_ref':{**reference,'revision':'f'*64}}),self.cfg)
        self.assertEqual(self.calls,[])

    def test_stage_write_is_preserved_but_never_accepted_as_research(self):
        reference=self.assign('define');self.mode='write';result=self.run_stage('define',reference)
        self.assertEqual(result['stage_result']['status'],'scope_required')
        self.assertFalse(result.get('shaping_refs'))
        self.assertEqual((self.project/'unapproved.py').read_text(),'partial effect')

    def test_permission_pause_has_no_automatic_retry(self):
        reference=self.assign('define');self.mode='permission';result=self.run_stage('define',reference)
        self.assertEqual(result['stage_result']['status'],'permission_required')
        self.graph.invoke(None,self.cfg);self.assertEqual(self.calls,['define'])

    def test_uncertain_stage_requires_reconciliation_before_any_replay(self):
        reference=self.assign('define');self.mode='crash'
        with self.assertRaisesRegex(RuntimeError,'crash after intent'):self.run_stage('define',reference)
        result=self.graph.invoke(None,self.cfg)
        self.assertEqual(result['__interrupt__'][0].value['kind'],'reconcile-effect')
        self.assertEqual(self.calls,['define'])
        result=self.graph.invoke(Command(resume={'effect':'completed','actor':'Andy','evidence':'Inspected saved evidence',
            'result':{'status':'completed','content':'Recovered substantive evidence'}}),self.cfg)
        self.assertEqual(self.calls,['define'])
        self.assertEqual(self.artifacts.read(result['shaping_refs']['define'])['payload']['content'],'Recovered substantive evidence')
