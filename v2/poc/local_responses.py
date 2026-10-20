"""Explicit loopback Responses namespace compatibility, not a retrieval service.
Same model/provider, same function arguments/results. Only wire names change.
Refuse unsupported tool types and collisions; never invent tool calls or output.
"""
import copy,hashlib,http.server,json,threading,urllib.request,urllib.error
from urllib.parse import urlparse

class ProtocolError(ValueError):pass

def flatten(request):
    data=copy.deepcopy(request);forward={};reverse={};tools=[];used=set()
    for entry in data.get('tools',[]):
        kind=entry.get('type')
        if kind=='function':items=[(None,entry)]
        elif kind=='namespace':items=[(entry['name'],x) for x in entry.get('tools',[])]
        else:raise ProtocolError('Local Responses compatibility requires function tools; unsupported '+str(kind))
        for namespace,item in items:
            if item.get('type')!='function':raise ProtocolError('Unsupported nested tool type')
            name=item['name'];key=(namespace,name)
            flat=name if namespace is None else 'flow_ns_'+hashlib.sha256((namespace+'\0'+name).encode()).hexdigest()[:12]+'_'+name[:35]
            if flat in used or key in forward:raise ProtocolError('Duplicate/colliding callable tool identity')
            used.add(flat);forward[key]=flat;reverse[flat]=key
            tool=copy.deepcopy(item);tool['name']=flat;tools.append(tool)
    data['tools']=tools
    if isinstance(data.get('input'),list):
        for item in data['input']:
            if item.get('type')=='function_call':
                key=(item.get('namespace'),item['name'])
                if key not in forward:raise ProtocolError('History references a tool outside the current catalog')
                item['name']=forward[key];item.pop('namespace',None)
    choice=data.get('tool_choice')
    if isinstance(choice,dict) and choice.get('type')=='function':
        key=(choice.pop('namespace',None),choice['name'])
        if key not in forward:raise ProtocolError('Unknown tool_choice identity')
        choice['name']=forward[key]
    return data,reverse

def restore(value,reverse,original_tools):
    if isinstance(value,list):return [restore(x,reverse,original_tools) for x in value]
    if not isinstance(value,dict):return value
    result={k:restore(v,reverse,original_tools) for k,v in value.items()}
    if result.get('type')=='function_call':
        name=result.get('name')
        if name not in reverse:raise ProtocolError('Provider returned an unregistered function call: '+str(name))
        namespace,leaf=reverse[name];result['name']=leaf
        if namespace is not None:result['namespace']=namespace
    if result.get('object')=='response' and 'tools' in result:result['tools']=original_tools
    return result

class LocalResponsesBridge:
    def __init__(self,upstream,audit=None):
        u=urlparse(upstream)
        if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.username or u.password or u.query or u.fragment:raise ProtocolError('Only credential-free loopback upstreams are allowed')
        self.upstream=upstream.rstrip('/');self.audit=audit;self.records=[]
    def __enter__(self):
        owner=self
        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version='HTTP/1.0'
            def log_message(self,*args):pass
            def do_POST(self):
                started=False
                try:
                    if self.path!='/v1/responses':raise ProtocolError('Only /v1/responses is supported')
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=32*1024*1024:raise ProtocolError('Invalid request size')
                    original=json.loads(self.rfile.read(size));data,mapping=flatten(original)
                    record={'model':data.get('model'),'tool_identities':[{'wire':flat,'namespace':ns,'name':name} for flat,(ns,name) in mapping.items()],'restored_calls':[],'reasoning':data.get('reasoning'),'previous_response_id':bool(data.get('previous_response_id')),'input_summary':[{'type':x.get('type'),'role':x.get('role'),'name':x.get('name'),'namespace':x.get('namespace'),'call_id':x.get('call_id'),'output_chars':len(str(x.get('output','')))} for x in data.get('input',[]) if isinstance(x,dict)]};owner.records.append(record)
                    request=urllib.request.Request(owner.upstream+'/responses',json.dumps(data).encode(),{'Content-Type':'application/json'})
                    with urllib.request.urlopen(request,timeout=180) as response:
                        self.send_response(response.status);ctype=response.headers.get('Content-Type','application/json');self.send_header('Content-Type',ctype);self.send_header('Connection','close');self.end_headers();started=True
                        def convert(obj):
                            result=restore(obj,mapping,original.get('tools',[]))
                            def calls(x):
                                if isinstance(x,dict):
                                    if x.get('type')=='function_call':record['restored_calls'].append({'namespace':x.get('namespace'),'name':x.get('name'),'call_id':x.get('call_id')})
                                    for v in x.values():calls(v)
                                elif isinstance(x,list):
                                    for v in x:calls(v)
                            calls(result);return result
                        if 'text/event-stream' in ctype:
                            for line in response:
                                if line.startswith(b'data: ') and line.strip()!=b'data: [DONE]':line=b'data: '+json.dumps(convert(json.loads(line[6:]))).encode()+b'\n'
                                self.wfile.write(line);self.wfile.flush()
                        else:self.wfile.write(json.dumps(convert(json.load(response))).encode());self.wfile.flush()
                except urllib.error.HTTPError as error:
                    owner.records.append({'upstream_http_status':error.code})
                    if not started:
                        self.send_response(error.code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(error.read())
                except (BrokenPipeError,ConnectionResetError):pass
                except Exception as error:
                    owner.records.append({'error':str(error)})
                    try:
                        if not started:self.send_error(422 if isinstance(error,ProtocolError) else 502,str(error))
                        else:self.close_connection=True
                    except (BrokenPipeError,ConnectionResetError):pass
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.endpoint='http://127.0.0.1:'+str(self.server.server_port)+'/v1';return self
    def __exit__(self,*args):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        if self.audit:self.audit.write_text(json.dumps({'adapter':'responses-namespace-v1','upstream':self.upstream,'records':self.records},indent=2)+'\n')
