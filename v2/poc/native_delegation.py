"""Operator-owned MCP capability for a single approved local implementation.

ACP providers forward stdio MCP servers, not Goose's built-in summon tools.
The operator retains the same delegate authority as its existing Summon path.
Only the frozen task/profile may execute; no caller-selected shell, path, recipe,
endpoint, provider or prompt is accepted. Native sandbox rules are unchanged.
"""
import json,os,shutil,socket,socketserver,subprocess,tempfile,threading,time
from pathlib import Path
from .contracts import digest_tree
from .implementation_profiles import validate,apply_environment
from .lifecycle import ProcessScope

TOOLS=[{'name':'delegate_implementation','description':'Start the ONE approved implementation with its frozen local worker. No arguments or task/provider overrides. If running, use delegation_status until terminal; never implement it yourself.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}},
       {'name':'delegation_status','description':'Wait up to 15 seconds and return the approved worker status/result. Repeat while running. Does not start another worker.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}]

class Delegation:
    def __init__(self,state,profile,bundle,env,binary,evidence,operation='implement'):
        validate(profile)
        if operation not in {'implement','review'}:raise ValueError('Invalid bound operation')
        if operation=='implement' and profile['provider']!='ollama':raise ValueError('Implementation requires frozen local worker')
        if operation=='review' and profile['provider']!='claude-acp':raise ValueError('Review requires fixed private Claude role')
        self.operation=operation;self.tool='delegate_implementation' if operation=='implement' else 'delegate_review'
        self.state=dict(state);self.profile=dict(profile);self.bundle=Path(bundle);self.env=dict(env);self.binary=str(binary)
        self.evidence=Path(evidence);self.evidence.mkdir(exist_ok=True)
        self.lock=threading.Lock();self.done=threading.Event();self.stop_requested=threading.Event();self.worker=None;self.scope=None
        self.result={'state':'not_started','model':profile['model'],'model_digest':profile.get('model_digest'),'operation':operation,'task_inputs':state.get('inputs'),'workspace':state.get('workspace')}
        for prior in self.evidence.parent.glob('delegation-*/delegation.json'):
            old=json.loads(prior.read_text())
            if old.get('state')=='running':raise RuntimeError('Unreconciled prior delegation; inspect '+str(prior))
        self.directory=Path(tempfile.mkdtemp(prefix='flow-delegate-'));self.socket=self.directory/'mcp.sock'
        owner=self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                for line in self.rfile:
                    request=json.loads(line)
                    if 'id' not in request:continue
                    try:reply={'jsonrpc':'2.0','id':request['id'],'result':owner.rpc(request)}
                    except Exception as error:reply={'jsonrpc':'2.0','id':request['id'],'error':{'code':-32602,'message':str(error)}}
                    self.wfile.write((json.dumps(reply)+'\n').encode());self.wfile.flush()
        class Server(socketserver.ThreadingUnixStreamServer):
            daemon_threads=True
        self.server=Server(str(self.socket),Handler);self.socket.chmod(0o600)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.save()
    def save(self):
        # Evidence is owned by the operator, never by the native MCP caller.
        target=self.evidence/'delegation.json';temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.result,indent=2)+'\n');temporary.replace(target)
    def rpc(self,request):
        method=request.get('method')
        if method=='initialize':return {'protocolVersion':request.get('params',{}).get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'Flow approved implementation','version':'1'}}
        if method=='ping':return {}
        if method=='tools/list':
            tools=[dict(TOOLS[0]),dict(TOOLS[1])];tools[0].update(name=self.tool,description='Start the ONE frozen '+self.operation+' role; no arguments or overrides. Poll delegation_status while running. Never perform this role yourself.')
            return {'tools':tools}
        if method!='tools/call':raise ValueError('Unsupported MCP method')
        args=request.get('params',{});name=args.get('name')
        if args.get('arguments',{}):raise ValueError('Frozen delegation accepts no arguments or overrides')
        if name==self.tool:
            with self.lock:
                if self.result['state']=='not_started':
                    self.result.update(state='running',started=time.time());self.save()
                    self.worker=threading.Thread(target=self.run,daemon=True);self.worker.start()
        elif name=='delegation_status':
            if self.result['state']=='running':self.done.wait(15)
        else:raise ValueError('Unknown bound tool')
        with self.lock:result=dict(self.result)
        return {'content':[{'type':'text','text':json.dumps(result)}],'isError':result['state']=='failed'}
    def run(self):
        from .runtime_env import environment
        from .knowledge import local_model_digest
        try:
            if self.stop_requested.is_set():raise RuntimeError('Operator cancelled before worker start')
            if self.operation=='implement' and local_model_digest(self.profile['endpoint'],self.profile['model'])!=self.profile['model_digest']:raise ValueError('Approved worker digest changed')
            workspace=Path(self.state['workspace']);before=digest_tree(workspace)
            if self.operation=='implement':
                worker_env=apply_environment(environment(workspace,'ollama',self.profile['model']),self.profile,'ollama',self.profile['model'])
                worker_env['HOME']=str(self.evidence/'home');Path(worker_env['HOME']).mkdir(exist_ok=True)
                recipe=self.bundle/'recipes/lead-developer.yaml'
            else:
                worker_env=dict(self.env);recipe=self.bundle/'recipes/quality-reviewer.yaml'
                worker_env['GOOSE_NATIVE_ACP_COMPLETION']='true'
            worker_env['GOOSE_PROVIDER']=self.profile['provider'];worker_env['GOOSE_MODEL']=self.profile['model']
            worker_env['GOOSE_PATH_ROOT']=str(self.evidence/'goose');worker_env['GOOSE_DISABLE_KEYRING']='1';worker_env['PYTHONPATH']=self.env.get('PYTHONPATH','');worker_env['PATH']=self.env['PATH']
            import yaml
            role=yaml.safe_load(recipe.read_text())
            prompt=role['instructions']+'\nPerform only the approved '+self.operation+' role in this disposable workspace. Preserve frozen tests; no publication or global changes. Report honestly.\n'+self.state['task']
            if self.operation=='review':prompt+='\nCandidate: '+str(self.state.get('candidate'))+'\nIndependent checks: '+json.dumps(self.state.get('test_results',{}))+'\nInspect/test the actual candidate independently. Do not edit or fix it.'
            prompt+='\nReturn only JSON matching this schema: '+json.dumps(role['response']['json_schema'])
            command=[self.binary,'run','--no-profile','--recipe',str(recipe),'--provider',self.profile['provider'],'--model',self.profile['model'],'--text',prompt,'--output-format','stream-json','--name','flow-bound-'+self.operation]
            remaining=max(0,self.state.get('deadline',time.time()+600)-time.time())
            if remaining<=0:raise RuntimeError('Approved execution budget exhausted before delegation')
            with (self.evidence/'worker.jsonl').open('w') as out,(self.evidence/'worker.stderr').open('w') as err:
                child=subprocess.Popen(command,cwd=workspace,env=worker_env,stdout=out,stderr=err,start_new_session=True)
                self.scope=ProcessScope(child.pid)
                with self.lock:self.result.update(pid=child.pid,processes=self.scope.known);self.save()
                try:
                    while child.poll() is None:
                        if self.stop_requested.is_set() or time.time()>self.state.get('deadline',time.time()+remaining):
                            self.scope.stop();child.wait(timeout=10);raise RuntimeError('Operator cancellation or approved deadline stopped worker')
                        time.sleep(.1)
                finally:
                    if self.scope.observe():self.scope.stop()
            result={'state':'completed' if child.returncode==0 else 'failed','exit':child.returncode,'before':before,'candidate':digest_tree(workspace),'output':str(self.evidence/'worker.jsonl'),'model':self.profile['model'],'model_digest':self.profile.get('model_digest'),'finished':time.time()}
            from .goose_job import final_object
            if child.returncode==0:result['report']=final_object(self.evidence/'worker.jsonl')
            if self.operation=='review' and result['candidate']!=before:raise RuntimeError('Independent reviewer changed candidate; refuse acceptance')
        except Exception as error:result={'state':'failed','reason':str(error),'model':self.profile['model'],'finished':time.time()}
        with self.lock:self.result.update(result);self.save()
        self.done.set()
    def close(self):
        self.stop_requested.set()
        if self.worker:self.worker.join(timeout=12)
        if self.scope and self.scope.observe():self.scope.stop()
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        shutil.rmtree(self.directory)
