"""User-overlay version-control status: read-only inspection of `~/.flow/user/`.

The overlay is the one authored layer in flow with no home in any repo the
framework ships — it holds personal commands, agent overrides, hook scripts,
and the manifest registering them. Making it a git repo is what gives that
content history and a way back after a lost machine.

This module only *reports*. It never inits, commits, or pushes: `doctor`
consumes it, and `doctor`'s contract is to observe conditions rather than
repair them (see the usage-store note there for the same reasoning). Setup
handles initialization; the agent that edits overlay files commits them.

Kept separate from `diagnostics.py` so the status is unit-testable against a
temporary directory without shelling through the CLI, and so `diagnostics.py`
keeps holding presentation rather than git plumbing.
"""

import subprocess
from pathlib import Path

# Shipped into a fresh overlay repo. Short on purpose: the overlay holds
# hand-authored markdown and shell, so the only real hazard is a future file
# carrying a credential — a token in a personal command's body, an .env a
# hook script sources. Everything here is that hazard, plus macOS noise.
OVERLAY_GITIGNORE = """# Managed by `flow setup user --overlay-repo`.
# The overlay is version-controlled so personal commands, agents, and hooks
# survive a lost machine. These patterns stay out of it.
*.local.*
.env
.env.*
keys/
*.pem
*.key
.DS_Store
"""


def _git(overlay_dir: Path, *args: str, timeout: float = 5.0) -> tuple[int, str]:
    """Run one git command in the overlay, returning (returncode, stdout).

    Bounded by a timeout because `doctor` must stay fast and must never hang
    on a git operation that wants input (a credential prompt on a
    misconfigured remote, say). A failure is reported as a failure, never
    raised — an unreadable overlay is a status to print, not a crash.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=overlay_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0", "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def overlay_vcs_status(overlay_dir: Path) -> dict:
    """Version-control status for the overlay directory.

    Returns `{"present", "tracked", "branch", "remote", "dirty", "unpushed"}`.

    - `present` False means there is no overlay at all — the opt-in default,
      not a problem.
    - `tracked` False with `present` True is the state this whole feature
      exists to surface: authored content with no history and no backup.
    - `unpushed` is None when the branch has no upstream (a local-only repo,
      or a fresh branch never pushed) — distinct from 0, which means an
      upstream exists and is level.
    """
    status = {
        "present": overlay_dir.is_dir(),
        "tracked": False,
        "branch": None,
        "remote": None,
        "dirty": [],
        "unpushed": None,
    }
    if not status["present"] or not (overlay_dir / ".git").exists():
        return status
    status["tracked"] = True

    rc, out = _git(overlay_dir, "status", "--porcelain")
    if rc == 0:
        status["dirty"] = [line[3:] for line in out.splitlines() if line.strip()]

    rc, out = _git(overlay_dir, "rev-parse", "--abbrev-ref", "HEAD")
    if rc == 0 and out:
        status["branch"] = out

    rc, out = _git(overlay_dir, "config", "--get", "remote.origin.url")
    if rc == 0 and out:
        status["remote"] = out

    # Purely local: compares against the already-fetched upstream ref, so it
    # never touches the network.
    rc, out = _git(overlay_dir, "rev-list", "--count", "@{u}..HEAD")
    if rc == 0 and out.isdigit():
        status["unpushed"] = int(out)

    return status


def format_overlay_vcs(status: dict) -> str:
    """One line for `doctor`. Names the fix when there is one to name."""
    if not status["present"]:
        return "n/a (no overlay)"
    if not status["tracked"]:
        return "untracked — run `flow setup user --overlay-repo <url>` to give it history"

    parts = []
    if status["dirty"]:
        parts.append(f"{len(status['dirty'])} uncommitted")
    if status["unpushed"] is None:
        parts.append("no upstream")
    elif status["unpushed"]:
        parts.append(f"{status['unpushed']} unpushed")
    if not parts:
        parts.append("clean")

    where = status["branch"] or "detached"
    return f"{', '.join(parts)} ({where})"
