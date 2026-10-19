"""Inventory only attributable legacy surfaces; never project work or credentials."""
import hashlib
import json
from pathlib import Path
import shlex
import tomllib

BEGIN = '\n# BEGIN FLOW MANAGED CODEX ROLES\n'
END = '# END FLOW MANAGED CODEX ROLES\n'
ALLOWED = ('.agents/skills/', '.claude/skills/', '.codex/skills/', '.claude/commands/',
           '.codex/prompts/', '.claude/hooks/', '.codex/hooks/', '.claude/agents/',
           '.codex/agents/', '.flow/generated/agents/')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inventory(home):
    home = Path(home).resolve()
    remove, edits, ambiguous = set(), {}, []
    overlay_commands = set()
    merge_entries = []
    for runtime in ('claude', 'codex'):
        manifest = home/('.'+runtime)/'flow.managed.toml'
        if not manifest.is_file():
            continue
        try:
            doc = tomllib.loads(manifest.read_text())
        except (ValueError, OSError) as error:
            ambiguous.append({'path': str(manifest), 'reason': str(error)}); continue
        if not isinstance(doc.get('managed'), dict) or doc['managed'].get('generator') != 'flow':
            ambiguous.append({'path': str(manifest), 'reason': 'Not a Flow ownership manifest'}); continue
        remove.add(manifest)
        for entry in doc.get('files', []):
            raw = entry.get('path', '')
            path = home/raw
            if path.is_absolute() and (Path(raw).is_absolute() or '..' in Path(raw).parts):
                ambiguous.append({'path': raw, 'reason': 'Unsafe manifest path'}); continue
            if entry.get('sync_mode') == 'merge':
                if raw in ('.claude/settings.json', '.codex/config.toml', '.codex/hooks.json'):
                    merge_entries.append((path, entry))
                else:
                    ambiguous.append({'path': str(path), 'reason': 'Unrecognized shared configuration; retained'})
                continue
            if raw == str(manifest.relative_to(home)):
                continue
            if not raw.startswith(ALLOWED) and raw not in ('.claude/CLAUDE.md', '.codex/AGENTS.md'):
                ambiguous.append({'path': str(path), 'reason': 'Outside legacy surface allowlist; retained'}); continue
            if not path.exists() and not path.is_symlink():
                continue
            if str(entry.get('source', '')).startswith('~/.flow/user/'):
                # Ownership by the old generator does not make a user's
                # command obsolete. Preserve its registration and any alias
                # target, even when it has a valid managed hash.
                overlay_commands.add(path)
                continue
            if path.is_symlink() and entry.get('link') == str(path.readlink()):
                remove.add(path)
            elif not path.is_symlink() and path.is_file() and entry.get('sha256') == sha(path.read_bytes()):
                remove.add(path)
            else:
                ambiguous.append({'path': str(path), 'reason': 'Missing or mismatched ownership hash; user edits preserved'})
    for path in (home/'.local/bin').glob('flow*'):
        if not path.is_file() or path.name == 'flow-v2':
            continue
        text = path.read_text(errors='replace')
        lines = [line for line in text.splitlines() if line.strip() and not line.startswith('#') and line != 'set -euo pipefail']
        # This exact old launch shape points to Flow's private source/runtime.
        if path.name in ('flow', 'flow-mcp', 'flow-shaper-mcp') and len(lines) == 1 and lines[0].startswith('exec ') and '/.flow/' in lines[0] and ('/cli/flow.py' in lines[0] or '/cli/shaper_mcp.py' in lines[0]):
            remove.add(path)
        elif path.name == 'flow' and 'Managed by Flow v2.0' not in text:
            ambiguous.append({'path': str(path), 'reason': 'Launcher is not an attributable Flow wrapper'})
    owned_hooks = {str(p.resolve()) for p in remove if '/hooks/flow-' in str(p)}
    for relative in ('.agents/skills', '.claude/skills', '.codex/skills', '.claude/commands', '.codex/prompts'):
        for path in (home/relative).glob('flow-*'):
            candidate = path/'SKILL.md' if path.is_dir() else path
            if not candidate.is_file() or candidate in remove or candidate in overlay_commands:
                continue
            if 'Managed by Flow v2.0' not in candidate.read_text(errors='replace'):
                ambiguous.append({'path': str(candidate), 'reason': 'Unmanifested or modified command registration; retained'})
    for path, entry in merge_entries:
        if not path.exists():
            continue
        if path.is_symlink():
            ambiguous.append({'path': str(path), 'reason': 'Shared configuration symlink; retained'}); continue
        if entry.get('kind') == 'agent-registration-config':
            text = path.read_text()
            if BEGIN not in text and END not in text:
                continue
            if text.count(BEGIN) != 1 or text.count(END) != 1:
                ambiguous.append({'path': str(path), 'reason': 'Malformed managed role markers'}); continue
            start, stop = text.index(BEGIN), text.index(END)+len(END)
            block = text[start:stop]; outside = text[:start]+text[stop:]
            owned = {entry.get('block_sha256'), entry.get('previous_block_sha256')}
            try:
                full_doc, block_doc, outside_doc = map(tomllib.loads, (text, block, outside))
                collision = not isinstance(full_doc.get('agents', {}), dict) or not isinstance(block_doc.get('agents', {}), dict)
                if not collision:
                    collision = any(full_doc.get('agents', {}).get(name) != value for name, value in block_doc.get('agents', {}).items())
            except ValueError:
                collision = True
            if sha(block.encode()) not in owned or collision:
                ambiguous.append({'path': str(path), 'reason': 'Edited/colliding role registration; retained'}); continue
            edits[path] = outside.encode()
        elif entry.get('kind') in ('settings', 'hooks-file'):
            try:
                doc = json.loads(path.read_text())
            except ValueError:
                ambiguous.append({'path': str(path), 'reason': 'Invalid shared JSON; retained'}); continue
            if not isinstance(doc, dict) or not isinstance(doc.get('hooks', {}), dict):
                ambiguous.append({'path': str(path), 'reason': 'Unrecognized shared hook shape; retained'}); continue
            changed = False
            for event, groups in list(doc.get('hooks', {}).items()):
                if not isinstance(groups, list):
                    continue
                new_groups = []
                for group in groups:
                    if not isinstance(group, dict) or not isinstance(group.get('hooks'), list):
                        new_groups.append(group); continue
                    kept = []
                    for handler in group['hooks']:
                        command = handler.get('command', '') if isinstance(handler, dict) else ''
                        try:
                            tokens = shlex.split(command.replace('$HOME', str(home)).replace('~/', str(home)+'/')) if isinstance(command, str) else []
                        except ValueError:
                            tokens = []
                        tokens = [str(Path(token).resolve()) if token.startswith('/') else token for token in tokens]
                        if isinstance(handler, dict) and handler.get('type') == 'command' and owned_hooks.intersection(tokens):
                            changed = True
                        else:
                            kept.append(handler)
                    if kept:
                        new_groups.append({**group, 'hooks': kept})
                    elif not group['hooks']:
                        new_groups.append(group)
                doc['hooks'][event] = new_groups
            if changed:
                edits[path] = (json.dumps(doc, indent=2)+'\n').encode()
    protected = set()
    for alias in {*(Path(item['path']) for item in ambiguous), *overlay_commands}:
        for prefix in (alias, *alias.parents):
            if not prefix.is_relative_to(home):
                break
            if prefix.is_symlink():
                target = prefix.resolve(strict=False)
                for candidate in remove:
                    if candidate.resolve(strict=False) == target or candidate.is_relative_to(target):
                        protected.add(candidate)
    remove.difference_update(protected)
    return {'remove': sorted(remove, key=str), 'edits': edits, 'ambiguous': ambiguous,
            'preserved_overlay_commands': sorted(overlay_commands, key=str),
            'protected_targets': sorted(protected, key=str),
            'retained': [str(home/'.flow/source'), str(home/'.flow/user'), str(home/'.flow/runtimes'),
                         'All project overlays/work artifacts and account/credential stores'],
            'note': 'Legacy source is retained for the current role composer and historical tools; old runtime/data backups are not automatically purged.'}


def public_inventory(value):
    return {'remove': [str(p) for p in value['remove']], 'shared_config_edits': [str(p) for p in value['edits']],
            'preserved_overlay_commands': [str(p) for p in value.get('preserved_overlay_commands', [])],
            'protected_ambiguous_targets': [str(p) for p in value.get('protected_targets', [])],
            'ambiguous': value['ambiguous'], 'retained': value['retained'], 'note': value['note']}
