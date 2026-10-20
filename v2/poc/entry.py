"""The supported managed flow command: conversation/approvals plus v2 runtime."""
import json
import os
from pathlib import Path
import sys
from .managed import lock,main as manage
from .runtime_env import ROOT


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ('install','update','rollback'):
        return manage(args)
    root=Path.home()/'.flow/v2'
    if args==['--version']:
        manifest=ROOT.parent/'release-manifest.json'
        version=json.loads(manifest.read_text())['version'] if manifest.exists() else 'development'
        print('Flow '+version+' (v2 Goose/LangGraph)');return 0
    if args and args[0]=='doctor':
        from .goose_artifact import selected_binary
        binary=selected_binary(ROOT)
        print(json.dumps({'ok':True,'engine':'Goose/LangGraph','source':str(ROOT),'goose':str(binary),'live_provider_qualification':'not_run'}));return 0
    with lock(root,exclusive=False):
        from .glg import main as workflow
        return workflow(args)


if __name__=='__main__': main()
