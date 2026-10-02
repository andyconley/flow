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
    executable_root = Path(executable).resolve().parent
    allowed_reads = [Path("/System"), Path("/usr"), Path("/bin"), Path("/sbin"),
                     Path("/Library"), Path("/Applications"), Path("/opt/homebrew"),
                     workspace.resolve(), private_home.resolve(), executable_root]
    temp_root = Path("/private/var/folders")
    clauses = " ".join(f"(subpath {json.dumps(str(path))})" for path in allowed_reads)
    write_clauses = " ".join(
        f"(subpath {json.dumps(str(path))})"
        for path in (workspace.resolve(), private_home.resolve(), temp_root)
    )
    profile = (
        "(version 1) (deny default) (allow process*) (allow sysctl-read) "
        "(allow mach-lookup) (allow network*) (allow file-read-metadata) "
        f"(allow file-read* {clauses}) (allow file-write* {write_clauses})"
    )
    return [str(sandbox_exec), "-p", profile, *argv]
