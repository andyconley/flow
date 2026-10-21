"""Explicit, immutable implementation-worker selection; no automatic routing."""
import hashlib
import json
from pathlib import Path
import tomllib
from urllib.parse import urlparse


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def validate(snapshot):
    if snapshot is None:return None
    if not isinstance(snapshot,dict):raise ValueError('Implementation profile must be an object')
    row={k:v for k,v in snapshot.items() if k!='sha256'}
    if snapshot.get('sha256')!=fingerprint(row):raise ValueError('Implementation profile snapshot changed; create a new work item')
    if row.get('provider') not in {'ollama','codex-acp','claude-acp'} or not isinstance(row.get('model'),str) or not row['model']:
        raise ValueError('Invalid implementation provider/model')
    if row['provider']=='ollama':
        u=urlparse(row['endpoint'])
        if u.scheme!='http' or u.hostname not in {'127.0.0.1','localhost','::1'} or u.username or u.password or u.path not in {'','/'} or u.query or u.fragment:
            raise ValueError('Implementation profile requires credential-free loopback Ollama')
        if type(row['context_tokens']) is not int or row['context_tokens']<1:raise ValueError('Implementation context must be positive')
        if type(row['output_tokens']) is not int or row['output_tokens'] not in {-1} and row['output_tokens']<1:raise ValueError('Invalid implementation output setting')
        condenser=row.get('condenser_max_tokens')
        if type(condenser) is not int or not 0<condenser<row['context_tokens']:
            raise ValueError('Implementation profiles require explicit condenser_max_tokens within context; mutable Goose defaults are not frozen')
    return snapshot


def resolve(project,name,home=None):
    home=Path(home or Path.home());project=Path(project)
    profiles={}
    for path in [home/'.flow/user/runtime.toml',project/'.flow/runtime.toml']:
        if path.is_file():
            for key,value in tomllib.loads(path.read_text()).get('profiles',{}).items():
                profiles[key]={**profiles.get(key,{}),**value}
    if name not in profiles:raise ValueError('Unknown implementation profile: '+name)
    profile=profiles[name];kind=profile.get('kind');model=profile.get('model')
    row={'name':name,'provider':{'local':'ollama','codex':'codex-acp','claude':'claude-acp'}.get(kind),'model':model}
    if kind=='local':
        if not isinstance(model,str) or not model.startswith(('ollama/','ollama_chat/')):raise ValueError('Implementation local profiles must select an Ollama model')
        row.update(model=model.removeprefix('ollama_chat/').removeprefix('ollama/'),endpoint=profile.get('base_url','').rstrip('/'),context_tokens=profile.get('max_input_tokens'),output_tokens=profile.get('max_output_tokens',-1),condenser_max_tokens=profile.get('condenser_max_tokens'))
        if row['model'].lower().endswith((':cloud','-cloud')):raise ValueError('Implementation worker must execute locally')
    elif kind in {'codex','claude'}:
        # Same defaults used by the role resolver, preserving native account ownership.
        row['model']=model or ('gpt-5.6-terra' if kind=='codex' else 'sonnet')
    else:raise ValueError('Implementation profile must be local Ollama, Codex or Claude')
    row['sha256']=fingerprint(row);validate(row)
    if kind=='local':
        from .knowledge import local_model_digest
        row.pop('sha256')
        row['model_digest']=local_model_digest(row['endpoint'],row['model'])
        row['sha256']=fingerprint(row)
    return row


def apply_environment(env,snapshot,provider,model):
    """Goose shares Ollama transport settings with in-process summoned workers."""
    validate(snapshot)
    if not snapshot or snapshot['provider']!='ollama':return env
    if provider=='ollama' and model!=snapshot['model']:
        raise ValueError('A distinct local coordinator would share worker transport settings; use a native coordinator or the same local model')
    env=dict(env);env['FLOW_V2_IMPLEMENTATION_PROFILE']=json.dumps(snapshot,sort_keys=True);env['OLLAMA_HOST']=snapshot['endpoint'];env['GOOSE_INPUT_LIMIT']=str(snapshot['context_tokens'])
    env.pop('GOOSE_MAX_TOKENS',None)
    if snapshot['output_tokens']==-1 and env.get('GOOSE_PATH_ROOT'):
        import yaml
        stored=Path(env['GOOSE_PATH_ROOT'])/'config.yaml'
        if stored.is_file():
            settings=yaml.safe_load(stored.read_text()) or {}
            if not isinstance(settings,dict):raise ValueError('Invalid persistent Goose configuration; reconcile before execution')
            if settings.get('GOOSE_MAX_TOKENS') is not None:
                raise ValueError('Persistent Goose output override conflicts with open-ended implementation profile; reconcile explicitly before execution')
    if snapshot['output_tokens']>0:env['GOOSE_MAX_TOKENS']=str(snapshot['output_tokens'])
    env.pop('GOOSE_AUTO_COMPACT_THRESHOLD',None)
    if snapshot.get('condenser_max_tokens'):env['GOOSE_AUTO_COMPACT_THRESHOLD']=str(snapshot['condenser_max_tokens']/snapshot['context_tokens'])
    return env


def bind(bundle,snapshot):
    """Change only the attempt-local implementation recipe, preserving review."""
    validate(snapshot)
    if snapshot is None:return
    import yaml
    path=Path(bundle)/'recipes/lead-developer.yaml'
    recipe=yaml.safe_load(path.read_text());recipe['settings'].update(goose_provider=snapshot['provider'],goose_model=snapshot['model'])
    class RecipeDumper(yaml.SafeDumper):pass
    RecipeDumper.add_representer(str,lambda dumper,value:dumper.represent_scalar('tag:yaml.org,2002:str',value,style='|' if '\n' in value else None))
    path.write_text(yaml.dump(recipe,Dumper=RecipeDumper,sort_keys=False,allow_unicode=True))
    path=Path(bundle)/'catalog.json'
    if path.exists():
        catalog=json.loads(path.read_text())
        for row in catalog.get('roles',[]):
            if row['role']=='lead-developer':row.update(profile=snapshot['name'],provider=snapshot['provider'],model=snapshot['model'])
        catalog['implementation_profile']=snapshot;path.write_text(json.dumps(catalog,indent=2)+'\n')


def preflight_scope(sandbox,tools,snapshot):
    """Allow only the local read-only readiness probe; worker policies stay intact."""
    validate(snapshot)
    if not snapshot or snapshot['provider']!='ollama':return None
    port=urlparse(snapshot['endpoint']).port or 80
    path=Path(tools)/'local-preflight.sb'
    path.write_text(Path(sandbox).read_text()+'\n(allow network-outbound (remote tcp "localhost:'+str(port)+'"))\n')
    return path
