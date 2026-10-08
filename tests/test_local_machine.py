"""Machine capacity changes never broaden sealed run or provider authority."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'cli'))
from local_machine import load_local_machine, check_local_compatibility, new_local_profile_settings
from runner_limits import resolve_local_agent_budget
from execution_contracts import ContractError
from local_worker import call_local
from tests.test_local_worker import _Response, payload, ENVELOPE


class MachineProfileTests(unittest.TestCase):
    def test_default_and_explicit_16k_profiles_are_independent_of_hosted_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'flow.toml'
            self.assertEqual(load_local_machine(path)['context_tokens'],12288)
            path.write_text('[local_machine]\ncontext_tokens=16384\nmax_context_tokens=16384\noutput_tokens=3072\ncontext_reserve=1024\nmodel="llama3.1:8b"\n')
            settings=load_local_machine(path)
            self.assertEqual(settings['context_tokens'],16384)
            self.assertEqual(settings['output_tokens'],3072)

    def test_old_studio_profile_requires_successor_on_laptop_without_mutation(self):
        profile=resolve_local_agent_budget({'context_tokens':49152,'output_tokens':12288,'context_reserve':2048})
        original=copy.deepcopy(profile)
        with self.assertRaisesRegex(ContractError,'successor approval'):
            check_local_compatibility(profile,machine={'max_context_tokens':16384,'model':''})
        self.assertEqual(profile,original)
        check_local_compatibility(profile,machine={'max_context_tokens':49152,'model':'gemma4:26b'},model='gemma4:26b')
        with self.assertRaisesRegex(ContractError,'model differs'):
            check_local_compatibility(profile,machine={'max_context_tokens':49152,'model':'gemma4:26b'},model='llama3.1:8b')

    def test_invalid_config_refuses_instead_of_clamping(self):
        for body in ('context_tokens=20000','output_tokens=12288','context_tokens=true','unknown=1'):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'flow.toml';path.write_text('[local_machine]\n'+body+'\n')
                with self.assertRaises(ContractError):load_local_machine(path)

    def test_ordinary_and_retained_requests_send_actual_context(self):
        settings={'context_tokens':16384,'max_context_tokens':16384,'output_tokens':3072,'context_reserve':1024,'model':''}
        sent=[]
        class Opener:
            def open(self,request,timeout):
                sent.append(json.loads(request.data));return _Response(json.dumps(payload('ok')).encode())
        with patch('local_machine.load_local_machine',return_value=settings), patch('local_worker.urllib.request.build_opener',return_value=Opener()):
            call_local(ENVELOPE)
            call_local(ENVELOPE,local_agent_profile=resolve_local_agent_budget({'context_tokens':16384,'output_tokens':3072,'context_reserve':1024}))
        self.assertEqual([r['options']['num_ctx'] for r in sent],[16384,16384])
        self.assertEqual(sent[1]['options']['num_predict'],3072)

    def test_moved_retained_call_refused_before_http(self):
        profile=resolve_local_agent_budget({'context_tokens':49152,'output_tokens':12288,'context_reserve':2048})
        with patch('local_worker.urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(ContractError,'capacity'):
                call_local(ENVELOPE,local_agent_profile=profile)
            opener.assert_not_called()

class SealedDispatchCapacityTests(unittest.TestCase):
    def test_catalog_narrows_context_without_replacing_hosted_candidates(self):
        from delivery_gateway import local_agent_selection_inputs
        from tests.test_delivery_selection import _envelope
        catalog=copy.deepcopy(_envelope()['selection_inputs']['catalog'])
        original=copy.deepcopy(catalog)
        native,policy=local_agent_selection_inputs(catalog,{'excluded_candidates':['codex']},resolve_local_agent_budget())
        self.assertEqual(catalog,original)
        self.assertEqual(native[0]['max_context_tokens'],12288)
        self.assertEqual(native[1:],original[1:])
        self.assertEqual(policy,{'excluded_candidates':['codex']})

    def test_incompatible_assignment_is_refused_before_physical_send_claim(self):
        from delivery_gateway import _v9_adapter_for_operation, execute_v9_selected_action
        from delivery_selection import make_action
        from execution_ledger import ExecutionLedger
        from tests.test_delivery_selection import _envelope
        envelope=_envelope(allowed_candidates=['local'])
        envelope['local_agent_profile']=resolve_local_agent_budget()
        original=copy.deepcopy(envelope)
        with tempfile.TemporaryDirectory() as directory:
            envelope['worktree']=directory;envelope['source_commit']='a'*40
            ledger=ExecutionLedger(Path(directory)/'ledger.sqlite');ledger.create_attempt(envelope)
            adapter=_v9_adapter_for_operation(envelope,read_paths=['app.py'],write_paths=['app.py'])
            action=make_action(envelope,'producer','approved task',sequence=1,manager_turn=1)
            with patch('delivery_gateway.NativeLocalAdapter') as native:
                with self.assertRaisesRegex(ContractError,'assignment context exceeds'):
                    execute_v9_selected_action(envelope,action,adapter,ledger=ledger,generation=1,
                        readiness_recheck=lambda binding:{**binding,'state':'ready'})
                native.assert_not_called()
            snapshot=ledger.snapshot(envelope['attempt_id'])
            self.assertFalse(any(row['status']=='started' for row in snapshot['actions']))
            self.assertEqual(envelope['selection_inputs'],original['selection_inputs'])
            self.assertEqual(envelope['local_agent_profile'],original['local_agent_profile'])
