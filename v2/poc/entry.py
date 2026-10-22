"""The supported managed flow command: conversation/approvals plus v2 runtime."""
import json
import os
from pathlib import Path
import sys
from .managed import lock,main as manage,installation_status
from .runtime_env import ROOT


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if args and args[0]=='installation':
        import argparse
        parser=argparse.ArgumentParser(prog='flow installation status',description='Read selected release identity and retained legacy metadata; no provisioning or Git operations.')
        parser.add_argument('--home',type=Path,default=Path.home());parser.add_argument('--json',action='store_true')
        rest=args[1:]
        if rest and rest[0]=='status':rest=rest[1:]
        options=parser.parse_args(rest)
        print(json.dumps(installation_status(options.home,ROOT),indent=2));return 0
    if args and args[0]=='knowledge':
        from .knowledge import main as knowledge
        return knowledge(args[1:])
    if args and args[0] in ('install','update','rollback'):
        return manage(args)
    root=Path.home()/'.flow/v2'
    if args==['--version']:
        manifest=ROOT.parent/'release-manifest.json'
        version=json.loads(manifest.read_text())['version'] if manifest.exists() else 'development'
        invocation=installation_status(Path.home(),ROOT)['invocation']['mode']
        print('Flow '+version+' (v2 Goose/LangGraph; '+invocation+')');return 0
    if args and args[0]=='doctor':
        from .goose_artifact import selected_binary
        binary=selected_binary(ROOT)
        print(json.dumps({'ok':True,'engine':'Goose/LangGraph','source':str(ROOT),'goose':str(binary),'live_provider_qualification':'not_run','installation':installation_status(Path.home(),ROOT)}));return 0
    from .knowledge import home as knowledge_home,trigger,status,reconcile_shared,locked
    kh=knowledge_home()
    try:
        if not (kh/'base.json').exists():
            with locked(kh):reconcile_shared(kh)
        ks=trigger(kh)
        if ks.get('pending'):print('Flow knowledge: '+json.dumps(ks),file=sys.stderr)
    except Exception as error:print('Flow knowledge pending: '+str(error),file=sys.stderr)
    with lock(root,exclusive=False):
        from .glg import main as workflow
        return workflow(args)


if __name__=='__main__': raise SystemExit(main())
