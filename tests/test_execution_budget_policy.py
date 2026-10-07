"""Normal selection/gateway regressions; transports are scripted, not inference."""
import copy
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
import delivery_gateway as gateway
from delivery_contracts import (build_shaper_contract, build_delivery_charter,
    inspect_budget_migration, validate_shaper_intent, validate_shaper_contract, DeliveryContractError)
from execution_contracts import validate_envelope, ContractError
from execution_ledger import ExecutionLedger
from delivery_selection import make_action
from local_agent import LocalAgentPool
from provider_selection import digest
from runner_limits import resolve_local_agent_budget
from runstate import _apply_authority_amendment, approve_orchestration_amendment
from selection_receipt import verify_selection_receipt, V9ReceiptError
from tests.shaper_intent_fixture import shaper_intent
from tests.test_delivery_selection import _envelope
import tests.test_chartered_delivery_gateway as fixtures
from tests.v9_coordinator import coordinate


class BudgetAuthorityTests(unittest.TestCase):
    def test_new_authority_defaults_to_retention_without_expanding_counts(self):
        intent = shaper_intent(limits={'runtime_seconds': 3600, 'max_replans': 0})
        original = copy.deepcopy(intent)
        sources = {'requirements': {'path': '.flow/runs/new/requirements.md', 'sha256': 'a'*64},
            'acceptance_criteria': {'path': '.flow/runs/new/acceptance.md', 'sha256': 'b'*64}}
        shaper = build_shaper_contract('new', sources, intent)
        charter = build_delivery_charter(shaper)
        self.assertEqual(intent, original)
        self.assertEqual(charter['limits']['runtime_seconds'], 3600)
        self.assertEqual(charter['limits']['max_paid_worker_calls'], 6)
        self.assertEqual(charter['local_agent_profile']['delegations'], 6)
        self.assertEqual(charter['local_agent_profile']['replans'], 0)
        self.assertEqual(charter['local_agent_profile']['context_tokens'], 12288)
        self.assertEqual(charter['local_agent_profile']['request_timeout_seconds'], 3600)
        validate_shaper_contract(shaper)

    def test_old_artifact_inspection_does_not_clamp_or_insert_token_authority(self):
        intent = shaper_intent(limits={'runtime_seconds': 3600})
        for key in ('max_lineage_tokens', 'token_tranche', 'unobserved_send_tokens'):
            del intent['budget_safety_envelope']['enforceable'][key]
        original = copy.deepcopy(intent)
        report = inspect_budget_migration(intent)
        self.assertEqual(intent, original)
        self.assertEqual(report['runtime_seconds_preserved'], 3600)
        self.assertTrue(report['approval_required'])
        self.assertEqual(report['automatic_changes'], [])
        self.assertEqual(report['proposed_token_fields']['max_lineage_tokens'], 200000)
        with self.assertRaises(DeliveryContractError):
            validate_shaper_intent(intent)

    def test_budget_amendment_requires_explicit_gate_and_preserves_predecessor(self):
        intent = shaper_intent(limits={'runtime_seconds': 3600})
        successor = copy.deepcopy(intent['budget_safety_envelope'])
        successor['enforceable']['runtime_seconds'] = 7200
        original = copy.deepcopy(intent)
        amended = _apply_authority_amendment(intent, {'authority_amendment': {
            'budget_safety_envelope': successor}})
        self.assertEqual(intent, original)
        self.assertEqual(amended['budget_safety_envelope']['enforceable']['runtime_seconds'], 7200)
        ok, _, errors = approve_orchestration_amendment('old', 'unused', 'expanded budget', approved_by_user=False)
        self.assertFalse(ok)
        self.assertIn('explicit user approval', errors[0])

    def test_reopening_old_sealed_envelope_keeps_original_budgets(self):
        envelope = _envelope()
        envelope['limits']['max_runtime_seconds'] = 3600
        original = copy.deepcopy(envelope)
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'ledger.sqlite'
            ExecutionLedger(path).create_attempt(envelope)
            reopened = ExecutionLedger(path).snapshot(envelope['attempt_id'])['envelope']
            self.assertEqual(reopened, original)
            self.assertNotIn('local_agent_profile', reopened)
            validate_envelope(reopened)

    def test_new_expired_budget_survives_reopen_and_refuses_physical_send(self):
        from execution_budgets import seal_runtime_budget, remaining_runtime
        envelope = _envelope(allowed_candidates=['codex'])
        envelope['limits']['max_runtime_seconds'] = 3600
        envelope['runtime_budget'] = seal_runtime_budget(3600,
            (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat())
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ledger.sqlite'
            ExecutionLedger(path).create_attempt(envelope)
            ledger=ExecutionLedger(path)
            reopened=ledger.snapshot(envelope['attempt_id'])['envelope']
            self.assertEqual(reopened['runtime_budget'],envelope['runtime_budget'])
            validate_envelope(reopened)  # Expired evidence stays readable.
            with self.assertRaises(TimeoutError): remaining_runtime(reopened)
            action=make_action(reopened,'producer','Approved task',sequence=1,manager_turn=1)
            with self.assertRaisesRegex(ContractError,'runtime budget exhausted'):
                gateway.execute_v9_selected_action(reopened,action,lambda *_:self.fail('must not send'),
                    readiness_recheck=lambda binding:{**binding,'state':'ready'},ledger=ledger,generation=1)

    def test_native_catalog_does_not_expand_administrator_permissions(self):
        catalog=copy.deepcopy(_envelope()['selection_inputs']['catalog'])
        catalog[0].update(enabled=False,operations=['verify'],max_context_tokens=32768,max_input_bytes=1000)
        original=copy.deepcopy(catalog)
        projected,_=gateway.local_agent_selection_inputs(catalog,{},resolve_local_agent_budget())
        self.assertEqual(catalog,original)
        self.assertFalse(projected[0]['enabled'])
        self.assertEqual(projected[0]['operations'],['verify'])
        self.assertEqual(projected[0]['max_context_tokens'],32768)
        self.assertEqual(projected[0]['max_input_bytes'],1000)
        self.assertEqual(projected[1:],original[1:])

    def test_mixed_profile_keeps_hosted_token_fence(self):
        envelope = _envelope(allowed_candidates=['codex'])
        envelope['local_agent_profile'] = resolve_local_agent_budget()
        envelope['limits'].update(max_manager_calls=20, max_delegations=20,
            max_verifier_calls=20, max_paid_worker_calls=20, max_lineage_tokens=1000,
            token_tranche=1000, unobserved_send_tokens=1000)
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            ledger = ExecutionLedger(Path(directory)/'ledger.sqlite')
            ledger.create_attempt(envelope)
            first = make_action(envelope, 'producer', 'Approved edit', sequence=1, manager_turn=1)
            gateway.execute_v9_selected_action(envelope, first, lambda *_: {'output': 'observed'},
                readiness_recheck=lambda binding: {**binding, 'state': 'ready'}, ledger=ledger, generation=1)
            second = make_action(envelope, 'producer', 'Further edit', sequence=2, manager_turn=2)
            with self.assertRaisesRegex(ContractError, 'token budget exhausted'):
                gateway.execute_v9_selected_action(envelope, second, lambda *_: self.fail('must not send'),
                    readiness_recheck=lambda binding: {**binding, 'state': 'ready'}, ledger=ledger, generation=1)


class MixedDefaultPipelineTests(unittest.TestCase):
    def exercise(self, producer, reviewer):
        fixture = fixtures.CharteredFixture(methodName='runTest')
        # Use new default authority, rather than the historical fixture helper.
        with patch.object(fixtures, 'build_shaper_contract', build_shaper_contract):
            fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.intent['budget_safety_envelope']['enforceable']['runtime_seconds'] = 3600
        (fixture.run/'shaper-intent.json').write_text(json.dumps(fixture.intent))
        with patch.object(fixtures, 'build_shaper_contract', build_shaper_contract):
            fixture._write_delivery_authority()
        template = _envelope()
        assignments = copy.deepcopy(template['logical_assignments'])
        for item in assignments:
            provider = 'claude' if item['requirements']['operation']=='manage' else (
                producer if item['requirements']['operation']=='edit' else reviewer)
            item['requirements']['locality'] = 'local_required' if provider=='ollama' else 'any'
            item['requirements']['context_tokens'] = 8192
            item['requirements']['input_bytes'] = 65536
        catalog = template['selection_inputs']['catalog']
        for candidate in catalog:
            candidate['operations'] = (['manage'] if candidate['provider']=='claude' else [])
            if candidate['provider']==producer: candidate['operations'].append('edit')
            if candidate['provider']==reviewer: candidate['operations'].append('verify')
        catalog, policy = gateway.local_agent_selection_inputs(catalog, template['selection_inputs']['policy'],
            resolve_local_agent_budget())
        self.assertEqual({c['provider'] for c in catalog}, {'ollama','claude','codex'})
        fixture.charter['logical_assignments'] = assignments
        fixture.charter['producer_instance_ids'] = ['producer']
        fixture.manifest['assignments'][1]['id'] = 'producer'
        for item in fixture.manifest['assignments']:
            item['execution']['timeout_seconds'] = 1800
        fixture._write_inputs()
        with patch.object(gateway,'run_status',return_value=fixture.state), \
             patch.object(gateway,'validate_orchestration',return_value=(True,None,[])):
            envelope,task,directory,ledger = gateway.prepare_v9_chartered_delivery('sample',fixture.worktree,
                fixture.commit,root=fixture.root,logical_assignments=assignments,catalog=catalog,
                availability=[{**item,'observed_at':datetime.now(timezone.utc).isoformat(),
                    'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()}
                    for item in template['selection_inputs']['availability']],effective_policy=policy)
        self.assertEqual(envelope['call_budgets']['producer'],1800)
        self.assertEqual(envelope['call_budgets']['manager'],1800)
        self.assertEqual(envelope['limits']['max_paid_worker_calls'],6)
        calls=[]
        def hosted(**options):
            calls.append(('hosted',options['timeout_seconds']))
            if 'next_speaker.answer must be exactly one of ' in options['task']:
                allowed=json.loads(re.search(r'next_speaker.answer must be exactly one of (\[[^\n]+\])',options['task']).group(1))
                return {'output':json.dumps({'is_request_satisfied':{'answer':False},'is_in_loop':{'answer':True},
                    'is_progress_being_made':{'answer':True},'next_speaker':{'answer':allowed[0],'reason':'approved frontier'},
                    'instruction_or_question':{'answer':'Complete approved assignment'}})}
            if options.get('sandbox')=='workspace-write' or producer=='claude' and reviewer!='claude':
                (options['workspace']/'target.py').write_text('new\n')
                return {'output':'Applied observed edit'}
            return {'output':json.dumps({'schema_version':1,'decision':'pass','summary':'Current diff and tests reviewed','findings':[]})}
        def native(pool,identity,instructions,task,callback,**options):
            calls.append(('local',options['request_timeout']))
            tools=[]
            def tool(name,args):
                result=callback(name,args)
                tools.append({'type':'tool_result','name':name,'result':result})
                return result
            if identity=='producer':
                tool('read_files',{'paths':['target.py']})
                tool('write_file',{'path':'target.py','content':'new\n'})
                tool('run_tests',{})
            else:
                tool('read_files',{'paths':['target.py']})
                tool('run_tests',{})
                tool('submit_review',{'approved':True,'findings':'Read current target.py and ran passing tests'})
            return {'output':'Observed native fixture turn','session_id':'fixture-'+identity,'events':tools,
                'model_requests':[],'model_sends':[],'model_responses':[],'tool_observations':tools}
        with patch.object(gateway,'call_codex',side_effect=hosted), \
             patch.object(gateway,'call_claude',side_effect=hosted), \
             patch.object(gateway,'call_claude_edit',side_effect=hosted), \
             patch.object(LocalAgentPool,'run',autospec=True,side_effect=native):
            result=gateway.execute_v9_logical_delivery(envelope,task,ledger,
                gateway._v9_adapter_for_operation(envelope,read_paths=['target.py'],write_paths=['target.py']),
                readiness_recheck=lambda binding:{**binding,'state':'ready'},supervisor=coordinate)
        self.assertEqual(result['status'],'completed',repr(result)+' '+repr([e for e in ledger.snapshot(envelope['attempt_id'])['events'] if e['event']=='v9_evidence_failed']))
        receipt=json.loads(Path(result['receipt_path']).read_text())
        verify_selection_receipt(receipt)
        self.assertEqual((fixture.worktree/'target.py').read_text(),'new\n')
        self.assertIn(('hosted',1800),calls)
        self.assertIn(('local',1800),calls)
        selected={a['assignment_id']:a['selection_decision']['selected_binding']['provider'] for a in receipt['actions']}
        self.assertEqual(selected['producer'],producer)
        self.assertEqual(selected['verifier'],reviewer)
        return receipt

    def test_local_producer_codex_reviewer_uses_normal_gateway(self):
        self.exercise('ollama','codex')

    def test_local_producer_claude_reviewer_uses_normal_gateway(self):
        self.exercise('ollama','claude')

    def test_codex_producer_local_reviewer_uses_normal_gateway(self):
        self.exercise('codex','ollama')

    def test_claude_producer_local_reviewer_uses_normal_gateway(self):
        self.exercise('claude','ollama')
