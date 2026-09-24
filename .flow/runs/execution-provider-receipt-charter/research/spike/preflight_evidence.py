"""Emit bounded, non-secret package and CLI status evidence for the spike."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path

import agent_framework


def main() -> None:
    status = subprocess.run(
        ["codex", "login", "status"],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    output = (status.stdout + status.stderr).lower()
    if "logged in using chatgpt" in output:
        auth_mode = "chatgpt"
    elif "logged in using api" in output:
        auth_mode = "api_key"
    else:
        auth_mode = "unknown"

    core_path = Path(agent_framework.__file__).parent
    needles = ("CodexAgent", "CodexClient", "openai_codex")
    named_reference_count = 0
    scanned_files = 0
    for source in core_path.rglob("*.py"):
        scanned_files += 1
        content = source.read_text(errors="replace")
        named_reference_count += sum(content.count(needle) for needle in needles)

    print(
        json.dumps(
            {
                "python": sys.version.split()[0],
                "packages": {
                    name: importlib.metadata.version(name)
                    for name in ("openai-codex", "openai-codex-cli-bin", "agent-framework-core")
                },
                "codex_login_status_command": "codex login status",
                "codex_login_status_exit_code": status.returncode,
                "codex_cli_auth_mode": auth_mode,
                "maf_core_named_reference_scan": {
                    "names": list(needles),
                    "python_files_scanned": scanned_files,
                    "matches": named_reference_count,
                    "scope": "installed agent_framework core package only",
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
