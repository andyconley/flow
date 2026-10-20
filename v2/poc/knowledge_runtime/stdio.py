"""Absolute-path MCP entrypoint: ACP clients need not inherit custom environment.
Only read-only knowledge tools are exposed; writes go to native per-run scratch.
"""
import os,sys
from pathlib import Path
sys.dont_write_bytecode=True
if len(sys.argv)!=2:raise SystemExit('usage: stdio.py KNOWLEDGE_HOME')
os.environ['FLOW_KNOWLEDGE_HOME']=str(Path(sys.argv[1]).resolve())
os.environ['FLOW_KNOWLEDGE_READONLY']='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from poc.knowledge_runtime.server import mcp
mcp.run(transport='stdio',show_banner=False)
