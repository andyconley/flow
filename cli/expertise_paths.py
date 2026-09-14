"""Lexical containment checks for private expertise application directories."""
from __future__ import annotations

from pathlib import Path


class PrivatePathError(ValueError):
    pass


def checked_path(path: Path, root: Path, *, anchor: Path) -> Path:
    """Reject application-tree symlinks before resolving a contained path.

    ``anchor`` is the trusted Flow home or project ``.flow`` directory.  We
    intentionally do not inspect system-owned ancestors above it: macOS can
    legitimately expose ``/var`` as a platform symlink.
    """
    lexical_path = Path(path).absolute()
    lexical_root = Path(root).absolute()
    lexical_anchor = Path(anchor).absolute()
    if (
        ".." in lexical_path.parts or ".." in lexical_root.parts
        or not lexical_root.is_relative_to(lexical_anchor)
        or not lexical_path.is_relative_to(lexical_root)
    ):
        raise PrivatePathError("path escapes its private root")
    for component in (lexical_path, *lexical_path.parents):
        if component.is_symlink():
            raise PrivatePathError("symlinked private path")
        if component == lexical_anchor:
            break
        if component.exists() and component != lexical_path and not component.is_dir():
            raise PrivatePathError("non-directory private path component")
    else:
        raise PrivatePathError("private anchor is not an ancestor")
    resolved = lexical_path.resolve(strict=False)
    if not resolved.is_relative_to(lexical_root.resolve(strict=False)):
        raise PrivatePathError("resolved path escapes its private root")
    return lexical_path
