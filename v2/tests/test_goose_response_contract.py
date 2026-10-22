import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from poc import goose_job
from poc.contracts import task_input_digest
class ResponseContractTests(unittest.TestCase):
 def exercise(self,provider='ollama',text='{"outcome":"completed"}',exit_code=0,stderr=''):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'runtime').mkdir();work=root/'work';work.mkdir();bundle=root/'bundle';(bundle/'recipes').mkdir(parents=True)
   (bundle/'recipes/fixture.yaml').write_text('version: 1.0.0\ntitle: fixture\ndescription: fixture\ninstructions: preserve role text\n')
   binary=root/'goose';argv_file=root/'argv.json'
   event={'type':'message','message':{'role':'assistant','content':[{'type':'text','text':text}]}}
   script='\n'.join(['#!/usr/bin/env python3','import sys,json','from pathlib import Path',f'Path({str(argv_file)!r}).write_text(json.dumps(sys.argv[1:]))',f'print({json.dumps(event)!r})','print(json.dumps({"type":"complete"}))',f'print({stderr!r},file=sys.stderr)',f'sys.exit({exit_code})'])+'\n'
   binary.write_text(script);binary.chmod(0o755)
   schema={'type':'object','properties':{'outcome':{'type':'string'}},'required':['outcome']}
   state={'task':'Approved fixture','workspace':str(work),'project_context':'','job_id':'contract-fixture','response_schema':schema};state['inputs']=task_input_digest(state['task'],work,'')
   def prepare(workspace,run_dir,roles,**kw):return run_dir/'worker.sb',{'PATH':os.environ['PATH'],'HOME':str(root/'home')}
   with patch.dict(os.environ,HOME=str(root/'home')),patch.object(goose_job,'ROOT',root),patch.object(goose_job,'goose_binary',return_value=binary),patch('poc.provider_preflight.check',return_value={'passed':True}),patch('poc.native_runtime.prepare',side_effect=prepare):result=goose_job.GooseJob(provider=provider,role_bundle=bundle)._run(state,'read','Exact approved instructions')
   args=json.loads(argv_file.read_text());contract=json.loads((root/'artifacts/contract-fixture/contracts/read-1-0.json').read_text())
   instructions=Path(args[args.index('--instructions')+1]).read_text() if '--instructions' in args else None
   return result,args,contract,instructions
 def test_unattended_goose_auth_failure_pauses_after_submission(self):
  result,*_=self.exercise('chatgpt_codex','',exit_code=1,stderr='Goose chatgpt_codex authentication unavailable. Unattended OAuth is disabled.')
  self.assertEqual(result['status'],'permission_required');self.assertTrue(result['submitted']);self.assertTrue(result['quiescent']);self.assertEqual(result['source'],'goose_auth')
  self.assertIn('inspect preserved effects',result['reason'])
 def test_schema_bound_normal_run_uses_recipe_without_conflicting_instructions_flag(self):
  result,args,contract,instructions=self.exercise();self.assertEqual('completed',result['status']);self.assertIn('--recipe',args);self.assertNotIn('--instructions',args);self.assertIn('Exact approved instructions',contract['prompt']);self.assertIn('FINAL response:',contract['prompt'])
 def test_native_route_forwards_task_and_schema_as_user_instructions(self):
  result,args,contract,instructions=self.exercise('codex-acp');self.assertEqual('completed',result['status']);self.assertNotIn('--recipe',args);self.assertIn('Exact approved instructions',instructions);self.assertIn('Schema:',instructions);self.assertTrue(result['response_contract']['passed'])
 def test_zero_exit_without_valid_final_contract_stays_blocked(self):
  result,*_=self.exercise('codex-acp','Prose is not the required result');self.assertEqual('blocked',result['status']);self.assertFalse(result['response_contract']['passed'])
 def test_opt_in_leaves_ordinary_coordinator_transport_unchanged(self):
  job=goose_job.GooseJob(provider='ollama',namespace_compat=True)
  with patch.object(job,'_run_impl',return_value={'status':'fixture'}) as run,patch('poc.native_runtime.local_codex_provider') as lookup:
   self.assertEqual({'status':'fixture'},job._run({'job_id':'fixture'},'read','task'));run.assert_called_once_with({'job_id':'fixture'},'read','task',None);lookup.assert_not_called()
 def test_cached_operation_does_not_replace_native_wire_audit(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);folder=root/'artifacts/cached';folder.mkdir(parents=True);(folder/'read-1-0.json').write_text('{}');audit=folder/'read-namespace-wire.json';audit.write_text('actual retained evidence')
   job=goose_job.GooseJob(provider='codex-acp',namespace_compat=True)
   with patch.object(goose_job,'ROOT',root),patch('poc.native_runtime.local_codex_provider',return_value=('local','http://127.0.0.1:1/v1')),patch('poc.local_responses.LocalResponsesBridge') as bridge,patch.object(job,'_run_impl',return_value={'status':'completed'}) as run:
    self.assertEqual('completed',job._run({'job_id':'cached'},'read','task')['status']);bridge.assert_not_called();self.assertEqual('actual retained evidence',audit.read_text())
 def test_explicit_adapter_refuses_nonlocal_provider_without_launch(self):
  with patch('poc.native_runtime.local_codex_provider',return_value=None),patch.object(goose_job.subprocess,'Popen') as launch:result=goose_job.GooseJob(provider='codex-acp',namespace_compat=True)._run({'job_id':'none'},'read','task')
  self.assertEqual('blocked',result['status']);self.assertFalse(result['submitted']);launch.assert_not_called()
if __name__=='__main__':unittest.main()
