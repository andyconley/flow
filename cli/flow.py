#!/usr/bin/env python3
import argparse
from pathlib import Path
import shutil
import sys


HOME = Path.home()
FLOW_HOME = HOME / ".flow"
FRAMEWORK_DIR = FLOW_HOME / "framework"
TEMPLATES_DIR = FRAMEWORK_DIR / "templates" / "framework"
USER_BIN_DIR = HOME / ".local" / "bin"
FLOW_CONFIG = FLOW_HOME / "config.toml"


def repo_root() -> Path:
    return Path.cwd()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_file(path: Path, content: str) -> None:
    if path.exists():
        return
    ensure_dir(path.parent)
    path.write_text(content)


def setup_machine() -> int:
    ensure_dir(FLOW_HOME)
    ensure_dir(USER_BIN_DIR)
    ensure_dir(FLOW_HOME / "hooks")
    ensure_dir(FLOW_HOME / "templates")
    ensure_dir(FLOW_HOME / "user")
    ensure_dir(FLOW_HOME / "logs")
    ensure_file(
        FLOW_CONFIG,
        "[flow]\nframework_home = \"~/.flow/framework\"\nlauncher = \"~/.local/bin/flow\"\n",
    )
    print(f"flow home ready: {FLOW_HOME}")
    print(f"config:     {FLOW_CONFIG}")
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
    print(f"config:      {'ok' if FLOW_CONFIG.exists() else 'missing'}")
    print(f"launcher:    {'ok' if (USER_BIN_DIR / 'flow').exists() else 'missing'}")
    print(f"templates:   {'ok' if TEMPLATES_DIR.exists() else 'missing'}")
    print(f"repo .flow:  {'ok' if (repo_root() / '.flow').exists() else 'missing'}")
    return 0


def bootstrap() -> int:
    root = repo_root()
    flow_dir = root / ".flow"
    if not flow_dir.exists():
        print("repo is missing .flow; run `flow setup project` first")
        return 1

    required = [
        flow_dir / "FRAMEWORK.md",
        flow_dir / "PROJECT.md",
        flow_dir / "standards",
        flow_dir / "project",
        flow_dir / "memory",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("bootstrap found missing framework paths:")
        for path in missing:
            print(f"- {path}")
        return 1

    print(f"bootstrap ok: {flow_dir}")
    print("next: run `flow doctor` or begin with `/flow-boot` once Claude integration exists")
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
