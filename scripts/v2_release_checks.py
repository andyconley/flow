"""Deterministic production-package checks; never invoke provider qualification."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from release_gate import STABLE_CHECK_IDS,ContractError,canonical_digest,load_plan,write_evidence

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'v2'))
from poc import managed


def command(argv,cwd=ROOT,home=None):
    env={k:v for k,v in os.environ.items() if k not in {'GITHUB_TOKEN','GH_TOKEN','FLOW_RELEASE_READ_TOKEN','GIT_ASKPASS','SSH_ASKPASS','FLOW_V2_GOOSE_BINARY'}}
    env['PYTHONDONTWRITEBYTECODE']='1'
    if home:env['HOME']=str(home)
    result=subprocess.run([str(x) for x in argv],cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    return result.returncode,result.stdout


def installed(home):return (home/'.flow/v2/current').resolve()
def flow(home,*args):return command([home/'.local/bin/flow',*args],cwd=home,home=home)


def install(bundle,home):
    result=managed.install_release(home,json.loads((bundle/'release-manifest.json').read_text()),bundle=bundle)
    return 0,json.dumps(result)+'\n'


def verify_assets(bundle,plan):
    expected=os.environ.get('FLOW_RELEASE_MANIFEST_SHA')
    if not expected or managed.sha(bundle/'release-manifest.json')!=expected:raise ContractError('Distribution manifest differs from build job identity')
    manifest=json.loads((bundle/'release-manifest.json').read_text());managed.validate(manifest)
    if manifest['source_sha']!=plan['source_sha'] or manifest['version']!=plan['predicted_release']['tag']:
        raise ContractError('Distribution identity differs from exact release plan')
    for name,expected in manifest['assets'].items():
        path=bundle/name
        if path.stat().st_size!=expected['size'] or managed.sha(path)!=expected['sha256']:raise ContractError('Distribution checksum mismatch: '+name)
    goose=json.loads((bundle/'goose-macos-arm64.json').read_text())
    if goose.get('build_kind')!='pinned-source-CI-release-build':raise ContractError('Publication requires a fresh pinned-source CI Goose build')
    if goose['source_lock']!=json.loads((ROOT/'v2/vendor/goose.lock.json').read_text()):raise ContractError('Goose provenance differs from source lock')
    return 0,'All code, wheel and Goose assets match exact plan, hashes and pinned-source build provenance\n'


def tests(home,pattern):
    release=installed(home);python=release/'v2/.venv/bin/python'
    return command([python,'-m','unittest','discover','-s','tests','-p',pattern,'-v'],cwd=release/'v2',home=home)


def run_candidate(plan_path,output,fail_check=None,command_overrides=None):
    from release_candidate import _git,_log_result,create_candidate_remote
    plan=load_plan(plan_path)
    if not plan['release_required'] or _git('rev-parse','HEAD')!=plan['source_sha']:raise ContractError('Candidate source/plan identity mismatch')
    bundle=Path(os.environ.get('FLOW_RELEASE_BUNDLE',ROOT/'.release/dist')).resolve()
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);logs=output.parent/'logs'
    checks=[];blocked=False
    with tempfile.TemporaryDirectory(prefix='flow-v2-candidate-') as temporary:
        root=Path(temporary);fresh=root/'fresh';fresh.mkdir();upgrade=root/'upgrade';upgrade.mkdir()
        candidate_url=create_candidate_remote(plan,root/'candidate.git')
        def migrate():
            # A legacy layout is preserved and replaced without starting its
            # retired engine or downloading any legacy runtime dependency.
            launcher=upgrade/'.local/bin/flow';launcher.parent.mkdir(parents=True)
            launcher.write_text('#!/bin/sh\nexec "'+str(upgrade)+'/.flow/runtime/python" "'+str(upgrade)+'/.flow/source/cli/flow.py" "$@"\n');launcher.chmod(0o755)
            overlay=upgrade/'.flow/user';overlay.mkdir(parents=True);(overlay/'flow.toml').write_text('# user configuration\n')
            history=upgrade/'.flow/archive/retained.json';history.parent.mkdir();history.write_text('retained history')
            result=install(bundle,upgrade)
            if (history.read_text()!='retained history' or (overlay/'flow.toml').read_text()!='# user configuration\n'):raise ContractError('Legacy user data changed')
            return result[0],result[1]+'One-time legacy migration fixture passed; retired engine was not executed\n'
        def user_surfaces():
            receipt=json.loads((fresh/'.flow-v2/install.json').read_text())
            for name,expected in receipt['files'].items():
                if managed.sha(name)!=expected:raise ContractError('Installed surface mismatch: '+name)
            return 0,'All installed native skills/launchers match ownership receipt\n'
        def smoke():
            result=tests(fresh,'test_role_renderer.py')
            if result[0]:return result
            return tests(fresh,'test_command_classification.py')
        def representative():
            version=flow(fresh,'--version')
            if version[0] or plan['predicted_release']['tag'] not in version[1]:return 1,version[1]
            project=fresh/'project';project.mkdir(exist_ok=True)
            result=flow(fresh,'--project',str(project),'context')
            if result[0]:return result
            return flow(fresh,'update','--check','--json','--bundle',str(bundle))
        def rollback():
            result=managed.rollback(upgrade)
            if (upgrade/'.flow/archive/retained.json').read_text()!='retained history':raise ContractError('Rollback lost history')
            return 0,json.dumps(result)+'\n'
        commands={
            'release-assets':lambda:verify_assets(bundle,plan),
            'clean-tracked-tree':lambda:command(['git','diff','--exit-code','HEAD']),
            'candidate-fresh-install':lambda:install(bundle,fresh),
            'python-test-suite':lambda:tests(fresh,'test_*.py'),
            'release-contract-tests':lambda:command([installed(fresh)/'v2/.venv/bin/python','-m','unittest','tests.test_release_gate','tests.test_release_highlights','-v']),
            'candidate-upgrade':migrate,'user-surfaces':user_surfaces,
            'stage-coordination':lambda:tests(fresh,'test_stage_coordination.py'),
            'doctor-check':lambda:flow(fresh,'doctor','--json'),'runtime-smoke-static':smoke,
            'representative-cli':representative,'candidate-rollback':rollback}
        if command_overrides is not None:
            if set(command_overrides)!=set(STABLE_CHECK_IDS):raise ContractError('Overrides must cover every required v2 release check')
            commands=dict(command_overrides)
        for check in STABLE_CHECK_IDS:
            started=time.monotonic()
            if blocked:result=None
            elif fail_check==check:result=(97,'Injected release gate regression failure\n')
            else:
                try:result=commands[check]()
                except Exception as error:result=(1,type(error).__name__+': '+str(error)+'\n')
            record=_log_result(logs,check,started,result);checks.append(record);blocked=blocked or record['result']=='failed'
        evidence={'schema_version':1,'plan_digest':canonical_digest(plan),'source_sha':plan['source_sha'],
            'candidate_version':plan['predicted_release']['version'],'candidate_tag':plan['predicted_release']['tag'],
            'candidate_repository':{'url':candidate_url,'main_sha':plan['source_sha'],'tag_sha':plan['source_sha']},
            'runner_sha':plan['source_sha'],'checks':checks,'overall_result':'failed' if blocked else 'passed'}
        write_evidence(output,evidence,plan=plan)
    return evidence,1 if blocked else 0


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args();code,message=verify_assets(args.bundle,load_plan(args.plan));print(message);raise SystemExit(code)
