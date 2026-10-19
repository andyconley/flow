"""Opt-in Flow v2.0 packaging and explicit reversible legacy selection."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid
from .artifacts import atomic_write
from .runtime_env import goose_binary
from .legacy_install import inventory, public_inventory

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2.0.0-preview'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def launcher(source):
    return ('#!/bin/sh\n# Managed by Flow v2.0; source-bound opt-in launcher.\n'
            + 'cd '+shlex.quote(str(source))+' || exit 1\n'
            + 'case "${1-}" in install|update|inventory|activate|restore)\n  exec '+shlex.quote(str(source/'.venv/bin/python'))+' -m poc.install "$@" ;;\nesac\n'
            + 'exec '+shlex.quote(str(source/'.venv/bin/python'))+' -m poc.glg "$@"\n').encode()


def content(source, home):
    private = home/'.flow-v2'
    command = str(home/'.local/bin/flow-v2')
    files = {home/'.local/bin/flow-v2': launcher(source)}
    for path in sorted((source/'skills').glob('flow-*/SKILL.md')):
        body = path.read_text().replace('FLOW_V2', command).replace('SKILLS', str(private/'skills')).replace('SOURCE', str(source))
        files[private/'skills'/path.parent.name/'SKILL.md'] = body.encode()
    bootstrap = f'''---
name: flow-v2
description: Opt into Flow v2.0 without replacing the legacy Flow commands.
---

<!-- Managed by Flow v2.0 -->

Use Flow v2.0 (Goose/LangGraph) for this requested workflow. The selected launcher is `{command}`. Existing global flow-* skills may still be legacy: do not invoke them as v2 merely because their names match. Read the requested command's v2 instructions at `{private}/skills/flow-NAME/SKILL.md`, replacing NAME with boot, define, solution, plan, implement, review, status, resume, close, archive, accept, scout, init-project or help. For an orientation request start with flow-boot. Read only relevant command instructions. Follow the real command body and its approval/recovery contracts; do not create another coordinator. See `{source}/FLOW_V2_INSTALL.md` for current usage and explicit reversible legacy selection. Do not cut over the global flow command or skills unless the user explicitly requests that switch.
'''.encode()
    for base in (home/'.agents/skills', home/'.claude/skills'):
        files[base/'flow-v2/SKILL.md'] = bootstrap
    return files


def active_files(source, home, staged):
    files = {home/'.local/bin/flow': launcher(source)}
    for path, data in staged.items():
        if path.is_relative_to(home/'.flow-v2/skills'):
            for base in (home/'.agents/skills', home/'.claude/skills'):
                files[base/path.parent.name/'SKILL.md'] = data
    return files


def copy_path(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        destination.symlink_to(source.readlink())
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    elif source.exists():
        shutil.copy2(source, destination)


def remove_path(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def selected_targets(home, files):
    return sorted({path.parent if path.name == 'SKILL.md' else path for path in files}, key=str)


def collapsed(paths):
    targets = []
    for path in sorted(set(paths), key=lambda p: (len(p.parts), str(p))):
        if not any(path.is_relative_to(parent) for parent in targets):
            targets.append(path)
    return targets


def install(action, home, source=ROOT, replace_legacy=False, dry_run=False):
    home, source = Path(home).resolve(), Path(source).resolve()
    private = home/'.flow-v2'; manifest = private/'install.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else {'files': {}, 'selection': 'side-by-side'}
    legacy = inventory(home)
    saved_inventory = {}
    if previous.get('backup'):
        saved_path = Path(previous['backup'])/'legacy-inventory.json'
        if saved_path.is_file():
            saved_inventory = json.loads(saved_path.read_text())
    retained = previous.get('retained_legacy', saved_inventory.get('ambiguous', []))
    known = {item['path'] for item in legacy['ambiguous']}
    for item in retained:
        path = Path(item['path'])
        if (path.exists() or path.is_symlink()) and item['path'] not in known:
            legacy['ambiguous'].append(item)
    prior_targets = previous.get('protected_legacy_targets', saved_inventory.get('protected_ambiguous_targets', []))
    legacy['protected_targets'] = sorted(set(legacy['protected_targets']) | {Path(p) for p in prior_targets if Path(p).exists()}, key=str)
    if action == 'inventory':
        return public_inventory(legacy)
    if action == 'activate' and not replace_legacy:
        raise ValueError('Activation requires --replace-legacy; normal install preserves legacy Flow')
    for required in (source/'.venv/bin/python', source/'role-bundle/catalog.json', goose_binary(source)):
        if not required.exists():
            raise ValueError(f'Existing local runtime is missing: {required}; this installer does not download dependencies')
    staged = content(source, home)
    full = active_files(source, home, staged)
    if action == 'restore':
        if previous.get('selection') != 'active':
            return {'action': action, 'selection': previous.get('selection'), 'changed': [], 'note': 'Legacy selection already restored'}
        backup = Path(previous['backup'])
        snapshots = json.loads((backup/'snapshot.json').read_text())
        for name, expected in previous.get('shared_after', {}).items():
            if digest(Path(name)) != expected:
                raise ValueError(f'Shared configuration changed since cutover: {name}; preserve it and reconcile from {backup} before rollback')
        result = {'action': action, 'selection': 'side-by-side', 'restore_from': str(backup), 'targets': list(snapshots), 'dry_run': dry_run}
        if dry_run:
            return result
        # Keep the v2 surfaces too, including any post-install user edits.
        before = backup/'before-restore'
        for index, (name, entry) in enumerate(snapshots.items()):
            path = Path(name)
            copy_path(path, before/str(index))
            remove_path(path)
            if entry['exists']:
                copy_path(backup/entry['stored'], path)
        previous['selection'] = 'side-by-side'
        previous['files'] = {name: sha for name, sha in previous['files'].items() if Path(name) not in full}
        atomic_write(manifest, (json.dumps(previous, indent=2, sort_keys=True)+'\n').encode())
        return result
    activate = action == 'activate' or previous.get('selection') == 'active'
    starting_activation = action == 'activate' and previous.get('selection') != 'active'
    if starting_activation:
        collisions = [str(path) for path in full if path.exists() and path not in legacy['remove'] and digest(path) != hashlib.sha256(full[path]).hexdigest()]
        critical = {str(home/p) for p in ('.claude/settings.json','.claude/CLAUDE.md','.codex/config.toml','.codex/hooks.json','.codex/AGENTS.md')}
        conflicts = [item for item in legacy['ambiguous'] if item['path'] in critical or item['path'] in collisions or any(token in item['path'] for token in ('/skills/flow-', '/commands/flow-', '/prompts/flow-'))]
        if collisions or conflicts:
            raise ValueError('Ambiguous legacy ownership blocks cutover; inspect inventory: '+', '.join(collisions+[item['path'] for item in conflicts]))
    files = {**staged, **full} if activate else staged
    changed = []
    for path, data in files.items():
        expected = hashlib.sha256(data).hexdigest(); current = digest(path)
        replacing = action == 'activate' and previous.get('selection') != 'active' and path in full
        if (path.exists() or path.is_symlink()) and current != expected and not replacing:
            if previous['files'].get(str(path)) != current or current is None:
                raise ValueError(f'Refusing to replace an unmanaged or locally modified surface: {path}')
        if current != expected:
            changed.append(str(path))
    result = {'action': action, 'selection': 'active' if activate else 'side-by-side',
              'changed': changed, 'managed_paths': [str(p) for p in files], 'dry_run': dry_run,
              'legacy_preserved': not activate}
    result['legacy_cleanup'] = public_inventory(legacy)
    if dry_run:
        return result
    backup = previous.get('backup')
    snapshots = {}
    if starting_activation:
        backup = str(private/'backups'/uuid.uuid4().hex)
        Path(backup).mkdir(parents=True, mode=0o700)
        snapshots = {}
        targets = collapsed([*selected_targets(home, full), *legacy['remove'], *legacy['edits']])
        for index, path in enumerate(targets):
            exists = path.exists() or path.is_symlink()
            stored = 'surfaces/'+str(index)
            if exists:
                copy_path(path, Path(backup)/stored)
            snapshots[str(path)] = {'exists': exists, 'stored': stored}
        atomic_write(Path(backup)/'snapshot.json', (json.dumps(snapshots, indent=2)+'\n').encode())
        atomic_write(Path(backup)/'legacy-inventory.json', (json.dumps(public_inventory(legacy), indent=2)+'\n').encode())
        # Replace directories rather than writing through a legacy skill symlink.
        for name in snapshots:
            remove_path(Path(name))
    try:
        for path, data in files.items():
            if str(path) in changed or not path.exists():
                if path.is_symlink():
                    path.unlink()
                atomic_write(path, data)
            if path.parent == home/'.local/bin':
                path.chmod(0o755)
        if starting_activation:
            for path, data in legacy['edits'].items():
                atomic_write(path, data)
    except OSError:
        if starting_activation:
            for name, entry in snapshots.items():
                path = Path(name)
                remove_path(path)
                if entry['exists']:
                    copy_path(Path(backup)/entry['stored'], path)
        raise
    commit = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    state = {'version': VERSION, 'source': str(source), 'source_commit': commit.stdout.strip(),
             'selection': result['selection'], 'backup': backup,
             'shared_after': {str(p): hashlib.sha256(data).hexdigest() for p, data in legacy['edits'].items()} if starting_activation else previous.get('shared_after', {}),
             'retained_legacy': legacy['ambiguous'],
             'protected_legacy_targets': [str(p) for p in legacy['protected_targets']] if starting_activation else previous.get('protected_legacy_targets', saved_inventory.get('protected_ambiguous_targets', [])),
             'files': {str(path): hashlib.sha256(data).hexdigest() for path, data in files.items()}}
    raw = (json.dumps(state, indent=2, sort_keys=True)+'\n').encode()
    if not manifest.exists() or manifest.read_bytes() != raw:
        atomic_write(manifest, raw)
    result['manifest'] = str(manifest)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'update', 'activate', 'restore', 'inventory'])
    parser.add_argument('--home', type=Path, default=Path.home(), help='Installation target; defaults to current user')
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--replace-legacy', action='store_true', help='Explicitly select v2 for global flow and supported flow-* skills')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(install(args.action, args.home, args.source, args.replace_legacy, args.dry_run), indent=2))
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
