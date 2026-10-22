import json,os,socket,subprocess,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from poc.native_delegation import Delegation
from poc.implementation_profiles import fingerprint

class DelegationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  profile={'name':'local','provider':'ollama','model':'fixture:local','endpoint':'http://127.0.0.1:11434','context_tokens':32768,'output_tokens':-1,'condenser_max_tokens':28672,'model_digest':'a'*64};profile['sha256']=fingerprint(profile);self.profile=profile
 def test_advertised_callable_fixed_capability_and_idempotence(self):
  calls=[]
  def run(owner):
   calls.append(owner.state['task']);owner.result['state']='completed';owner.done.set()
  with patch.object(Delegation,'run',run):
   broker=Delegation({'task':'frozen approved task'},self.profile,self.root,{},'/fixture/goose',self.root/'evidence');self.addCleanup(broker.close)
   with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
    client.connect(str(broker.socket));reader=client.makefile('rb')
    for number,method,params in [(1,'initialize',{}),(2,'tools/list',{}),(3,'tools/call',{'name':'delegate_implementation','arguments':{}}),(4,'tools/call',{'name':'delegation_status','arguments':{}}),(5,'tools/call',{'name':'delegate_implementation','arguments':{}}),(6,'tools/call',{'name':'delegate_implementation','arguments':{'command':'forbidden'}})]:
     client.sendall((json.dumps({'jsonrpc':'2.0','id':number,'method':method,'params':params})+'\n').encode());response=json.loads(reader.readline())
     if number==2:self.assertEqual({t['name'] for t in response['result']['tools']},{'delegate_implementation','delegation_status'})
     if number==6:self.assertIn('error',response)
   if broker.worker:broker.worker.join(2)
   self.assertEqual(calls,['frozen approved task']);self.assertEqual(broker.directory.stat().st_mode&0o777,0o700);self.assertEqual(broker.socket.stat().st_mode&0o777,0o600)
 def test_stdio_proxy_works_as_real_mcp_transport(self):
  broker=Delegation({'task':'approved'},self.profile,self.root,{},'/fixture/goose',self.root/'evidence');self.addCleanup(broker.close)
  proxy=Path(__file__).resolve().parents[1]/'poc/delegation_stdio.py'
  request={'jsonrpc':'2.0','id':1,'method':'tools/list'}
  import sys
  result=subprocess.run([sys.executable,str(proxy),str(broker.socket)],input=json.dumps(request)+'\n',capture_output=True,text=True,timeout=5)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(len(json.loads(result.stdout)['result']['tools']),2)

 def test_review_is_fixed_private_role_and_cannot_start_implementation(self):
  profile={'name':'quality-reviewer','provider':'claude-acp','model':'opus'};profile['sha256']=fingerprint(profile)
  broker=Delegation({'task':'review approved candidate'},profile,self.root,{},'/fixture/goose',self.root/'review',operation='review');self.addCleanup(broker.close)
  tools=broker.rpc({'method':'tools/list'})['tools'];self.assertEqual(tools[0]['name'],'delegate_review')
  with self.assertRaisesRegex(ValueError,'Unknown bound tool'):broker.rpc({'method':'tools/call','params':{'name':'delegate_implementation'}})
  self.assertIsNone(broker.worker)
 def test_uncertain_prior_delegation_blocks_a_new_operation(self):
  prior=self.root/'delegation-old';prior.mkdir();(prior/'delegation.json').write_text('{"state":"running"}')
  with self.assertRaisesRegex(RuntimeError,'Unreconciled prior'):
   Delegation({'task':'approved'},self.profile,self.root,{},'/fixture/goose',self.root/'delegation-new')
 def test_bound_worker_uses_frozen_provider_model_and_native_review_settings(self):
  from types import SimpleNamespace
  import yaml
  workspace=self.root/'workspace';workspace.mkdir();recipes=self.root/'recipes';recipes.mkdir()
  report={'success':True,'verdict':'approve','summary':'fixture','findings':[],'verification':[],'limitations':[]}
  for name in ('lead-developer','quality-reviewer'):(recipes/(name+'.yaml')).write_text(yaml.safe_dump({'instructions':'fixture role','response':{'json_schema':{'type':'object'}}}))
  class Scope:
   def __init__(self,pid):self.known={}
   def observe(self):return {}
  for operation in ('implement','review'):
   profile=dict(self.profile) if operation=='implement' else {'name':'quality-reviewer','provider':'claude-acp','model':'opus'}
   if operation=='review':profile['sha256']=fingerprint(profile)
   native={'PATH':'/usr/bin','HOME':'/isolated/codex-home','CODEX_HOME':'/private/codex','CLAUDE_CONFIG_DIR':'/private/claude','FLOW_V2_CLAUDE_USER_HOME':'/real/user'}
   broker=Delegation({'task':'frozen task','workspace':str(workspace)},profile,self.root,native,'/fixture/goose',self.root/('evidence-'+operation),operation=operation)
   def launch(command,**kwargs):
    self.assertEqual(command[command.index('--provider')+1],profile['provider']);self.assertEqual(command[command.index('--model')+1],profile['model']);self.assertEqual(kwargs['cwd'],workspace);self.assertNotIn('--text',command)
    bound=json.loads(Path(command[command.index('--recipe')+1]).read_text());self.assertIn('frozen task',bound['prompt'])
    if operation=='implement':self.assertEqual(kwargs['env']['GOOSE_INPUT_LIMIT'],'32768');self.assertNotIn('GOOSE_MAX_TOKENS',kwargs['env'])
    else:self.assertEqual(kwargs['env']['CLAUDE_CONFIG_DIR'],'/private/claude');self.assertEqual(kwargs['env']['CODEX_HOME'],'/private/codex');self.assertEqual(kwargs['env']['GOOSE_NATIVE_ACP_COMPLETION'],'true')
    kwargs['stdout'].write(json.dumps({'type':'message','message':{'role':'assistant','content':[{'type':'text','text':json.dumps(report)}]}})+'\n');kwargs['stdout'].flush()
    return SimpleNamespace(pid=123,returncode=0,poll=lambda:0)
   try:
    with patch('poc.knowledge.local_model_digest',return_value='a'*64),patch('poc.runtime_env.environment',return_value={'PATH':'/usr/bin','GOOSE_PATH_ROOT':str(self.root/'goose')}),patch('poc.native_delegation.subprocess.Popen',side_effect=launch),patch('poc.native_delegation.ProcessScope',Scope):broker.run()
    self.assertEqual(broker.result['state'],'completed',broker.result);self.assertEqual(broker.result['report'],report)
   finally:broker.close()
