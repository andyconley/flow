"""Explicit official-source acquisition, isolated versioned environments, no chat downloads."""
import hashlib,json,os,re,shlex,shutil,subprocess,sys,tempfile,urllib.request,uuid
from pathlib import Path
from urllib.parse import urlparse
from . import knowledge as k
MIN_FREE=6*1024**3

def require_host():
    from .managed import supported
    supported()

def progress(message):print('Flow knowledge setup: '+message,file=sys.stderr,flush=True)
def plan():
    model=k.read(k.SHARED/'embedding.lock.json')
    return {'command':'flow knowledge setup --download','consent':'Install/update interactive download consent or --knowledge download permits acquisition; advanced setup --download also permits it. Workflow execution/status never acquire assets.', 'sources':['https://pypi.org/simple','https://pypi.org/pypi/<pinned-package>/<pinned-version>/json','https://files.pythonhosted.org','https://huggingface.co/'+model['repository']+'/resolve/'+model['revision']+'/<pinned-file> (official HF CDN redirects)'],'embedding_bytes':sum(x['size'] for x in model['files'].values()),'minimum_free_bytes':MIN_FREE,'source_builds':'Only pinned pybars3/PyMeta3 source archives are built, using four pinned build-tool wheels in a disposable macOS environment with network denied','disk':'Reserve at least 6 GiB for wheels, installed dependencies and staging; corpus backups/generations and Ollama weights need additional space','network':'Dependency transfer varies by platform (typically hundreds of MB to a few GiB); embedding files add about 67 MB. Exact wheel sizes/hashes are recorded after resolution. No Ollama chat model is downloaded.','supported_host':'Managed macOS 15+ arm64 release','python':'Python 3.12 required; uses the managed Flow interpreter by default','offline':'flow knowledge setup --python /path/to/python3.12 --wheelhouse /path/to/wheels; configure with a transferred embedding cache separately'}

def allowed(url):
    u=urlparse(url);host=u.hostname or ''
    return u.scheme=='https' and not u.username and not u.password and (host in ('pypi.org','files.pythonhosted.org','huggingface.co') or host.endswith('.hf.co'))
class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl):raise ValueError('Non-official HTTPS redirect refused')
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def open_official(url):
    if not allowed(url):raise ValueError('Non-official download URL refused')
    return urllib.request.build_opener(urllib.request.ProxyHandler({}),OfficialRedirect()).open(url,timeout=60)
def fetch_json(url):
    with open_official(url) as response:
        body=response.read(4*1024*1024+1)
        if len(body)>4*1024*1024:raise ValueError('Registry metadata exceeds limit')
        return json.loads(body)
def verified(path,row):return path.is_file() and path.stat().st_size==row['size'] and k.digest(path.read_bytes())==row['sha256']
def download(url,path,row):
    if verified(path,row):return
    if path.exists():raise ValueError('Existing managed artifact failed checksum: '+str(path)+'; inspect/remove that artifact before explicit retry')
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.partial');count=0;sha=hashlib.sha256()
    try:
        with open_official(url) as response,temporary.open('xb') as output:
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                count+=len(chunk)
                if count>row['size']:raise ValueError('Artifact exceeds pinned size')
                sha.update(chunk);output.write(chunk)
        if count!=row['size'] or sha.hexdigest()!=row['sha256']:raise ValueError('Artifact checksum/size mismatch: '+path.name)
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)

def requirements(path):
    rows={}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith('#'):continue
        name,version=line.split('==');rows[re.sub(r'[-_.]+','-',name.lower())]=version
    return rows

def wheels(destination,lock,offline=False):
    """Choose compatible official binary wheels and verify every registry SHA-256."""
    destination.mkdir(parents=True,exist_ok=True);receipt=destination/'verified.json';pins=requirements(lock)
    if not receipt.exists():
        if offline:raise ValueError('Offline wheelhouse missing verified.json receipt; transfer the verified wheels folder from Flow online provisioning. No network attempted.')
        from packaging.tags import sys_tags
        from packaging.utils import parse_wheel_filename
        ranks={tag:index for index,tag in enumerate(sys_tags())};rows={}
        for index,(name,version) in enumerate(pins.items(),1):
            metadata=fetch_json('https://pypi.org/pypi/'+name+'/'+version+'/json');choices=[]
            for item in metadata['urls']:
                if item.get('packagetype')!='bdist_wheel' or item.get('yanked'):continue
                parsed_name,parsed_version,build,tags=parse_wheel_filename(item['filename'])
                if str(parsed_name)!=name or str(parsed_version)!=version:continue
                matching=[ranks[tag] for tag in tags if tag in ranks]
                if matching:choices.append((min(matching),item['filename'],item))
            if not choices:
                sources=k.read(k.SHARED/'source-builds.lock.json')['sources'];pin=sources.get(name)
                if not pin or pin['version']!=version:raise ValueError('No compatible official binary wheel for '+name+'=='+version+'; no unapproved source build or alternate index is allowed')
                items=[x for x in metadata['urls'] if x['filename']==pin['filename'] and x['digests']['sha256']==pin['sha256'] and x['size']==pin['size'] and x['url']==pin['url'] and not x.get('yanked')]
                if len(items)!=1:raise ValueError('Pinned source release changed: '+name)
                built=build_source(destination.parent,name,pin)
                target=destination/built.name;shutil.copyfile(built,target)
                rows[target.name]={'package':name,'version':version,'size':target.stat().st_size,'sha256':k.digest(target.read_bytes()),'source':pin,'build_requirements_sha256':k.digest((k.SHARED/'build-requirements.lock').read_bytes())}
                continue
            item=min(choices,key=lambda row:(row[0],row[1]))[2];filename=item['filename']
            if Path(filename).name!=filename or urlparse(item['url']).hostname!='files.pythonhosted.org':raise ValueError('Unexpected official wheel location')
            row={'sha256':item['digests']['sha256'],'size':item['size'],'package':name,'version':version}
            progress(str(index)+'/'+str(len(pins))+' '+filename+' ('+str(row['size'])+' bytes)')
            download(item['url'],destination/filename,row);rows[filename]=row
        k.write(receipt,{'requirements_sha256':k.digest(lock.read_bytes()),'files':rows})
    data=k.read(receipt)
    if data['requirements_sha256']!=k.digest(lock.read_bytes()):raise ValueError('Wheelhouse belongs to different dependency lock')
    if {r['package']:r['version'] for r in data['files'].values()}!=pins:raise ValueError('Wheel receipt pin inventory mismatch')
    for name,row in data['files'].items():
        if Path(name).name!=name or not verified(destination/name,row):raise ValueError('Cached wheel checksum failed: '+name)
    hashed=destination/'requirements.hashed.txt'
    text=''.join(r['package']+'=='+r['version']+' --hash=sha256:'+r['sha256']+'\n' for r in data['files'].values())
    if offline:
        if not hashed.is_file() or hashed.read_text()!=text:raise ValueError('Offline hashed requirements missing/changed; transfer the complete verified wheel folder. No network attempted.')
    elif not hashed.exists() or hashed.read_text()!=text:hashed.write_text(text)
    progress('Verified '+str(len(data['files']))+' wheels ('+str(sum(r['size'] for r in data['files'].values()))+' bytes)')
    return hashed

def build_source(base,name,pin):
    """The only allowed source builds; offline sandbox and pinned build backend."""
    if sys.platform!='darwin':raise ValueError('Pinned legacy source build requires the supported macOS sandbox; no unsandboxed fallback')
    sources=base/'source-archives';sources.mkdir(exist_ok=True)
    archive=sources/pin['filename'];download(pin['url'],archive,pin)
    lock=k.SHARED/'build-requirements.lock';tools=base/('build-tools-'+k.digest(lock.read_bytes())[:16]);tools.mkdir(exist_ok=True)
    hashed=wheels(tools/'wheels',lock);ready=k.read(tools/'ready.json',{})
    python=Path(ready.get('python',str(tools/'runtime/bin/python'))) if ready else tools/('env-'+uuid.uuid4().hex)/'bin/python'
    if not python.parent.parent.resolve().is_relative_to(tools.resolve()):raise ValueError('Build-tools receipt escapes owned profile')
    env=k.clean_env(tools);(tools/'home').mkdir(exist_ok=True)
    env.update(PIP_CONFIG_FILE=os.devnull,PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_NO_INPUT='1',SOURCE_DATE_EPOCH='315532800',PYTHONHASHSEED='0')
    if not ready:
        subprocess.run([sys.executable,'-m','venv',str(python.parent.parent)],env=env,check=True,timeout=120)
        subprocess.run([str(python),'-m','pip','--isolated','install','--no-index','--find-links',str(tools/'wheels'),'--require-hashes','--no-deps','-r',str(hashed)],env=env,check=True,timeout=180)
        k.write(tools/'ready.json',{'python':str(python),'build_requirements_sha256':k.digest(lock.read_bytes())})
    subprocess.run([str(python),'-c','import importlib.metadata,json,sys; pins=json.loads(sys.argv[1]); assert all(importlib.metadata.version(n)==v for n,v in pins.items())',json.dumps(requirements(lock))],env=env,check=True,timeout=30)
    output=base/'built-wheels';output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='flow-source-build-',dir=base) as temporary:
        command=['/usr/bin/sandbox-exec','-p','(version 1)(allow default)(deny network*)',str(python),'-m','pip','--isolated','wheel','--no-index','--no-deps','--no-build-isolation','--wheel-dir',temporary,str(archive)]
        progress('Building only pinned '+name+' source, with network denied')
        subprocess.run(command,env=env,check=True,timeout=180)
        candidates=list(Path(temporary).glob('*.whl'))
        if len(candidates)!=1:raise ValueError('Source builder did not emit one wheel')
        from packaging.utils import parse_wheel_filename
        n,v,_,_=parse_wheel_filename(candidates[0].name)
        if str(n)!=name or str(v)!=pin['version']:raise ValueError('Source wheel identity mismatch')
        target=output/candidates[0].name;shutil.copyfile(candidates[0],target)
    return target

def embeddings(cache,manifest):
    # Standard HF snapshot layout, with regular files and an immutable revision.
    folder=cache/('models--'+manifest['repository'].replace('/','--'));snapshot=folder/'snapshots'/manifest['revision']
    for name,row in manifest['files'].items():
        if Path(name).name!=name:raise ValueError('Unsafe pinned embedding filename')
        progress('Verifying/acquiring embedding '+name+' ('+str(row['size'])+' bytes)')
        download('https://huggingface.co/'+manifest['repository']+'/resolve/'+manifest['revision']+'/'+name,snapshot/name,row)
    (folder/'refs').mkdir(parents=True,exist_ok=True);(folder/'refs/main').write_text(manifest['revision'])
    k.write(cache/'flow-embedding-receipt.json',manifest)
    return cache

def online(root,python,model,endpoint,rebuild=False):
    from urllib.parse import urlparse
    u=urlparse(endpoint)
    if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.username or u.password or u.path not in ('','/'):raise ValueError('Only unauthenticated loopback Ollama is supported')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*',model):raise ValueError('Invalid local extraction model name')
    progress(json.dumps(plan()))
    require_host()
    progress('Extraction model '+model+' at '+endpoint+'; agent provider/model remains unchanged')
    lock=k.SHARED/'requirements.lock';manifest=k.read(k.SHARED/'embedding.lock.json');key=k.digest(lock.read_bytes()+json.dumps(manifest,sort_keys=True).encode()+(k.SHARED/'build-requirements.lock').read_bytes()+(k.SHARED/'source-builds.lock.json').read_bytes())[:20]
    base=root/'provisioning'/key
    installed={} if rebuild else k.read(base/'installed.json',{})
    minimum=128*1024**2 if installed else MIN_FREE
    if shutil.disk_usage(root).free<minimum:raise ValueError('Free disk below '+str(minimum)+' bytes required for this setup; no download started')
    if not base.resolve().is_relative_to(root.resolve()):raise ValueError('Managed provisioning path escapes knowledge home')
    base.mkdir(parents=True,exist_ok=True)
    env=k.clean_env(base);(base/'home').mkdir(exist_ok=True)
    # Dedicated subprocess HOME/config; pip cannot consume user index/auth settings.
    env={key:value for key,value in env.items() if not key.startswith('PIP_')};env.update(PIP_CONFIG_FILE=os.devnull,PIP_DISABLE_PIP_VERSION_CHECK='1',PIP_NO_INPUT='1')
    subprocess.run([python,'-c','import sys,platform; assert sys.version_info[:2]==(3,12), "Python 3.12 required"; assert platform.machine()=='+repr(__import__('platform').machine())],env=env,check=True,timeout=30)
    hashed=wheels(base/'wheels',lock)
    cache=embeddings(base/'embedding-cache',manifest)
    runtime=Path(installed['python']) if installed else base/('env-'+uuid.uuid4().hex)/'bin/python'
    if runtime.name!='python' or runtime.parent.name!='bin' or not runtime.parent.parent.resolve().is_relative_to(base.resolve()):raise ValueError('Managed runtime receipt points outside its owned profile')
    if not installed:
        progress('Creating isolated versioned Python environment')
        subprocess.run([python,'-m','venv',str(runtime.parent.parent)],env=env,check=True,timeout=120)
        subprocess.run([str(runtime),'-m','pip','--isolated','install','--no-index','--find-links',str(base/'wheels'),'--require-hashes','--no-deps','-r',str(hashed)],env=env,check=True,timeout=1800)
        subprocess.run([str(runtime),'-m','pip','check'],env=env,check=True,timeout=60)
    progress('Verifying every installed dependency pin and audited embedding/runtime load')
    subprocess.run([str(runtime),'-c','import importlib.metadata,json,sys; pins=json.loads(sys.argv[1]); bad=[name for name,version in pins.items() if importlib.metadata.version(name)!=version]; assert not bad, "Installed dependency pins changed: "+repr(bad)',json.dumps(requirements(lock))],env=env,check=True,timeout=60)
    from .knowledge_health import doctor
    health=doctor(root,python=str(runtime),cache=str(cache),model=model,ollama=endpoint)
    if not health['checks']['dependencies']['ok'] or not health['checks']['embedding_cache']['ok']:raise ValueError('Acquired runtime failed offline verification; rerun setup --download --rebuild-runtime to create a fresh isolated environment: '+json.dumps(health))
    k.write(base/'installed.json',{'python':str(runtime),'requirements_sha256':k.digest(lock.read_bytes())})
    k.write(root/'provisioned-runtime.json',{'python':str(runtime),'cache':str(cache),'model':model,'ollama':endpoint})
    if not health['checks']['local_model']['ok']:
        progress('Assets ready; local extraction model unavailable. No chat-model download or agent-provider change was attempted.')
        return {'configured':False,'assets_ready':True,'diagnostics':health,'required_model_setup':{'model':model,'commands':[shlex.join(['env','OLLAMA_HOST='+u.netloc,'ollama','serve']),shlex.join(['env','OLLAMA_HOST='+u.netloc,'ollama','pull',model])],'next':'After starting compatible local Ollama and explicitly provisioning this extraction model, rerun the same flow knowledge setup --download command. Agent provider/model is unchanged.'}}
    k.backup(root,'before-online-configure')
    shared=k.reconcile_shared(root)
    k.write(root/'settings.json',{'python':str(runtime),'cache':str(cache),'model':model,'ollama':endpoint.rstrip('/'),'model_digest':health['checks']['local_model']['digest']})
    progress('Configured verified local runtime; initial indexing will be queued')
    return {'configured':True,'assets_ready':True,'python':str(runtime),'cache':str(cache),'shared':shared,'agent_provider_changed':False}
