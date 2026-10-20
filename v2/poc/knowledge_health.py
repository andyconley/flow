"""Explicit offline dependency/cache and loopback model diagnostics; never install."""
import json,shlex,subprocess,tempfile
from pathlib import Path
from urllib.parse import urlparse
from . import knowledge as k

def hint(root,cfg=None):
    cfg={**k.read(root/'provisioned-runtime.json',{}),**k.read(root/'settings.json',{})} if cfg is None else cfg
    prefix='flow knowledge'+(' --home '+shlex.quote(str(root)) if root!=k.home() else '')
    return {'configured':bool(k.read(root/'settings.json',{})),'acquisition':k.read(root/'provisioning-status.json',{'state':'not_requested'}),'python_present':bool(cfg.get('python') and Path(cfg['python']).is_file()),'diagnostics':prefix+' doctor','setup':prefix+' setup --download','offline_setup':prefix+' setup --python /path/to/python3.12 --wheelhouse /path/to/knowledge-wheels','configure':prefix+' configure --python '+shlex.quote(cfg.get('python',str(root/'runtime/bin/python')))+' --cache '+shlex.quote(cfg.get('cache','/path/to/preprovisioned/fastembed_cache'))+' --model '+shlex.quote(cfg.get('model','qwen3:4b'))+' --ollama '+shlex.quote(cfg.get('ollama','http://127.0.0.1:11434'))}

def doctor(root,**overrides):
    cfg={**k.read(root/'provisioned-runtime.json',{}),**k.read(root/'settings.json',{}),**{key:value for key,value in overrides.items() if value is not None}}
    checks={};python=cfg.get('python') or str(root/'runtime/bin/python')
    checks['python']={'ok':Path(python).is_file(),'path':python}
    if checks['python']['ok']:
        probe="from poc.knowledge_runtime.policy import verify_compatibility; verify_compatibility(); import cocoindex; import importlib.metadata; assert importlib.metadata.version('cocoindex')=='1.0.25'"
        try:
            with tempfile.TemporaryDirectory(prefix='flow-knowledge-doctor-') as t:
                run=subprocess.run([python,'-c',probe],cwd=k.REPO/'v2',env=k.clean_env(Path(t)),capture_output=True,text=True,timeout=30)
                checks['dependencies']={'ok':run.returncode==0,'detail':run.stderr[-2000:] if run.returncode else 'Audited Basic Memory 0.23.2 and CocoIndex 1.0.25'}
                if run.returncode==0 and cfg.get('cache'):
                    probe="import onnxruntime; onnxruntime.disable_telemetry_events(); from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5',cache_dir="+repr(cfg['cache'])+",local_files_only=True,lazy_load=False)"
                    result=subprocess.run([python,'-c',probe],cwd=k.REPO/'v2',env=k.clean_env(Path(t)),capture_output=True,text=True,timeout=30)
                    checks['embedding_cache']={'ok':result.returncode==0,'detail':result.stderr[-2000:] if result.returncode else 'BAAI/bge-small-en-v1.5 found offline'}
        except (OSError,subprocess.TimeoutExpired) as e:checks['dependencies']={'ok':False,'detail':str(e)}
    checks.setdefault('dependencies',{'ok':False,'detail':'Provision a separate local environment with flow knowledge setup'})
    checks.setdefault('embedding_cache',{'ok':False,'detail':'Supply --cache with a preprovisioned BAAI/bge-small-en-v1.5 cache; dependency verification must pass first'})
    endpoint=cfg.get('ollama','http://127.0.0.1:11434');model=cfg.get('model','qwen3:4b');u=urlparse(endpoint)
    if u.scheme!='http' or u.hostname not in ('localhost','127.0.0.1','::1') or u.username or u.password or u.path not in ('','/'):raise ValueError('Only unauthenticated loopback Ollama is supported')
    try:checks['local_model']={'ok':True,'model':model,'digest':k.local_model_digest(endpoint.rstrip('/'),model)}
    except Exception as e:checks['local_model']={'ok':False,'model':model,'detail':str(e),'action':'Start your local Ollama server and explicitly provision this model; no download was attempted'}
    commands=hint(root,cfg)
    commands['dependency_lock']=str(k.SHARED/'requirements.lock')
    commands['offline_transfer']='Transfer the verified wheels folder including verified.json and the embedding-cache folder from an explicit flow knowledge setup --download run.'
    return {'ok':all(row['ok'] for row in checks.values()),'checks':checks,'commands':commands,'next':'Use commands.setup for supported acquisition and automatic configuration/indexing. Manual configure remains available for transferred offline assets; status reports readiness.','downloads_attempted':False}
