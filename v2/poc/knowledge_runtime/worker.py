"""Explicit private BM startup shim. Never imported by the ordinary Flow runtime."""
import json,os,sys
from pathlib import Path
from .policy import verify_compatibility,install,authored_text
verify_compatibility()
stage=Path(os.environ['FLOW_KNOWLEDGE_STAGE']).resolve();cache=Path(os.environ['FLOW_KNOWLEDGE_CACHE'])
os.environ.update(BASIC_MEMORY_CONFIG_DIR=str(stage/'config'),BASIC_MEMORY_HOME=str(stage/'notes'),HOME=str(stage/'home'),BASIC_MEMORY_SEMANTIC_EMBEDDING_CACHE_DIR=str(cache),BASIC_MEMORY_DEFAULT_SEARCH_TYPE='text',BASIC_MEMORY_SEMANTIC_SEARCH_ENABLED='true',BASIC_MEMORY_SEMANTIC_EMBEDDING_PROVIDER='fastembed',BASIC_MEMORY_SEMANTIC_EMBEDDING_MODEL='BAAI/bge-small-en-v1.5',BASIC_MEMORY_SEMANTIC_EMBEDDING_DIMENSIONS='384',HF_HUB_OFFLINE='1',COCOINDEX_DB=str(stage/'state/cocoindex'),FLOW_BM_TRACE=str(stage/'index-trace.jsonl'))
import onnxruntime
onnxruntime.disable_telemetry_events()
action=sys.argv[1]
if action=='build':
    from . import enrich
    enrich.run()
    (stage/'config').mkdir(exist_ok=True)
    config={'projects':{'managed':{'path':str(stage/'notes'),'mode':'local'}},'default_project':'managed','database_backend':'sqlite','semantic_search_enabled':True,'semantic_vector_index':'pgvector','semantic_embedding_provider':'fastembed','semantic_embedding_model':'BAAI/bge-small-en-v1.5','semantic_embedding_dimensions':384,'semantic_embedding_cache_dir':str(cache),'ensure_frontmatter_on_sync':False,'auto_update':False,'cloud_promo_opt_out':True,'logfire_enabled':False,'logfire_send_to_logfire':False,'default_search_type':'text'}
    (stage/'config/config.json').write_text(json.dumps(config))
    install()
    from basic_memory.cli.main import app
    app(['reindex','-p','managed','--full'],standalone_mode=False)
    from .audit import audit
    (stage/'audit.json').write_text(json.dumps(audit(stage)))
elif action=='query':
    cfg=json.loads((stage/'config/config.json').read_text());cfg['projects']['managed']['path']=str(stage/'notes');cfg['skip_initialization_sync']=True
    (stage/'config/config.json').write_text(json.dumps(cfg))
    install()
    from basic_memory.cli.main import app
    import contextlib,io
    mode=sys.argv[3]
    if mode not in ('text','vector','hybrid'):raise ValueError('Invalid search mode')
    args=['tool','search-notes',sys.argv[2],'--project','managed','--local','--json','--entity-type','entity','--page-size','5']
    if mode!='text':args+=['--'+mode]
    if sys.argv[4]:args+=['--meta','role='+sys.argv[4]]
    out=io.StringIO()
    with contextlib.redirect_stdout(out):app(args,standalone_mode=False)
    data=json.loads(out.getvalue())
    for item in data.get('results',[]):
        item.pop('matched_chunk',None)
        name=Path(item.get('file_path','')).name
        if name and (stage/'notes'/name).exists():item['content']=authored_text((stage/'notes'/name).read_text())
    (stage/'result.json').write_text(json.dumps(data,default=str))
else:raise ValueError('Unknown worker action')
