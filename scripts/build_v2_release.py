#!/usr/bin/env python3
"""Build checksum/provenance-bound v2 assets. This is maintainer/CI tooling only."""
import argparse
import gzip
import hashlib
import importlib.util
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

ROOT=Path(__file__).resolve().parents[1]


def run(args,**kwargs): return subprocess.check_output([str(x) for x in args],text=True,**kwargs).strip()
def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def package_goose(binary,output,source_lock,build_kind):
    if platform.system()!='Darwin' or platform.machine()!='arm64':raise ValueError('Only Darwin arm64 production artifacts are qualified')
    if 'arm64' not in run(['file',binary]):raise ValueError('Unexpected Goose architecture')
    load=run(['otool','-l',binary]);libraries=run(['otool','-L',binary]).splitlines()[1:]
    if 'LC_RPATH' in load or any(not line.strip().startswith(('/System/Library/','/usr/lib/')) for line in libraries):raise ValueError('Non-system Goose linkage')
    run(['codesign','--verify','--strict',binary])
    with tempfile.TemporaryDirectory() as home:
        env={**os.environ,'HOME':home,'GOOSE_PATH_ROOT':home+'/goose','GOOSE_DISABLE_KEYRING':'1','GOOSE_TELEMETRY_ENABLED':'false'}
        if run([binary,'--version'],env=env)!=source_lock['version']:raise ValueError('Unexpected Goose version')
        help_text=run([binary,'run','--help'],env=env)
        if any(flag not in help_text for flag in ('--no-profile','--output-format','--max-tool-repetitions')):raise ValueError('Missing native Goose CLI capability')
    archive=output/'goose-macos-arm64.gz'
    with Path(binary).open('rb') as source,archive.open('wb') as target:
        with gzip.GzipFile(filename='',fileobj=target,mode='wb',mtime=0,compresslevel=9) as compressed:shutil.copyfileobj(source,compressed)
    metadata={'schema_version':1,'platform':'Darwin','architecture':'arm64','minimum_macos':'15.0',
        'deployment_target':re.search(r'minos\s+(\S+)',load)[1],'sdk':re.search(r'sdk\s+(\S+)',load)[1],
        'version':source_lock['version'],'archive':archive.name,'archive_size':archive.stat().st_size,'archive_sha256':digest(archive),
        'binary_size':Path(binary).stat().st_size,'binary_sha256':digest(binary),'source_lock':source_lock,
        'dynamic_libraries':libraries,'build_kind':build_kind,'rust_toolchain':'1.99.0',
        'build_command':['cargo','build','--release','--locked','-p','goose-cli','--bin','goose','--no-default-features','--features',','.join(source_lock['features'])],
        'qualification':'Offline binary/recipe/consumer checks on Apple Silicon macOS; no live provider qualification',
        'runner':{'system':platform.system(),'architecture':platform.machine(),'macos':platform.mac_ver()[0]}}
    (output/'goose-macos-arm64.json').write_text(json.dumps(metadata,indent=2)+'\n')


def build_goose(directory,output,binary=None):
    lock=json.loads((ROOT/'v2/vendor/goose.lock.json').read_text());patch=ROOT/'v2/vendor'/lock['patch']
    if digest(patch)!=lock['patch_sha256']:raise ValueError('Goose patch hash mismatch')
    if binary:
        package_goose(binary,output,lock,'existing-qualified-Studio-binary/offline-package-test')
        return
    directory.mkdir(parents=True)
    run(['git','init','-q',directory]);run(['git','-C',directory,'remote','add','origin',lock['repository']])
    run(['git','-C',directory,'fetch','--depth','1','origin',lock['base_commit']])
    run(['git','-C',directory,'checkout','--detach',lock['base_commit']])
    if run(['git','-C',directory,'rev-parse','HEAD'])!=lock['base_commit']:raise ValueError('Wrong Goose source')
    run(['git','-C',directory,'apply','--index',patch])
    spec=importlib.util.spec_from_file_location('bootstrap',ROOT/'v2/bootstrap.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.verify_goose_source(directory,lock)
    if '1.99.0' not in run(['rustc','--version']):raise ValueError('Pinned Rust 1.99.0 required by build pipeline')
    environment={**os.environ,'CARGO_BUILD_JOBS':'2','CARGO_PROFILE_RELEASE_LTO':'false','CARGO_PROFILE_RELEASE_CODEGEN_UNITS':'16','CARGO_TARGET_DIR':str(ROOT/'.release/goose-target')}
    subprocess.run(['cargo','build','--release','--locked','-p','goose-cli','--bin','goose','--no-default-features','--features',','.join(lock['features'])],cwd=directory,env=environment,check=True)
    module.verify_goose_source(directory,lock)
    package_goose(ROOT/'.release/goose-target/release/goose',output,lock,'pinned-source-CI-release-build')


def wheels(destination):
    destination.mkdir(parents=True)
    subprocess.run([sys.executable,'-m','pip','download','--only-binary=:all:','--no-deps','-r',str(ROOT/'v2/requirements.lock'),'-d',str(destination)],check=True)
    hashes={re.sub(r'[-_.]+','-',wheel.name.split('-')[0]).lower():digest(wheel) for wheel in destination.glob('*.whl')}
    locked=[]
    for requirement in (ROOT/'v2/requirements.lock').read_text().splitlines():
        if not requirement.strip() or requirement.startswith('#'):continue
        name=re.sub(r'[-_.]+','-',requirement.split('==')[0]).lower()
        locked.append(requirement+' --hash=sha256:'+hashes[name])
    (destination/'requirements.lock').write_text('\n'.join(locked)+'\n')


def build(version,output,source_sha,binary=None):
    if not re.fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('Stable version tag required')
    if run(['git','rev-parse','HEAD'],cwd=ROOT)!=source_sha:raise ValueError('Build source SHA mismatch')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='flow-v2-build-') as directory:
        temporary=Path(directory)
        build_goose(ROOT/'.release/goose-source',output,binary)
        with (output/'flow-code.tar.gz').open('wb') as target:
            subprocess.run(['git','archive','--format=tar.gz',source_sha,'--','.',':(exclude)v2/vendor/artifacts/goose-macos-arm64.gz'],cwd=ROOT,stdout=target,check=True)
        wheelhouse=temporary/'wheels';wheels(wheelhouse)
        with tarfile.open(output/'python-wheels.tar.gz','w:gz') as archive:
            for path in sorted(wheelhouse.iterdir()):archive.add(path,arcname=path.name)
    manifest={'schema_version':1,'version':version,'source_sha':source_sha,'supported_targets':['Darwin-arm64'],'minimum_macos':'15.0',
        'assets':{p.name:{'size':p.stat().st_size,'sha256':digest(p)} for p in sorted(output.iterdir()) if p.name in ('flow-code.tar.gz','python-wheels.tar.gz','goose-macos-arm64.gz','goose-macos-arm64.json')}}
    (output/'release-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(row['sha256']+'  '+name+'\n' for name,row in manifest['assets'].items()))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--version',required=True);parser.add_argument('--source-sha',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--existing-binary',type=Path,help='Offline maintainer packaging test only; publication pipeline always builds pinned source')
    args=parser.parse_args();build(args.version,args.output.resolve(),args.source_sha,args.existing_binary)
