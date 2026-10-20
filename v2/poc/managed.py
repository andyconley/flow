"""V2-only verified release installation. No legacy execution or Rust fallback."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import uuid

REPOSITORY = 'andyconley/flow'
ASSETS = ('flow-code.tar.gz','python-wheels.tar.gz','goose-macos-arm64.gz','goose-macos-arm64.json')
NODE_HELP = ('Select Node.js 24 in this shell using your existing version manager '
             '(for example, nvm use 24). If absent, install Node.js 24 with your '
             'preferred installer or manager (for example, nvm install 24). '
             'Ensure node and npm are on PATH, then retry. Flow does not install or switch Node automatically.')
NPM_HELP = ('Repair or reinstall npm for your selected Node.js 24 installation using '
            'the same installer or version manager. Ensure npm is on PATH and '
            'npm --version succeeds, then retry. Flow does not install npm automatically.')


def prerequisite_version(name, required, remedy):
    path = shutil.which(name)
    if not path:
        raise ValueError(f'{name}: missing executable on PATH. Required: {required}. {remedy}')
    try:
        result = subprocess.run([path,'--version'],text=True,capture_output=True,check=True,timeout=10)
    except (OSError,subprocess.SubprocessError,UnicodeError) as error:
        detail = (f'exit {error.returncode}: '+(error.stderr or error.stdout or str(error))) if isinstance(error,subprocess.CalledProcessError) else str(error)
        raise ValueError(f'{name} at {path}: cannot read version ({str(detail).strip()[:512]}). '
                         f'Required: {required}. {remedy}') from error
    version = result.stdout.strip()
    if not re.fullmatch(r'v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?',version):
        raise ValueError(f'{name} at {path}: unrecognized version output {version[:512]!r}. '
                         f'Required: {required}. {remedy}')
    return path,version


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex)
    temporary.write_text(json.dumps(value,indent=2)+'\n'); temporary.replace(path)


def supported():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64' or int(platform.mac_ver()[0].split('.')[0]) < 15:
        raise ValueError('Supported installation target: Apple Silicon macOS 15 or later. No local-build or legacy fallback.')
    if sys.version_info[:2] != (3,12):
        raise ValueError('Managed Flow requires Python 3.12; select FLOW_V2_PYTHON=python3.12')
    node,version = prerequisite_version('node','Node.js exactly 24.x',NODE_HELP)
    detected = f'Detected Node.js {version} at {node}; required exactly 24.x.'
    if int(version.lstrip('v').split('.')[0]) != 24:
        raise ValueError(detected+' '+NODE_HELP)
    try:
        npm,npm_version = prerequisite_version('npm','working npm for Node.js 24',NPM_HELP)
    except ValueError as error:
        raise ValueError(detected+' '+str(error)) from error
    print(f'{detected} Detected npm {npm_version} at {npm}.',file=sys.stderr)


def latest(repository=REPOSITORY, tag=None):
    if not re.fullmatch(r'[\w.-]+/[\w.-]+',repository): raise ValueError('Invalid release repository')
    endpoint = 'tags/'+tag if tag else 'latest'
    if tag and not re.fullmatch(r'v\d+\.\d+\.\d+',tag): raise ValueError('Stable release tag required')
    headers={'User-Agent':'Flow-v2-installer','Accept':'application/vnd.github+json'}
    if os.environ.get('FLOW_RELEASE_READ_TOKEN'):headers['Authorization']='Bearer '+os.environ['FLOW_RELEASE_READ_TOKEN']
    request = urllib.request.Request(f'https://api.github.com/repos/{repository}/releases/{endpoint}',headers=headers)
    with urllib.request.urlopen(request,timeout=30) as response: release=json.load(response)
    if release.get('draft') or release.get('prerelease'): raise ValueError('A published stable release is required')
    tag=release['tag_name']
    if not re.fullmatch(r'v\d+\.\d+\.\d+',tag): raise ValueError('Invalid release tag')
    base=f'https://github.com/{repository}/releases/download/{tag}/'
    urls={asset['name']:asset['browser_download_url'] for asset in release.get('assets',[])}
    if any(urls.get(name) != base+name for name in (*ASSETS,'release-manifest.json')):
        raise ValueError('Release assets are incomplete or have unexpected URLs')
    with urllib.request.urlopen(urls['release-manifest.json'],timeout=30) as response:
        raw=response.read(1024*1024+1)
    if len(raw)>1024*1024: raise ValueError('Oversized release manifest')
    manifest=json.loads(raw)
    validate(manifest)
    if manifest['version'] != tag: raise ValueError('Release manifest/tag mismatch')
    return manifest,urls


def validate(manifest):
    if manifest.get('schema_version') != 1 or not re.fullmatch(r'v\d+\.\d+\.\d+',manifest.get('version','')):
        raise ValueError('Invalid release manifest')
    if not re.fullmatch(r'[a-f0-9]{40}',manifest.get('source_sha','')): raise ValueError('Invalid release source identity')
    if manifest.get('supported_targets') != ['Darwin-arm64'] or manifest.get('minimum_macos') != '15.0':
        raise ValueError('Unsupported release target contract')
    if set(manifest.get('assets',{})) != set(ASSETS): raise ValueError('Incomplete asset manifest')
    for asset in manifest['assets'].values():
        if not re.fullmatch(r'[a-f0-9]{64}',asset.get('sha256','')) or type(asset.get('size')) is not int or not 0<asset['size']<2*1024**3:
            raise ValueError('Invalid release asset digest/size')


def fetch_assets(manifest, destination, urls=None, bundle=None):
    validate(manifest); destination.mkdir(parents=True,exist_ok=True)
    for name, expected in manifest['assets'].items():
        target=destination/name
        if bundle:
            shutil.copyfile(Path(bundle)/name,target)
        else:
            with urllib.request.urlopen(urls[name],timeout=120) as response, target.open('wb') as out:
                size=0
                while chunk:=response.read(1024*1024):
                    size+=len(chunk)
                    if size>expected['size']: raise ValueError('Oversized release asset: '+name)
                    out.write(chunk)
        if target.stat().st_size!=expected['size'] or sha(target)!=expected['sha256']:
            raise ValueError('Release asset checksum mismatch: '+name)


def unpack(archive, destination):
    with tarfile.open(archive,'r:gz') as source:
        members=source.getmembers()
        if sum(item.size for item in members)>2*1024**3: raise ValueError('Oversized expanded release')
        for item in members:
            if item.issym() or item.islnk() or not (item.isfile() or item.isdir()) or Path(item.name).is_absolute() or '..' in Path(item.name).parts:
                raise ValueError('Unsafe release archive member')
        source.extractall(destination,members=members,filter='data')


@contextlib.contextmanager
def lock(root, exclusive=True):
    if root.is_symlink():raise ValueError('Managed runtime root is a symlink; preserve and reconcile it before installation')
    root.mkdir(parents=True,exist_ok=True,mode=0o700);root.chmod(0o700)
    descriptor=os.open(root/'operator.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'a') as stream:
        try: fcntl.flock(stream, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('Flow is in use; finish the running operation before installation/update/rollback')
        yield


def quiescent(artifacts):
    for path in Path(artifacts).rglob('operator.lock'):
        with path.open('r') as stream:
            try: fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError('Active workflow prevents update: '+str(path))
    for path in Path(artifacts).glob('*/*.json'):
        try: record=json.loads(path.read_text())
        except (ValueError,OSError): continue
        if record.get('quiescent') is False or record.get('status') in ('uncertain','pending'):
            if record.get('processes'):
                from .lifecycle import ProcessScope
                scope=ProcessScope.__new__(ProcessScope);scope.root=record['pid'];scope.known={int(k):v for k,v in record['processes'].items()}
                if scope.observe(): raise ValueError('Unreconciled live execution prevents update: '+str(path))


def launcher(root):
    import shlex
    current=root/'current/v2'
    return '#!/bin/sh\n# Managed by Flow v2 release installer.\ncd '+shlex.quote(str(current))+' || exit 1\nexec '+shlex.quote(str(current/'.venv/bin/python'))+' -m poc.entry "$@"\n'


def migrate_state(home, root):
    receipt=home/'.flow-v2/install.json'
    if not receipt.is_file(): return
    old=Path(json.loads(receipt.read_text())['source'])
    if old.is_relative_to(root): return
    quiescent(old/'artifacts')
    state=root/'state'; state.mkdir(exist_ok=True)
    if (old/'artifacts').is_dir() and not (state/'artifacts').exists():
        shutil.copytree(old/'artifacts',state/'artifacts',symlinks=True)
        write(state/'imported-work.json',{'source':str(old),'work_paths':[str(p.relative_to(old/'artifacts')) for p in (old/'artifacts/glg-state').glob('*/*')],
              'policy':'Read-only historical work. Create a fresh successor; approvals are not migrated into new execution.'})
    write(state/'prior-install.json',{'source':str(old),'preserved':True,'credentials_copied':False})


def relocate_clients(home,root):
    """Move opaque native stores without reading/copying credentials; keep old aliases."""
    receipt=home/'.flow-v2/install.json'
    if not receipt.exists():return []
    old=Path(json.loads(receipt.read_text())['source'])
    if old.is_relative_to(root):return []
    moved=[]
    try:
        for name in ('goose-home','codex-home','claude-home'):
            source=old/'runtime'/name;target=root/'state'/name
            if not source.is_dir() or (target.exists() and any(target.iterdir())):continue
            if target.exists():target.rmdir()
            if source.is_symlink():
                target.symlink_to(source.resolve());moved.append((source,target,'alias'))
            else:
                source.rename(target);moved.append((source,target,'move'));source.symlink_to(target)
        return moved
    except BaseException:
        undo_client_moves(moved)
        raise


def undo_client_moves(moved):
    for source,target,kind in reversed(moved):
        if kind=='move':source.unlink(missing_ok=True);target.rename(source)
        else:target.unlink()
        target.mkdir(exist_ok=True)


def prepare_release(release, root):
    v2=release/'v2'; state=root/'state'; state.mkdir(exist_ok=True)
    for name in ('artifacts','workspaces'):
        target=state/name; target.mkdir(exist_ok=True); (v2/name).symlink_to(target)
    runtime=v2/'runtime'; runtime.mkdir()
    for name in ('goose-home','codex-home','home','tmp','claude-home'):
        target=state/name; target.mkdir(exist_ok=True); (runtime/name).symlink_to(target)
    python=v2/'.venv/bin/python'
    env={k:v for k,v in os.environ.items() if k not in {'GITHUB_TOKEN','GH_TOKEN','FLOW_RELEASE_READ_TOKEN','GIT_ASKPASS','SSH_ASKPASS'}}
    subprocess.run([sys.executable,'-m','venv',str(v2/'.venv')],check=True,env=env)
    subprocess.run([str(python),'-m','pip','install','--no-index','--find-links',str(release/'wheels'),'--require-hashes','--no-deps','-r',str(release/'wheels/requirements.lock')],check=True,env=env)
    subprocess.run([str(python),'-m','pip','check'],check=True,env=env)
    adapters=runtime/'adapters'; adapters.mkdir()
    shutil.copyfile(v2/'adapters.package.json',adapters/'package.json');shutil.copyfile(v2/'adapters.package-lock.json',adapters/'package-lock.json')
    subprocess.run(['npm','ci','--ignore-scripts','--prefix',str(adapters)],check=True,env={**env,'npm_config_cache':str(root/'cache/npm')})
    subprocess.run([str(python),'-m','poc.goose_artifact','--extract'],cwd=v2,check=True,env=env)


def switch(root,target):
    temporary=root/('current-'+uuid.uuid4().hex);temporary.symlink_to(target);temporary.replace(root/'current')


def install_release(home, manifest, *, urls=None, bundle=None, preparer=prepare_release):
    home=Path(home).resolve();root=home/'.flow/v2';validate(manifest)
    with lock(root):
        current=(root/'current').resolve() if (root/'current').exists() else None
        if current and json.loads((current/'release-manifest.json').read_text())==manifest:
            return {'version':manifest['version'],'changed':False,'runtime':str(current)}
        quiescent(root/'state/artifacts'); migrate_state(home,root)
        with tempfile.TemporaryDirectory(prefix='download-',dir=root) as temporary:
            downloads=Path(temporary);fetch_assets(manifest,downloads,urls,bundle)
            release=root/'releases'/(manifest['version']+'-'+manifest['source_sha'][:12]+'-'+uuid.uuid4().hex[:8]);release.mkdir(parents=True)
            unpack(downloads/'flow-code.tar.gz',release);unpack(downloads/'python-wheels.tar.gz',release/'wheels')
            vendor=release/'v2/vendor/artifacts'
            for name in ('goose-macos-arm64.gz','goose-macos-arm64.json'):shutil.copyfile(downloads/name,vendor/name)
            write(release/'release-manifest.json',manifest)
            preparer(release,root)
        quiescent(root/'state/artifacts')
        from . import install as surfaces
        old_receipt=home/'.flow-v2/install.json'
        files={**surfaces.content(release/'v2',home),**surfaces.active_files(release/'v2',home,surfaces.content(release/'v2',home))}
        paths=[*surfaces.selected_targets(home,files),old_receipt]
        inventory=surfaces.inventory(home);paths.extend(surfaces.selected_targets(home,inventory['remove']));paths.extend(inventory['edits'])
        backup=root/'backups'/uuid.uuid4().hex;backup.mkdir(parents=True)
        snapshots={}
        for i,path in enumerate(surfaces.collapsed(paths)):
            exists=path.exists() or path.is_symlink();saved=backup/str(i)
            if exists:surfaces.copy_path(path,saved)
            snapshots[str(path)]={'exists':exists,'saved':str(saved)}
        moved=[]
        try:
            moved=relocate_clients(home,root)
            surfaces.install('install',home,source=release/'v2')
            surfaces.install('activate',home,source=release/'v2',replace_legacy=True)
            for name in ('flow','flow-v2'):
                path=home/'.local/bin'/name;path.write_text(launcher(root));path.chmod(0o755)
            receipt=json.loads(old_receipt.read_text())
            for name in ('flow','flow-v2'):
                path=home/'.local/bin'/name;receipt['files'][str(path)]=sha(path)
            write(old_receipt,receipt)
            switch(root,release)
            write(root/'install.json',{'version':manifest['version'],'source_sha':manifest['source_sha'],'current':str(release),
                  'previous':str(current) if current else None,'backup':str(backup),'snapshots':snapshots,
                  'after':{str(p):tree_digest(p) for p in surfaces.collapsed(paths)}})
        except BaseException:
            for name,entry in snapshots.items():
                path=Path(name);surfaces.remove_path(path)
                if entry['exists']:surfaces.copy_path(Path(entry['saved']),path)
            if current:switch(root,current)
            elif (root/'current').is_symlink():(root/'current').unlink()
            undo_client_moves(moved)
            raise
        return {'version':manifest['version'],'changed':True,'runtime':str(release),'rollback':'flow rollback'}


def tree_digest(path):
    path=Path(path)
    if path.is_symlink():return 'link:'+str(path.readlink())
    if path.is_file():return sha(path)
    if path.is_dir():return hashlib.sha256(json.dumps([(str(p.relative_to(path)),tree_digest(p)) for p in sorted(path.rglob('*')) if p.is_file() or p.is_symlink()]).encode()).hexdigest()
    return None


def rollback(home):
    root=Path(home).resolve()/'.flow/v2'
    with lock(root):
        quiescent(root/'state/artifacts');receipt=json.loads((root/'install.json').read_text())
        for name,digest in receipt['after'].items():
            if tree_digest(name)!=digest:raise ValueError('User edits prevent rollback; preserve and reconcile: '+name)
        from .install import remove_path,copy_path
        for name,entry in receipt['snapshots'].items():
            path=Path(name);remove_path(path)
            if entry['exists']:copy_path(Path(entry['saved']),path)
        if receipt['previous']:switch(root,Path(receipt['previous']))
        else:(root/'current').unlink(missing_ok=True)
        write(root/'rollback.json',receipt)
        (root/'install.json').unlink()
        return {'restored':receipt['previous'] or 'pre-v2 installation','history_preserved':True}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['install','update','rollback'])
    parser.add_argument('--home',type=Path,default=Path.home());parser.add_argument('--bundle',type=Path)
    parser.add_argument('--repository',default=REPOSITORY);parser.add_argument('--version');parser.add_argument('--check',action='store_true');parser.add_argument('--json',action='store_true')
    args=parser.parse_args(argv)
    try:
        if args.action=='rollback': result=rollback(args.home)
        else:
            supported()
            if args.bundle:manifest=json.loads((args.bundle/'release-manifest.json').read_text());urls=None
            else:manifest,urls=latest(args.repository,args.version)
            if args.check:
                validate(manifest);result={'latest':manifest['version'],'source_sha':manifest['source_sha'],'supported_targets':manifest['supported_targets']}
            else:result=install_release(args.home,manifest,urls=urls,bundle=args.bundle)
        print(json.dumps(result,indent=2));return 0
    except (ValueError,OSError,subprocess.CalledProcessError) as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__': main()
