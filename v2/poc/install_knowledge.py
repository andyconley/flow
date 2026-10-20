"""Install/update knowledge gate, executed by the staged release interpreter."""
import argparse
import json
from pathlib import Path
import sys
from . import knowledge as k
from .knowledge_health import doctor
from .knowledge_provision import online, plan


def provision(root, mode='ask', *, interactive=None, choose=None):
    """No detached worker: installation succeeds only after an audited snapshot."""
    root = Path(root)
    current = k.read(root/'settings.json', {})
    candidate = k.read(root/'provisioned-runtime.json', {})
    health = doctor(root) if current or candidate else {'ok': False, 'checks': {}, 'reason': 'Not configured'}
    if not health['ok'] and mode == 'ask':
        print('Flow install/update: local knowledge needs provisioning. '+json.dumps(plan()), file=sys.stderr, flush=True)
        print('No chat weights, agent provider changes or credential copying. Provisioning/initial audit is bounded to 30 minutes. Deferring a fresh store leaves agent launches blocked until provisioning; existing known-good snapshots remain usable. Download, defer or cancel.', file=sys.stderr, flush=True)
        tty = sys.stdin.isatty() if interactive is None else interactive
        terminal = None
        # curl | bash consumes stdin; use only an existing controlling terminal.
        # Explicit noninteractive/JSON policy never enters this ask branch.
        if interactive is None and not tty:
            try:terminal = open('/dev/tty', 'r')
            except OSError:pass
            tty = terminal is not None
        if not tty:
            raise ValueError('Knowledge provisioning requires consent; no terminal input was read. Retry install/update with --knowledge download, --knowledge offline (verified existing assets), or --knowledge defer. No runtime activation occurred.')
        print('Choose [download/defer/cancel] (default cancel): ', end='', file=sys.stderr, flush=True)
        try:answer = (choose() if choose else (terminal or sys.stdin).readline()).strip().lower()
        finally:
            if terminal:terminal.close()
        if answer not in ('download', 'defer'):
            raise ValueError('Installation canceled; previous runtime and knowledge remain selected')
        mode = answer
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
        if health['ok'] and not current:
            k.backup(root, 'before-install-configuration')
            k.write(root/'settings.json', {**candidate, 'model_digest': health['checks']['local_model']['digest']})
        if not health['ok']:
            if mode == 'offline':
                raise ValueError('Offline knowledge assets/configuration are incomplete; no downloads attempted. '+json.dumps(health)+'; supply verified offline assets using knowledge setup/configure, or explicitly choose --knowledge defer.')
            previous = {**k.read(root/'provisioned-runtime.json', {}), **current}
            k.write(root/'provisioning-status.json', {'state': 'running', 'consent': 'install/update --knowledge download or interactive download'})
            result = online(root, sys.executable, previous.get('model', 'qwen3:4b'), previous.get('ollama', 'http://127.0.0.1:11434'))
            if not result['configured']:
                k.write(root/'provisioning-status.json', {'state': 'awaiting_model', **result})
                raise ValueError('Local extraction model unavailable; chat weights were not downloaded. '+json.dumps(result)+'; satisfy the printed Ollama requirement and retry install/update --knowledge download, or explicitly defer.')
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
    args = parser.parse_args(argv)
    try:
        result = provision(args.root, args.mode)
        args.result.write_text(json.dumps(result))
        return 0
    except Exception as error:
        print('Flow install/update knowledge failed: '+str(error), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
