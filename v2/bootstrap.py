"""Explicit local dependency preparation and installation; no model downloads/login."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def run(command, **kwargs):
    subprocess.run([str(x) for x in command], check=True, **kwargs)


def verify_goose_source(source, lock):
    """Validate exact tracked patch and reject unrelated untracked source."""
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if head != lock['base_commit']:
        raise SystemExit('Existing Goose source is not at the locked upstream base')
    untracked = subprocess.check_output(['git','ls-files','--others','--exclude-standard'], cwd=source, text=True).splitlines()
    if any(path != '.flow-v2-patch.json' for path in untracked):
        raise SystemExit('Existing Goose source contains unrelated untracked files; preserve them before building')
    applied = subprocess.check_output(['git','diff','--binary','--full-index','--no-ext-diff',
                                      '--no-textconv','--no-renames','--no-color',
                                      '--src-prefix=a/','--dst-prefix=b/',lock['base_commit']], cwd=source)
    if hashlib.sha256(applied).hexdigest() != lock['patch_sha256']:
        raise SystemExit('Existing Goose source differs from the locked integration patch; refusing to build unrelated edits')


def prepare(build_goose=False):
    if sys.version_info < (3, 12):
        raise SystemExit('Flow v2 preparation requires Python 3.12 or later')
    if not build_goose:
        from poc.goose_artifact import provision
        provision(ROOT)
    python = ROOT/'.venv/bin/python'
    if not python.exists():
        run([sys.executable, '-m', 'venv', ROOT/'.venv'])
    run([python, '-m', 'pip', 'install', '-r', ROOT/'requirements.lock'])
    adapters = ROOT/'runtime/adapters'; adapters.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT/'adapters.package.json', adapters/'package.json')
    shutil.copyfile(ROOT/'adapters.package-lock.json', adapters/'package-lock.json')
    run(['npm', 'ci', '--ignore-scripts'], cwd=adapters)
    if build_goose:
        lock = json.loads((ROOT/'vendor/goose.lock.json').read_text())
        patch = ROOT/'vendor'/lock['patch']
        if hashlib.sha256(patch.read_bytes()).hexdigest() != lock['patch_sha256']:
            raise SystemExit('The shipped Goose patch does not match its source lock')
        source = ROOT/'runtime/goose'
        if not source.exists():
            run(['git', 'clone', '--no-checkout', lock['repository'], source])
            run(['git','checkout','--detach',lock['base_commit']],cwd=source)
        dirty = subprocess.run(['git','status','--porcelain'],cwd=source,capture_output=True,text=True,check=True).stdout
        stamp = source/'.flow-v2-patch.json'
        if stamp.exists():
            if json.loads(stamp.read_text()) != lock:
                raise SystemExit('Existing Goose source uses a different lock; preserve it and prepare a separate checkout')
        else:
            if dirty:
                raise SystemExit('Existing Goose source has changes; refusing to reset or overwrite it')
            run(['git','checkout','--detach',lock['base_commit']],cwd=source)
            run(['git','apply','--check',patch],cwd=source)
            run(['git','apply','--index',patch],cwd=source)
            stamp.write_text(json.dumps(lock,indent=2)+'\n')
        verify_goose_source(source, lock)
        run(['cargo','build','--locked','-p','goose-cli','--bin','goose','--no-default-features','--features',','.join(lock['features'])],cwd=source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','install','update','inventory','activate','restore'])
    parser.add_argument('--build-goose', action='store_true', help='Prepare the locked upstream source plus shipped integration patch and build locally')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--replace-legacy', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if args.action == 'prepare':
        try:
            if args.dry_run:
                if not args.build_goose:
                    from poc.goose_artifact import provision
                    provision(ROOT, dry_run=True)
                print('Would create the local venv, install locked Python/npm packages'+(' and build locked Goose source' if args.build_goose else ' and verify/extract the bundled Goose build on Apple Silicon macOS'))
            else:
                prepare(args.build_goose)
        except (ValueError, OSError) as error:
            parser.error(str(error))
        return
    python = ROOT/'.venv/bin/python'
    if not python.exists():
        parser.error('Run prepare first, or supply the existing local v2 Python environment at v2/.venv')
    command = [python, '-m', 'poc.install', args.action]
    if args.home: command += ['--home', args.home]
    if args.replace_legacy: command += ['--replace-legacy']
    if args.dry_run: command += ['--dry-run']
    run(command, cwd=ROOT)


if __name__ == '__main__':
    main()
