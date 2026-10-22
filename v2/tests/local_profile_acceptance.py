"""Disposable coordinator/summon/worker/check/review acceptance; never production state.
Live mode forwards only the selected installed model to local Ollama. Coordinator
responses are deterministic fixtures. Reviewer is either a boundary fixture or an
existing default Claude session with tools disabled; private Flow auth is not changed.
"""
import argparse,hashlib,http.server,json,os,shlex,shutil,subprocess,sys,threading,time,urllib.error,urllib.request
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from poc import implementation_profiles as profiles
from poc.role_renderer import bind_bundle
from poc.artifacts import Artifacts
from poc.contracts import digest_tree
from poc.work_lifecycle import build
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

GOOD='def greet(name):\n    name = name.strip()\n    if not name:\n        raise ValueError("blank name")\n    return "Hello, " + name + "!"\n'
TEST='''import unittest
from greet import greet
class GreetingTests(unittest.TestCase):
 def test_strip(self): self.assertEqual(greet("  Ada  "),"Hello, Ada!")
 def test_inner(self): self.assertEqual(greet("Ada  Lovelace"),"Hello, Ada  Lovelace!")
 def test_blank(self):
  for value in ("", "  ", "\\t\\n"):
   with self.assertRaises(ValueError): greet(value)
if __name__ == '__main__': unittest.main()
'''
TASK='Fix greet(name): strip leading/trailing whitespace, preserve internal whitespace, return Hello, NAME!, and reject empty/whitespace-only names with ValueError. Inspect, edit and run tests in this disposable workspace. Do not alter tests, access other files, change models/providers or send external communications.'

def write(path,value):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2,default=str)+'\n');tmp.replace(path)

def api(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:11434'+path,None if body is None else json.dumps(body).encode(),{'Content-Type':'application/json'})
 return json.load(urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=30))

def run_case(root,model,binary,live=False,native_review=False):
 from poc.goose_artifact import metadata
 permitted={metadata(ROOT)['binary_sha256'],'e07d4c3771351af306117ee4db069c3c09e4588859e55f6606f28cbd23833318'}
 with Path(binary).open('rb') as stream:
  if hashlib.file_digest(stream,'sha256').hexdigest() not in permitted:raise RuntimeError('Acceptance requires a provenance-verified Goose binary')
 root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
 receipt=root/'receipt.json'
 if receipt.exists():raise RuntimeError('Existing acceptance receipt; inspect it before any retry: '+str(receipt))
 record={'state':'preparing','model':model,'live_generation':live,'native_review_requested':native_review,'started':time.time(),'limitations':['Coordinator is a deterministic protocol fixture; this does not qualify a real native coordinator or private Flow reviewer authentication.']};write(receipt,record)
 workspace=root/'workspace';workspace.mkdir();(workspace/'greet.py').write_text('def greet(name):\n    return "Hello, " + name\n');(workspace/'test_greet.py').write_text(TEST)
 command=[sys.executable,'-B','-m','unittest','-v','test_greet.py']
 original_tests=hashlib.sha256((workspace/'test_greet.py').read_bytes()).hexdigest()
 baseline=subprocess.run(command,cwd=workspace,capture_output=True,text=True);write(root/'baseline.json',{'exit':baseline.returncode,'stdout':baseline.stdout,'stderr':baseline.stderr})
 if baseline.returncode==0:raise RuntimeError('Fixture baseline unexpectedly passes')
 wire=root/'wire';wire.mkdir();requests=[];worker_calls=[0];stopped=[];process=[None]
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def json(self,data,status=200):
   raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  def do_GET(self):
   if self.path=='/api/tags':return self.json({'models':[{'name':model,'digest':'a'*64},{'name':'fixture-coordinator'}]})
   return self.json({},403)
  def do_POST(self):
   body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));index=len(requests);requests.append({'path':self.path,'body':body,'time':time.time()});write(wire/f'{index:03d}-request.json',requests[-1])
   selected=body.get('model')
   if selected not in {model,'fixture-coordinator'}:return self.json({'error':'Unapproved fixture model'},403)
   if selected==model and live:
    if self.path not in {'/api/show','/v1/chat/completions'}:return self.json({'error':'Fixture endpoint denied'},403)
    req=urllib.request.Request('http://127.0.0.1:11434'+self.path,json.dumps(body).encode(),{'Content-Type':'application/json'})
    try:
     response=urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=600)
    except urllib.error.HTTPError as error:
     raw=error.read();(wire/f'{index:03d}-response').write_bytes(raw);self.send_response(error.code);self.end_headers();self.wfile.write(raw);return
    self.send_response(response.status);self.send_header('Content-Type',response.headers.get('Content-Type','application/json'));self.end_headers()
    with response,(wire/f'{index:03d}-response').open('wb') as log:
     while True:
      chunk=response.read1(4096)
      if not chunk:break
      log.write(chunk);log.flush();self.wfile.write(chunk);self.wfile.flush()
    return
   if self.path=='/api/show':return self.json({'capabilities':['completion','tools'],'model_info':{}})
   if self.path!='/v1/chat/completions':return self.json({},403)
   functions=[t['function']['name'] for t in body.get('tools',[])];delta={'role':'assistant','content':'Done.'};finish='stop'
   if selected=='fixture-coordinator':
    delegate=next((n for n in functions if n.endswith('__delegate') or n=='delegate'),None)
    if delegate and not any(m.get('role')=='tool' for m in body.get('messages',[])):
     delta={'role':'assistant','tool_calls':[{'index':0,'id':'delegate-fixture','type':'function','function':{'name':delegate,'arguments':json.dumps({'source':'lead-developer'})}}]};finish='tool_calls'
   elif worker_calls[0]==0:
    shell=next((n for n in functions if n.endswith('__shell') or n=='shell'),None)
    if shell is None:
     write(root/'loader-schema.json',body.get('tools',[]));stopped.append('Developer tools unavailable in fixture');return self.json({'error':'fixture developer extension unavailable'},400)
    code='from pathlib import Path; Path("greet.py").write_text('+repr(GOOD)+'); import subprocess; raise SystemExit(subprocess.call(["/usr/bin/python3","-B","-m","unittest","-v","test_greet.py"]))'
    delta={'role':'assistant','tool_calls':[{'index':0,'id':'edit-fixture','type':'function','function':{'name':shell,'arguments':json.dumps({'command':shlex.join(['/usr/bin/python3','-c',code])})}}]};finish='tool_calls';worker_calls[0]+=1
   else:
    final=next(n for n in functions if n.endswith('final_output'));result={'success':True,'summary':'Fixed greeting','verdict':'implemented','findings':[],'verification':['Tests passed'],'limitations':[]}
    delta={'role':'assistant','tool_calls':[{'index':0,'id':'final-fixture','type':'function','function':{'name':final,'arguments':json.dumps(result)}}]};finish='tool_calls'
   chunks=[{'id':'fixture','object':'chat.completion.chunk','created':1,'model':selected,'choices':[{'index':0,'delta':delta,'finish_reason':None}]},{'id':'fixture','object':'chat.completion.chunk','created':1,'model':selected,'choices':[{'index':0,'delta':{},'finish_reason':finish}],'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130}}]
   raw=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode();(wire/f'{index:03d}-response').write_bytes(raw);self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 home=root/'home';user=home/'.flow/user';user.mkdir(parents=True)
 endpoint=f'http://127.0.0.1:{server.server_port}'
 (user/'runtime.toml').write_text(f'[profiles.selected]\nkind="local"\nmodel="ollama_chat/{model}"\nbase_url="{endpoint}"\nmax_input_tokens=32768\nmax_output_tokens=-1\ncondenser_max_tokens=28672\n')
 # Resolve against the actual server in live mode, then freeze the safe test proxy endpoint.
 actual=next(m for m in api('/api/tags')['models'] if m['name']==model) if live else {'digest':'a'*64}
 if actual.get('remote_host') or actual.get('remote_model'):raise RuntimeError('Cloud model alias is not permitted')
 with patch('poc.knowledge.local_model_digest',return_value=actual['digest']):selected=profiles.resolve(workspace,'selected',home)
 if live:
  exact=next(m for m in api('/api/tags')['models'] if m['name']==model)
  selected.pop('sha256');selected['model_digest']=exact['digest'];selected['sha256']=profiles.fingerprint(selected)
 record['profile']=selected;write(receipt,record)
 phases=[];review_evidence={}
 class Harness:
  def implement(self,state):
   phases.append('implementation');bundle=bind_bundle(ROOT/'role-bundle',root/'bound-roles',state['task'],state['project_context'],implementation_profile=selected)
   env={k:v for k,v in os.environ.items() if k in ['LANG','LC_ALL','TERM']};env.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin',HOME=str(home),GOOSE_PATH_ROOT=str(home),GOOSE_DISABLE_KEYRING='1',GOOSE_TELEMETRY_ENABLED='false',GOOSE_MODE='auto',TMPDIR=str(home),GOOSE_RECIPE_PATH=str(bundle/'recipes'),GOOSE_SUBAGENT_MAX_TURNS='12',OLLAMA_TIMEOUT='600',OLLAMA_STREAM_TIMEOUT='600',PYTHONDONTWRITEBYTECODE='1')
   env=profiles.apply_environment(env,selected,'chatgpt_codex','fixture-native-coordinator')
   scope=root/'fixture.sb';scope.write_text('(version 1)\n(allow default)\n(deny file-read* file-write*)\n(allow file-read-metadata)\n(allow file-read* (literal "/") (literal "/private") (literal "/System/Volumes") (literal "/System/Volumes/Preboot"))\n(allow file-read* (subpath "/System") (subpath "/usr") (subpath "/bin") (subpath "/sbin") (subpath "/opt") (subpath "/Library") (subpath "/Applications") (subpath "/dev") (subpath "/private/var/db") (subpath "/private/preboot") (subpath "/private/etc") (literal '+json.dumps(str(Path(binary).resolve()))+'))\n(allow file-read* file-write* (subpath '+json.dumps(str(workspace))+') (subpath '+json.dumps(str(home))+'))\n(allow file-read* (subpath '+json.dumps(str(bundle))+') (literal '+json.dumps(str(root))+'))\n(allow file-write* (literal \"/dev/null\"))\n(deny network*)\n(allow network-outbound (remote tcp "localhost:'+str(server.server_port)+'"))\n')
   cmd=['/usr/bin/sandbox-exec','-f',str(scope),binary,'run','--no-profile','--with-builtin','developer','--with-builtin','summon','--provider','ollama','--model','fixture-coordinator','--text','Delegate the approved task to source lead-developer. Consume its report, then finish. Do not implement the task yourself.','--max-turns','8','--output-format','stream-json']
   with (root/'goose.jsonl').open('w') as stdout,(root/'goose.stderr').open('w') as stderr:
    process[0]=subprocess.Popen(cmd,cwd=workspace,env=env,stdout=stdout,stderr=stderr)
    record.update(state='running',pid=process[0].pid);write(receipt,record)
    deadline=time.monotonic()+600
    while process[0].poll() is None:
     if stopped or time.monotonic()>deadline or shutil.disk_usage(root).free<8*1024**3:
      if not stopped:stopped.append('600-second fixture budget' if time.monotonic()>deadline else '8-GiB disk reserve')
      process[0].terminate();process[0].wait(timeout=15);break
     time.sleep(.5)
   record['goose_exit']=process[0].returncode;record['safeguard']=stopped;write(receipt,record)
   if live and any(m['name']==model for m in api('/api/ps')['models']):
    record['unload_after_implementation']=api('/api/generate',{'model':model,'keep_alive':0});write(receipt,record)
   return {'status':'completed' if process[0].returncode==0 and not stopped else 'blocked','findings':stopped,'test_results':{}}
  def review(self,state):
   phases.append('independent-review');review_evidence['recipe']=json.loads(json.dumps(__import__('yaml').safe_load((ROOT/'role-bundle/recipes/quality-reviewer.yaml').read_text())['settings']))
   if native_review:
    prompt='Independently review this disposable fixture against these requirements. Do not change files or use tools. Return approve or request_changes with reasons. Requirements: '+TASK+'\nCandidate:\n'+(workspace/'greet.py').read_text()+'\nTests:\n'+TEST+'\nIndependent test results:\n'+json.dumps(record.get('independent_check'))
    cmd=['/Users/andyconley/.local/bin/claude','-p',prompt,'--model',review_evidence['recipe']['goose_model'],'--setting-sources','','--disable-slash-commands','--tools','','--no-session-persistence','--output-format','json','--json-schema',json.dumps({'type':'object','properties':{'verdict':{'type':'string','enum':['approve','request_changes']},'reasons':{'type':'array','items':{'type':'string'}}},'required':['verdict','reasons'],'additionalProperties':False}),'--settings','{"disableAllHooks":true,"enabledPlugins":{},"autoMemoryEnabled":false}']
    result=subprocess.run(cmd,cwd=workspace,capture_output=True,text=True,timeout=300)
    (root/'native-review.json').write_text(result.stdout);(root/'native-review.stderr').write_text(result.stderr)
    data=json.loads(result.stdout) if result.stdout else {};answer=data.get('structured_output',{})
    review_evidence.update(mode='existing default Claude session; not Flow private configuration',exit=result.returncode,model_usage=data.get('modelUsage'),answer=answer)
    passed=result.returncode==0 and answer.get('verdict')=='approve'
   else:review_evidence['mode']='deterministic native-review boundary fixture';passed=True
   return {'passed':passed,'candidate':digest_tree(workspace),'findings':[] if passed else ['Native review did not approve; inspect evidence']}
  def reconcile(self,state):raise RuntimeError('No automatic replay of uncertain acceptance effects')
 def check(path):
  phases.append('independent-check')
  if hashlib.sha256((Path(path)/'test_greet.py').read_bytes()).hexdigest()!=original_tests:
   result=subprocess.CompletedProcess(command,-1,'','Acceptance tests changed; candidate refused')
  else:result=subprocess.run(command,cwd=path,capture_output=True,text=True,timeout=60)
  record['independent_check']={'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr};write(receipt,record)
  return {'passed':result.returncode==0,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
 try:
  artifacts=Artifacts(workspace,'acceptance');ctx={'workspace':str(workspace),'instruction_precedence':'Fixture context only; no ancestor files loaded','documents':[],'historical_flow':None,'implementation_profile':selected}
  brief={'goal':TASK,'scope':['greet.py only'],'acceptance_criteria':['All stated greeting requirements and unchanged tests'],'check_command':command,'historical_references':[]}
  initial={'work_id':'acceptance','job_id':'acceptance','workspace':str(workspace),'request':TASK,'brief_ref':artifacts.publish('briefs','brief',brief),'context_ref':artifacts.publish('contexts','project',ctx),'runtime_options':{'implementation_profile':selected},'budget_seconds':600,'max_corrections':0}
  with SqliteSaver.from_conn_string(str(root/'workflow.sqlite')) as saver:
   graph=build(artifacts,Harness(),check).compile(checkpointer=saver);config={'configurable':{'thread_id':'acceptance'},'recursion_limit':100};graph.invoke(initial,config)
   result=graph.invoke(Command(resume={'action':'approve','actor':'authorized-isolated-acceptance','brief_ref':initial['brief_ref']}),config)
  record.update(state='terminal',phase=result.get('phase'),lifecycle_phase=result.get('lifecycle_phase'),outcome=result.get('outcome'),phases=phases,review=review_evidence,tests_unchanged=original_tests==hashlib.sha256((workspace/'test_greet.py').read_bytes()).hexdigest(),request_models=[r['body'].get('model') for r in requests if r['path']=='/v1/chat/completions'],finished=time.time())
  record['accepted']=record.get('phase')=='reviewed-and-ready' and record.get('independent_check',{}).get('exit')==0 and record['tests_unchanged']
  record['generation_requests']=[]
  for index,request in enumerate(requests):
   if request['path']=='/v1/chat/completions' and request['body'].get('model')==model:
    response=(wire/f'{index:03d}-response').read_text(errors='replace') if (wire/f'{index:03d}-response').exists() else ''
    chunks=[]
    for line in response.splitlines():
     if line.startswith('data: ') and line!='data: [DONE]':
      try:chunks.append(json.loads(line[6:]))
      except ValueError:pass
    record['generation_requests'].append({'wire_index':index,'output_cap_fields':{k:request['body'][k] for k in ['max_tokens','max_completion_tokens'] if k in request['body']},'options':request['body'].get('options'),'finish_reasons':[c.get('finish_reason') for chunk in chunks for c in chunk.get('choices',[]) if c.get('finish_reason')], 'usage':[chunk['usage'] for chunk in chunks if chunk.get('usage')]})
 except BaseException as error:
  if process[0] is not None and process[0].poll() is None:
   process[0].terminate();process[0].wait(timeout=15)
  record.update(state='failed',error=f'{type(error).__name__}: {error}',phases=phases);write(receipt,record);raise
 finally:
  server.shutdown();server.server_close();thread.join()
  if live:
   loaded=api('/api/ps')['models'];record['loaded_before_unload']=[m['name'] for m in loaded]
   if any(m['name']==model for m in loaded):record['unload']=api('/api/generate',{'model':model,'keep_alive':0})
   record['loaded_after_unload']=api('/api/ps')['models']
  write(receipt,record)
 return record

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--root',required=True,type=Path);parser.add_argument('--model',required=True);parser.add_argument('--binary',required=True);parser.add_argument('--live',action='store_true');parser.add_argument('--native-review',action='store_true');a=parser.parse_args()
 if a.live:
  if api('/api/ps')['models']:raise SystemExit('Existing loaded model; inspect before acceptance')
  if shutil.disk_usage(a.root.parent).free<8*1024**3:raise SystemExit('Insufficient 8-GiB disk reserve')
 print(json.dumps(run_case(a.root,a.model,a.binary,a.live,a.native_review),indent=2))
