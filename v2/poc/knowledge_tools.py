"""Attach the managed read-only knowledge MCP server at the Goose parent boundary.
Summon children inherit parent extensions; recipe-only wiring is insufficient.
"""
import json,shlex,sys
from pathlib import Path
from . import knowledge

class KnowledgeUnavailable(RuntimeError):pass

def require_ready():
    root=knowledge.home()
    if not (root/'base.json').exists() and not (root/'settings.json').exists():return
    cfg=knowledge.read(root/'settings.json',{})
    if not cfg.get('python') or not Path(cfg['python']).is_file():
        raise KnowledgeUnavailable('Knowledge runtime is not provisioned; run flow knowledge setup/configure, then process. No agent was launched.')
    try:knowledge.snapshot(root)
    except Exception as error:raise KnowledgeUnavailable(str(error)+'; no agent was launched') from error
    import subprocess
    try:
        check=subprocess.run([cfg['python'],'-c','from poc.knowledge_runtime.policy import verify_compatibility; verify_compatibility(); import cocoindex'],cwd=knowledge.REPO/'v2',env=knowledge.clean_env(root),capture_output=True,text=True,timeout=30)
    except (OSError,subprocess.TimeoutExpired) as error:raise KnowledgeUnavailable('Knowledge dependency check failed; no agent was launched: '+str(error)) from error
    if check.returncode:raise KnowledgeUnavailable('Pinned Basic Memory/CocoIndex unavailable: '+check.stderr[-2000:])

def attach(cmd,env):
    require_ready()
    root=knowledge.home();cfg=knowledge.read(root/'settings.json',{})
    if not cfg.get('python') or not knowledge.read(root/'CURRENT.json'):
        print('Flow knowledge unavailable/pending: '+json.dumps(knowledge.status(root)),file=sys.stderr)
        return cmd,env
    # Goose --with-extension uses shell command text. Quote every argument.
    command=shlex.join([cfg['python'],str(Path(__file__).with_name('knowledge_runtime')/'stdio.py'),str(root)])
    return [*cmd,'--with-extension',command],{**env,'FLOW_KNOWLEDGE_HOME':str(root),'FLOW_KNOWLEDGE_READONLY':'1','PYTHONPATH':str(knowledge.REPO/'v2')}
