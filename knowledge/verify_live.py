"""Read-only live verification of an already built isolated knowledge generation.
Run with the configured knowledge Python, --home pointing at test data.
Does not modify authored notes or initiate an inference run when fingerprints match.
"""
import argparse,asyncio,hashlib,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from poc import knowledge as k
CASES=[('What should a delivery plan say before an irreversible migration?','reversible delivery','lead-developer--plan-a-reversible-delivery-path'),('How should a handoff distinguish guesses from facts?','hypothesis fact handoff','support-lead--carry-hypothesis-and-fact-separately-across-a-handoff'),('What should we do when requirements lack enough evidence?','requirement undefined evidence thin','business-analyst--leave-a-requirement-undefined-while-the-evidence-is-thin'),('How should an incident review avoid oversimplifying causes?','contributing conditions root cause','sre--contributing-conditions-instead-of-a-root-cause'),('How do we decide whether a test passes?','test oracle concrete example','test-engineer--define-a-test-oracle-with-a-concrete-example')]
async def mcp_check(root):
 from fastmcp import Client
 from fastmcp.client.transports import StdioTransport
 env={**k.clean_env(root),'FLOW_KNOWLEDGE_HOME':str(root),'PYTHONPATH':str(k.REPO/'v2')}
 transport=StdioTransport(command=sys.executable,args=['-m','poc.knowledge_runtime.server'],env=env,cwd=str(k.REPO/'v2'))
 async with Client(transport) as client:
  tools=await client.list_tools();names=sorted(t.name for t in tools)
  assert names==['knowledge_status','search_cards','traverse_cards'],names
  state=await client.call_tool('knowledge_status',{})
  assert not state.is_error
  response=await client.call_tool('search_cards',{'query':'requirement evidence','mode':'text','role':'business-analyst'})
  assert not response.is_error
  graph=await client.call_tool('traverse_cards',{'permalink':'cards/business-analyst--mark-the-evidentiary-status-of-every-statement','relation_type':'complements','depth':2})
  assert not graph.is_error
  return {'tools':names,'status_ok':True,'search_ok':True,'graph_ok':True}
def main():
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.home.resolve();os.environ['FLOW_KNOWLEDGE_HOME']=str(root)
 before=k.read(root/'CURRENT.json');assert not k.status(root)['pending'],k.status(root)
 notes=k.inventory(root/'notes');snapshot=k.snapshot(root)
 hashes={str(p.relative_to(snapshot)):k.digest(p.read_bytes()) for p in snapshot.rglob('*') if p.is_file()}
 k.process(root);assert k.read(root/'CURRENT.json')==before
 rows=[]
 for question,keywords,expected in CASES:
  for mode in ('text','vector','hybrid'):
   start=time.monotonic();data=k.query(root,keywords if mode=='text' else question,mode)
   hits=data.get('results',[]);rank=next((i for i,x in enumerate(hits,1) if expected in str(x.get('permalink',''))),None)
   rows.append({'question':question,'mode':mode,'rank':rank,'seconds':time.monotonic()-start,'results':hits})
 role=k.query(root,'current workflow for analytics dashboards','hybrid','business-analyst');assert role.get('results')
 assert all(Path(x['file_path']).name.startswith('business-analyst--') for x in role['results']),[x['file_path'] for x in role['results']]
 import sqlite3
 with sqlite3.connect('file:'+str(snapshot/'config/memory.db')+'?mode=ro',uri=True) as db:
  start=db.execute("SELECT e.permalink FROM entity e JOIN relation r ON r.from_id=e.id WHERE r.relation_type='complements' AND r.to_id IS NOT NULL LIMIT 1").fetchone()[0]
 graph=k.graph(root,start,'complements',2);assert graph['edges'];assert graph['timeframe'] is None
 assert all(x['from_note'] and x['to_note'] and x['target_content'] for x in graph['edges'])
 mcp=asyncio.run(mcp_check(root))
 assert notes==k.inventory(root/'notes');assert before==k.read(root/'CURRENT.json')
 after={str(p.relative_to(snapshot)):k.digest(p.read_bytes()) for p in snapshot.rglob('*') if p.is_file()}
 assert hashes==after,'Published snapshot mutated during reads'
 result={'passed':True,'snapshot':before,'audit':k.read(snapshot/'audit.json'),'repeated_build_noop':True,'authored_files_unchanged':True,'snapshot_bytes_unchanged_by_concurrent_capable_reads':True,'search_cases':rows,'role_scope':role,'graph':graph,'mcp':mcp}
 a.output.write_text(json.dumps(result,indent=2,default=str)+'\n');print(json.dumps({'passed':True,'search_requests':len(rows),'mcp':mcp,'graph_edges':len(graph['edges'])}))
if __name__=='__main__':main()
