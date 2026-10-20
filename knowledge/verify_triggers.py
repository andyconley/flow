"""Destructive only to a NEW isolated --home. Real local model/BM trigger test."""
import argparse,json,os,signal,sqlite3,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from poc import knowledge as k

def main():
 p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--python',required=True);p.add_argument('--cache',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=a.home.absolute()
 if root.exists():raise ValueError('Use a fresh isolated home')
 root.mkdir();(root/'notes').mkdir();os.environ['FLOW_KNOWLEDGE_HOME']=str(root)
 for n in ['business-analyst--mark-the-evidentiary-status-of-every-statement.md','support-lead--carry-hypothesis-and-fact-separately-across-a-handoff.md']:(root/'notes'/n).write_bytes((k.SHARED/'cards'/n).read_bytes())
 k.write(root/'settings.json',{'python':a.python,'cache':a.cache,'model':'qwen3:4b','model_digest':k.local_model_digest('http://127.0.0.1:11435','qwen3:4b'),'ollama':'http://127.0.0.1:11435'})
 events=[]
 def wait(label,old=None,failed=False):
  deadline=time.monotonic()+180
  while time.monotonic()<deadline:
   s=k.status(root)
   if failed and s['state']=='failed':break
   if not failed and s['state']=='ready' and not s['pending'] and s.get('snapshot')!=old:break
   time.sleep(.25)
  else:raise AssertionError((label,k.status(root)))
  events.append({'label':label,'status':s});print(json.dumps(events[-1]),flush=True);return s
 def current():return k.read(root/'CURRENT.json')['generation']
 k.trigger(root);wait('automatic initial')
 old=current();k.trigger(root);time.sleep(.5);assert old==current()
 external=root/'edit-input.txt';external.write_text('---\ntitle: Local manual note\npermalink: local/manual\n---\nAuthored local addition, preserve every word.\n')
 assert k.main(['--home',str(root),'write','manual.md','--from-file',str(external)])==0
 wait('automatic add',old);old=current()
 # Foreground watcher is a small local reconciliation process; this models an
 # editor changing a file while Flow's stdio server performs the same polling.
 env={**os.environ,'PYTHONPATH':str(k.REPO/'v2'),'PYTHONPYCACHEPREFIX':str(root/'home/pycache')}
 log=(root/'watch.log').open('w');watch=subprocess.Popen([a.python,'-m','poc.knowledge','--home',str(root),'watch'],cwd=k.REPO/'v2',env=env,stdout=log,stderr=log,start_new_session=True)
 try:
  (root/'notes/manual.md').write_text(external.read_text()+'\nExternal editor change must be caught.\n')
  wait('manual edit fingerprint backstop',old);old=current()
  assert 'External editor change' in (k.snapshot(root)/'notes/manual.md').read_text()
  assert k.main(['--home',str(root),'delete','support-lead--carry-hypothesis-and-fact-separately-across-a-handoff.md'])==0
  wait('automatic delete and stale link cleanup',old);old=current()
  audit=k.read(k.snapshot(root)/'audit.json');assert audit['notes']==2 and audit['graph_edges']==0 and audit['unresolved_edges']==0,audit
  before=k.read(root/'CURRENT.json');text=(root/'notes/manual.md').read_text();(root/'notes/manual.md').write_text(text+'<!-- cocoindex:relationships:v2 -->\ninvalid\n')
  wait('failed fingerprint visible',failed=True);assert before==k.read(root/'CURRENT.json')
  assert list((root/'backups').glob('*before-enrichment.zip'))
  # Restart with interrupted status and a newly corrected authored input.
  (root/'notes/manual.md').write_text(text+'\nRecovery edit.\n');k.write(root/'status.json',{'state':'running','generation':'simulated-dead-private-stage'})
  wait('restart recovery preserves last good until ready',old)
 finally:
  os.killpg(watch.pid,signal.SIGTERM);watch.wait(timeout=10);log.close()
 result={'passed':True,'events':events,'final_audit':k.read(k.snapshot(root)/'audit.json'),'manual_text_preserved':True,'failed_run_kept_previous_snapshot':True,'backups':len(list((root/'backups').glob('*.zip')))}
 a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'passed':True,'events':len(events)}))
if __name__=='__main__':main()
