"""Durable authored knowledge, guarded jobs and atomically selected BM snapshots.
This supervisor uses only the standard library. Heavy dependencies live in a separate
explicitly configured environment; no dependency installation happens on agent launch.
"""
from __future__ import annotations
import argparse,contextlib,fcntl,hashlib,json,os,shutil,subprocess,sys,tempfile,time,uuid,zipfile
from pathlib import Path

REPO=Path(__file__).resolve().parents[2]
SHARED=REPO/'knowledge'
PIPELINE='flow-knowledge-1'
START='<!-- cocoindex:relationships:v1 -->'
END='<!-- /cocoindex:relationships:v1 -->'

def home():return Path(os.environ.get('FLOW_KNOWLEDGE_HOME',str(Path.home()/'.flow/v2/state/knowledge'))).absolute()
def read(p,default=None):return json.loads(p.read_text()) if p.exists() else default
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix(p.suffix+'.tmp')
    payload=(json.dumps(value,indent=2)+'\n').encode()
    with t.open('wb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
    record_install_write(p,payload)
    t.replace(p)
def record_install_write(path,intended):
    """Audit intended bytes, never a reread that could claim concurrent edits."""
    root=os.environ.get("FLOW_INSTALL_KNOWLEDGE_ROOT");receipt=os.environ.get("FLOW_INSTALL_WRITE_RECEIPT")
    if not root or not receipt:return
    path=Path(path);root=Path(root)
    if not path.is_relative_to(root):return
    rel=path.relative_to(root)
    if not (len(rel.parts)==1 and path.suffix==".json" or rel.parts[0] in ("notes","incoming")):return
    values=read(Path(receipt),{});values[str(rel)]=digest(intended) if intended is not None else None
    temp=Path(receipt+".tmp");temp.write_text(json.dumps(values));temp.replace(receipt)
def digest(data):return hashlib.sha256(data).hexdigest()
def source(text):
    # Retain frontmatter and every authored byte; exclude only the managed block.
    import re
    if any(v!='v1' for v in re.findall(r'<!-- /?cocoindex:relationships:([^ >]+) -->',text)):raise ValueError('Unsupported generated marker version')
    if START not in text and END not in text:return text
    if text.count(START)!=1 or text.count(END)!=1 or text.index(END)<text.index(START):raise ValueError('Malformed generated markers')
    a=text.index(START);b=text.index(END)+len(END)
    return text[:a]+text[b:].removeprefix('\n')
def inventory(folder):
    result={}
    if folder.is_symlink():raise ValueError('Symlink knowledge root refused')
    for p in sorted(folder.rglob('*')):
        if p.is_symlink():raise ValueError('Symlink knowledge path refused: '+str(p))
        if p.is_file() and p.suffix=='.md':
            if p.parent!=folder:raise ValueError('Knowledge cards must be flat .md files')
            result[p.name]=p.read_bytes()
    return result
@contextlib.contextmanager
def locked(root,nonblocking=False):
    root.mkdir(parents=True,exist_ok=True)
    if root.is_symlink():raise ValueError('Symlink knowledge home refused')
    delegated=os.environ.get('FLOW_INSTALL_KNOWLEDGE_FD')
    valid=False
    if delegated:
        try:
            fd=int(delegated);info=os.fstat(fd);target=(root/'lock').stat()
            valid=(info.st_dev,info.st_ino)==(target.st_dev,target.st_ino)
        except (ValueError,OSError):pass
    if valid:
        yield fd;return
    with (root/'lock').open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX|(fcntl.LOCK_NB if nonblocking else 0));yield f.fileno()

def backup(root,label):
    name=str(time.time_ns())+'-'+label+'.zip';p=root/'backups'/name;p.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in inventory(root/'notes').items():z.writestr('notes/'+n,b)
        for n in ('base.json','settings.json','native-transport.json','provisioned-runtime.json','provisioning-status.json','status.json','CURRENT.json'):
            if (root/n).exists():z.write(root/n,n)
    return p

def reconcile_shared(root,shared=SHARED):
    manifest=read(shared/'manifest.json');incoming=inventory(shared/'cards')
    if not manifest or manifest.get('schema')!=1 or {n:digest(b) for n,b in incoming.items()}!=manifest['files']:raise ValueError('Shared corpus manifest mismatch')
    import re
    if not isinstance(manifest.get('version'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*',manifest['version']):raise ValueError('Invalid corpus version')
    if any(source(b.decode())!=b.decode() for b in incoming.values()):raise ValueError('Shared corpus must contain authored text only')
    (root/'notes').mkdir(parents=True,exist_ok=True)
    local=inventory(root/'notes');base=read(root/'base.json',{'files':{}})['files'];conflicts=[]
    backup(root,'before-fetch')
    newbase=dict(base)
    for n in sorted(set(base)|set(incoming)):
        old=base.get(n);actual=digest(source(local[n].decode()).encode()) if n in local else None
        # Shared corpus contains authored text only. Preserve local edits and deletions.
        new=digest(incoming[n]) if n in incoming else None
        if actual==new:newbase[n]=new;continue
        if new==old:continue # No upstream change: local edits/deletions are not conflicts.
        if actual==old:
            record_install_write(root/'notes'/n,incoming.get(n))
            if n in incoming:(root/'notes'/n).write_bytes(incoming[n]);newbase[n]=new
            else:(root/'notes'/n).unlink(missing_ok=True);newbase.pop(n,None)
        elif old is None and n not in local:
            record_install_write(root/'notes'/n,incoming[n])
            (root/'notes'/n).write_bytes(incoming[n]);newbase[n]=new
        else:
            conflicts.append(n)
            folder=root/'incoming'/manifest['version'];folder.mkdir(parents=True,exist_ok=True)
            if n in incoming:
                record_install_write(folder/n,incoming[n]);(folder/n).write_bytes(incoming[n])
    write(root/'base.json',{'version':manifest['version'],'files':newbase,'conflicts':conflicts})
    return {'version':manifest['version'],'conflicts':conflicts}

def fetch_shared(root,ref):
    """Fetch this one subcomponent at an exact resolved Git commit, no credentials."""
    if not ref or ref.startswith('-') or any(c.isspace() for c in ref):raise ValueError('Invalid knowledge ref')
    repo=root/'shared.git'
    env={k:v for k,v in clean_env(root).items() if k not in ('GIT_ASKPASS','SSH_ASKPASS','GIT_CONFIG','GIT_CONFIG_GLOBAL','GIT_CONFIG_SYSTEM')}
    env.update(GIT_TERMINAL_PROMPT='0',GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
    if not repo.exists():subprocess.run(['git','init','--bare',str(repo)],check=True,env=env,capture_output=True)
    base=['git','-c','credential.helper=','--git-dir',str(repo)]
    subprocess.run([*base,'fetch','--depth=1','https://github.com/andyconley/flow.git',ref],check=True,env=env,capture_output=True,timeout=120)
    commit=subprocess.check_output([*base,'rev-parse','FETCH_HEAD'],env=env,text=True).strip()
    listing=subprocess.check_output([*base,'ls-tree','-r','--name-only',commit,'--','knowledge/manifest.json','knowledge/cards'],env=env,text=True).splitlines()
    dest=root/'fetched'/commit;dest.mkdir(parents=True,exist_ok=True)
    for name in listing:
        rel=Path(name).relative_to('knowledge')
        if '..' in rel.parts:raise ValueError('Unsafe fetched path')
        target=dest/rel;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(subprocess.check_output([*base,'show',commit+':'+name],env=env))
    write(root/'fetch-receipt.json',{'commit':commit,'ref':ref})
    return dest

def local_model_digest(endpoint,model):
    import urllib.request
    from urllib.parse import urlparse
    u=urlparse(endpoint)
    if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):raise ValueError('Only unauthenticated loopback Ollama is supported')
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(endpoint+'/api/tags',timeout=2) as response:models=json.load(response)['models']
    found=[m['digest'] for m in models if m.get('name')==model or m.get('model')==model]
    if len(found)!=1:raise ValueError('Configured local model not installed; no automatic model download: '+model)
    return found[0]

def fingerprint(root):
    cfg=read(root/'settings.json',{})
    authored={n:digest(b) for n,b in inventory(root/'notes').items()}
    if cfg.get('model_digest'):
        cfg={**cfg,'observed_model_digest':local_model_digest(cfg['ollama'],cfg['model'])}
    # Include all pipeline code and pins, not just a manually bumped number.
    code=[Path(__file__),*sorted(Path(__file__).with_name('knowledge_runtime').glob('*.py')),Path(__file__).with_name('knowledge_runtime')/'compatibility.json',SHARED/'requirements.lock',SHARED/'embedding.lock.json']
    return digest(json.dumps({'pipeline':PIPELINE,'code':{p.name:digest(p.read_bytes()) for p in code},'settings':cfg,'authored':authored},sort_keys=True).encode())
def status(root):
    from .knowledge_health import hint
    state={**read(root/'status.json',{'state':'pending','reason':'not processed'}),'provisioning':hint(root),'installation':read(root/'install-status.json',{}),'last_install_failure':read(root/'last-install-failure.json',{})}
    current=read(root/'CURRENT.json',{})
    if current and state.get('fingerprint')==current.get('fingerprint') and state.get('state')!='ready':
        receipt=read(root/'generations'/current['generation']/'receipt.json',{})
        if receipt.get('fingerprint')==current['fingerprint'] and receipt.get('audit',{}).get('passed'):
            state={**state,'state':'ready','generation':current['generation'],'recovered_publication':True}
    if os.environ.get('FLOW_KNOWLEDGE_READONLY')=='1':
        current=read(root/'CURRENT.json',{})
        return {**state,'pending':state.get('state')!='ready' or state.get('fingerprint')!=current.get('fingerprint'),'snapshot':current.get('generation'),'reconciliation_owner':'Flow supervisor'}
    try:
        desired=fingerprint(root);current=read(root/'CURRENT.json',{})
        state={**state,'pending':current.get('fingerprint')!=desired,'desired':desired,'snapshot':current.get('generation')}
    except Exception as e:state={**state,'pending':True,'input_error':str(e)}
    return state

def clean_env(root):
    env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ('TOKEN','SECRET','PASSWORD','API_KEY'))}
    env.update(PYTHONPYCACHEPREFIX=str(root/'home/pycache'),HOME=str(root/'home'),COCOINDEX_DISABLE_USAGE_TRACKING='1',BASIC_MEMORY_CLOUD_MODE='false',BASIC_MEMORY_CLOUD_PROMO_OPT_OUT='true',BASIC_MEMORY_AUTO_UPDATE='false',BASIC_MEMORY_LOGFIRE_ENABLED='false',BASIC_MEMORY_LOGFIRE_SEND_TO_LOGFIRE='false',HF_HUB_OFFLINE='1',DO_NOT_TRACK='1',PYTHONPATH=str(REPO/'v2'))
    return env

def worker_command(root,stage,action,*args):
    cfg=read(root/'settings.json',{})
    python=cfg.get('python')
    if not python or not Path(python).is_file():raise RuntimeError('Knowledge runtime not configured: flow knowledge configure --python /path/to/isolated/python --cache /path/to/cached/embeddings --model qwen3:4b')
    scratch=stage if action=='query' else root
    env=clean_env(scratch);env.update(FLOW_KNOWLEDGE_HOME=str(root),FLOW_KNOWLEDGE_STAGE=str(stage),FLOW_KNOWLEDGE_MODEL=cfg.get('model','qwen3:4b'),FLOW_KNOWLEDGE_OLLAMA=cfg.get('ollama','http://127.0.0.1:11434'),FLOW_KNOWLEDGE_CACHE=cfg['cache'])
    log=stage/'worker.log';stage.mkdir(parents=True,exist_ok=True);(scratch/'home').mkdir(exist_ok=True)
    with log.open('a') as f:
        child=subprocess.Popen([python,'-m','poc.knowledge_runtime.worker',action,*args],cwd=REPO/'v2',env=env,stdout=f,stderr=f,start_new_session=True)
        write(stage/'worker.json',{'pid':child.pid,'action':action,'state':'running'})
        try:code=child.wait(timeout=900)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            raise RuntimeError('Knowledge worker timed out; process group stopped')
        write(stage/'worker.json',{'pid':child.pid,'action':action,'state':'exited','exit':code})
        if code:raise RuntimeError(f'Knowledge {action} failed ({code}); see {log}')

def process(root,builder=None):
    """Single writer. Crash leaves private staging; CURRENT is the sole commit point."""
    with locked(root,True):
        wanted=fingerprint(root);current=read(root/'CURRENT.json',{})
        if current.get('fingerprint')==wanted:return status(root)
        previous=read(root/'status.json',{})
        ident=str(time.time_ns())+'-'+uuid.uuid4().hex[:8];stage=root/'generations'/ident
        saved=backup(root,'before-enrichment')
        write(root/'status.json',{'state':'running','fingerprint':wanted,'generation':ident,'backup':str(saved),'recovered_interrupted_run':previous.get('state')=='running'})
        try:
            before=inventory(root/'notes');stage.mkdir(parents=True);shutil.copytree(root/'notes',stage/'notes')
            for n in ('logs','state','backups'):(stage/n).mkdir()
            # Never accept manual edits in an owned generated block silently.
            hashes=read(root/'generated-hashes.json',{})
            for n,b in before.items():
                text=b.decode();source(text)
                if START in text:
                    block=text[text.index(START):text.index(END)+len(END)]
                    if hashes.get(n)!=digest(block.encode()):raise ValueError('Manual edit in generated block: '+n+'; backup retained')
            write(stage/'state/generated-hashes.json',hashes)
            if builder:result=builder(stage)
            else:
                worker_command(root,stage,'build');result=read(stage/'audit.json')
            if not result or not result.get('passed') or result.get('unresolved_edges'):raise ValueError('Snapshot audit failed or unresolved graph endpoints')
            after=inventory(stage/'notes')
            if set(before)!=set(after) or any(source(before[n].decode())!=source(after[n].decode()) for n in before):raise ValueError('Enrichment changed authored content or inventory')
            if inventory(root/'notes')!=before or fingerprint(root)!=wanted:raise ValueError('Inputs changed during build; keep previous snapshot and retry')
            # Local working notes remain authoritative authored files. Managed output
            # lives in the same note inside this immutable published generation.
            write(stage/'receipt.json',{'fingerprint':wanted,'audit':result,'backup':str(saved)})
            write(root/'CURRENT.json',{'generation':ident,'fingerprint':wanted})
            write(root/'status.json',{'state':'ready','fingerprint':wanted,'generation':ident,'finished':time.time()})
            return status(root)
        except BaseException as e:
            write(root/'status.json',{'state':'failed','fingerprint':wanted,'generation':ident,'error':str(e),'backup':str(saved),'previous_snapshot':current.get('generation')})
            raise

def trigger(root):
    """Debounced by writer lock and fingerprint, also reconciled on every read."""
    s=status(root)
    if not s['pending'] or s.get('input_error'):return s
    try:
        with locked(root,True):pass
    except BlockingIOError:return s
    # A failed fingerprint is retried only explicitly or after a real edit/version change.
    if s.get('state')=='failed' and s.get('fingerprint')==s.get('desired'):return s
    root.mkdir(parents=True,exist_ok=True)
    with (root/'supervisor.log').open('a') as log:
        subprocess.Popen([sys.executable,'-m','poc.knowledge','--home',str(root),'process'],cwd=REPO/'v2',stdout=log,stderr=log,env={**os.environ,'PYTHONPATH':str(REPO/'v2')},start_new_session=True)
    return s

def snapshot(root):
    current=read(root/'CURRENT.json')
    if not current:raise RuntimeError('No successful knowledge snapshot; flow knowledge status/process')
    generation=current['generation']
    if '/' in generation or generation.startswith('.'):raise ValueError('Unsafe snapshot selector')
    p=root/'generations'/generation
    if not read(p/'receipt.json',{}).get('audit',{}).get('passed'):raise ValueError('Snapshot not audited')
    return p

def query(root,query,mode='hybrid',role=None):
    if os.environ.get('FLOW_KNOWLEDGE_READONLY')!='1':trigger(root)
    p=snapshot(root)
    # Native BM CLI can write initialization metadata; private per-read copy keeps
    # published generations immutable even when multiple agents read concurrently.
    with tempfile.TemporaryDirectory(prefix='flow-knowledge-query-') as t:
        stage=Path(t);shutil.copytree(p/'notes',stage/'notes');shutil.copytree(p/'config',stage/'config')
        worker_command(root,stage,'query',query,mode,role or '')
        return read(stage/'result.json')

def graph(root,start,kind='complements',depth=2):
    import sqlite3
    if kind not in ('complements','reinforces'):raise ValueError('Unsupported relation type')
    if os.environ.get('FLOW_KNOWLEDGE_READONLY')!='1':trigger(root)
    p=snapshot(root);depth=max(1,min(3,int(depth)))
    with sqlite3.connect('file:'+str(p/'config/memory.db')+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        edges=c.execute('''WITH RECURSIVE walk(id,depth,path) AS (
        SELECT id,0,','||id||',' FROM entity WHERE permalink=?
        UNION ALL SELECT r.to_id,w.depth+1,w.path||r.to_id||',' FROM walk w JOIN relation r ON r.from_id=w.id
        WHERE r.relation_type=? AND r.to_id IS NOT NULL AND w.depth<? AND instr(w.path,','||r.to_id||',')=0)
        SELECT DISTINCT a.permalink AS from_note,b.permalink AS to_note,r.relation_type,w.depth+1 AS depth,
        a.file_path AS containing_note,b.file_path AS target_note FROM walk w JOIN relation r ON r.from_id=w.id
        JOIN entity a ON a.id=r.from_id JOIN entity b ON b.id=r.to_id WHERE r.relation_type=? AND w.depth<?''',(start,kind,depth,kind,depth)).fetchall()
        result=[]
        for row in edges:
            item=dict(row);item['target_content']=source((p/'notes'/item['target_note']).read_text());result.append(item)
        return {'snapshot':p.name,'timeframe':None,'edges':result}

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--home',type=Path,default=home());sub=parser.add_subparsers(dest='action',required=True)
    for name in ('seed','status','process','watch','export'):sub.add_parser(name)
    health=sub.add_parser('doctor')
    for option in ('python','cache','model','ollama'):health.add_argument('--'+option)
    setup=sub.add_parser('setup');setup.add_argument('--python',default=sys.executable);modes=setup.add_mutually_exclusive_group();modes.add_argument('--wheelhouse',type=Path);modes.add_argument('--download',action='store_true');setup.add_argument('--rebuild-runtime',action='store_true');setup.add_argument('--model');setup.add_argument('--ollama')
    c=sub.add_parser('configure');c.add_argument('--python',required=True);c.add_argument('--cache',required=True);c.add_argument('--model',default='qwen3:4b');c.add_argument('--ollama',default='http://127.0.0.1:11434')
    transport=sub.add_parser('namespace-compat');transport.add_argument('mode',choices=('on','off'))
    f=sub.add_parser('fetch');f.add_argument('--from-directory',type=Path);f.add_argument('--ref',default='main')
    w=sub.add_parser('write');w.add_argument('name');w.add_argument('--from-file',type=Path,required=True)
    d=sub.add_parser('delete');d.add_argument('name')
    edit=sub.add_parser('edit');edit.add_argument('name');edit.add_argument('--from-file',type=Path,required=True)
    restore=sub.add_parser('restore');restore.add_argument('archive',type=Path)
    s=sub.add_parser('search');s.add_argument('query');s.add_argument('--mode',choices=('text','vector','hybrid'),default='hybrid');s.add_argument('--role')
    g=sub.add_parser('graph');g.add_argument('permalink');g.add_argument('--type',default='complements');g.add_argument('--depth',type=int,default=2)
    a=parser.parse_args(argv);root=a.home.absolute()
    try:
        if a.action=='doctor':
            from .knowledge_health import doctor
            result=doctor(root,python=a.python,cache=a.cache,model=a.model,ollama=a.ollama)
            print(json.dumps(result,indent=2));return 0 if result['ok'] else 1
        elif a.action=='setup' and not a.wheelhouse:
            from .knowledge_provision import plan,online
            if not a.download:print(json.dumps(plan(),indent=2));return 0
            with locked(root):
                previous={**read(root/'provisioned-runtime.json',{}),**read(root/'settings.json',{})}
                write(root/'provisioning-status.json',{'state':'running','consent':'explicit --download'})
                try:
                    result=online(root,a.python,a.model or previous.get('model','qwen3:4b'),a.ollama or previous.get('ollama','http://127.0.0.1:11434'),rebuild=a.rebuild_runtime)
                except Exception as error:
                    write(root/'provisioning-status.json',{'state':'failed','error':str(error),'retry':'Repeat setup --download after fixing the reported cause; verified files are retained'})
                    raise
                write(root/'provisioning-status.json',{'state':'ready' if result['configured'] else 'awaiting_model','assets_ready':True,'required_model_setup':result.get('required_model_setup')})
            if result['configured']:trigger(root)
            print(json.dumps(result,indent=2));return 0 if result['configured'] else 1
        elif a.action=='setup':
            with locked(root):
                target=root/'runtime'
                if target.exists():raise ValueError('Knowledge runtime exists; stage a new runtime and configure explicitly')
                from .knowledge_provision import wheels
                hashed=wheels(a.wheelhouse,SHARED/'requirements.lock',offline=True)
                env=clean_env(root);env.update(PIP_CONFIG_FILE=os.devnull,PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_NO_INPUT='1')
                subprocess.run([a.python,'-m','venv',str(target)],check=True,env=env)
                subprocess.run([str(target/'bin/python'),'-m','pip','--isolated','install','--no-index','--find-links',str(a.wheelhouse),'--require-hashes','--no-deps','-r',str(hashed)],check=True,env=env)
                subprocess.run([str(target/'bin/python'),'-m','pip','check'],check=True,env=env)
                result={'python':str(target/'bin/python'),'next':'flow knowledge configure --python this-path --cache local-embedding-cache --model local-model'}
        elif a.action=='configure':
            from urllib.parse import urlparse
            u=urlparse(a.ollama)
            if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.username or u.password or u.path not in ('','/'):raise ValueError('Only unauthenticated loopback Ollama is supported')
            with locked(root):
                write(root/'settings.json',{'python':str(Path(a.python).absolute()),'cache':str(Path(a.cache).absolute()),'model':a.model,'ollama':a.ollama.rstrip('/'),'model_digest':local_model_digest(a.ollama.rstrip('/'),a.model)})
                result=reconcile_shared(root)
            trigger(root)
        elif a.action=='namespace-compat':
            with locked(root):
                if not (root/'settings.json').exists():raise ValueError('Configure the local knowledge runtime first')
                backup(root,'before-transport-change')
                result={'namespace_compat':a.mode=='on','scope':'explicit credential-free local Codex provider only'}
                write(root/'native-transport.json',result)
        elif a.action in ('seed','fetch'):
            with locked(root):result=reconcile_shared(root,(a.from_directory or fetch_shared(root,a.ref)) if a.action=='fetch' else SHARED)
            trigger(root)
        elif a.action=='status':result=status(root)
        elif a.action=='process':result=process(root)
        elif a.action=='watch':
            while True:trigger(root);time.sleep(2)
        elif a.action=='restore':
            with locked(root):
                restored={}
                with zipfile.ZipFile(a.archive) as archive:
                    for n in archive.namelist():
                        if n.startswith('notes/'):
                            name=n.removeprefix('notes/')
                            if Path(name).name!=name or not name.endswith('.md'):raise ValueError('Unsafe backup path')
                            b=archive.read(n);source(b.decode());restored[name]=b
                if not restored:raise ValueError('Backup contains no notes')
                backup(root,'before-restore')
                for n in inventory(root/'notes'):(root/'notes'/n).unlink()
                for n,b in restored.items():(root/'notes'/n).write_bytes(b)
            result=trigger(root)
        elif a.action in ('write','edit','delete'):
            if Path(a.name).name!=a.name or not a.name.endswith('.md'):raise ValueError('A flat .md filename is required')
            with locked(root):
                (root/'notes').mkdir(parents=True,exist_ok=True);backup(root,'before-'+a.action)
                p=root/'notes'/a.name
                if a.action in ('write','edit'):
                    if a.action=='edit' and not p.exists():raise ValueError('Cannot edit missing note')
                    b=a.from_file.read_bytes();source(b.decode());tmp=p.with_suffix('.tmp');tmp.write_bytes(b);tmp.replace(p)
                else:p.unlink()
            result=trigger(root)
        elif a.action=='export':
            with locked(root):
                backup(root,'before-export');dest=root/'exports'/str(time.time_ns());(dest/'cards').mkdir(parents=True)
                for n,b in inventory(root/'notes').items():(dest/'cards'/n).write_text(source(b.decode()))
                write(dest/'manifest.json',{'schema':1,'version':'review-required-'+dest.name,'files':{n:digest(b) for n,b in inventory(dest/'cards').items()}})
                result={'export':str(dest),'promotion':'Review diff, copy cards and manifest to knowledge/ on a branch, test, commit and open PR. No publication performed.'}
        elif a.action=='search':result=query(root,a.query,a.mode,a.role)
        elif a.action=='graph':result=graph(root,a.permalink,a.type,a.depth)
        print(json.dumps(result,indent=2));return 0
    except BlockingIOError:return 0
    except Exception as e:print(json.dumps({'error':str(e)}),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
