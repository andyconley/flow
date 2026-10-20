"""Attach the managed read-only knowledge MCP server at the Goose parent boundary.
Summon children inherit parent extensions; recipe-only wiring is insufficient.
"""
import json,shlex,sys
from pathlib import Path
from . import knowledge

def attach(cmd,env):
    root=knowledge.home();cfg=knowledge.read(root/'settings.json',{})
    if not cfg.get('python') or not knowledge.read(root/'CURRENT.json'):
        print('Flow knowledge unavailable/pending: '+json.dumps(knowledge.status(root)),file=sys.stderr)
        return cmd,env
    # Goose --with-extension uses shell command text. Quote every argument.
    command=shlex.join([cfg['python'],'-m','poc.knowledge_runtime.server'])
    return [*cmd,'--with-extension',command],{**env,'FLOW_KNOWLEDGE_HOME':str(root),'PYTHONPATH':str(knowledge.REPO/'v2')}
