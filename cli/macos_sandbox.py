"""Minimal macOS process confinement for hosted provider workers."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


class ProcessSandboxError(RuntimeError):
    pass


def confined_argv(argv: list[str], *, workspace: Path, private_home: Path) -> list[str]:
    """Deny user-file reads outside a staged workspace and private runtime home."""
    if sys.platform != "darwin":
        raise ProcessSandboxError("hosted scoped workers require macOS sandbox confinement")
    sandbox_exec = Path("/usr/bin/sandbox-exec")
    if not sandbox_exec.is_file():
        raise ProcessSandboxError("macOS sandbox-exec is unavailable")
    executable = shutil.which(argv[0])
    if not executable:
        raise ProcessSandboxError("hosted provider executable is unavailable")
    # A deny-default profile is not viable for general signed CLIs on current
    # macOS: dyld, security services, and frameworks make undocumented reads
    # that cause even /bin/cat to abort. Keep the OS runtime available, but
    # deny data access in every user-controlled root unless it is the staged
    # workspace or isolated credential home. Metadata alone is not source
    # disclosure and remains available for executable/runtime discovery.
    allowed = (workspace.resolve(), private_home.resolve())
    try:
        executable_path = Path(executable).resolve(strict=True)
    except OSError as exc:
        raise ProcessSandboxError("hosted provider executable cannot be resolved") from exc
    protected_roots = (Path("/Users"), Path("/Volumes"), Path("/private/tmp"),
                       Path("/tmp"), Path("/private/var/folders"))
    exceptions = " ".join(
        f"(require-not (subpath {json.dumps(str(path))}))" for path in allowed
    )
    exceptions += f" (require-not (literal {json.dumps(str(executable_path))}))"
    denied = " ".join(
        f"(deny file-read-data file-write* "
        f"(require-all (subpath {json.dumps(str(root))}) {exceptions}))"
        for root in protected_roots
    )
    profile = f"(version 1) (allow default) {denied}"
    return [str(sandbox_exec), "-p", profile, *argv]
