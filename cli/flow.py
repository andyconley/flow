#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil
import sys


HOME = Path.home()
FLOW_HOME = HOME / ".flow"
FRAMEWORK_DIR = FLOW_HOME / "framework"
TEMPLATES_DIR = FRAMEWORK_DIR / "templates" / "framework"


def repo_root() -> Path:
    return Path.cwd()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def setup_machine() -> int:
    ensure_dir(FLOW_HOME)
    ensure_dir(HOME / ".local" / "bin")
    print(f"flow home ready: {FLOW_HOME}")
    print("next: run `flow setup project` inside a repository")
    return 0


def copy_if_missing(src: Path, dest: Path) -> None:
    if dest.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        ensure_dir(dest.parent)
        shutil.copy2(src, dest)


def setup_project() -> int:
    root = repo_root()
    target = root / ".flow"
    ensure_dir(target)

    for item in TEMPLATES_DIR.iterdir():
        copy_if_missing(item, target / item.name)

    print(f"project scaffold ready: {target}")
    print("next: fill in .flow/PROJECT.md and run `flow sync claude` later")
    return 0


def doctor() -> int:
    print(f"python:      {sys.executable}")
    print(f"flow home:   {FLOW_HOME}")
    print(f"framework:   {FRAMEWORK_DIR}")
    print(f"repo:        {repo_root()}")
    print(f"templates:   {'ok' if TEMPLATES_DIR.exists() else 'missing'}")
    print(f"repo .flow:  {'ok' if (repo_root() / '.flow').exists() else 'missing'}")
    return 0


def bootstrap() -> int:
    print("bootstrap not implemented yet")
    return 0


def sync_claude() -> int:
    print("sync claude not implemented yet")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="flow")
    sub = parser.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup")
    setup_sub = setup.add_subparsers(dest="setup_target", required=True)
    setup_sub.add_parser("machine")
    setup_sub.add_parser("project")

    sub.add_parser("doctor")
    sub.add_parser("bootstrap")
    sync = sub.add_parser("sync")
    sync.add_argument("target", choices=["claude"])

    args = parser.parse_args()

    if args.command == "setup" and args.setup_target == "machine":
        return setup_machine()
    if args.command == "setup" and args.setup_target == "project":
        return setup_project()
    if args.command == "doctor":
        return doctor()
    if args.command == "bootstrap":
        return bootstrap()
    if args.command == "sync" and args.target == "claude":
        return sync_claude()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
