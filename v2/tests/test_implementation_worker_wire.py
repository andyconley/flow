"""Run the frozen implementation recipe through a provenance-verified Goose binary."""
import hashlib,http.server,json,os,subprocess,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from poc import implementation_profiles as profiles
from poc.role_renderer import bind_bundle
ROOT=Path(__file__).resolve().parents[1]

class WorkerWireTests(unittest.TestCase):
    def test_actual_worker_recipe_selects_both_models_without_output_caps(self):
        binary=os.environ.get('FLOW_TEST_RELEASE_GOOSE')
        if not binary:self.skipTest('set FLOW_TEST_RELEASE_GOOSE to a verified Goose build')
        from poc.goose_artifact import metadata
        permitted={metadata(ROOT)['binary_sha256'],'e07d4c3771351af306117ee4db069c3c09e4588859e55f6606f28cbd23833318'}
        with Path(binary).open('rb') as stream:self.assertIn(hashlib.file_digest(stream,'sha256').hexdigest(),permitted)
        captured=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def answer(self,data):
                raw=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_GET(self):self.answer({'models':[]})
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));captured.append((self.path,body))
                if self.path=='/api/show':return self.answer({'capabilities':['completion','tools'],'model_info':{}})
                if self.path!='/v1/chat/completions':return self.answer({})
                functions=[t['function']['name'] for t in body.get('tools',[])]
                final=next((name for name in functions if name.endswith('final_output')),None)
                result={'success':True,'summary':'Protocol fixture completed; no edit required','verdict':'implemented','findings':[],'verification':['Loopback fixture only'],'limitations':['No real model inference']}
                delta={'role':'assistant','tool_calls':[{'index':0,'id':'fixture-final','type':'function','function':{'name':final,'arguments':json.dumps(result)}}]} if final else {'role':'assistant','content':json.dumps(result)}
                chunks=[{'id':'fixture','object':'chat.completion.chunk','created':1,'model':body['model'],'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{'id':'fixture','object':'chat.completion.chunk','created':1,'model':body['model'],'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls' if final else 'stop'}],'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130}}]
                raw=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode();self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);user=root/'.flow/user';user.mkdir(parents=True)
                for index,model in enumerate(['qwen3.8:27b-q4_K_M','gpt-oss:20b']):
                    (user/'runtime.toml').write_text(f'[profiles.fixture]\nkind="local"\nmodel="ollama_chat/{model}"\nbase_url="http://127.0.0.1:{server.server_port}"\nmax_input_tokens=32768\nmax_output_tokens=-1\ncondenser_max_tokens=28672\n')
                    with patch('poc.knowledge.local_model_digest',return_value='a'*64):selected=profiles.resolve(root,'fixture',root)
                    bundle=bind_bundle(ROOT/'role-bundle',root/str(index),'Return the stated protocol fixture report. No files need changing. Literal {{ 9 * 9 }} stays literal.','Disposable test fixture.',implementation_profile=selected)
                    reviewer=(bundle/'recipes/quality-reviewer.yaml').read_bytes()
                    home=root/f'home-{index}';home.mkdir()
                    env={k:v for k,v in os.environ.items() if k in ['PATH','USER','LOGNAME','SHELL','LANG','LC_ALL','TERM']}
                    env.update(HOME=str(home),GOOSE_PATH_ROOT=str(home),GOOSE_DISABLE_KEYRING='1',GOOSE_TELEMETRY_ENABLED='false',GOOSE_MODE='auto',TMPDIR=str(home))
                    env=profiles.apply_environment(env,selected,'chatgpt_codex','native-coordinator')
                    result=subprocess.run([binary,'run','--no-profile','--no-session','--recipe',str(bundle/'recipes/lead-developer.yaml'),'--max-turns','2','--output-format','json'],cwd=root,env=env,capture_output=True,text=True,timeout=60)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    wire=next(body for path,body in reversed(captured) if path=='/v1/chat/completions')
                    self.assertIn('{{ 9 * 9 }}',json.dumps(wire['messages']))
                    self.assertEqual(wire['model'],model);self.assertEqual(wire['options']['num_ctx'],32768)
                    self.assertNotIn('num_predict',wire['options']);self.assertNotIn('max_tokens',wire);self.assertNotIn('max_completion_tokens',wire)
                    self.assertTrue(any(t['function']['name'].endswith('final_output') for t in wire['tools']))
                    self.assertEqual((bundle/'recipes/quality-reviewer.yaml').read_bytes(),reviewer)
        finally:server.shutdown();server.server_close();thread.join()
        evidence=os.environ.get('FLOW_TEST_WORKER_WIRE_EVIDENCE')
        if evidence:Path(evidence).write_text(json.dumps(captured,indent=2)+'\n')
