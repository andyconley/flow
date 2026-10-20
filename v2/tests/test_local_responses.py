import copy,unittest
from poc.local_responses import flatten,restore,ProtocolError
class NamespaceProtocolTests(unittest.TestCase):
 def request(self):
  return {'model':'local-model','tools':[{'type':'namespace','name':'mcp__python','tools':[{'type':'function','name':'search_cards','parameters':{'type':'object','properties':{'query':{'type':'string'}}}},{'type':'function','name':'traverse_cards','parameters':{'type':'object'}}]},{'type':'function','name':'exec_command','parameters':{'type':'object'}}],'input':[]}
 def test_roundtrip_keeps_namespace_schema_arguments_and_call_identity(self):
  req=self.request();before=copy.deepcopy(req);flat,mapping=flatten(req);self.assertEqual(req,before)
  self.assertTrue(all(t['type']=='function' for t in flat['tools']));wire=flat['tools'][0]['name']
  call={'type':'function_call','name':wire,'call_id':'unique-call','arguments':'{"query":"literal evidence"}'}
  restored=restore({'type':'response.output_item.done','item':call},mapping,req['tools'])['item']
  self.assertEqual('mcp__python',restored['namespace']);self.assertEqual('search_cards',restored['name']);self.assertEqual(call['arguments'],restored['arguments']);self.assertEqual('unique-call',restored['call_id'])
  req['input']=[restored,{'type':'function_call_output','call_id':'unique-call','output':'actual MCP result'}];history,_=flatten(req)
  self.assertEqual(wire,history['input'][0]['name']);self.assertNotIn('namespace',history['input'][0]);self.assertEqual('actual MCP result',history['input'][1]['output'])
 def test_rejects_unsupported_tools_unknown_calls_and_duplicates(self):
  for tool in [{'type':'web_search'},{'type':'namespace','name':'x','tools':[{'type':'custom','name':'x'}]}]:
   with self.assertRaises(ProtocolError):flatten({'tools':[tool]})
  req=self.request();req['tools'].append(req['tools'][0])
  with self.assertRaises(ProtocolError):flatten(req)
  with self.assertRaises(ProtocolError):restore({'type':'function_call','name':'invented'}, {}, [])
 def test_same_leaf_in_distinct_namespaces_has_distinct_reversible_names(self):
  req=self.request();req['tools'].append({'type':'namespace','name':'another','tools':[{'type':'function','name':'search_cards'}]});flat,mapping=flatten(req)
  self.assertNotEqual(flat['tools'][0]['name'],flat['tools'][-1]['name']);self.assertEqual(4,len(mapping))

class TransportConfigurationTests(unittest.TestCase):
 def test_explicit_transport_toggle_is_backed_up_and_does_not_reindex_notes(self):
  import tempfile,json,contextlib,io
  from pathlib import Path
  from poc import knowledge as k
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'notes').mkdir();(root/'notes/a.md').write_text('Preserved authored note.\n');k.write(root/'settings.json',{})
   before=k.fingerprint(root)
   with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,k.main(['--home',str(root),'namespace-compat','on']))
   self.assertTrue(k.read(root/'native-transport.json')['namespace_compat']);self.assertEqual(before,k.fingerprint(root));self.assertTrue(list((root/'backups').glob('*.zip')))
   with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(0,k.main(['--home',str(root),'namespace-compat','off']))
   self.assertFalse(k.read(root/'native-transport.json')['namespace_compat']);self.assertEqual('Preserved authored note.\n',(root/'notes/a.md').read_text())

class LocalHttpProtocolTests(unittest.TestCase):
 @unittest.skipUnless(__import__('os').environ.get('FLOW_TEST_LOCAL_HTTP')=='1','explicit loopback HTTP fixture')
 def test_sse_mapping_and_upstream_error_status(self):
  import http.server,json,threading,urllib.request,urllib.error
  from poc.local_responses import LocalResponsesBridge
  observed=[]
  class Upstream(http.server.BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));observed.append(data)
    if data['model']=='fail':
     self.send_response(400);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"error":{"message":"fixture original error"}}');return
    name=data['tools'][0]['name'];call={'type':'function_call','name':name,'call_id':'preserved-id','arguments':'{"query":"literal evidence"}'}
    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.end_headers()
    for event in [{'type':'response.output_item.done','item':call},{'type':'response.completed','response':{'object':'response','output':[call],'tools':data['tools']}}]:self.wfile.write(b'data: '+json.dumps(event).encode()+b'\n\n')
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Upstream);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with LocalResponsesBridge('http://127.0.0.1:'+str(server.server_port)+'/v1') as bridge:
    req={'model':'fixture','stream':True,'input':[],'tools':[{'type':'namespace','name':'mcp__real','tools':[{'type':'function','name':'search_cards','parameters':{'type':'object'}}]}]}
    def send(data):return urllib.request.urlopen(urllib.request.Request(bridge.endpoint+'/responses',json.dumps(data).encode(),{'Content-Type':'application/json'}),timeout=5)
    with send(req) as response:events=[json.loads(line[6:]) for line in response if line.startswith(b'data: ')]
    self.assertEqual('function',observed[0]['tools'][0]['type']);self.assertEqual('mcp__real',events[0]['item']['namespace']);self.assertEqual('search_cards',events[0]['item']['name']);self.assertEqual('preserved-id',events[0]['item']['call_id']);self.assertEqual(req['tools'],events[1]['response']['tools'])
    req['model']='fail'
    with self.assertRaises(urllib.error.HTTPError) as error:send(req)
    self.assertEqual(400,error.exception.code);self.assertIn('fixture original error',error.exception.read().decode())
  finally:server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
