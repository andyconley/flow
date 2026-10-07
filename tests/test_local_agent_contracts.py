"""Sealed retained-agent profile and native offline evidence boundaries."""
from __future__ import annotations
import copy
import sys
import unittest
import tempfile
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
from execution_contracts import (ContractError, validate_envelope, validate_local_agent_observations, validate_local_manager_context_refusal,
                                 validate_local_agent_profile, chartered_test_argv_supported)
from runner_limits import resolve_local_agent_budget
from provider_selection import digest
from selection_receipt import V9ReceiptError, verify_selection_receipt, seal_selection_receipt
from verifier_contracts import evaluate_candidate
from tests.test_delivery_selection import _envelope
from tests.test_selection_receipt import _receipt
from delivery_contracts import build_shaper_contract, build_delivery_charter, DeliveryContractError
from tests.shaper_intent_fixture import shaper_intent
from execution_ledger import ExecutionLedger
from delivery_selection import make_action
from delivery_gateway import execute_v9_selected_action
from runstate import _delivery_plan_errors


def evidence():
    events = []
    for number in (1, 2):
        events.extend([
            {'type': 'model_request', 'number': number, 'request': {
                'options': {'num_ctx': 49152, 'num_predict': 12288}}},
            {'type': 'model_send', 'number': number},
            {'type': 'model_response', 'number': number, 'responses': [{'done_reason': 'stop'}]},
        ])
    tools = [{'type': 'tool_result', 'name': 'write_file', 'result': {'status': 'written'}},
             {'type': 'tool_result', 'name': 'run_tests', 'result': {'status': 'passed'}}]
    events.extend(tools)
    return {'session_id': 'retained-session', 'events': events,
            'model_requests': [item for item in events if item['type'] == 'model_request'],
            'model_responses': [item for item in events if item['type'] == 'model_response'],
            'tool_observations': tools}


def iterative_receipt(steps, *, missing_evidence_at=None, envelope=None):
    """Deterministic parent observations, not claimed model execution."""
    envelope = _envelope() if envelope is None else envelope
    envelope['local_agent_profile'] = resolve_local_agent_budget()
    actions, rows, semantic, observed, failures = [], [], [], [], []
    current_source = None
    for sequence, (operation, value) in enumerate(steps, 1):
        identity = 'producer' if operation == 'edit' else 'verifier'
        action = make_action(envelope, identity, f'Observed turn {sequence}', sequence=sequence, manager_turn=sequence)
        actions.append(action)
        rows.append({'selection_id': action['selection_id'], 'logical_action_id': action['logical_action_id'],
            'decision_digest': action['selection_decision']['decision_digest'],
            'candidate_id': action['selection_decision']['selected_candidate_id'], 'state': 'consumed',
            'reason': '', 'predecessor_selection_id': None, 'provider_action_id': action['action_id'],
            'prior_no_send_failures': []})
        if operation == 'edit':
            current_source = value
            result = {'status': 'written', 'source_digest': current_source}
            tool = {'type': 'tool_result', 'name': 'write_file', 'result': result}
        else:
            candidate = {'schema_version': 1, 'decision': value, 'summary': 'Current source reviewed',
                'findings': [] if value == 'pass' else [{'severity': 'blocking', 'summary': 'Repair needed', 'evidence': 'Observed source'}]}
            review = {'candidate': candidate, 'source_digest': current_source,
                'test_evidence': {'status': 'passed', 'source_digest': current_source, 'current_source_digest': current_source},
                'raw_findings': 'Actual fixture observations'}
            tool = {'type': 'tool_result', 'name': 'submit_review', 'result': {'status': 'review_recorded', **review}}
            provider_input = {'provider_task': action['task'], 'assignment_id': identity}
            raw = json.dumps(candidate)
            evaluation = evaluate_candidate(action_id=action['action_id'], verifier_input_digest=digest(provider_input),
                raw_output=raw, diff_digest='a'*64, test_evidence_digest='b'*64)
            if missing_evidence_at != sequence:
                semantic.append({'action_id': action['action_id'], 'input': provider_input, 'input_digest': digest(provider_input),
                    'diff_digest': 'a'*64, 'test_digest': 'b'*64, 'result': {'output': raw, 'current_source_review': review},
                    'evaluation': evaluation})
        body = {'session_id': f'fixture-{sequence}', 'events': [tool], 'model_requests': [], 'model_responses': [],
                'tool_observations': [tool]}
        observed.append({'action_id': action['action_id'], 'evidence': body, 'evidence_digest': digest(body)})
        if missing_evidence_at == sequence:
            failures.append({'action_id': action['action_id'], 'stage': 'assignment_evidence', 'detail': 'Observed incomplete turn'})
    return seal_selection_receipt(envelope, actions, rows, semantic_verification=semantic,
        local_agent_observations=observed, evidence_failures=failures,
        outcome={'status': 'completed', 'reason': 'Current source independently accepted'})


class LocalAgentContractsTests(unittest.TestCase):
    def test_zero_io_manager_context_refusal_reconciles_only_after_current_worker_proof(self):
        from delivery_selection import RecoveryRequired
        for mutation in ('none', 'send', 'budget', 'scope', 'artifact', 'stale_review'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                envelope = _envelope(allowed_candidates=['local'])
                envelope['checkpoint_dir'] = str(root/'checkpoints')
                steps = [('edit', 'a'*64), ('review', 'pass')]
                if mutation == 'stale_review':
                    steps = [('edit', 'a'*64), ('review', 'pass'), ('edit', 'c'*64), ('review', 'pass')]
                fixture = iterative_receipt(steps, envelope=envelope)
                observations = {item['action_id']: item['evidence'] for item in fixture['local_agent_observations']}
                semantic = {item['action_id']: item for item in fixture['semantic_verification']}
                ledger = ExecutionLedger(root/'ledger.sqlite3')
                ledger.create_attempt(envelope)
                for action in fixture['actions']:
                    if mutation == 'stale_review' and action['sequence'] == 4:
                        continue
                    item = semantic.get(action['action_id'])
                    result = {**(item['result'] if item else {'output': 'Edited'}),
                              'local_agent_observations': observations[action['action_id']]}
                    execute_v9_selected_action(envelope, action, lambda *_: result,
                        readiness_recheck=lambda binding: {**binding, 'state': 'ready'}, ledger=ledger, generation=1)
                    if item:
                        ledger.record_v9_verifier_evaluation(action['action_id'], item['input'], result,
                            item['evaluation'], item['diff_digest'], item['test_digest'], generation=1)
                assignment = 'producer' if mutation == 'scope' else 'manager'
                action = make_action(envelope, assignment, 'Final control turn', sequence=5, manager_turn=5)
                with self.assertRaises(RecoveryRequired):
                    execute_v9_selected_action(envelope, action,
                        lambda *_: (_ for _ in ()).throw(TimeoutError('pre-send context guard')),
                        readiness_recheck=lambda binding: {**binding, 'state': 'ready'}, ledger=ledger, generation=1)
                event = {'type': 'context_denied', 'bound': 35847, 'allowance': 34816}
                if mutation == 'budget':
                    event['allowance'] = 30000
                path = root/f"action-{action['action_id']}-observations.jsonl"
                raw = json.dumps(event)+'\n'
                if mutation == 'send':
                    raw += json.dumps({'type': 'model_send', 'number': 1})+'\n'
                path.write_text(raw)
                if mutation == 'artifact':
                    path.unlink()
                    (root/'outside').write_text(raw)
                    path.symlink_to(root/'outside')
                if mutation != 'none':
                    with self.assertRaises((ContractError, V9ReceiptError)):
                        ledger.reconcile_local_manager_context_denial(envelope['attempt_id'], action['action_id'], generation=1)
                    self.assertEqual(ledger.snapshot(envelope['attempt_id'])['actions'][-1]['status'], 'unknown')
                    continue
                closed = ledger.reconcile_local_manager_context_denial(envelope['attempt_id'], action['action_id'], generation=1)
                self.assertEqual(closed['status'], 'pre_send_refused')
                self.assertEqual(validate_local_agent_observations(closed['result']['local_agent_observations'],
                    profile=envelope['local_agent_profile'])['model_sends'], 0)
                sealed = ledger.seal_v9_attempt(envelope['attempt_id'], 'completed', 'Current review accepted', root/'receipt.json', generation=1)
                receipt = json.loads(Path(sealed['receipt_path']).read_text())
                self.assertEqual(verify_selection_receipt(receipt)['status'], 'valid_pass')
                self.assertEqual(receipt['selections'][-1]['state'], 'pre_send_refused')
                self.assertIsNone(receipt['selections'][-1]['provider_action_id'])
                self.assertNotIn('output', closed['result'])
                forged = copy.deepcopy(closed['result'])
                forged['local_agent_observations']['context_denial']['artifact_sha256'] = '0'*64
                with self.assertRaises(ContractError):
                    validate_local_manager_context_refusal(envelope, action, forged)
                legacy = copy.deepcopy(envelope)
                legacy.pop('local_agent_profile')
                with self.assertRaises(ContractError):
                    validate_local_manager_context_refusal(legacy, action, closed['result'])

    def test_ledger_seals_failed_review_repair_current_pass_with_full_history(self):
        fixture = iterative_receipt([('edit', 'a'*64), ('review', 'fail'), ('edit', 'c'*64), ('review', 'pass')])
        envelope = fixture['envelope']
        observations = {item['action_id']: item['evidence'] for item in fixture['local_agent_observations']}
        semantic = {item['action_id']: item for item in fixture['semantic_verification']}
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / 'ledger.sqlite3')
            ledger.create_attempt(envelope)
            for action in fixture['actions']:
                item = semantic.get(action['action_id'])
                result = {**(item['result'] if item else {'output': 'Edited current source'}),
                          'local_agent_observations': observations[action['action_id']]}
                execute_v9_selected_action(envelope, action, lambda *_: result,
                    readiness_recheck=lambda binding: {**binding, 'state': 'ready'}, ledger=ledger, generation=1)
                if item:
                    ledger.record_v9_verifier_evaluation(action['action_id'], item['input'], result,
                        item['evaluation'], item['diff_digest'], item['test_digest'], generation=1)
            sealed = ledger.seal_v9_attempt(envelope['attempt_id'], 'completed', 'Fresh review passed',
                Path(tmp) / 'receipt.json', generation=1)
            receipt = json.loads(Path(sealed['receipt_path']).read_text())
            self.assertEqual(verify_selection_receipt(receipt)['status'], 'valid_pass')
            self.assertEqual([item['evaluation']['disposition'] for item in receipt['semantic_verification']],
                             ['valid_fail', 'valid_pass'])

    def test_legacy_ledger_still_rejects_repeated_completed_verifiers(self):
        fixture = iterative_receipt([('edit', 'a'*64), ('review', 'fail'), ('edit', 'c'*64), ('review', 'pass')])
        envelope = fixture['envelope']
        envelope.pop('local_agent_profile')
        semantic = {item['action_id']: item for item in fixture['semantic_verification']}
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp) / 'ledger.sqlite3')
            ledger.create_attempt(envelope)
            for action in fixture['actions']:
                item = semantic.get(action['action_id'])
                action = make_action(envelope, action['assignment_id'], action['task'],
                                     sequence=action['sequence'], manager_turn=action['manager_turn'])
                if item:
                    item['evaluation'] = evaluate_candidate(action_id=action['action_id'],
                        verifier_input_digest=digest(item['input']), raw_output=item['result']['output'],
                        diff_digest=item['diff_digest'], test_evidence_digest=item['test_digest'])
                result = item['result'] if item else {'output': 'Edited current source'}
                execute_v9_selected_action(envelope, action, lambda *_: result,
                    readiness_recheck=lambda binding: {**binding, 'state': 'ready'}, ledger=ledger, generation=1)
                if item:
                    ledger.record_v9_verifier_evaluation(action['action_id'], item['input'], result,
                        item['evaluation'], item['diff_digest'], item['test_digest'], generation=1)
            with self.assertRaisesRegex(ContractError, 'terminal status contradicts verifier evidence'):
                ledger.seal_v9_attempt(envelope['attempt_id'], 'completed', 'Repeated reviews',
                    Path(tmp) / 'receipt.json', generation=1)

    def test_failed_review_repair_then_current_pass_closes_without_erasing_history(self):
        receipt = iterative_receipt([('edit', 'a'*64), ('review', 'fail'), ('edit', 'c'*64), ('review', 'pass')])
        self.assertEqual(verify_selection_receipt(receipt)['status'], 'valid_pass')
        self.assertEqual([item['evaluation']['disposition'] for item in receipt['semantic_verification']],
                         ['valid_fail', 'valid_pass'])

    def test_pass_before_new_edit_is_stale_and_cannot_close(self):
        with self.assertRaises(V9ReceiptError):
            iterative_receipt([('edit', 'a'*64), ('review', 'pass'), ('edit', 'c'*64)])

    def test_incomplete_review_then_repair_and_observed_review_can_close(self):
        receipt = iterative_receipt([('edit', 'a'*64), ('review', 'fail'), ('edit', 'c'*64), ('review', 'pass')], missing_evidence_at=2)
        self.assertEqual(verify_selection_receipt(receipt)['status'], 'valid_pass')
        self.assertEqual(len(receipt['evidence_failures']), 1)

    def test_incomplete_producer_then_repair_and_review_retains_feedback(self):
        receipt = iterative_receipt([('edit', 'a'*64), ('edit', 'c'*64), ('review', 'pass')], missing_evidence_at=1)
        self.assertEqual(verify_selection_receipt(receipt)['status'], 'valid_pass')
        self.assertEqual(receipt['evidence_failures'][0]['stage'], 'assignment_evidence')

    def test_source_mismatch_and_missing_parent_observation_cannot_close(self):
        for mutation in ('source', 'observations', 'no_write'):
            receipt = iterative_receipt([('edit', 'a'*64), ('review', 'pass')])
            if mutation == 'source':
                receipt['semantic_verification'][-1]['result']['current_source_review']['source_digest'] = 'f'*64
            elif mutation == 'observations':
                receipt['local_agent_observations'] = receipt['local_agent_observations'][1:]
            else:
                body = receipt['local_agent_observations'][0]['evidence']
                body['events'] = body['tool_observations'] = []
                receipt['local_agent_observations'][0]['evidence_digest'] = digest(body)
            receipt['receipt_digest'] = digest({key: value for key, value in receipt.items() if key != 'receipt_digest'})
            with self.assertRaises(V9ReceiptError):
                verify_selection_receipt(receipt)
    def test_native_test_discovery_matches_approved_fixture_and_preserves_legacy(self):
        native = ['python3', '-m', 'unittest', 'discover', '-s', '.', '-p', 'test_*.py']
        self.assertTrue(chartered_test_argv_supported(native, native_local=True))
        self.assertFalse(chartered_test_argv_supported(native))
        legacy = ['python3', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_example.py']
        self.assertTrue(chartered_test_argv_supported(legacy))
        self.assertTrue(chartered_test_argv_supported(legacy, native_local=True))
        for invalid in (['python3', '-m', 'unittest', 'discover', '-s', '../outside'],
                        ['python3', '-m', 'unittest', 'discover', '-s', '.', '-p', '*.py'],
                        ['python3', '-m', 'unittest', 'discover', '-s', '.', '-p', None]):
            self.assertFalse(chartered_test_argv_supported(invalid, native_local=True))
    def test_normal_plan_accepts_local_manager_and_sequential_producers(self):
        logical = copy.deepcopy(_envelope()['logical_assignments'])
        second = copy.deepcopy(logical[1])
        second.update(assignment_id='consumer', depends_on=['producer'])
        logical.insert(2, second)
        logical[-1]['depends_on'] = ['producer', 'consumer']
        profile = resolve_local_agent_budget()
        charter = {'task': 'Implement with two sequential specialists.', 'read_paths': ['app.py'],
            'write_paths': ['app.py'], 'test': {'argv': ['python3', '-m', 'unittest', 'discover', '-s', '.', '-p', 'test_*.py'], 'timeout_seconds': 600},
            'baseline': {'kind': 'clean', 'diff_sha256': 'a'*64},
            'producer_instance_ids': ['producer', 'consumer'], 'verifier_instance_ids': ['verifier'],
            'logical_assignments': logical, 'local_agent_profile': profile}
        manifest = {'assignments': [{'id': 'magentic-manager', 'lane': 'implement', 'role': 'delivery-lead',
            'execution': {'provider': 'ollama', 'model': 'gemma4-26b-dev:latest', 'timeout_seconds': 2400},
            'input_evidence': ['.flow/runs/demo/job-charter.json']},
            {'id': 'producer', 'read_only': False}, {'id': 'consumer', 'read_only': False},
            {'id': 'verifier', 'read_only': True}]}
        payload = {'artifacts': {'orchestration_manifest': '.flow/runs/demo/orchestration.json',
                                'job_charter': '.flow/runs/demo/job-charter.json'}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root/'.flow/runs/demo'
            run.mkdir(parents=True)
            (run/'orchestration.json').write_text(json.dumps(manifest))
            (run/'job-charter.json').write_text(json.dumps(charter))
            self.assertEqual(_delivery_plan_errors('demo', payload, root=root), [])
            del charter['local_agent_profile']
            (run/'job-charter.json').write_text(json.dumps(charter))
            errors = _delivery_plan_errors('demo', payload, root=root)
            self.assertTrue(any('exactly one logical producer' in error for error in errors))
            self.assertTrue(any('Ollama delivery manager' in error for error in errors))
    def test_nullable_native_ledger_budget_and_completed_observations(self):
        envelope = _envelope()
        envelope['local_agent_profile'] = resolve_local_agent_budget()
        envelope['limits']['max_actions'] = None
        action = make_action(envelope, 'producer', 'Iterate within approved scope.', sequence=1, manager_turn=1)
        with tempfile.TemporaryDirectory() as tmp:
            ledger = ExecutionLedger(Path(tmp)/'ledger.sqlite3')
            ledger.create_attempt(envelope)
            result = execute_v9_selected_action(envelope, action,
                lambda binding, selected: {'output': 'done', 'local_agent_observations': evidence()},
                readiness_recheck=lambda binding: {**binding, 'state': 'ready'}, ledger=ledger, generation=1)
            self.assertEqual(result['status'], 'completed')
            observed = ledger.snapshot(envelope['attempt_id'])['actions'][0]['result']['result']
            self.assertEqual(validate_local_agent_observations(observed['local_agent_observations'])['model_sends'], 2)
    def test_profile_is_sealed_across_intent_and_delivery_authority(self):
        intent = shaper_intent()
        intent['local_agent_profile'] = {}
        intent['delegation_matrix']['max_delegations'] = 20
        intent['budget_safety_envelope']['enforceable']['runtime_seconds'] = 2400
        intent['budget_safety_envelope']['enforceable']['max_manager_calls'] = 30
        sources = {'requirements': {'path': '.flow/runs/demo/requirements.md', 'sha256': 'a'*64},
                   'acceptance_criteria': {'path': '.flow/runs/demo/acceptance.md', 'sha256': 'b'*64}}
        shaper = build_shaper_contract('demo', sources, intent)
        charter = build_delivery_charter(shaper)
        self.assertEqual(shaper['local_agent_profile'], resolve_local_agent_budget())
        self.assertEqual(charter['local_agent_profile'], shaper['local_agent_profile'])
        del intent['local_agent_profile']
        with self.assertRaises(DeliveryContractError):
            build_shaper_contract('demo', sources, intent)
    def test_resolved_profile_allows_uncapped_counts_but_reserves_context(self):
        profile = resolve_local_agent_budget()
        self.assertEqual(validate_local_agent_profile(profile), profile)
        self.assertIsNone(profile['delegations'])
        broken = {**profile, 'output_tokens': profile['context_tokens']}
        with self.assertRaises(ContractError):
            validate_local_agent_profile(broken)
        with self.assertRaises(ContractError):
            validate_local_agent_profile({'context_tokens': 49152})

    def test_profile_transport_not_four_kib_task_or_one_producer_rule(self):
        envelope = _envelope()
        envelope['local_agent_profile'] = resolve_local_agent_budget()
        envelope['limits']['max_actions'] = None
        envelope['logical_assignments'][1]['instructions'] = 'Complete compact source.\n' * 4000
        # Context is evaluated at send time. IPC remains independently bounded.
        validate_envelope(envelope)
        del envelope['local_agent_profile']
        envelope['limits']['max_actions'] = 6
        with self.assertRaises(ContractError):
            validate_envelope(envelope)

    def test_delegation_is_not_one_model_call_and_no_test_before_edit_gate(self):
        counts = validate_local_agent_observations(evidence(), profile=resolve_local_agent_budget())
        self.assertEqual(counts, {'model_requests': 2, 'model_sends': 2,
                                 'model_responses': 2, 'tool_calls': 2, 'delegations': 1})

    def test_request_hook_without_send_is_not_physical_call(self):
        observed = evidence()
        observed['events'] = observed['events'][:1]
        observed['model_requests'] = observed['events'][:]
        observed['model_responses'] = []
        observed['tool_observations'] = []
        self.assertEqual(validate_local_agent_observations(observed)['model_sends'], 0)

    def test_wrong_context_and_unbound_or_reordered_response_denied(self):
        observed = evidence()
        observed['model_requests'][0]['request']['options']['num_ctx'] = 16384
        with self.assertRaises(ContractError):
            validate_local_agent_observations(observed, profile=resolve_local_agent_budget())
        observed = evidence()
        observed['events'][1], observed['events'][2] = observed['events'][2], observed['events'][1]
        with self.assertRaises(ContractError):
            validate_local_agent_observations(observed)
        observed = evidence()
        observed['tool_observations'] = []
        with self.assertRaises(ContractError):
            validate_local_agent_observations(observed)
        observed = evidence()
        observed['model_sends'] = []
        with self.assertRaises(ContractError):
            validate_local_agent_observations(observed)
        observed = evidence()
        observed['model_responses'].append({'type': 'model_response', 'number': 99})
        with self.assertRaises(ContractError):
            validate_local_agent_observations(observed)

    def test_legacy_receipt_unmodified_and_new_observations_bound(self):
        receipt = _receipt()
        verify_selection_receipt(receipt)
        altered = copy.deepcopy(receipt)
        altered['local_agent_observations'] = [{'action_id': receipt['actions'][-1]['action_id'],
            'evidence': evidence(), 'evidence_digest': digest(evidence())}]
        altered['receipt_digest'] = digest({key: value for key, value in altered.items() if key != 'receipt_digest'})
        with self.assertRaises(V9ReceiptError):
            verify_selection_receipt(altered)  # No sealed retained profile.


if __name__ == '__main__':
    unittest.main()
