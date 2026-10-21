"""Real pinned SDK + LiteLLM projection against a disposable loopback receiver."""
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'cli'))
from openhands_config import Selection
from openhands_runtime import local_llm

class OpenHandsProjectionTests(unittest.TestCase):
    def test_native_wire_overrides_sdk_generation_default(self):
        try:
            from openhands.sdk import Message, TextContent
        except ImportError:
            self.skipTest('requires pinned OpenHands SDK')
        captured=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                captured.append((self.path,request))
                body={'model':'fixture','created_at':'2026-10-21T00:00:00Z','message':{'role':'assistant','content':'ok'},'done':True,'done_reason':'stop','prompt_eval_count':4,'eval_count':1}
                data=json.dumps(body).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        server=HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            provider={'kind':'local','model':'ollama_chat/fixture','base_url':f'http://127.0.0.1:{server.server_port}','max_input_tokens':16384,'max_output_tokens':-1}
            llm=local_llm(Selection('lead-developer','local',provider,ROOT,{},{}))
            llm.completion(messages=[Message(role='user',content=[TextContent(text='test')])])
            wire=next(body for path,body in captured if path=='/api/chat')
            self.assertEqual(wire['options']['num_predict'],-1)
            self.assertEqual(wire['options']['num_ctx'],16384)
        finally:
            server.shutdown();server.server_close();thread.join()
