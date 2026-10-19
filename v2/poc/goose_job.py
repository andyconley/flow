"""One job boundary, never dispatch individual workers. External intents reconcile first."""
import json,os,signal,subprocess,time,hashlib,sys
from pathlib import Path
from .runtime_env import ROOT,environment,scoped,goose_binary
from .evidence import final_object,delegations,native_sessions
from .contracts import task_input_digest
from .lifecycle import ProcessScope
from .native_errors import boundary_error

def store(path,data):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(path)

class GooseJob:
 def __init__(self,model='llama3.1:8b',timeout=1200,provider='ollama',native_boundary=False,role_bundle=None):self.role_bundle=Path(role_bundle).resolve() if role_bundle else ROOT/'role-bundle';self.model=model;self.timeout=timeout;self.provider=provider;self.native_boundary=native_boundary
 def _run(self,s,kind,prompt,provider_override=None):
  provider=provider_override or self.provider
  if s['inputs']!=task_input_digest(s['task'],s['workspace'],s.get('project_context','')):return {'status':'scope_required' if self.role_bundle else 'blocked','reason':'approved task/check inputs changed'}
  budget=min(self.timeout,max(0,s['deadline']-time.time())) if self.role_bundle and s.get('deadline') is not None else self.timeout
  if budget<=0:return {'status':'blocked','reason':'Approved workflow time budget exhausted; no execution submitted'}
  index=f"{s.get('corrections',0)+1}-{s.get('resume_epoch',0)}" if self.role_bundle else s.get('attempt',0)+1; p=ROOT/'artifacts'/s['job_id']/f'{kind}-{index}.json';p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists():
   prior=json.loads(p.read_text())
   if prior['inputs']!=s['inputs']:return {'status':'blocked','reason':'input identity changed'}
   if prior['status'] in {'completed','permission_required','scope_required'}:return prior
   return self.reconcile_record(p)
  record={'output':str(p.with_suffix('.jsonl')),'stderr':str(p.with_suffix('.stderr')),'status':'uncertain','inputs':s['inputs'],'workspace':s['workspace'],'started':time.time(),'kind':kind}
  store(p,record) # Before submit: crash here is explicitly uncertain, never silently resubmitted.
  instructions=ROOT/'runtime'/f'{s["job_id"]}-{kind}-{index}.md';instructions.write_text(prompt)
  output=p.with_suffix('.jsonl');err=p.with_suffix('.stderr')
  cmd=scoped([str(goose_binary()),'run','--no-profile','--with-builtin','developer','--with-builtin','summon','--provider',provider,'--model',self.model,'--max-turns','25','--max-tool-repetitions','3','--output-format','stream-json','--name',f'{s["job_id"]}-{kind}-{index}','--instructions',str(instructions)])
  env=environment(project=s['workspace'],provider=provider,model=self.model);env['GOOSE_PROVIDER']=provider;env['GOOSE_MODEL']=self.model
  if self.role_bundle:
   from .native_runtime import prepare
   profile, native_env = prepare(Path(s['workspace']), p.parent, self.role_bundle,provider=provider,model=self.model)
   cmd=cmd[3:];cmd[0]=str(goose_binary())
   position=cmd.index('developer');del cmd[position-1:position+1]
   env=native_env;env['GOOSE_PROVIDER']=provider;env['GOOSE_MODEL']=self.model;env['GOOSE_RECIPE_PATH']=str(self.role_bundle/'recipes');env['GOOSE_NATIVE_ACP_COMPLETION']='true'
   cmd[cmd.index('--max-turns')+1]='8'
  from .device_context import settings
  record['context_configuration']=settings(s['workspace'],self.model)
  record['context_configuration']['context_tokens']=int(env['GOOSE_INPUT_LIMIT']) if env.get('GOOSE_INPUT_LIMIT') else None
  record['context_configuration']['application_basis']='captured launch environment; Goose Ollama maps GOOSE_INPUT_LIMIT to num_ctx'
  store(p,record)
  with output.open('w') as out,err.open('w') as errors:
   child=subprocess.Popen(cmd,cwd=s['workspace'],env=env,stdout=out,stderr=errors,start_new_session=True)
   scope=ProcessScope(child.pid)
   record.update(pid=child.pid,execution_scope=child.pid,processes=scope.known,supervisor_pid=os.getpid());store(p,record)
   deadline=time.monotonic()+budget
   next_observation=time.monotonic()
   while child.poll() is None:
    scope.observe();record['processes']=scope.known;store(p,record)
    if time.monotonic()>deadline:
     stopped=scope.stop();child.wait(timeout=5)
     record.update(status='blocked',reason='timeout; do not resubmit without reconciliation',stop=stopped);self._observe(record,s,kind,index);store(p,record);return record
    if time.monotonic()>=next_observation:
     self._observe(record,s,kind,index);store(p,record);next_observation=time.monotonic()+5
    time.sleep(.25)
   code=child.returncode
  deadline=time.monotonic()+2
  while scope.observe() and time.monotonic()<deadline:time.sleep(.1)
  alive=scope.observe()
  boundary=boundary_error(output.read_text()+'\n'+err.read_text()) if self.role_bundle else None
  if boundary:
   stopped=scope.stop() if alive else None
   record.update(status=boundary['kind'],native_error=boundary,reason=boundary['error'].get('message','Explicit native permission/scope boundary'),exit=code,quiescent=not scope.observe(),stop=stopped,finished=time.time())
   self._observe(record,s,kind,index);store(p,record);return record
  record.update(status='completed' if code==0 and not alive else 'blocked',exit=code,quiescent=not alive,processes=scope.known,alive=list(alive),output=str(output),stderr=str(err),finished=time.time())
  self._observe(record,s,kind,index);store(p,record);return record
 def _observe(self,record,s,kind,index):
  from .monitoring import attach,context_for_usage
  attach(record,s['workspace'],f'{s["job_id"]}-{kind}-{index}')
  try:
   context=context_for_usage(s['workspace'],record['usage'],self.model,record.get('context_configuration'));record['context_monitoring']=context
   warned=set(record.get('context_warning_sessions',[]))
   for observation in context['observations']:
    if observation['warning'] and observation['session_id'] not in warned:
     print(f"Flow context observation: {observation['session_id']} last reported request {observation['last_reported_request_percent']:.1f}% of configured local window. {observation['warning']}",file=sys.stderr)
     warned.add(observation['session_id'])
   record['context_warning_sessions']=sorted(warned)
  except Exception as error:
   record['context_monitoring']={'available':False,'reason':str(error),'informational_only':True}
 def reconcile_record(self,p):
  r=json.loads(p.read_text())
  if r.get('status')=='completed':return r
  if r.get('processes'):
   scope=ProcessScope.__new__(ProcessScope);scope.root=r['pid'];scope.known={int(k):v for k,v in r['processes'].items()}
   alive=scope.observe()
   if alive:return {**r,'status':'blocked','reason':'observed execution processes still live','alive':list(alive)}
   from .evidence import events
   stream=list(events(r['output'])) if Path(r.get('output','')).is_file() else []
   if any(e.get('type')=='complete' for e in stream) and not any(e.get('type')=='error' for e in stream):
    return {**r,'status':'completed','reconciled':True,'exit':None,'quiescent':True,'reason':'observed processes absent; complete stream recovered; graph must recheck candidate'}
   reason='observed scope absent; no complete outcome; effects need explicit snapshot reconciliation'
  elif r.get('execution_scope'):
   reason='legacy group-only record cannot establish descendant quiescence'
  else:reason='submission may or may not have happened; reconcile before new attempt'
  return {**r,'status':'blocked','reason':reason}
 def reconcile(self,s):
  paths=sorted((ROOT/'artifacts'/s['job_id']).glob(f"{s.get('pending_kind','implement')}-*.json"))
  return self.reconcile_record(paths[-1]) if paths else {'status':'blocked','reason':'missing attempt record'}
 def implement(self,s):return self._role_operation(s,'implement')
 def review(self,s):return self._role_operation(s,'review')

 def _role_operation(self,s,kind):
  roles=[p.stem for p in (self.role_bundle/'recipes').glob('*.yaml')]
  prompt=f"""You are Goose's implementation coordinator. Use the converted role recipes available through summon; select appropriate roles and configured providers yourself. Available roles: {', '.join(sorted(roles))}.
Approved task: {s['task']}
Workspace: {s['workspace']}
Project context: {s.get('project_context','')}
Operation: {kind}. {'Delegate actual implementation, normally using lead-developer, and consume its result.' if kind=='implement' else 'Delegate quality-reviewer in a FRESH session to inspect the actual candidate and independently run tests. Do not silently fix the candidate.'}
Pass task and project_context as recipe parameters. Both roles have normal broad development tools under the same workspace permissions. No role-specific tool restrictions. No nested coordinators or background work. Use existing signed-in providers; no new login, API billing fallback or global settings changes. Existing credential and external-action approvals apply. Stop and report actual scope/permission blockers immediately; do not reinterpret them as correction work.
Previous findings: {json.dumps(s.get('findings',[]))}
Previous test results: {json.dumps(s.get('test_results',{}))}
Candidate revision: {s.get('candidate','not yet checked')}
Return only JSON with outcome, findings (array) and test_results (object). Outcomes: completed or correction for implementation; approve or request_changes for review; permission_required, scope_required or blocked for either. For review include candidate_revision exactly as supplied. Preserve actual failures and limitations in findings. Final acceptance belongs to the task graph. Parent 8 turns, children at most 4 Goose turns, no merge or deployment."""
  try:result=self._run(s,kind,prompt)
  except PermissionError as error:result={'status':'permission_required','reason':str(error)}
  if result['status']!='completed':
   return result if kind=='implement' else {'outcome':result['status'],'blocked':True,'passed':False,'candidate':s.get('candidate'),'runtime':result,'reason':result.get('reason','Native review did not complete')}
  value=final_object(result['output'])
  outcome=value.get('outcome')
  if outcome not in {'completed','correction','approve','request_changes','permission_required','scope_required','blocked'} or not isinstance(value.get('findings'),list) or not isinstance(value.get('test_results'),dict):
   value={'outcome':'blocked','findings':['Coordinator did not return the required task result.'],'test_results':{}}
  payload={'outcome':value['outcome'],'findings':value['findings'],'test_results':value['test_results'],'runtime':result}
  if kind=='implement':return {**payload,'status':value['outcome']}
  # Preserve the actual reported revision, including the common structured
  # test-results location. Never substitute the expected candidate if absent.
  revision=value.get('candidate_revision',value.get('test_results',{}).get('candidate_revision'))
  return {**payload,'passed':value['outcome']=='approve','blocked':value['outcome']=='blocked','candidate':revision}
