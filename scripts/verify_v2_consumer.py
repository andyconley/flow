#!/usr/bin/env python3
"""Install actual distribution assets in a disposable home; no provider calls."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'v2'))
from poc import managed


def verify(bundle,full_tests=True):
    bundle=Path(bundle).resolve();manifest=json.loads((bundle/'release-manifest.json').read_text())
    managed.supported();managed.validate(manifest)
    with tempfile.TemporaryDirectory(prefix='flow-v2-consumer-') as temporary:
        home=Path(temporary);env={**os.environ,'HOME':str(home),'PYTHONDONTWRITEBYTECODE':'1'}
        for key in ('GITHUB_TOKEN','GH_TOKEN','FLOW_RELEASE_READ_TOKEN','FLOW_V2_GOOSE_BINARY'):
            env.pop(key,None)
        # No model acquisition/provider calls in this package-consumer gate.
        initial=managed.install_release(home,manifest,bundle=bundle,knowledge_mode='defer')
        if initial.get('knowledge',{}).get('state')!='deferred':raise ValueError('Consumer gate requires an explicit visible deferred knowledge policy')
        release=(home/'.flow/v2/current').resolve()
        def run(args,cwd=home):subprocess.run([str(x) for x in args],cwd=cwd,env=env,check=True)
        launcher=home/'.local/bin/flow'
        run([launcher,'--version']);run([launcher,'doctor','--json'])
        project=home/'project';project.mkdir();run([launcher,'--project',project,'context'])
        if full_tests:run([release/'v2/.venv/bin/python','-m','unittest','discover','-s','tests','-v'],cwd=release/'v2')
        if managed.install_release(home,manifest,bundle=bundle,knowledge_mode='defer')['changed']:raise ValueError('Repeated install is not idempotent')
        managed.rollback(home)
    return {'result':'passed','version':manifest['version'],'source_sha':manifest['source_sha'],'live_provider_calls':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=verify(args.bundle)
    if args.output:args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
