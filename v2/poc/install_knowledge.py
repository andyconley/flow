"""Install/update knowledge gate, executed by the staged release interpreter."""
import argparse
import json
import shlex
import re
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
import sys
from . import knowledge as k
from .knowledge_health import doctor
from .knowledge_provision import online, plan


MODEL_ACQUISITION_PROTOCOL = 1


def read_choice(prompt, *, interactive=None, choose=None):
    tty=sys.stdin.isatty() if interactive is None else interactive
    terminal=None
    if interactive is None and not tty:
        try:terminal=open('/dev/tty','r')
        except OSError:pass
        tty=terminal is not None
    if not tty:raise ValueError('Knowledge provisioning requires consent; no terminal input was read. Use explicit --knowledge download|offline|defer; chat weights additionally require --knowledge-model download. No runtime activation occurred.')
    print(prompt+' [download/defer/cancel] (default cancel): ',end='',file=sys.stderr,flush=True)
    try:answer=(choose() if choose else (terminal or sys.stdin).readline()).strip().lower()
    finally:
        if terminal:terminal.close()
    if answer not in ('download','defer'):raise ValueError('Installation canceled; previous runtime and knowledge remain selected')
    return answer


def resolve_mode(mode, health, *, interactive=None, choose=None):
    """Read consent in the foreground parent, before detaching a worker."""
    if mode!='ask':return mode
    if health['ok']:return 'offline'
    print('Flow install/update: local knowledge needs provisioning. '+json.dumps(plan()),file=sys.stderr,flush=True)
    print('Dependency/embedding consent does not authorize chat weights. No agent provider changes or credential copying. Provisioning/initial audit is bounded to 30 minutes. Deferral leaves knowledge pending.',file=sys.stderr,flush=True)
    return read_choice('Choose',interactive=interactive,choose=choose)


def model_selection(root):
    cfg={**k.read(root/'provisioned-runtime.json',{}),**k.read(root/'settings.json',{})}
    model=cfg.get('model','qwen3:4b');endpoint=cfg.get('ollama','http://127.0.0.1:11434').rstrip('/')
    u=urlparse(endpoint)
    if u.scheme!='http' or u.hostname not in ('127.0.0.1','localhost','::1') or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
        raise ValueError('Only unauthenticated loopback Ollama is supported')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]*',model):raise ValueError('Invalid local extraction model name')
    if model.lower().endswith((':cloud','-cloud')):raise k.LocalModelRequiredError('Cloud-hosted extraction models are unsupported; choose downloaded locally executed weights')
    return model,endpoint


class ModelIdentityMismatch(ValueError):pass


def model_profile(root,model):
    profile=k.read(k.SHARED/'extraction-models.json',{}).get('models',{}).get(model,{})
    cfg={**k.read(root/'provisioned-runtime.json',{}),**k.read(root/'settings.json',{})}
    if cfg.get('model_digest') and cfg['model_digest']!=profile.get('digest'):
        return {'digest':cfg['model_digest'],'qualification':'Existing explicit local configuration; size unknown'}
    return profile


def checked_model_digest(root,model,endpoint):
    observed=k.local_model_digest(endpoint,model)
    expected=model_profile(root,model).get('digest')
    if expected and observed.removeprefix('sha256:')!=expected.removeprefix('sha256:'):
        raise ModelIdentityMismatch('Selected extraction model identity changed: expected '+expected+', observed '+observed+'. No dependency acquisition or provider change. Preserve the existing model and explicitly review/configure an intended model version before retrying; --knowledge defer remains available.')
    return observed


def model_requirement(model,endpoint,error,profile=None):
    serve=shlex.join(['env','OLLAMA_HOST='+endpoint,'ollama','serve'])
    pull=shlex.join(['env','OLLAMA_HOST='+endpoint,'ollama','pull',model])
    profile=profile or {}
    size=('Recorded download size '+str(profile['download_bytes'])+' bytes; expected digest '+profile['digest']) if profile.get('download_bytes') else 'Size unknown until Ollama registry transfer; weights may require multiple GiB'
    return ('Local extraction model prerequisite unmet before knowledge dependency/embedding acquisition: '+str(error)+'. Selected model: '+model+' at '+endpoint+'. '+size+'. Start local Ollama if needed: '+serve+'. If you choose to install this chat model, run: '+pull+'; or retry install/update --knowledge download --knowledge-model download. Alternatively choose --knowledge defer. No coding-agent provider/model change is made.')


def resolve_model_mode(root,mode,policy='ask',*,interactive=None,choose=None):
    if mode!='download':return mode,'offline'
    model,endpoint=model_selection(root)
    try:checked_model_digest(root,model,endpoint);return mode,'offline'
    except (ModelIdentityMismatch,k.LocalModelRequiredError):raise
    except Exception as error:detail=model_requirement(model,endpoint,error,model_profile(root,model))
    if policy=='download':return mode,'download'
    if policy=='offline':raise ValueError(detail)
    if policy!='ask':raise ValueError('Invalid extraction model policy')
    print(detail,file=sys.stderr,flush=True)
    answer=read_choice('Extraction model',interactive=interactive,choose=choose)
    return ('defer','offline') if answer=='defer' else ('download','download')


def ensure_model(root,policy):
    model,endpoint=model_selection(root)
    try:return checked_model_digest(root,model,endpoint)
    except (ModelIdentityMismatch,k.LocalModelRequiredError):raise
    except Exception as error:
        if policy!='download':raise ValueError(model_requirement(model,endpoint,error,model_profile(root,model))) from error
    # Only the separately consented worker performs model acquisition, inside
    # its existing bounded/cancellable process scope. No service is started.
    request=urllib.request.Request(endpoint+'/api/pull',data=json.dumps({'model':model,'stream':True}).encode(),headers={'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request,timeout=30) as response:
            for line in response:
                row=json.loads(line)
                if row.get('error'):raise ValueError(row['error'])
                print('Ollama extraction model: '+str(row.get('status',''))+' '+str(row.get('completed',''))+'/'+str(row.get('total',''))+' bytes',file=sys.stderr,flush=True)
        return checked_model_digest(root,model,endpoint)
    except (ModelIdentityMismatch,k.LocalModelRequiredError):raise
    except Exception as error:raise ValueError('Explicit extraction-model acquisition failed; no coding-agent provider change. '+model_requirement(model,endpoint,error,model_profile(root,model))) from error


def provision(root, mode='ask', *, interactive=None, choose=None, model_policy='offline'):
    """No detached worker: installation succeeds only after an audited snapshot."""
    root = Path(root)
    current = k.read(root/'settings.json', {})
    candidate = k.read(root/'provisioned-runtime.json', {})
    health = doctor(root) if current or candidate else {'ok': False, 'checks': {}, 'reason': 'Not configured'}
    mode = resolve_mode(mode, health, interactive=interactive, choose=choose)
    if mode == 'defer':
        # Deliberate opt-out is visible, including when an old good snapshot exists.
        with k.locked(root):
            shared = k.reconcile_shared(root) if not (root/'base.json').exists() else None
            result = {'state': 'deferred', 'ready': False, 'previous_snapshot': k.read(root/'CURRENT.json', {}).get('generation'),
                      'reason': 'User explicitly deferred provisioning. Knowledge-dependent agent launches require an audited snapshot and pinned runtime.',
                      'resume': 'flow update --knowledge download', 'diagnostics': health, 'shared': shared}
            k.write(root/'install-status.json', result)
        print('Flow knowledge DEFERRED: '+json.dumps(result), file=sys.stderr, flush=True)
        return result
    with k.locked(root):
        if health['ok']:
            model,endpoint=model_selection(root)
            checked_model_digest(root,model,endpoint)
        if health['ok'] and not current:
            k.backup(root, 'before-install-configuration')
            k.write(root/'settings.json', {**candidate, 'model_digest': health['checks']['local_model']['digest']})
        if not health['ok']:
            if mode == 'offline':
                raise ValueError('Offline knowledge assets/configuration are incomplete; no downloads attempted. '+json.dumps(health)+'; supply verified offline assets using knowledge setup/configure, or explicitly choose --knowledge defer.')
            previous = {**k.read(root/'provisioned-runtime.json', {}), **current}
            ensure_model(root,model_policy)
            k.write(root/'provisioning-status.json', {'state': 'running', 'consent': 'install/update --knowledge download or interactive download'})
            result = online(root, sys.executable, previous.get('model', 'qwen3:4b'), previous.get('ollama', 'http://127.0.0.1:11434'))
            if not result['configured']:
                k.write(root/'provisioning-status.json', {'state': 'awaiting_model', **result})
                raise ValueError('Local extraction model unavailable after provisioning; acquired assets remain cached. '+json.dumps(result)+'; satisfy the printed Ollama requirement and retry install/update --knowledge download, or explicitly defer.')
            k.write(root/'provisioning-status.json', {'state': 'ready', 'assets_ready': True})
        shared = k.reconcile_shared(root)
    # Bounded worker build, audit and atomic CURRENT publication; no background job.
    state = k.process(root)
    if state.get('pending') or state.get('state') != 'ready':
        raise ValueError('Knowledge snapshot did not become ready: '+json.dumps(state))
    result = {'state': 'ready', 'ready': True, 'reused_assets': health['ok'], 'shared': shared, 'snapshot': state.get('snapshot')}
    k.write(root/'install-status.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--mode', choices=('ask', 'download', 'offline', 'defer'), default='ask')
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--model-policy',choices=('offline','download'),default='offline')
    args = parser.parse_args(argv)
    try:
        result = provision(args.root, args.mode, model_policy=args.model_policy)
        args.result.write_text(json.dumps(result))
        return 0
    except Exception as error:
        print('Flow install/update knowledge failed: '+str(error), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
