"""Deterministic SDK lifecycle/accounting across new parent processes.

Uses only a loopback synthetic endpoint and temporary project/store. No native
credentials, Ollama service, user configuration, or historical artifacts.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Endpoint(BaseHTTPRequestHandler):
    calls = []
    def log_message(self, *_):
        pass
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append(request)
        model = request['model']
        if model == 'parent' and request['messages'][-1]['role'] == 'user':
            tool = next(t['function']['name'] for t in request['tools'] if t['function']['name'] == 'task')
            roster = str(request['messages'][0]['content'])
            key = roster.split('test-engineer: use task subagent_type=')[-1].split()[0]
            message = {'role':'assistant','content':None,'tool_calls':[{'id':f'delegate_{len(self.calls)}','type':'function',
                'function':{'name':tool,'arguments':json.dumps({'prompt':'Report the disposable accounting proof.','subagent_type':key})}}]}
            finish = 'tool_calls'
        else:
            message = {'role':'assistant','content':'Disposable accounting proof complete.'}
            finish = 'stop'
        count = 100 if model == 'parent' else 50
        body = json.dumps({'id':f'accounting_{len(self.calls)}','object':'chat.completion','created':1,'model':model,
            'choices':[{'index':0,'message':message,'finish_reason':finish}],
            'usage':{'prompt_tokens':count,'completion_tokens':20,'total_tokens':count+20}}).encode()
        self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)


WORKER = '''
import json,sys
from pathlib import Path
from argparse import Namespace
sys.path.insert(0,sys.argv[1])
import openhands_flow as flow
import runstate
args=Namespace(project_root=Path(sys.argv[2]),work_id='accounting',stage='define',role=None,profile=None,
               task_file=Path('task.md'),new_session=sys.argv[3]=='new',disposition=[],confirm_pending=False,reject_pending=None)
if sys.argv[3]=='init':
 flow.initialize(args)
else:
 if sys.argv[3] in ('interrupt','failure'):
  from openhands.sdk.conversation.impl.local_conversation import LocalConversation
  original=LocalConversation.run
  def fail(self,*a,**kw):
   original(self,*a,**kw)
   raise KeyboardInterrupt() if sys.argv[3]=='interrupt' else RuntimeError('injected failure after metered inference')
  LocalConversation.run=fail
 try:
  flow.execute(args)
 except BaseException as exc:
  if sys.argv[3] not in ('interrupt','failure'): raise
 print(json.dumps(runstate.status('accounting',args.project_root)))
'''


def main():
    cli = str(Path(__file__).resolve().parents[1]/'cli')
    worker_cli = os.environ.get("FLOW_USAGE_BASELINE_CLI", cli)
    sys.path.insert(0, cli)
    from openhands_usage import harvest_project, reporting_rows
    from normalize import normalize_all
    from cost import summary_rows, active_rows, trend_rows
    import usage_store
    import sqlite3
    with tempfile.TemporaryDirectory(prefix='flow-usage-eval-') as d:
        root = Path(d)
        (root/'.flow').mkdir()
        (root/'task.md').write_text('Delegate the disposable proof to test-engineer, then finish.')
        server = ThreadingHTTPServer(('127.0.0.1',0),Endpoint)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        url = f'http://127.0.0.1:{server.server_port}/v1'
        (root/'.flow/runtime.toml').write_text(f'''default_profile="parent"
[profiles.parent]
kind="local"
model="openai/parent"
base_url="{url}"
max_input_tokens=65536
max_output_tokens=8192
[profiles.child]
kind="local"
model="openai/child"
base_url="{url}"
max_input_tokens=65536
max_output_tokens=8192
[roles.business-analyst]
specialists=["test-engineer"]
tools=["task"]
[roles.test-engineer]
profile="child"
specialists=[]
tools=[]
''')
        env = {**os.environ,'OPENHANDS_SUPPRESS_BANNER':'1','LITELLM_LOCAL_MODEL_COST_MAP':'True','OH_PERSISTENCE_DIR':str(root/'sdk-settings')}
        store = root/'usage.db'; usage_store.ensure_store(store)
        conn = sqlite3.connect(store);conn.row_factory=sqlite3.Row
        def invoke(mode):
            done = subprocess.run([sys.executable,'-c',WORKER,worker_cli,str(root),mode],env=env,capture_output=True,text=True,timeout=60)
            assert done.returncode == 0,done.stdout+done.stderr
            return json.loads(done.stdout.splitlines()[-1]) if mode != 'init' else None
        def check_totals():
            imported=harvest_project(conn,root);assert not imported['failures'],imported
            normalized=normalize_all(conn);assert not normalized['failures'],normalized
            rows=summary_rows(conn,None)
            expected_in=sum(100 if r['model']=='parent' else 50 for r in Endpoint.calls)
            assert sum(r['fresh_input_tokens'] for r in rows)==expected_in,(rows,expected_in,imported)
            assert sum(r['output_tokens'] for r in rows)==20*len(Endpoint.calls),(rows,Endpoint.calls)
            repeat=harvest_project(conn,root);assert repeat['turns']==0,repeat
            assert normalize_all(conn)['normalized']==0
            return rows
        try:
            invoke('init')
            first=invoke('run');check_totals()
            if worker_cli != cli:
                second=invoke('run')
                reported=second['sessions']['define:business-analyst']['metrics']['accumulated_token_usage']['prompt_tokens']
                expected=sum(100 if r['model']=='parent' else 50 for r in Endpoint.calls)
                assert reported < expected, (reported, expected)
                print(json.dumps({'status':'baseline_risk_reproduced','sdk_requests':len(Endpoint.calls),
                    'projected_prompt_tokens':reported,'actual_prompt_tokens':expected,'lost_prompt_tokens':expected-reported}))
                return
            key='define:business-analyst';identity=first['sessions'][key]['conversation_id']
            second=invoke('run');check_totals()
            assert second['sessions'][key]['conversation_id']==identity
            assert second['sessions'][key]['elapsed_seconds']>first['sessions'][key]['elapsed_seconds']
            task_buckets=[k for k in second['sessions'][key]['metrics_by_usage'] if k.startswith('task:')]
            assert len(task_buckets)==2,task_buckets
            assert len(set(task_buckets))==2
            third=invoke('new');check_totals()
            assert third['sessions'][key]['conversation_id']!=identity
            assert third['prior_sessions'][0]['conversation_id']==identity
            interrupted=invoke('interrupt');check_totals()
            assert interrupted['sessions'][key]['status']=='interrupted',interrupted
            failed=invoke('failure');rows=check_totals()
            assert failed['sessions'][key]['status']=='error',failed
            assert failed['sessions'][key]['elapsed_seconds']>interrupted['sessions'][key]['elapsed_seconds']
            assert failed['sessions'][key]['metrics']['accumulated_token_usage']['completion_tokens']>interrupted['sessions'][key]['metrics']['accumulated_token_usage']['completion_tokens']
            assert active_rows(conn,60), 'SDK sessions absent from active report'
            assert trend_rows(conn,None,'day'), 'SDK sessions absent from trend'
            # Exercise the user-facing parser and persisted reporting store too.
            cli_env = {**env, 'HOME': str(root/'report-home')}
            for arguments in (['harvest','openhands','--project-root',str(root)],
                              ['cost','summary','--all','--json'], ['cost','active','--json']):
                done = subprocess.run([sys.executable,str(Path(cli)/'flow.py'),*arguments],cwd=root,
                                      env=cli_env,capture_output=True,text=True,timeout=30)
                assert done.returncode == 0, done.stdout+done.stderr
                report = json.loads(done.stdout)
                if arguments[1] == 'summary':
                    assert sum(r['fresh_input_tokens'] for r in report['rows']) == 1050, report
                    assert report['sdk_usage'], report
                elif arguments[1] == 'active':
                    assert report['rows'] and report['sdk_usage'], report
            evidence=reporting_rows(conn)
            assert any(r['role']=='test-engineer' and r['provider']=='local' for r in evidence),evidence
            print(json.dumps({'status':'passed','fresh_processes':5,'sdk_requests':len(Endpoint.calls),
                'parent_task_buckets_after_restart':task_buckets,'combined_rows':rows,
                'reimport_idempotent':True,'interruption_and_failure_preserved':True,'prior_session_retained':True}))
        finally:
            conn.close();server.shutdown();server.server_close()

if __name__=='__main__':main()
