"""Role-backed LangGraph entrypoint. Invocation may launch native inference."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from .runtime_env import ROOT, setup
from .contracts import task_input_digest
from .workflow import build
from .goose_job import GooseJob


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',required=True)
    parser.add_argument('--task-file',type=Path,required=True,help='JSON: task, workspace, project_context, check_command (argument array)')
    parser.add_argument('--approved',action='store_true')
    parser.add_argument('--budget-seconds',type=int,default=600)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--decision',help='Approval digest, resume, or stop for the pending interrupt')
    args=parser.parse_args();contract=json.loads(args.task_file.read_text())
    command=contract['check_command']
    if not isinstance(command,list) or not command or any(not isinstance(x,str) for x in command):
        parser.error('check_command must be a nonempty argument array')
    workspace=str(Path(contract['workspace']).resolve())
    context=contract.get('project_context','')+'\nTest command: '+json.dumps(command)
    digest=task_input_digest(contract['task'],workspace,context)
    state={'task':contract['task'],'workspace':workspace,'project_context':context,'job_id':args.job,
           'inputs':digest,'approved':digest if args.approved else '', 'check_command':command,'corrections':0,'attempt':0,'deadline':time.time()+args.budget_seconds}
    if args.budget_seconds<=0:parser.error('budget-seconds must be positive')
    remaining_deadline=[state['deadline']]
    setup();out=ROOT/'artifacts'/args.job;out.mkdir(parents=True,exist_ok=True)
    def check(path):
        remaining=remaining_deadline[0]-time.time()
        if remaining<=0:return {'passed':False,'outcome':'blocked','reason':'Workflow time budget exhausted'}
        from .project_python import check_command
        try:result=subprocess.run(check_command(path,command),cwd=path,capture_output=True,text=True,timeout=min(60,remaining))
        except subprocess.TimeoutExpired:return {'passed':False,'outcome':'blocked','reason':'Independent check time budget exhausted'}
        except (OSError,ValueError) as error:return {'passed':False,'outcome':'scope_required','reason':str(error)}
        return {'passed':result.returncode==0,'exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    with SqliteSaver.from_conn_string(str(out/'workflow.sqlite')) as saver:
        graph=build(GooseJob(provider='chatgpt_codex',model='gpt-5.6-sol',timeout=600,role_bundle=ROOT/'role-bundle'),check).compile(checkpointer=saver)
        config={'configurable':{'thread_id':args.job},'recursion_limit':60}
        saved=graph.get_state(config)
        if args.resume and saved.values:remaining_deadline[0]=saved.values['deadline']
        if args.resume and saved.values and saved.values.get('inputs')!=digest:
            parser.error('Task/check configuration changed; start a separately approved job')
        if not args.resume and saved.values:
            parser.error('Job already exists; use --resume to continue it')
        result=graph.invoke(Command(resume=args.decision) if args.resume and args.decision else None if args.resume else state,config)
    (out/'role-workflow-outcome.json').write_text(json.dumps(result,indent=2,default=str)+'\n')
    handoff={key:result.get(key) for key in ['task','workspace','candidate_revision','outcome','findings','test_results']}
    handoff['outcome']=result.get('outcome',result.get('phase','paused'))
    (out/'handoff.json').write_text(json.dumps(handoff,indent=2,default=str)+'\n')
    print(json.dumps({'phase':result.get('phase'),'outcome':result.get('outcome'),'interrupts':str(result.get('__interrupt__',[]))}))

if __name__=='__main__':main()
