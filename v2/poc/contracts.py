from pathlib import Path
import hashlib,json,os
os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK","true")
from typing import TypedDict

class State(TypedDict,total=False):
 brief_ref:dict
 context_ref:dict
 approval_ref:dict
 assignment_ref:dict
 assignment_refs:dict
 result_ref:dict
 result_refs:dict
 decision_refs:list
 work_id:str
 deadline:float
 task:str
 project_context:str
 candidate_revision:str
 outcome:str
 findings:list
 test_results:dict
 corrections:int
 max_corrections:int
 resume_stage:str
 pending_kind:str
 resume_epoch:int
 recommendation:str
 job_id:str
 inputs:str
 approved:str
 workspace:str
 attempt:int
 phase:str
 candidate:str
 check:dict
 review:dict
 result:dict
 candidate_reused:bool
 max_attempts:int
 failure:str

def digest_tree(root):
 root=Path(root); records=[]
 for p in sorted(root.rglob('*')):
  if p.is_file() and not any(x in p.relative_to(root).parts for x in ('.git','.glg','__pycache__')):
   records.append((str(p.relative_to(root)),hashlib.sha256(p.read_bytes()).hexdigest()))
 return hashlib.sha256(json.dumps(records).encode()).hexdigest()

def fixture_digest(root):
 return digest_tree(root)


def approved_input_digest(root):
 root=Path(root)
 return hashlib.sha256((digest_tree(root/'fixtures')+digest_tree(root/'trusted')).encode()).hexdigest()


def task_input_digest(task, workspace, project_context=''):
 return hashlib.sha256(json.dumps({'task':task,'workspace':str(Path(workspace).resolve()),'project_context':project_context},sort_keys=True).encode()).hexdigest()
