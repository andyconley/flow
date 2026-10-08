"""Scope and evidence gates for the native adapter, without provider inference."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from local_agent_delivery import NativeLocalAdapter
from delivery_gateway import _publish_local_reconciliation
from runner_limits import resolve_local_agent_budget
from execution_contracts import ContractError

class NativeLocalDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.work = self.root / 'work'; self.work.mkdir()
        (self.work / 'a.py').write_text('value = 1\n')
        (self.work / 'tests').mkdir()
        (self.work / 'tests/test_fixture.py').write_text('import unittest\nclass TestFixture(unittest.TestCase):\n    def test_real(self): self.assertEqual(1,1)\n')
        self.attempt = self.root / 'execution' / 'attempt'; (self.attempt / 'checkpoints').mkdir(parents=True)
        operations = [('first', 'edit', []), ('second', 'edit', ['first']), ('reviewer', 'verify', ['first','second'])]
        assignments = [{'assignment_id': key, 'instructions': 'Approved task', 'depends_on': deps,
                        'requirements': {'operation': op}} for key,op,deps in operations]
        (self.attempt / 'manifest.snapshot.json').write_text(json.dumps({'assignments': [
            {'id': key, 'read_scopes':['a.py','b.py'], 'write_scopes':[{'first':'a.py','second':'b.py'}.get(key,'a.py')]
                if op=='edit' else []} for key,op,_ in operations]}))
        (self.attempt / 'job-charter.snapshot.json').write_text(json.dumps({'test':{'argv':['python3','-m','unittest','discover','-s','tests'], 'timeout_seconds':10}}))
        self.envelope = {'attempt_id':'attempt', 'worktree':str(self.work), 'checkpoint_dir':str(self.attempt/'checkpoints'),
            'local_agent_profile':resolve_local_agent_budget(), 'logical_assignments':assignments,
            'maf_runtime':{'interpreter':sys.executable}, 'delivery_lead_claim':{'generation':1}}
        self.poolpatch=patch('local_agent_delivery.LocalAgentPool'); self.pool=self.poolpatch.start().return_value
        self.addCleanup(self.poolpatch.stop)
        self.ledgerpatch=patch('local_agent_delivery.ExecutionLedger', autospec=True); self.ledger=self.ledgerpatch.start().return_value
        self.addCleanup(self.ledgerpatch.stop)
        self.adapter=NativeLocalAdapter(self.envelope,read_paths=['a.py','b.py'],write_paths=['a.py','b.py'])
        self.addCleanup(self.adapter.close)
        self.binding={'provider':'ollama','model':'approved-model'}

    def call(self, name, handler):
        action={'assignment_id':name,'action_id':name+'-action','attempt_id':'attempt','task':'Complete approved source'}
        self.ledger.snapshot.return_value={'status':'started','actions':[{'request':action,'status':'started'}]}
        def run(assignment,instructions,task,callback,**options):
            observations=handler(callback)
            return {'output':'Model report', 'text':'Model report', 'session_id':name, 'events':[],
                    'model_requests':[], 'model_sends':[], 'model_responses':[], 'tool_observations':observations}
        self.pool.run.side_effect=run
        return self.adapter(self.binding,action)

    def write(self,callback,path,content):
        result=callback('write_file',{'path':path,'content':content})
        return {'name':'write_file','result':result}

    def test_producer_completion_requires_actual_write_and_handoff(self):
        self.assertTrue(self.call('first',lambda cb:[])['observed_invalid'])
        def edit(cb):
            cb('read_files',{'paths':['a.py']})
            return [self.write(cb,'a.py','value = 2\n')]
        self.assertIn('handoff',self.call('first',edit)['detail'])

    def test_consumer_write_requires_observed_hash_bound_handoff(self):
        def skipped(cb):
            event=self.write(cb,'b.py','from a import value\n')
            self.assertEqual(event['result']['status'],'denied')
            return [event]
        self.assertTrue(self.call('second',skipped)['observed_invalid'])
        def first(cb):
            cb('read_files',{'paths':['a.py']})
            event=self.write(cb,'a.py','value = 2\n')
            cb('submit_handoff',{'summary':'Import value from a; expected 2.'})
            return [event]
        self.call('first',first)
        def second(cb):
            self.assertEqual(cb('read_handoff',{})['status'],'handoff_read')
            return [self.write(cb,'b.py','from a import value\n')]
        self.call('second',second)
        self.assertTrue((self.work/'b.py').exists())

    def test_reviewer_does_not_pass_by_plain_completion_text(self):
        self.assertIn('current-source findings',self.call('reviewer',lambda cb:[])['detail'])

    def test_readonly_reviewer_cannot_mutate_source(self):
        def reviewer(cb):
            self.assertEqual(cb('write_file',{'path':'a.py','content':'bad'})['status'],'denied')
            cb('read_files',{'paths':['a.py']})
            self.assertEqual(cb('run_tests',{})['status'],'passed')
            cb('submit_review',{'approved':True,'findings':'Read actual current source and passing approved tests.'})
            return []
        result=self.call('reviewer',reviewer)
        self.assertEqual(json.loads(result['output'])['decision'],'pass')
        self.assertEqual(result['model_output'],'Model report')
        self.assertEqual((self.work/'a.py').read_text(),'value = 1\n')

class NativeManagerConversationTests(unittest.TestCase):
    def setUp(self):
        NativeLocalDeliveryTests.setUp(self)
        self.adapter.assignments['manager']={'assignment_id':'manager','instructions':'Coordinate approved task',
                                            'requirements':{'operation':'manage'}}

    def manager(self,phase):
        packet={'phase':phase,'messages':[{'role':'user','content':'Original request'},
            {'role':'assistant','content':'next_speaker.answer must be exactly one of legacy phrase'},
            {'role':'user','content':'Current phase request'}],
            'flow_authority':{'completed':['first'],'frontier':['second']}}
        action={'assignment_id':'manager','action_id':'manager-action','attempt_id':'attempt',
                'task':json.dumps(packet)}
        self.ledger.snapshot.return_value={'status':'started','actions':[{'request':action,'status':'started'}]}
        return packet,action

    def test_progress_preserves_native_conversation_and_typed_frontier(self):
        packet,action=self.manager('progress')
        with patch('local_agent_delivery.call_ollama_manager',return_value={'output':'progress'}) as send:
            self.adapter(self.binding,action)
        args,kwargs=send.call_args
        self.assertEqual(args[0],packet['messages'])
        self.assertEqual(kwargs['native_messages'][0],{'role':'system','content':'Coordinate approved task'})
        self.assertEqual(kwargs['native_messages'][1:-1],packet['messages'])
        self.assertEqual(kwargs['native_messages'][-1]['role'],'system')
        self.assertEqual(kwargs['allowed_speakers'],['second'])
        self.assertEqual(kwargs['phase'],'progress')

    def test_context_denial_preserves_positive_zero_io_evidence_without_provider_response(self):
        packet,action=self.manager('final')
        packet['messages'][-1]['content']='x'*40000
        action['task']=json.dumps(packet)
        with patch('local_worker.urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(ContractError,'context reserve; no send'):
                self.adapter(self.binding,action)
        opener.assert_not_called()
        path=self.attempt/('action-'+action['action_id']+'-observations.jsonl')
        observations=[json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(len(observations),1)
        self.assertEqual(set(observations[0]),{'type','bound','allowance'})
        self.assertEqual(observations[0]['type'],'context_denied')
        self.assertEqual(observations[0]['allowance'],12288-2048-1024)
        self.assertGreater(observations[0]['bound'],observations[0]['allowance'])
        self.assertNotIn('model_request',[event['type'] for event in observations])
        self.assertNotIn('model_send',[event['type'] for event in observations])
        self.assertNotIn('model_response',[event['type'] for event in observations])

    def test_nonprogress_phase_is_explicit_despite_old_progress_phrase_in_history(self):
        packet,action=self.manager('final')
        with patch('local_agent_delivery.call_ollama_manager') as progress, \
             patch('local_agent_delivery.call_local',return_value={'output':'final narrative'}) as send:
            self.adapter(self.binding,action)
        progress.assert_not_called()
        self.assertEqual(send.call_args.kwargs['chat_messages'][:-1],packet['messages'])
        self.assertNotIn('response_schema',send.call_args.kwargs)


class LocalReconciliationTests(unittest.TestCase):
    def test_unverified_receipt_cannot_publish_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            envelope = {'work_id': 'run', 'attempt_id': 'attempt', 'checkpoint_dir': str(root/'checkpoints')}
            with patch('receipt_verify.verify_receipt', return_value={'exit_code': 1, 'status': 'failed'}):
                with self.assertRaisesRegex(ContractError, 'verified completed receipt'):
                    _publish_local_reconciliation(envelope, root=root)
            self.assertEqual(list(root.iterdir()), [])

    def test_declared_artifact_must_stay_in_its_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            attempt = root/'.flow/runs/run/execution/attempt'
            (attempt/'checkpoints').mkdir(parents=True)
            (attempt/'manifest.snapshot.json').write_text(json.dumps({'reconciliation': {'artifact_path':'outside.md'}}))
            envelope = {'work_id':'run','attempt_id':'attempt','checkpoint_dir':str(attempt/'checkpoints')}
            with patch('receipt_verify.verify_receipt',return_value={'exit_code':0,'status':'completed','attempt_id':'attempt'}):
                with self.assertRaisesRegex(ContractError, 'declared run artifact scope'):
                    _publish_local_reconciliation(envelope,root=root)
            self.assertFalse((root/'outside.md').exists())


class ClosedNativeCompletionTests(unittest.TestCase):
    """Closed identities cannot authorize a second provider process."""
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.attempt=Path(self.directory.name)
        (self.attempt/'checkpoints').mkdir()
        self.control=self.attempt/'control-g1.json'
        self.closed=self.attempt/'control-g1.closed'
        self.control.write_bytes(b'original process identity evidence')
        self.closed.write_bytes(b'original closed marker')
        self.envelope={'attempt_id':'attempt','local_agent_profile':resolve_local_agent_budget(),
            'checkpoint_dir':str(self.attempt/'checkpoints'),'delivery_lead_claim':{'generation':1},
            'logical_assignments':[{'assignment_id':identity,'requirements':{'operation':operation}}
                for identity,operation in [('manager','manage'),('producer','edit'),('review','verify')]]}
        self.snapshot={'actions':[{'request':{'assignment_id':identity,'action_id':identity+'-action'},
                                  'status':'completed'} for identity in ['manager','producer','review']],
                       'evidence_failures':[],
                       'verifier_evaluations':[{'action_id':'review-action','outcome':'valid_pass'}]}
        self.ledger=Mock()
        self.ledger.snapshot.return_value=self.snapshot

    def assert_identity_preserved(self):
        self.assertEqual(self.control.read_bytes(),b'original process identity evidence')
        self.assertEqual(self.closed.read_bytes(),b'original closed marker')

    def test_completed_boundary_uses_evidence_only_supervisor_without_scope_or_provider(self):
        from delivery_gateway import _execute_v9_controlled
        adapter=Mock()
        def revalidate(envelope,task,ledger,send,**options):
            # This is the unchanged ordinary gateway boundary, not an adapter replay.
            self.assertIs(envelope,self.envelope)
            self.assertIs(ledger,self.ledger)
            self.assertIs(send,adapter)
            worker,manager=Mock(),Mock()
            result=options['supervisor'](envelope,task,worker,on_manager=manager,
                                         completed_assignments=['producer','review'])
            worker.assert_not_called()
            manager.assert_not_called()
            self.assertEqual(result['coordination'],'retained_observed_completion')
            return {'status':'completed','revalidated':True}
        with patch('delivery_gateway.delivery_cancel.parent_scope') as scope, \
             patch('delivery_gateway.execute_v9_logical_delivery',side_effect=revalidate) as execute:
            result=_execute_v9_controlled(self.envelope,'task',self.ledger,adapter,
                                          readiness_recheck=Mock())
        self.assertTrue(result['revalidated'])
        execute.assert_called_once()
        scope.assert_not_called()
        adapter.assert_not_called()
        self.assert_identity_preserved()

    def test_partial_or_failed_review_closed_boundary_refuses_without_new_process(self):
        from delivery_gateway import _execute_v9_controlled
        for failure in ['missing_worker','unknown_send','failed_assignment','failed_review']:
            with self.subTest(failure=failure):
                original=json.loads(json.dumps(self.snapshot))
                if failure=='missing_worker':
                    original['actions']=original['actions'][:-1]
                elif failure=='unknown_send':
                    original['actions'][1]['status']='unknown'
                elif failure=='failed_assignment':
                    original['evidence_failures']=[{'action_id':'producer-action'}]
                else:
                    original['verifier_evaluations'][0]['outcome']='valid_fail'
                self.ledger.snapshot.return_value=original
                with patch('delivery_gateway.delivery_cancel.parent_scope') as scope, \
                     patch('delivery_gateway.execute_v9_logical_delivery') as execute:
                    with self.assertRaisesRegex(ContractError,'explicit recovery'):
                        _execute_v9_controlled(self.envelope,'task',self.ledger,Mock(),readiness_recheck=Mock())
                scope.assert_not_called()
                execute.assert_not_called()
                self.assert_identity_preserved()

    def test_actual_gateway_missing_assignment_is_not_overridden_by_cached_snapshot(self):
        from delivery_gateway import _execute_v9_controlled
        def mismatch(envelope,task,ledger,send,**options):
            return options['supervisor'](envelope,task,Mock(),completed_assignments=['producer'])
        with patch('delivery_gateway.delivery_cancel.parent_scope') as scope, \
             patch('delivery_gateway.execute_v9_logical_delivery',side_effect=mismatch):
            with self.assertRaisesRegex(ContractError,'all required assignment evidence'):
                _execute_v9_controlled(self.envelope,'task',self.ledger,Mock(),readiness_recheck=Mock())
        scope.assert_not_called()
        self.assert_identity_preserved()


class CanonicalManagerNoSendCompletionTests(unittest.TestCase):
    def setUp(self):
        ClosedNativeCompletionTests.setUp(self)

    def canonical_row(self):
        allowance=12288-2048-1024
        event={'type':'context_denied','bound':allowance+1,'allowance':allowance}
        text=json.dumps(event)+'\n'
        path=Path(self.envelope['checkpoint_dir']).parent/'action-manager-action-observations.jsonl'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text)
        evidence={'session_id':'manager-action','model_requests':[],'model_responses':[],
            'tool_observations':[],'events':[event], 'context_denial':{
                'artifact_path':str(path),'artifact_sha256':hashlib.sha256(text.encode()).hexdigest(),
                'serialized_observation':text}}
        return {'request':{'assignment_id':'manager','action_id':'manager-action',
                    'selection_decision':{'selected_binding':{'provider':'ollama'}}},
                'status':'pre_send_refused','reason':'local_manager_context_denied',
                'result':{'result':{'kind':'local_manager_context_denied','local_agent_observations':evidence}}}

    def test_canonical_no_send_manager_does_not_reopen_control_or_inference(self):
        from delivery_gateway import _execute_v9_controlled
        self.snapshot['actions'][0]=self.canonical_row()
        with patch('delivery_gateway.delivery_cancel.parent_scope') as scope, \
             patch('delivery_gateway.execute_v9_logical_delivery',return_value={'status':'completed'}) as execute:
            _execute_v9_controlled(self.envelope,'task',self.ledger,Mock(),readiness_recheck=Mock())
        scope.assert_not_called()
        self.assertIn('supervisor',execute.call_args.kwargs)
        ClosedNativeCompletionTests.assert_identity_preserved(self)

    def test_forged_no_send_manager_evidence_cannot_enter_completion_path(self):
        from delivery_gateway import _execute_v9_controlled
        for forged in ['digest','bound','provider','worker_identity']:
            with self.subTest(forged=forged):
                row=self.canonical_row()
                evidence=row['result']['result']['local_agent_observations']
                if forged=='digest':
                    evidence['context_denial']['artifact_sha256']='0'*64
                elif forged=='bound':
                    evidence['events'][0]['bound']=evidence['events'][0]['allowance']
                elif forged=='provider':
                    row['request']['selection_decision']['selected_binding']['provider']='claude'
                else:
                    row['request']['assignment_id']='producer'
                self.snapshot['actions'][0]=row
                with patch('delivery_gateway.delivery_cancel.parent_scope') as scope, \
                     patch('delivery_gateway.execute_v9_logical_delivery') as execute:
                    with self.assertRaises(ContractError):
                        _execute_v9_controlled(self.envelope,'task',self.ledger,Mock(),readiness_recheck=Mock())
                scope.assert_not_called()
                execute.assert_not_called()
                ClosedNativeCompletionTests.assert_identity_preserved(self)

    def test_operator_resume_reconciles_only_manager_and_then_uses_refreshed_snapshot(self):
        from delivery_gateway import resume_v9_chartered_job
        run=self.attempt/'.flow/runs/sample/execution/attempt'
        (run/'checkpoints').mkdir(parents=True)
        self.envelope['checkpoint_dir']=str(run/'checkpoints')
        self.envelope['selection_inputs']={'catalog':[]}
        (run/'job-charter.snapshot.json').write_text(json.dumps({
            'task':'approved task','read_paths':['source.py'],'write_paths':['source.py']}))
        self.snapshot.update(status='started',work_id='sample',execution_protocol_version=9,
                             envelope=self.envelope,owner_generation=1)
        row=self.canonical_row()
        self.snapshot['actions'][0]=dict(row,status='unknown',result=None)
        def reconcile(attempt,action,*,generation):
            self.assertEqual((attempt,action,generation),('attempt','manager-action',1))
            self.snapshot['actions'][0]=row
        self.ledger.reconcile_local_manager_context_denial.side_effect=reconcile
        with patch('delivery_gateway.ExecutionLedger',return_value=self.ledger), \
             patch('delivery_gateway._v9_adapter_for_operation'), \
             patch('delivery_gateway._execute_v9_controlled',return_value={'status':'pending-proof'}) as controlled:
            result=resume_v9_chartered_job('sample','attempt',root=self.attempt)
        self.assertEqual(result['status'],'pending-proof')
        self.ledger.reconcile_local_manager_context_denial.assert_called_once()
        self.assertGreaterEqual(self.ledger.snapshot.call_count,2)
        controlled.assert_called_once()
