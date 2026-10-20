"""Bounded Flow workflow using actual Codex ACP + credential-free local Ollama.
Fixture writes only under --work and source-local ignored runtime/artifacts.
No installed accounts, auth.json, production installs or paid APIs are used.
"""
import argparse,json,os,shutil,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from poc import knowledge as k

def main():
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model',default='qwen3:4b');p.add_argument('--coordinator-model',default='qwen2.5:7b');a=p.parse_args()
 if a.work.exists():raise ValueError('Use a fresh fixture workspace')
 a.work.mkdir();os.environ['FLOW_KNOWLEDGE_HOME']=str(a.home.resolve())
 from poc.runtime_env import ROOT,setup
 from poc.contracts import task_input_digest
 from poc.goose_job import GooseJob
 from poc.workflow import build
 from langgraph.checkpoint.sqlite import SqliteSaver
 import yaml
 setup()
 private=ROOT/'runtime/codex-home';assert not (private/'auth.json').exists(),'Never use existing account credentials in this test'
 (private/'config.toml').write_text('model = '+json.dumps(a.model)+'\nmodel_provider = "local_ollama"\napproval_policy = "never"\nsandbox_mode = "workspace-write"\n[model_providers.local_ollama]\nname = "Local Ollama fixture"\nbase_url = "http://127.0.0.1:11435/v1"\nwire_api = "responses"\nrequires_openai_auth = false\n[otel]\nexporter = "none"\n')
 bundle=a.work.parent/(a.work.name+'-roles');shutil.copytree(ROOT/'role-bundle',bundle)
 for f in (bundle/'recipes').glob('*.yaml'):
  r=yaml.safe_load(f.read_text());r['settings']['goose_provider']='codex-acp';r['settings']['goose_model']=a.model;f.write_text(yaml.safe_dump(r,sort_keys=False))
 # Both implementation and independent review use real production ACP machinery.
 # Recipe copies change only provider/model, preserving actual role instructions.
 task='''Create handoff.md for this small incident handoff. Observation: database CPU was measured high at 14:00. Hypothesis: overload may be involved, but its cause is not confirmed. Use the managed search_cards tool to retrieve the business analyst card about marking evidentiary status, then use traverse_cards starting at cards/business-analyst--mark-the-evidentiary-status-of-every-statement with relation_type complements to retrieve its support-lead neighbor. Do not substitute embedded role expertise for these tool calls. Read the returned authored guidance and apply both cards: visibly separate observed, inferred, assumed and decided information, and carry the overload hypothesis as unconfirmed. Include one exact sentence quoted from each card and both exact card permalinks. Do not invent investigation results. Write the file and run the check command. Review must independently verify the file and the quoted text. No other implementation, external action, credential use or deployment.'''
 expected=[]
 for n in ['business-analyst--mark-the-evidentiary-status-of-every-statement.md','support-lead--carry-hypothesis-and-fact-separately-across-a-handoff.md']:
  raw=(k.SHARED/'cards'/n).read_text();required=raw.split('## Required behavior\n\n')[1].split('\n\n## Avoid')[0];expected.append({'permalink':'cards/'+n.removesuffix('.md'),'quote_fragment':' '.join(required.split()[:8])})
 (a.work/'expected.json').write_text(json.dumps(expected))
 check='''import json,re\nfrom pathlib import Path\ns=Path('handoff.md').read_text()\nfor x in json.loads(Path('expected.json').read_text()):\n assert x['permalink'] in s,x['permalink']\n assert x['quote_fragment'].lower() in s.lower(),x['quote_fragment']\nfor label in ['observed','inferred','assumed','decided']:assert label in s.lower(),label\nassert 'unconfirmed' in s.lower() or 'not confirmed' in s.lower()\nprint('HANDOFF_CHECK_PASSED')\n'''
 (a.work/'verify.py').write_text(check)
 command=[sys.executable,'verify.py'];context='Use only provided observation/hypothesis. Required independent check: '+json.dumps(command)
 ident='knowledge-acp-'+str(time.time_ns());state={'task':task,'workspace':str(a.work.resolve()),'project_context':context,'job_id':ident,'inputs':task_input_digest(task,a.work,context),'check_command':command,'corrections':0,'max_corrections':0,'attempt':0,'deadline':time.time()+420};state['approved']=state['inputs']
 def checker(work):
  p=subprocess.run(command,cwd=work,capture_output=True,text=True,timeout=30);return {'passed':p.returncode==0,'exit':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 with SqliteSaver.from_conn_string(str(a.work.parent/(ident+'.sqlite'))) as saver:
  graph=build(GooseJob(provider='ollama',model=a.coordinator_model,timeout=420,role_bundle=bundle),checker).compile(checkpointer=saver)
  outcome=graph.invoke(state,{'configurable':{'thread_id':ident},'recursion_limit':30})
 evidence=ROOT/'artifacts'/ident
 records=[]
 for f in evidence.rglob('*.jsonl'):
  if 'acp-evidence' in str(f):records.append({'path':str(f),'text':f.read_text()})
 result={'workflow':outcome,'acp_frames':records,'artifact':(a.work/'handoff.md').read_text() if (a.work/'handoff.md').exists() else None,'credential_free':not (private/'auth.json').exists(),'evidence_directory':str(evidence)}
 a.output.write_text(json.dumps(result,indent=2,default=str)+'\n');print(json.dumps({'phase':outcome.get('phase'),'outcome':outcome.get('outcome'),'evidence':str(evidence)}))
if __name__=='__main__':main()
