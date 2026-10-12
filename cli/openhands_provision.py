"""Credential-free, transactional provisioning for the stock OpenHands SDK.

No profile, provider or global Python configuration is changed. Environments
are immutable after publication; a failed build never changes current.json.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from flowtoml import read_toml

PACKAGES = ('openhands-sdk', 'openhands-tools', 'openhands-workspace', 'openhands-agent-server')
VERSION = '1.54.0'


def ready(python: str) -> bool:
    code = "import sys; from importlib.metadata import version; from openhands.sdk import Agent, Conversation; from openhands.sdk.subagent import register_agent_if_absent; assert sys.version_info >= (3,12); assert all(version(p)==" + repr(VERSION) + " for p in " + repr(PACKAGES) + ")"
    try:
        return subprocess.run([python, '-c', code], capture_output=True, timeout=60, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def compatible(python: str) -> bool:
    try:
        return subprocess.run([python, '-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)'], capture_output=True, timeout=10, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def provision(source_root: Path, home: Path, preferred_python: str | None = None) -> str:
    """Reuse pinned-ready selections, otherwise build an isolated Python 3.12+ venv."""
    requirements = source_root / 'runtime/openhands/requirements.txt'
    root = home / 'runtimes/openhands'
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / '.provision.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        lock_stat = os.fstat(fd)
        if lock_stat.st_uid != os.getuid() or lock_stat.st_mode & 0o077:
            raise RuntimeError('managed OpenHands provision lock must be owned by this user with mode 0600')
        fcntl.flock(fd, fcntl.LOCK_EX)
        configured = None
        config = home / 'config.toml'
        if config.is_file():
            try:
                configured = read_toml(config).get('flow', {}).get('python')
            except (OSError, ValueError):
                pass
        preferred = os.environ.get('FLOW_PYTHON') or configured or preferred_python or sys.executable
        if ready(preferred):
            return preferred
        pointer = root / 'current.json'
        if pointer.is_file() and not pointer.is_symlink():
            try:
                selected = json.loads(pointer.read_text())['interpreter']
                if ready(selected):
                    return selected
            except (ValueError, KeyError, TypeError):
                pass
        candidates = [preferred, sys.executable] + [shutil.which(name) for name in ('python3.12', 'python3.13', 'python3.14', 'python3')]
        base = next((p for p in candidates if p and compatible(p)), None)
        if base is None:
            raise RuntimeError('OpenHands requires Python 3.12+; install it and rerun with FLOW_PYTHON=/path/to/python3.12')
        identity = hashlib.sha256(requirements.read_bytes() + os.fsencode(base)).hexdigest()[:16]
        environment = root / (VERSION + '-' + identity)
        python = str(environment / 'bin/python')
        if not ready(python):
            # Create at its final immutable path: venv scripts embed absolute paths.
            # Only current.json publishes it, so no running launcher can use an
            # incomplete build. Never overwrite an existing failed/custom path.
            if environment.exists():
                environment = root / (VERSION + '-' + identity + '-' + uuid.uuid4().hex[:8])
                python = str(environment / 'bin/python')
            try:
                subprocess.run([base, '-m', 'venv', str(environment)], check=True)
                subprocess.run([python, '-m', 'pip', 'install', '-r', str(requirements)], check=True, stdout=sys.stderr)
                if not ready(python):
                    raise RuntimeError('installed OpenHands packages failed the pinned SDK import/readiness check')
            except Exception:
                shutil.rmtree(environment, ignore_errors=True)
                raise
        temporary = pointer.with_name('.current-' + uuid.uuid4().hex + '.tmp')
        try:
            temp_fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(temp_fd, 'w') as handle:
                json.dump({'schema_version': 1, 'interpreter': python, 'version': VERSION, 'requirements_sha256': hashlib.sha256(requirements.read_bytes()).hexdigest()}, handle)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, pointer)
        finally:
            temporary.unlink(missing_ok=True)
        return python
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--home', type=Path, default=Path.home() / '.flow')
    parser.add_argument('--python', default=None)
    args = parser.parse_args()
    try:
        print(provision(args.source_root, args.home, args.python))
    except Exception as exc:
        print(f'OpenHands provisioning failed: {exc}. Previous runtime remains selected.', file=sys.stderr)
        raise SystemExit(1)
