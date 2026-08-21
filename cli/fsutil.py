"""Filesystem primitives shared across the CLI.

A leaf module: it imports nothing from its siblings, only the stdlib. Every
function here is non-destructive by default — `ensure_*` and `copy_if_missing`
never overwrite, and `sync_missing_tree` reports what it skipped rather than
clobbering it. That bias is deliberate: these run against user repos and
`~/.flow`, where an overwrite loses hand-edited content.

`_remove_path` and `write_atomic` are the two exceptions, and both exist for a
reason their docstrings give: `shutil.rmtree` has a symlink blind spot, and a
non-atomic rewrite can be interrupted into a zero-length file.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path


def _flow_home() -> Path:
    """`~/.flow` — flow's own home, which is not a project overlay.

    Derived here instead of imported from `paths.FLOW_HOME` so this module stays
    a stdlib-only leaf (see the module docstring). A test pins the two
    derivations together so they cannot drift apart.

    Resolved because the comparison in `repo_root` is against a resolved path,
    and on macOS a temporary or symlinked home reaches the same directory by two
    different spellings. An unresolved comparison silently never matches, which
    would leave the guard below looking present and doing nothing.
    """
    return Path.home().resolve() / ".flow"


def repo_root() -> Path:
    """The nearest enclosing project root, or the working directory.

    `.flow` names two different things: a project's overlay, and flow's own home
    at `~/.flow`. Only the first marks a project. Without the exclusion below,
    any directory under $HOME that is not itself a repo walks up, matches flow
    home, and reports $HOME as its project root — so commands that resolve paths
    against the root operate on the home directory instead of failing to find a
    project.
    """
    flow_home = _flow_home()
    cwd = Path.cwd().resolve()
    for path in [cwd, *cwd.parents]:
        overlay = path / ".flow"
        if (overlay.exists() and overlay != flow_home) or (path / ".git").exists():
            return path
    return cwd


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ensure_file(path: Path, content: str) -> None:
    if path.exists():
        return
    ensure_dir(path.parent)
    path.write_text(content)


def write_atomic(path: Path, content: str, *, mode: int | None = None) -> None:
    """Replace a file's contents so a crash leaves either the old file or the new.

    The one destructive-by-default function in a module whose whole bias is the
    opposite, and it exists for the migration path: a manifest rewritten
    non-atomically can be interrupted between truncate and write, leaving an
    empty file that names none of the sources still on disk.

    Four details are load-bearing and each has a plausible wrong version:

    **The temp file goes in the destination's own directory.** `os.replace` is
    atomic only within a filesystem; a temp file under `/tmp` is a different
    mount on many systems and the rename raises `EXDEV`.

    **fsync before the rename.** Without it a crash can land the rename ahead of
    the data and leave a zero-length file — worse than either the old or the new
    contents, and worse than not being atomic at all.

    **The mode is carried over.** `mkstemp` creates `0600`, so a rewritten
    `settings.json` would silently become owner-only.

    **The temp file is removed on any failure**, and the exception is re-raised
    rather than swallowed. A caller that believes a write succeeded is how a
    migration deletes the files a manifest was supposed to stop naming.
    """
    ensure_dir(path.parent)
    if mode is None:
        mode = (path.stat().st_mode & 0o7777) if path.exists() else 0o644
    fd, temp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


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
