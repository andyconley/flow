from pathlib import Path
import json,subprocess,os,hashlib,re
R=Path('/Users/andyconley/Documents/Codex/2026-10-14/task');C=R/'flow-verification';B=Path('/Users/andyconley/Documents/Codex/2026-10-12/task-3/flow');P='/Users/andyconley/.flow/runtimes/openhands/1.54.0-0d3941a/venv/bin/python'
old=Path('/tmp/flow-review-reliability-aggregate.log').read_text();names=re.findall(r'^FAIL: (\S+) \(tests.test_flow.FlowCliTests\.\1\)',old,re.M);names=[n for n in names if n!='test_release_staging_requires_every_real_cli_sibling'];assert len(names)==19
E=C/'docs/evidence/review-reliability';same={f:hashlib.sha256((C/f).read_bytes()).hexdigest()==hashlib.sha256((B/f).read_bytes()).hexdigest() for f in ['cli/openhands_provision.py','install-flow.sh','install.sh','runtime/openhands/requirements.txt']}
code="import sys;sys.path.insert(0,'cli');import openhands_provision as p;print(p.ready(sys.executable))"
checks={}
for label,repo in [('baseline',B),('candidate',C)]:
 checks[label]={}
 for route,python in [('original_base','/opt/homebrew/bin/python3.12'),('existing_pinned',P)]:
  q=subprocess.run([python,'-c',code],cwd=repo,capture_output=True,text=True,env={**os.environ,'LITELLM_LOCAL_MODEL_COST_MAP':'True','OPENHANDS_SUPPRESS_BANNER':'1'});checks[label][route]={'exit':q.returncode,'ready':q.stdout.strip(),'stderr':q.stderr[-500:]}
(E/'aggregate-gap-diagnosis.json').write_text(json.dumps({'previous_failures':names,'unchanged_provisioning_sources':same,'readiness_probes':checks,'supported_route':'FLOW_PYTHON selects the already provisioned pinned SDK interpreter; no package installation needed.','incorrect_module':'tests.test_runstate does not exist; lifecycle tests reside in tests.test_flow, test_openhands_workflow and test_openhands_lifecycle.','network':'Restricted; no bypass or permission expansion.'},indent=2)+'\n')
Path('/tmp/flow-provisioning-failed-names.json').write_text(json.dumps(names))
print(json.dumps({'unchanged_sources':same,'readiness':checks,'count':len(names)},indent=2))
