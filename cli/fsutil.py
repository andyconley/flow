"""Filesystem primitives shared across the CLI.

A leaf module: it imports nothing from its siblings, only the stdlib. Every
function here is non-destructive by default — `ensure_*` and `copy_if_missing`
never overwrite, and `sync_missing_tree` reports what it skipped rather than
clobbering it. That bias is deliberate: these run against user repos and
`~/.flow`, where an overwrite loses hand-edited content.

`_remove_path` is the one destructive helper, and it exists because the obvious
call (`shutil.rmtree`) has a symlink blind spot — see its docstring.
"""

import json
import shutil
from pathlib import Path


def repo_root() -> Path:
    cwd = Path.cwd().resolve()
    for path in [cwd, *cwd.parents]:
        if (path / ".flow").exists() or (path / ".git").exists():
            return path
    return cwd


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_file(path: Path, content: str) -> None:
    if path.exists():
        return
    ensure_dir(path.parent)
    path.write_text(content)


def copy_if_missing(src: Path, dest: Path) -> None:
    if dest.exists():
        return
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        ensure_dir(dest.parent)
        shutil.copy2(src, dest)


def sync_missing_tree(src: Path, dest: Path) -> tuple[int, int]:
    added = 0
    skipped = 0
    if src.is_dir():
        ensure_dir(dest)
        for child in src.iterdir():
            child_added, child_skipped = sync_missing_tree(child, dest / child.name)
            added += child_added
            skipped += child_skipped
        return added, skipped
    if dest.exists():
        return 0, 1
    ensure_dir(dest.parent)
    shutil.copy2(src, dest)
    return 1, 0


def rel_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def remove_empty_parents(path: Path, stop_at: Path) -> None:
    current = path.parent
    while current != stop_at and current.exists():
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


def _remove_path(path: Path) -> None:
    """Best-effort removal of any path entry: symlink, file, or directory.

    `shutil.rmtree(..., ignore_errors=True)` silently no-ops on symlinks (even
    symlinks to directories) — it refuses to follow them by design. That meant
    stale `source.old` symlinks left over from `flow install --release` (where
    the original develop-mode symlink got renamed aside) were never cleaned up,
    and the next `flow update` crashed with ENOTDIR when trying to rename
    `source` over the leftover symlink. This helper routes symlinks and
    regular files through `os.unlink` and only uses `shutil.rmtree` for real
    directories.
    """
    if path.is_symlink():
        try:
            path.unlink()
        except OSError:
            pass
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
