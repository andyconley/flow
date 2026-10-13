"""Text-preserving, hash-owned Codex role registration; no execution routing."""
import hashlib
import json
import os
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

from fsutil import write_atomic

BEGIN = '\n# BEGIN FLOW MANAGED CODEX ROLES\n'
END = '# END FLOW MANAGED CODEX ROLES\n'


def registration_config(root: Path, roles: dict[str, Path], ownership: dict | None) -> tuple[str, str, str]:
    if tomllib is None:
        raise ValueError('Safe Codex registration requires Python 3.11+; use the installed OpenHands interpreter')
    path = root / '.codex/config.toml'
    if path.is_symlink():
        raise ValueError('Codex config.toml is a symlink; preserve it and resolve registration manually')
    if path.exists() and not path.is_file():
        raise ValueError('Codex config.toml is not a regular file; preserve it')
    original = path.read_bytes().decode('utf-8') if path.exists() else ''
    try:
        full = tomllib.loads(original)
    except tomllib.TOMLDecodeError as err:
        raise ValueError('Codex config.toml is invalid; no registration changes written') from err
    old = ''
    base = original
    if original.count(BEGIN.strip()) or original.count(END.strip()):
        if original.count(BEGIN) != 1 or original.count(END) != 1:
            raise ValueError('Codex role registration markers are malformed; preserve and resolve manually')
        start = original.index(BEGIN)
        stop = original.index(END) + len(END)
        if stop <= start:
            raise ValueError('Codex role registration markers are reversed')
        old = original[start:stop]
        base = original[:start] + original[stop:]
        if not ownership or not ownership.get('block_sha256'):
            raise ValueError('Codex role registration block has no Flow ownership record; preserve it')
        # Outside text must not add keys to an owned role by inheriting its TOML table.
        old_roles = tomllib.loads(old).get('agents', {})
        for name, value in old_roles.items():
            if full.get('agents', {}).get(name) != value:
                raise ValueError(f'Codex registration collision outside managed block: {name}')
    try:
        outside = tomllib.loads(base)
    except tomllib.TOMLDecodeError as err:
        raise ValueError('Removing the owned Codex block would invalidate user configuration') from err
    existing = outside.get('agents', {})
    if not isinstance(existing, dict):
        raise ValueError('Codex agents configuration is not a table; preserve it')
    lines = []
    for name, target in sorted(roles.items()):
        if name in existing:
            entry = existing[name]
            pointer = entry.get('config_file') if isinstance(entry, dict) else None
            if not isinstance(pointer, str):
                raise ValueError(f'Codex user-owned registration collision: {name}')
            candidate = Path(pointer).expanduser()
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            if candidate.is_symlink() or Path(os.path.abspath(candidate)) != target:
                raise ValueError(f'Codex user-owned registration collision: {name}')
            # Compatible user-owned registrations stay outside Flow's ownership.
            continue
        lines.extend([f'[agents.{json.dumps(name)}]', f'config_file = {json.dumps(str(target))}', ''])
    block = BEGIN + '\n'.join(lines) + END if lines else ''
    if old and hashlib.sha256(old.encode()).hexdigest() != ownership['block_sha256'] and old != block:
        raise ValueError('Flow-owned Codex registrations were edited; preserve and resolve manually')
    desired = base + block
    try:
        tomllib.loads(desired)
    except tomllib.TOMLDecodeError as err:
        raise ValueError('Codex role registrations conflict with user TOML; no changes written') from err
    return original, desired, hashlib.sha256(block.encode()).hexdigest()


def write_registration_config(root: Path, original: str, desired: str) -> None:
    path = root / '.codex/config.toml'
    if path.is_symlink() or (path.read_bytes().decode('utf-8') if path.exists() else '') != original:
        raise ValueError('Codex config.toml changed during sync; preserve and retry after review')
    if original == desired:
        return
    if path.exists():
        digest = hashlib.sha256(original.encode()).hexdigest()
        backup = root / '.flow/backups/codex-role-registration' / f'{digest}.toml'
        if not backup.parent.resolve().is_relative_to(root.resolve()):
            raise ValueError('Codex registration backup escapes the user home; preserve and resolve manually')
        backup.parent.mkdir(parents=True, exist_ok=True)
        if backup.is_symlink():
            raise ValueError('Codex registration backup is a symlink; preserve and resolve manually')
        if backup.exists():
            if backup.read_bytes().decode('utf-8') != original:
                raise ValueError('Codex registration backup does not match original configuration')
        else:
            write_atomic(backup, original, mode=0o600)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, desired)
