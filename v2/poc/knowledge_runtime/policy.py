from __future__ import annotations
import hashlib,importlib.metadata,json,os,inspect,re
from pathlib import Path
START='<!-- cocoindex:relationships:v1 -->'
END='<!-- /cocoindex:relationships:v1 -->'
LABEL='## Original guidance'
class PolicyError(RuntimeError):pass

def verify_compatibility(installed_version=None,package_root=None):
    pin=json.loads(Path(__file__).with_name('compatibility.json').read_text())
    actual=installed_version or importlib.metadata.version('basic-memory')
    if actual!=pin['version']:raise PolicyError(f'Unsupported Basic Memory {actual}; managed adapter requires exactly {pin["version"]}. Re-audit and test before upgrading.')
    package_root=package_root or Path(importlib.metadata.distribution('basic-memory').locate_file('basic_memory'))
    actual_files={str(p.relative_to(package_root)) for p in package_root.rglob('*.py')}
    if actual_files!=set(pin['python_sources_sha256']):raise PolicyError('Basic Memory source-file inventory changed; adapter review required')
    for name,expected in pin['python_sources_sha256'].items():
        if hashlib.sha256((package_root/name).read_bytes()).hexdigest()!=expected:raise PolicyError('Basic Memory audited source changed: '+name)
    return pin['version']

def authored_text(text):
    # Full accepted Markdown and body-only strings both occur in BM's indexing paths.
    import frontmatter
    text=frontmatter.loads(text).content if text.startswith('---\n') else text
    versions=re.findall(r'<!-- /?cocoindex:relationships:([^ >]+) -->',text)
    if any(v!='v1' for v in versions):raise PolicyError('Unsupported generated section version; only v1 is supported')
    count=(text.count(START),text.count(END))
    if count!=(0,0):
        if count!=(1,1):raise PolicyError('Malformed generated section: require one start and one end marker')
        a=text.index(START);b=text.index(END)
        if b<a:raise PolicyError('Generated section markers are reversed')
        if (a and text[a-1]!='\n') or (b and text[b-1]!='\n'):raise PolicyError('Generated markers must start on their own lines')
        text=text[:a]+text[b+len(END):]
    # Presentation heading is not guidance. Other text outside the owned block is authored.
    lines=text.splitlines()
    if LABEL in lines:lines.remove(LABEL)
    return '\n'.join(lines).strip()

def allowed_features(text):
    from basic_memory.markdown.entity_parser import parse
    parsed=parse(authored_text(text))
    return ({(o.category or 'Note',o.content) for o in parsed.observations},
            {(r.type,r.target) for r in parsed.relations})

class EntityProjection:
    def __init__(self,entity,raw):
        self.entity=entity;obs,rels=allowed_features(raw)
        self.observations=[o for o in entity.observations if (o.category or 'Note',o.content) in obs]
        self.outgoing_relations=[r for r in entity.outgoing_relations if (r.relation_type,r.to_name) in rels]
    def __getattr__(self,name):return getattr(self.entity,name)

def validate_search_rows(rows,relation_keys=None):
    """Gate vector source rows against their own authored entity projection.
    FTS writes already pass the service shim; this rejects contaminated stock rebuilds.
    """
    for entity_id,group in rows.items():
        base=next((r for r in group if r.type=='entity'),None)
        if base is None:continue # deleted/empty entities are legitimate vector cleanup jobs
        if authored_text(base.content_snippet or '')!=(base.content_snippet or '').strip():raise PolicyError(f'Unmanaged generated text in vector source entity {entity_id}; run managed repair')
        obs,rels=allowed_features(base.content_snippet or '')
        for row in group:
            if row.type=='observation' and (row.category or 'Note',row.content_snippet or '') not in obs:raise PolicyError('Generated observation reached vector source; run managed repair')
            # Relation source rows lack to_name. Their permalink ends in the target permalink.
            if row.type=='relation' and (relation_keys or {}).get(row.id) not in rels:raise PolicyError('Non-authored relation reached vector source; run managed repair')

def trace(event,**fields):
    if not os.environ.get('FLOW_BM_TRACE'):return
    callers=[{'file':Path(f.filename).name,'function':f.function} for f in inspect.stack(context=0)[2:14] if '/basic_memory/' in f.filename]
    with Path(os.environ['FLOW_BM_TRACE']).open('a') as out:out.write(json.dumps({'event':event,'callers':callers,**fields})+'\n')

def install():
    verify_compatibility() # Deliberately version/source locked; not an arbitrary-version patch.
    from basic_memory.services.search_service import SearchService
    from basic_memory.repository import semantic_vector_sync
    if getattr(SearchService,'_flow_managed_projection',False):return
    original_data=SearchService.index_entity_data
    original_markdown=SearchService.index_entity_markdown
    original_fetch=semantic_vector_sync.fetch_prepare_window_source_rows
    async def data(self,entity,content=None):
        trace('index_entity_data',entity_id=entity.id,path=entity.file_path,supplied_content=content is not None)
        if entity.is_markdown:
            if content is None:content=await self.file_service.read_entity_content(entity)
            authored_text(content or '') # validate BEFORE BM deletes the old FTS projection
        return await original_data(self,entity,content)
    async def markdown(self,entity,content=None):
        if content is None:content=await self.file_service.read_entity_content(entity)
        projected=EntityProjection(entity,content or '')
        trace('index_entity_markdown',entity_id=entity.id,authored_observations=len(projected.observations),authored_relations=len(projected.outgoing_relations))
        return await original_markdown(self,projected,authored_text(content or ''))
    async def fetch(repository,session,entity_ids):
        rows=await original_fetch(repository,session,entity_ids)
        from sqlalchemy import text
        result=await session.execute(text('SELECT id,relation_type,to_name FROM relation WHERE project_id=:pid'),{'pid':repository.project_id})
        relation_keys={r.id:(r.relation_type,r.to_name) for r in result}
        validate_search_rows(rows,relation_keys);trace('vector_source_gate',entity_ids=entity_ids);return rows
    SearchService.index_entity_data=data
    SearchService.index_entity_markdown=markdown
    semantic_vector_sync.fetch_prepare_window_source_rows=fetch
    SearchService._flow_managed_projection=True
