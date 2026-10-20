"""Read-only agent tools, last known-good snapshot plus local reconciliation."""
import threading,time
from fastmcp import FastMCP
from .. import knowledge
root=knowledge.home();stop=threading.Event()
def reconcile():
    while not stop.wait(2):
        try:knowledge.trigger(root)
        except Exception:pass # Report exact state through the status tool.
mcp=FastMCP('Flow local knowledge')
@mcp.tool()
def knowledge_status()->dict:
    """Show pending/failed processing and the known-good snapshot agents are using."""
    return knowledge.status(root)
@mcp.tool()
def search_cards(query:str,mode:str='hybrid',role:str|None=None)->dict:
    """Search authored guidance only. Optional exact role scope; no recency filter."""
    return knowledge.query(root,query,mode,role)
@mcp.tool()
def traverse_cards(permalink:str,relation_type:str='complements',depth:int=2)->dict:
    """Follow real typed BM edges FROM containing note, returning authored neighbor content, all time."""
    return knowledge.graph(root,permalink,relation_type,depth)
if __name__=='__main__':
    threading.Thread(target=reconcile,daemon=True).start()
    try:mcp.run(transport='stdio',show_banner=False)
    finally:stop.set()
