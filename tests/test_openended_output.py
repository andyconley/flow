"""Open-ended local output preserves finite context and explicit safety guards."""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'cli'))
from runner_limits import resolve_local_agent_budget
from local_machine import load_local_machine
from local_worker import call_local

class OpenEndedOutputTests(unittest.TestCase):
    def test_sentinel_validation_preserves_context_timeout_and_pressure_contract(self):
        budget = resolve_local_agent_budget()
        self.assertEqual(budget['output_tokens'], -1)
        self.assertEqual((budget['context_tokens'], budget['context_reserve']), (12288,1024))
        self.assertEqual((budget['request_timeout_seconds'],budget['turn_timeout_seconds']), (600,2400))
        for bad in (0,-2,True):
            with self.assertRaises(ValueError): resolve_local_agent_budget({'output_tokens':bad})
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'flow.toml'
            path.write_text('[local_machine]\noutput_tokens=-1\n')
            self.assertEqual(load_local_machine(path)['output_tokens'], -1)

    def test_native_http_body_not_default_or_adapter_cap(self):
        bodies=[]
        class Response:
            status=200
            def __enter__(self): return self
            def __exit__(self,*a): pass
            def read(self,n): return json.dumps({'model':'fixture','message':{'content':'x'*20000}}).encode()
        class Opener:
            def open(self,request,timeout):
                bodies.append(json.loads(request.data)); self_timeout=timeout
                return Response()
        with patch('local_worker.urllib.request.build_opener',return_value=Opener()):
            result=call_local({'model':'fixture','provider':'ollama','instructions':'a','task':'b','attempt_id':'x'},local_agent_profile={})
        self.assertEqual(bodies[0]['options']['num_predict'],-1)
        self.assertEqual(bodies[0]['options']['num_ctx'],12288)
        self.assertEqual(len(result['output']),20000)

    def test_enrichment_payload_keeps_context_and_timeout(self):
        text=(ROOT/'v2/poc/knowledge_runtime/enrich.py').read_text()
        tree=ast.parse(text)
        payload=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='payload' for t in n.targets))
        options=ast.literal_eval(payload.values[payload.keys.index(next(k for k in payload.keys if isinstance(k,ast.Constant) and k.value=='options'))])
        self.assertEqual(options['num_predict'],-1)
        self.assertEqual(options['num_ctx'],16384)
        self.assertIn('timeout=180',text)

class AdapterProjectionTests(unittest.TestCase):
    def test_goose_environment_supports_negative_one_without_native_override(self):
        sys.path.insert(0,str(ROOT/'v2'))
        from poc import device_context
        with tempfile.TemporaryDirectory() as d, patch.dict('os.environ', {'HOME': d,'GOOSE_INPUT_LIMIT':''}):
            user=Path(d)/'.flow/user'; user.mkdir(parents=True)
            (user/'runtime.toml').write_text('[profiles.local]\nkind="local"\nmodel="ollama_chat/fixture"\nmax_input_tokens=12288\nmax_output_tokens=-1\ncondenser_max_tokens=10240\n')
            local=device_context.ollama_environment(Path(d),'fixture','ollama')
            self.assertNotIn('GOOSE_MAX_TOKENS',local)
            self.assertEqual(local['GOOSE_INPUT_LIMIT'],'12288')
            self.assertAlmostEqual(float(local['GOOSE_AUTO_COMPACT_THRESHOLD']),10240/12288)
            self.assertNotIn('GOOSE_MAX_TOKENS', device_context.ollama_environment(Path(d),'fixture','claude'))

    def test_actual_maf_adapter_preserves_sentinel(self):
        try:
            from agent_framework import Message
            from agent_framework.ollama import OllamaChatClient
        except ImportError:
            self.skipTest('requires pinned MAF runtime')
        client=OllamaChatClient(model='fixture')
        request=client._prepare_options([Message(role='user',contents=['test'])], {'num_ctx':12288,'max_tokens':-1,'think':False})
        self.assertEqual(request['options']['num_predict'],-1)
        self.assertEqual(request['options']['num_ctx'],12288)

    def test_context_derived_transport_overflow_fails_without_truncation(self):
        with self.assertRaisesRegex(RuntimeError, 'no truncation'):
            call_local({'model':'fixture','provider':'ollama','instructions':'a','task':'b','attempt_id':'x'}, local_agent_profile={}, transport=lambda _: {'model':'fixture','message':{'content':'x'*(12288*8+1)}})

    def test_local_profile_allows_sentinel_only_for_ollama(self):
        import openhands_config as config
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            config.provision_native_profiles(root)
            cfg=config.load_config(root,root)
            cfg['profiles']['fixture']={'kind':'local','model':'ollama_chat/fixture','base_url':'http://127.0.0.1:11434','max_input_tokens':16384,'max_output_tokens':-1}
            selected=config.select(root,'plan',profile='fixture',config=cfg,user_overlay=root)
            self.assertEqual(selected.provider['max_output_tokens'],-1)
            cfg['profiles']['fixture']['model']='openai/fixture'
            with self.assertRaises(config.RuntimeConfigurationError):
                config.select(root,'plan',profile='fixture',config=cfg,user_overlay=root)
