"""Complete one read-only task through Flow's real native ACP provider boundary."""
import argparse,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from poc import knowledge as k

def main():
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--work',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--endpoint',default='http://127.0.0.1:11435/v1');a=p.parse_args()
 if a.work.exists():raise ValueError('Fresh workspace required')
 a.work.mkdir();os.environ['FLOW_KNOWLEDGE_HOME']=str(a.home.resolve())
 from poc.runtime_env import ROOT,setup
 from poc.goose_job import GooseJob
 from poc.contracts import task_input_digest
 from poc.evidence import final_object
 setup();private=ROOT/'runtime/codex-home';assert not (private/'auth.json').exists()
 (private/'config.toml').write_text('model="qwen3:4b"\nmodel_provider="local_ollama"\nmodel_reasoning_effort="none"\napproval_policy="never"\nsandbox_mode="workspace-write"\n[model_providers.local_ollama]\nname="Local Ollama fixture"\nbase_url='+json.dumps(a.endpoint)+'\nwire_api="responses"\nrequires_openai_auth=false\n[otel]\nexporter="none"\n')
 task='''Perform one read-only knowledge task. First call search_cards with query evidentiary, mode text, role business-analyst. Then call traverse_cards with permalink cards/business-analyst--mark-the-evidentiary-status-of-every-statement, relation_type complements and depth 1. Use their actual returned authored text to explain a safe handoff of an unconfirmed database-overload hypothesis. Quote at least eight consecutive words from each of the two cards and include both exact card permalinks. Keep observed, inferred, assumed and decided distinct. Do not use filesystem/terminal tools, do not delegate, and do not modify any files. Return only JSON with outcome completed and content containing the answer. If a required tool fails, return outcome blocked and its exact error. /no_think'''
 ident='knowledge-acp-read-'+str(time.time_ns());state={'task':task,'workspace':str(a.work.resolve()),'project_context':'Read-only knowledge-use task; no implementation or external actions.','job_id':ident,'deadline':time.time()+180}
 state['inputs']=task_input_digest(task,state['workspace'],state['project_context'])
 result=GooseJob(provider='codex-acp',model='qwen3:4b',timeout=180)._run(state,'read',task)
 report=final_object(result['output']) if result.get('output') else {};evidence=ROOT/'artifacts'/ident;frames=[]
 for file in evidence.rglob('acp-evidence/*.jsonl'):
  for line in file.read_text().splitlines():
   x=json.loads(line)
   if x.get('type')=='server_tool_frame':frames.append(x)
 titles=[str(x.get('frame',{}).get('params',{}).get('update',{}).get('title','')) for x in frames]
 content=report.get('content','');expected=[]
 for n in ('business-analyst--mark-the-evidentiary-status-of-every-statement.md','support-lead--carry-hypothesis-and-fact-separately-across-a-handoff.md'):
  raw=(k.SHARED/'cards'/n).read_text();body=raw.split('## Complete authored card (lossless)')[0];words=body.split();chunks=[' '.join(words[i:i+8]) for i in range(len(words)-7)]
  found=any(s in ' '.join(content.split()) for s in chunks);expected.append({'card':n,'quoted_eight_authored_words':found,'permalink_present':'cards/'+n.removesuffix('.md') in content})
 checks={'provider_completed':result.get('status')=='completed','task_completed':report.get('outcome')=='completed','actual_search_call':any('search_cards' in t for t in titles),'actual_graph_call':any('traverse_cards' in t for t in titles),'authored_quotes_and_ids':all(x['quoted_eight_authored_words'] and x['permalink_present'] for x in expected),'no_workspace_writes':not list(a.work.iterdir()),'credential_free':not (private/'auth.json').exists()}
 data={'passed':all(checks.values()),'checks':checks,'result':result,'report':report,'expected':expected,'acp_frames':frames}
 a.output.write_text(json.dumps(data,indent=2,default=str)+'\n');print(json.dumps({'passed':data['passed'],'checks':checks,'job':ident}))
if __name__=='__main__':main()
