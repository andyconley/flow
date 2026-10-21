"""Shipped Goose and v2 enrichment request paths against disposable loopback stubs."""
import ast, asyncio, hashlib, http.server, json, os, subprocess, sys, tempfile, threading, time, unittest, urllib.request
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v2'))
from poc.runtime_env import environment

class V2WireTests(unittest.TestCase):
    def test_shipped_goose_preserves_explicit_models_context_and_openended_output(self):
        binary=os.environ.get('FLOW_TEST_RELEASE_GOOSE')
        if not binary:self.skipTest('set FLOW_TEST_RELEASE_GOOSE to the verified v0.52.2 binary')
        with Path(binary).open('rb') as stream:
            self.assertEqual(hashlib.file_digest(stream,'sha256').hexdigest(),'e07d4c3771351af306117ee4db069c3c09e4588859e55f6606f28cbd23833318')
        captured=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.answer({'models':[]})
            def answer(self,data):
                body=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append((self.path,body))
                if self.path=='/api/show':return self.answer({'capabilities':['completion','tools'],'model_info':{}})
                if self.path!='/v1/chat/completions':return self.answer({})
                model=body['model']
                chunks=[{'id':'fixture','object':'chat.completion.chunk','created':1,'model':model,'choices':[{'index':0,'delta':{'role':'assistant','content':'ok'},'finish_reason':None}]}, {'id':'fixture','object':'chat.completion.chunk','created':1,'model':model,'choices':[{'index':0,'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':1,'total_tokens':11}}]
                data=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'HOME':d,'GOOSE_INPUT_LIMIT':''}):
                home=Path(d);user=home/'.flow/user';user.mkdir(parents=True)
                for model in ['qwen3.8:27b-q4_K_M','gpt-oss:20b']:
                    (user/'runtime.toml').write_text('[profiles.fixture]\nkind="local"\nmodel="ollama_chat/'+model+'"\nmax_input_tokens=32768\nmax_output_tokens=-1\ncondenser_max_tokens=28672\n')
                    env=environment(home,provider='ollama',model=model)
                    env.update(HOME=d,GOOSE_PATH_ROOT=d,OLLAMA_HOST=f'http://127.0.0.1:{server.server_port}',GOOSE_PROVIDER='ollama',GOOSE_MODEL=model,GOOSE_TELEMETRY_ENABLED='false',GOOSE_DISABLE_KEYRING='1',TMPDIR=d)
                    result=subprocess.run([binary,'run','--no-profile','--no-session','--provider','ollama','--model',model,'--text','Reply ok.','--max-turns','1','--output-format','json'],cwd=d,env=env,capture_output=True,text=True,timeout=45)
                    self.assertEqual(result.returncode,0,result.stderr+result.stdout)
                    request=next(body for path,body in reversed(captured) if path=='/v1/chat/completions')
                    self.assertEqual(request['model'],model)
                    self.assertNotIn('num_predict',request.get('options',{}))
                    self.assertNotIn('max_tokens',request)
                    self.assertNotIn('max_completion_tokens',request)
                    self.assertEqual(request['options']['num_ctx'],32768)
                    self.assertEqual(env['GOOSE_AUTO_COMPACT_THRESHOLD'],'0.875')
        finally:server.shutdown();server.server_close();thread.join()
        evidence=os.environ.get('FLOW_TEST_WIRE_EVIDENCE')
        if evidence:Path(evidence).write_text(json.dumps(captured,indent=2)+'\n')

    def test_enrichment_actual_function_sends_openended_payload(self):
        # Execute the real function body, omitting only its Coco memo decorator:
        # no model runtime dependencies, indexing or corpus write is invoked.
        tree=ast.parse((ROOT/'v2/poc/knowledge_runtime/enrich.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='extract');function.decorator_list=[]
        module=ast.Module(body=[function],type_ignores=[]);ast.fix_missing_locations(module)
        captured=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self):return json.dumps({'message':{'content':'{"relationships":[]}'},'eval_count':2}).encode()
        def receive(request,timeout):captured.append((json.loads(request.data),timeout));return Response()
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d);(stage/'logs').mkdir()
            scope={'json':json,'asyncio':asyncio,'urllib':__import__('urllib'),'time':time,'ROOT':stage,'os':os,'SCHEMA':{'type':'object'}}
            exec(compile(module,'real-v2-enrichment-function','exec'),scope)
            with patch.dict(os.environ,{'FLOW_KNOWLEDGE_OLLAMA':'http://127.0.0.1:11434'}),patch('urllib.request.urlopen',side_effect=receive):
                self.assertEqual(asyncio.run(scope['extract']('{"id":"source"}','[{"id":"target"}]','qwen3.5:9b-q4_K_M')),'[]')
        payload,timeout=captured[0]
        self.assertEqual(payload['model'],'qwen3.5:9b-q4_K_M');self.assertEqual(payload['options']['num_predict'],-1);self.assertEqual(payload['options']['num_ctx'],16384);self.assertEqual(timeout,180)
