"""One job boundary, never dispatch individual workers. External intents reconcile first."""
import json,os,signal,subprocess,time,hashlib,sys
from pathlib import Path
from .runtime_env import ROOT,environment,scoped,goose_binary,WORKER_MAX_TURNS
from .evidence import final_object,delegations,native_sessions
from .contracts import task_input_digest
from .lifecycle import ProcessScope
from .native_errors import boundary_error

def store(path,data):
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2));tmp.replace(path)

class GooseJob:
 def __init__(self,model='llama3.1:8b',timeout=1200,provider='ollama',native_boundary=False,role_bundle=None,namespace_compat=None,implementation_profile=None):self.implementation_profile=implementation_profile;self.role_bundle=Path(role_bundle).resolve() if role_bundle else ROOT/'role-bundle';self.model=model;self.timeout=timeout;self.provider=provider;self.native_boundary=native_boundary;self.namespace_compat=namespace_compat
 def _run(self,s,kind,prompt,provider_override=None):
  from .knowledge import home as knowledge_home,read
  enabled=self.namespace_compat if self.namespace_compat is not None else read(knowledge_home()/'native-transport.json',{}).get('namespace_compat',False)
  if not enabled or (provider_override or self.provider)!='codex-acp':return self._run_impl(s,kind,prompt,provider_override)
  from .native_runtime import local_codex_provider
  from .local_responses import LocalResponsesBridge
  info=local_codex_provider()
  if not info:return {'status':'blocked','submitted':False,'source':'namespace_compat','reason':'Explicit namespace adapter requires a credential-free loopback Codex provider'}
  folder=ROOT/'artifacts'/s['job_id'];folder.mkdir(parents=True,exist_ok=True)
  index=f"{s.get('corrections',0)+1}-{s.get('resume_epoch',0)}" if self.role_bundle else s.get('attempt',0)+1
  if (folder/f'{kind}-{index}.json').exists():return self._run_impl(s,kind,prompt,provider_override)
  audit=folder/'wire'/(kind+'-'+str(index)+'-'+str(time.time_ns())+'.json');audit.parent.mkdir(exist_ok=True)
  with LocalResponsesBridge(info[1],audit) as bridge:
   return self._run_impl(s,kind,prompt,provider_override,namespace_endpoint=bridge.endpoint,namespace_audit=str(audit))
 def _run_impl(self,s,kind,prompt,provider_override=None,namespace_endpoint=None,namespace_audit=None):
  provider=provider_override or self.provider
  from .implementation_profiles import validate as validate_profile
  try:validate_profile(self.implementation_profile)
  except ValueError as error:return {'status':'scope_required','submitted':False,'reason':str(error)}
  if kind in {'implement','review'} and self.implementation_profile and s.get('implementation_profile_digest')!=self.implementation_profile['sha256']:
   return {'status':'scope_required','submitted':False,'reason':'Implementation profile differs from approved work configuration'}
  if s['inputs']!=task_input_digest(s['task'],s['workspace'],s.get('project_context','')):return {'status':'scope_required' if self.role_bundle else 'blocked','reason':'approved task/check inputs changed'}
  budget=min(self.timeout,max(0,s['deadline']-time.time())) if self.role_bundle and s.get('deadline') is not None else self.timeout
  if budget<=0:return {'status':'blocked','reason':'Approved workflow time budget exhausted; no execution submitted'}
  index=f"{s.get('corrections',0)+1}-{s.get('resume_epoch',0)}" if self.role_bundle else s.get('attempt',0)+1; p=ROOT/'artifacts'/s['job_id']/f'{kind}-{index}.json';p.parent.mkdir(parents=True,exist_ok=True)
  if p.exists():
   prior=json.loads(p.read_text())
   if prior['inputs']!=s['inputs']:return {'status':'blocked','reason':'input identity changed'}
   if prior['status'] in {'completed','permission_required','scope_required'}:return prior
   return self.reconcile_record(p)
  from .knowledge_tools import require_ready,KnowledgeUnavailable
  try:require_ready()
  except KnowledgeUnavailable as error:return {'status':'blocked','reason':str(error),'source':'knowledge_preflight','submitted':False}
  from .project_python import select
  try:python = select(s['workspace'], s.get('check_command'))
  except ValueError as error:return {'status':'scope_required','reason':str(error)}
  record={'output':str(p.with_suffix('.jsonl')),'stderr':str(p.with_suffix('.stderr')),'status':'uncertain','inputs':s['inputs'],'workspace':s['workspace'],'started':time.time(),'kind':kind}
  if kind=='implement' and self.implementation_profile:record['implementation_profile']=self.implementation_profile
  if namespace_audit:record['namespace_wire_audit']=namespace_audit
  # Publish the uncertain native intent only after readiness checks succeed.
  instructions=ROOT/'runtime'/f'{s["job_id"]}-{kind}-{index}.md';instructions.write_text(prompt)
  output=p.with_suffix('.jsonl');err=p.with_suffix('.stderr')
  cmd=scoped([str(goose_binary()),'run','--no-profile','--with-builtin','developer','--with-builtin','summon','--provider',provider,'--model',self.model,'--max-turns','25','--max-tool-repetitions','3','--output-format','stream-json','--name',f'{s["job_id"]}-{kind}-{index}','--instructions',str(instructions)])
  env=environment(project=s['workspace'],provider=provider,model=self.model);env['GOOSE_PROVIDER']=provider;env['GOOSE_MODEL']=self.model
  if self.role_bundle:
   from .native_runtime import prepare
   from .role_renderer import bind_bundle
   selected=self.implementation_profile if kind=='implement' else None
   role_bundle = bind_bundle(self.role_bundle, p.parent/f'{kind}-{index}-roles-{time.time_ns()}',
                             s['task']+'\nOperation: '+kind+'\nCandidate revision: '+str(s.get('candidate','not yet checked')),
                             s.get('project_context',''),implementation_profile=selected)
   options={'provider':provider,'model':self.model,'check_command':s.get('check_command')}
   if selected:options['implementation_profile']=selected
   if namespace_endpoint:options['namespace_endpoint']=namespace_endpoint
   from .provider_preflight import check as provider_check,PreflightError
   try:
    profile, native_env = prepare(Path(s['workspace']), p.parent, role_bundle,**options)
    record['provider_preflight']=provider_check(role_bundle,provider,self.model,profile,native_env,s.get('deadline'),workspace=s['workspace'])
   except PreflightError as error:
    return {'status':error.status,'reason':str(error),'source':'provider_preflight','submitted':False}
   except (OSError,ValueError,KeyError) as error:
    return {'status':'scope_required','reason':'Provider readiness configuration needs attention: '+str(error),'source':'provider_preflight','submitted':False}
   record['native_evidence_directory'] = native_env.get('FLOW_V2_ACP_EVIDENCE_DIR')
   record['native_client_error_file'] = native_env.get('FLOW_V2_CLIENT_ERROR_FILE')
   record['project_python'] = str(python) if python else None
   cmd=cmd[3:];cmd[0]=str(goose_binary())
   # Summon inherits session extensions, not recipe.extensions. Local workers
   # need the developer extension retained on their parent session.
   if not selected or selected['provider']!='ollama':
    position=cmd.index('developer');del cmd[position-1:position+1]
   env=native_env;env['GOOSE_PROVIDER']=provider;env['GOOSE_MODEL']=self.model;env['GOOSE_RECIPE_PATH']=str(role_bundle/'recipes');env['GOOSE_NATIVE_ACP_COMPLETION']='true'
   env['FLOW_V2_ROLE_SOURCES']=json.dumps(sorted(path.stem for path in (role_bundle/'recipes').glob('*.yaml')))
   cmd[cmd.index('--max-turns')+1]='8'
  if s.get('response_schema'):
   native_contract='\n\nFINAL response: exactly one JSON document matching this schema; no prose, headings or Markdown fences. '+('Do not call final_output; it is not a native tool. ' if provider.endswith('-acp') else '')+'Schema: '+json.dumps(s['response_schema'],sort_keys=True)
   contract={'version':'1.0.0','title':'Flow '+kind+' contract','description':'Managed task output contract','instructions':prompt,'prompt':prompt+native_contract,'response':{'json_schema':s['response_schema']}}
   contract_path=p.parent/'contracts'/(kind+'-'+str(index)+'.json');contract_path.parent.mkdir(parents=True,exist_ok=True);store(contract_path,contract)
   if provider.endswith('-acp'):
    # Native ACP consumes the user prompt; Goose-only system/recipe context is insufficient.
    instructions.write_text(prompt+native_contract)
   else:
    at=cmd.index('--instructions');del cmd[at:at+2]
    cmd+=['--recipe',str(contract_path)]
  from .knowledge_tools import attach
  if self.role_bundle:cmd,env=attach(cmd,env)
  from .device_context import settings
  record['context_configuration']=settings(s['workspace'],self.model)
  record['context_configuration']['context_tokens']=int(env['GOOSE_INPUT_LIMIT']) if env.get('GOOSE_INPUT_LIMIT') else None
  record['context_configuration']['application_basis']='captured launch environment; Goose Ollama maps GOOSE_INPUT_LIMIT to num_ctx'
  if self.role_bundle and s.get('deadline') is not None:
   budget=min(budget,max(0,s['deadline']-time.time()))
   if budget<=0:return {'status':'blocked','reason':'Approved workflow time budget exhausted during preflight; no execution submitted','submitted':False}
  store(p,record) # Native invocation intent; a crash now requires reconciliation.
  with output.open('w') as out,err.open('w') as errors:
   child=subprocess.Popen(cmd,cwd=s['workspace'],env=env,stdout=out,stderr=errors,start_new_session=True)
   record.update(pid=child.pid,execution_scope=child.pid,processes={},supervisor_pid=os.getpid());store(p,record)
   try:scope=ProcessScope(child.pid)
   except PermissionError as error:
    # Record identity before observation, and stop the owned initial process group.
    # Detached descendants remain uncertain without process visibility; never retry.
    try:os.killpg(child.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:
     os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
    record.update(status='permission_required',reason=str(error),exit=child.returncode,scope_uncertain=True)
    store(p,record);return record
   record['processes']=scope.known;store(p,record)
   deadline=time.monotonic()+budget
   next_observation=time.monotonic()
   while child.poll() is None:
    scope.observe();record['processes']=scope.known;store(p,record)
    if record.get('native_client_error_file') and Path(record['native_client_error_file']).is_file():
     scope.stop();child.wait(timeout=5)
     break
    if time.monotonic()>deadline:
     stopped=scope.stop();child.wait(timeout=5)
     record.update(status='blocked',reason='timeout; do not resubmit without reconciliation',stop=stopped);self._observe(record,s,kind,index);store(p,record);return record
    if time.monotonic()>=next_observation:
     from .knowledge import home as knowledge_home,trigger
     try:
      kh=knowledge_home()
      record['knowledge_status']=trigger(kh) if (kh/'settings.json').exists() else {'state':'unconfigured'}
     except Exception as error:record['knowledge_status']={'state':'pending','error':str(error)}
     self._observe(record,s,kind,index);store(p,record);next_observation=time.monotonic()+5
    time.sleep(.25)
   code=child.returncode
  deadline=time.monotonic()+2
  while scope.observe() and time.monotonic()<deadline:time.sleep(.1)
  alive=scope.observe()
  if alive:
   record['cleanup_after_provider_exit']=scope.stop()
   record['outlived_provider_root']=list(alive)
  alive=scope.observe()
  boundary=boundary_error(output.read_text()+'\n'+err.read_text()) if self.role_bundle else None
  if record.get('native_client_error_file') and Path(record['native_client_error_file']).is_file():
   boundary=boundary_error('Error: GLG_NATIVE_BOUNDARY:'+Path(record['native_client_error_file']).read_text()) or boundary
  if boundary:
   stopped=scope.stop() if alive else None
   record.update(status=boundary['kind'],native_error=boundary,reason=boundary['error'].get('message','Explicit native permission/scope boundary'),exit=code,quiescent=not scope.observe(),stop=stopped,finished=time.time())
   self._observe(record,s,kind,index);store(p,record);return record
  record.update(status='completed' if code==0 and not alive else 'blocked',exit=code,quiescent=not alive,processes=scope.known,alive=list(alive),output=str(output),stderr=str(err),finished=time.time())
  if record['status']=='completed' and s.get('response_schema'):
   import jsonschema
   try:jsonschema.validate(final_object(output),s['response_schema']);record['response_contract']={'passed':True}
   except (jsonschema.ValidationError,jsonschema.SchemaError) as error:
    record.update(status='blocked',reason='Native/task final response violates its JSON contract: '+error.message,response_contract={'passed':False})
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

 def shape(self,s,stage,assignment):
  from .project_context import render
  from .artifacts import Artifacts
  roles={'define':'business-analyst','solution':'solution-architect','plan':'lead-developer'}
  context=render(Artifacts(s['workspace'],s['work_id']).read(s['context_ref'])['payload'])
  task=json.dumps({'stage':stage,'assignment':assignment,'approval':s['stage_authorization_ref']},sort_keys=True)
  state={**s,'task':task,'project_context':context,'inputs':task_input_digest(task,s['workspace'],context),
         'job_id':s['job_id']+'-'+stage+'-'+s['stage_authorization_ref']['revision'][:12],
         'deadline':time.time()+s.get('budget_seconds',600),'corrections':0,'resume_epoch':0}
  prompt=f'''You are the Goose coordinator for Flow's {stage} stage. LangGraph owns dispatch and durable state; the native host is only the conversational interface and human approval surface.
Delegate through converted role source {roles[stage]} and other configured specialists as appropriate. You own research coordination, comparison, synthesis and the proposed stage result. Do not ask the host model to do research, delegate specialists or write the plan. Ask consequential questions in findings for the human.
Assignment: {task}
Project context: {context}
Research/planning authority only. No implementation, install, deployment, new login or automatic approval. Preserve existing scope and permission boundaries. Return only JSON with outcome completed|blocked|permission_required|scope_required, content containing substantive findings and limitations. Plan may additionally return brief with goal, scope, acceptance_criteria and check_command argv. Human approval remains mandatory; no stage result grants implementation authority.'''
  contract={'type':'object','properties':{'outcome':{'type':'string'},'content':{'type':'string'},'brief':{'type':'object'}},'required':['outcome','content'],'additionalProperties':False}
  result=self._run({**state,'response_schema':contract},'shape-'+stage,prompt)
  if result['status']!='completed':return result
  report=final_object(result['output'])
  status=report.get('outcome')
  if status not in {'completed','blocked','permission_required','scope_required'} or not isinstance(report.get('content'),str) or not report['content'].strip():
   return {'status':'blocked','reason':'Stage coordinator did not return the required substantive result','runtime':result}
  return {'status':status,'content':report['content'],'runtime':result,**({'brief':report['brief']} if 'brief' in report else {})}

 def _role_operation(self,s,kind):
  roles=[p.stem for p in (self.role_bundle/'recipes').glob('*.yaml')]
  implementation_instruction='Delegate actual implementation, normally using lead-developer, and consume its result.'
  if self.implementation_profile:
   implementation_instruction='Delegate actual implementation to source lead-developer using its frozen implementation profile. Do not edit directly or override its provider/model. Consume the worker result.'
  prompt=f"""You are Goose's implementation coordinator. Use the converted role recipes available through summon; select appropriate roles and configured providers yourself. Available roles: {', '.join(sorted(roles))}.
Approved task: {s['task']}
Workspace: {s['workspace']}
Project context: {s.get('project_context','')}
Operation: {kind}. {implementation_instruction if kind=='implement' else 'Delegate quality-reviewer in a FRESH session to inspect the actual candidate and independently run tests. Do not silently fix the candidate.'}
Every delegate call must select a converted role with source; do not use role-less ad-hoc delegates, which have no development extensions. Recipes default to this approved task and project_context. Use the delegate parameters object only when refining a role assignment; preserve the approved scope. Both roles have normal broad development tools under the same workspace permissions. No role-specific tool restrictions. No nested coordinators or background work. Use existing signed-in providers; no new login, API billing fallback or global settings changes. Existing credential and external-action approvals apply. Stop and report actual scope/permission blockers immediately; do not reinterpret them as correction work.
Previous findings: {json.dumps(s.get('findings',[]))}
Previous test results: {json.dumps(s.get('test_results',{}))}
Candidate revision: {s.get('candidate','not yet checked')}
Return only JSON with outcome, findings (array) and test_results (object). Outcomes: completed or correction for implementation; approve or request_changes for review; permission_required, scope_required or blocked for either. For review include candidate_revision exactly as supplied. Preserve actual failures and limitations in findings. Final acceptance belongs to the task graph. Parent 8 turns, children at most {WORKER_MAX_TURNS} Goose turns within the original approved deadline, no merge or deployment."""
  contract={'type':'object','properties':{'outcome':{'type':'string'},'findings':{'type':'array','items':{'type':'string'}},'test_results':{'type':'object'},'candidate_revision':{'type':'string'}},'required':['outcome','findings','test_results'],'additionalProperties':False}
  try:result=self._run({**s,'response_schema':contract},kind,prompt)
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
