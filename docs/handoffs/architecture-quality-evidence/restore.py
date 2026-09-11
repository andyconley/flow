#!/usr/bin/env python3
"""Verify and optionally restore the frozen architecture-evidence run."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile


def sha256_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def restore(destination=None):
    bundle = Path(__file__).resolve().parent
    manifest = json.loads((bundle / 'artifact-manifest.json').read_text())
    archive = bundle / 'run-artifacts.tar.xz'
    if archive.stat().st_size != manifest['archive_bytes']:
        raise ValueError('Archive size mismatch')
    if sha256_file(archive) != manifest['archive_sha256']:
        raise ValueError('Archive SHA256 mismatch')
    expected = {entry['path']: entry for entry in manifest['files']}
    if len(expected) != manifest['file_count'] or len(expected) != len(manifest['files']):
        raise ValueError('Manifest count or duplicate path mismatch')
    temporary = None
    if destination is not None:
        destination = destination.absolute()
        if os.path.lexists(destination):
            raise ValueError(f'Refusing to overwrite {destination}')
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.restore-', dir=destination.parent))
    try:
        seen = set()
        with tarfile.open(archive, 'r|xz') as stream:
            for member in stream:
                path = PurePosixPath(member.name)
                if (not member.isfile() or path.is_absolute() or '..' in path.parts
                        or '\\' in member.name or str(path) != member.name
                        or member.name not in expected or member.name in seen):
                    raise ValueError(f'Unsafe, unexpected or duplicate entry: {member.name}')
                entry = expected[member.name]
                if member.size != entry['bytes']:
                    raise ValueError(f'Size mismatch: {member.name}')
                source = stream.extractfile(member)
                target = None
                if temporary is not None:
                    target_path = temporary.joinpath(*path.parts)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target = target_path.open('xb')
                digest = hashlib.sha256()
                try:
                    while chunk := source.read(1024 * 1024):
                        digest.update(chunk)
                        if target is not None:
                            target.write(chunk)
                finally:
                    source.close()
                    if target is not None:
                        target.close()
                if digest.hexdigest() != entry['sha256']:
                    raise ValueError(f'File SHA256 mismatch: {member.name}')
                seen.add(member.name)
        if seen != set(expected):
            raise ValueError('Archive is missing manifest entries')
        if temporary is not None:
            # Exclusive reservation prevents overwriting even an empty directory.
            destination.mkdir()
            try:
                for child in temporary.iterdir():
                    shutil.move(str(child), str(destination / child.name))
            except BaseException:
                shutil.rmtree(destination)
                raise
        print(f'Verified {len(seen)} files; archive SHA256 {manifest["archive_sha256"]}')
        if destination is not None:
            print(f'Restored run to {destination}')
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--verify-only', action='store_true')
    mode.add_argument('--destination', type=Path)
    arguments = parser.parse_args()
    try:
        restore(arguments.destination)
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, f'Restore failed: {error}\n')
