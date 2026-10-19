"""Verify and unpack the retained Studio Goose build without Rust or downloads."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import tempfile
import fcntl

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def metadata(source=ROOT):
    value = json.loads((source/'vendor/artifacts/goose-macos-arm64.json').read_text())
    lock = json.loads((source/'vendor/goose.lock.json').read_text())
    if value['source_lock'] != lock or digest(source/'vendor'/lock['patch']) != lock['patch_sha256']:
        raise ValueError('Bundled Goose provenance differs from the shipped source lock')
    return value


def check_platform(value):
    if platform.system() != value['platform'] or platform.machine() != value['architecture']:
        raise ValueError('Bundled Goose requires an arm64 macOS process; use an explicit qualified build on other platforms')
    current = tuple(int(x) for x in platform.mac_ver()[0].split('.'))
    required = tuple(int(x) for x in value['minimum_macos'].split('.'))
    if current < required:
        raise ValueError('Bundled Goose requires macOS '+value['minimum_macos']+' or later')


def binary_path(source=ROOT):
    return source/'runtime/bundled-goose/goose'


def verify_binary(path, value):
    if path.stat().st_size != value['binary_size'] or digest(path) != value['binary_sha256']:
        raise ValueError('Bundled Goose executable checksum mismatch; preserve it and investigate')
    if not os.access(path, os.X_OK):
        raise ValueError('Bundled Goose executable is not executable')
    return path.resolve()


def selected_binary(source=ROOT):
    value = metadata(source)
    check_platform(value)
    return verify_binary(binary_path(source), value)


def verify_archive(source=ROOT):
    value = metadata(source)
    check_platform(value)
    archive = source/'vendor/artifacts'/value['archive']
    if archive.stat().st_size != value['archive_size'] or digest(archive) != value['archive_sha256']:
        raise ValueError('Bundled Goose archive checksum mismatch')
    return archive, value


def previous_binary(target, value):
    """Only exact shipped predecessor digests qualify for a preserved upgrade."""
    if target.is_symlink():
        raise ValueError('Conflicting Goose symlink; preserve it and investigate')
    for previous in value.get('previous_binaries', []):
        try:
            verify_binary(target, previous)
            return previous
        except ValueError:
            continue
    raise ValueError('Bundled Goose executable checksum mismatch; preserve it and investigate')


def extract(source=ROOT):
    archive, value = verify_archive(source)
    target = binary_path(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target.parent/'.artifact.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = None
        if target.exists() or target.is_symlink():
            try:
                return verify_binary(target, value)
            except ValueError:
                previous = previous_binary(target, value)
        fd, name = tempfile.mkstemp(prefix='.goose-', dir=target.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, 'wb') as output, gzip.open(archive, 'rb') as input_stream:
                shutil.copyfileobj(input_stream, output)
            temporary.chmod(0o755)
            verify_binary(temporary, value)
            if previous:
                backup = target.with_name('goose-'+previous['binary_sha256'])
                if backup.exists() or backup.is_symlink():
                    if backup.is_symlink():
                        raise ValueError('Conflicting Goose backup symlink; preserve it and investigate')
                    verify_binary(backup, previous)
                else:
                    os.link(target, backup)
                # Replacement happens only after both archive and predecessor
                # verification. The original remains at its digest-named backup.
                os.replace(temporary, target)
            else:
                os.link(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    return target.resolve()


def provision(source=ROOT, dry_run=False):
    """Return (executable, extraction_planned) for installer/preparation use."""
    explicit = os.environ.get('FLOW_V2_GOOSE_BINARY')
    if explicit:
        return Path(explicit).resolve(), False
    target = binary_path(source)
    if target.exists() or target.is_symlink():
        try:
            return selected_binary(source), False
        except ValueError:
            value = metadata(source)
            check_platform(value)
            previous_binary(target, value)
            verify_archive(source)
            return (target.absolute(), True) if dry_run else (extract(source), False)
    if platform.system() == 'Darwin' and platform.machine() == 'arm64':
        if dry_run:
            verify_archive(source)
            return target.resolve(), True
        return extract(source), False
    # Preserve the existing source-build route on platforms without an artifact.
    return (source/'runtime/goose/target/debug/goose').resolve(), False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--extract', action='store_true', help='Verify archive and extract into this checkout only')
    args = parser.parse_args()
    try:
        print(extract() if args.extract else selected_binary())
    except (ValueError, OSError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
