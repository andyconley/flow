"""Absolute-path MCP entrypoint: ACP clients need not inherit custom environment.
Only read-only knowledge tools are exposed; writes go to native per-run scratch.
"""
import os,sys,importlib.util
from pathlib import Path
sys.dont_write_bytecode=True
worker_mode=len(sys.argv)>2 and sys.argv[1]=='--worker'
if not worker_mode:
    if len(sys.argv)!=2:raise SystemExit('usage: stdio.py KNOWLEDGE_HOME | --worker ACTION')
    os.environ['FLOW_KNOWLEDGE_HOME']=str(Path(sys.argv[1]).resolve())
os.environ['FLOW_KNOWLEDGE_READONLY']='1'
# Import the explicitly allowed package directly: discovering it through v2
# would require reading a parent directory the native sandbox intentionally denies.
package = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('poc', package/'__init__.py', submodule_search_locations=[str(package)])
module = importlib.util.module_from_spec(spec)
sys.modules['poc'] = module
spec.loader.exec_module(module)
if worker_mode:
    import runpy
    sys.argv=[str(package/'knowledge_runtime/worker.py'),*sys.argv[2:]]
    runpy.run_module('poc.knowledge_runtime.worker',run_name='__main__')
else:
    from poc.knowledge_runtime.server import mcp
    mcp.run(transport='stdio',show_banner=False)
