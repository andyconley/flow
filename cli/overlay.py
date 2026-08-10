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

import os
import subprocess
from pathlib import Path

# Shipped into a fresh overlay repo. The overlay holds hand-authored markdown
# and shell, so the hazard is a file carrying a credential: an .env a hook
# sources, a key someone parked here, an editor's local-settings file.
#
# What this CANNOT protect against, and the reason it is hygiene rather than a
# control: a token pasted inline into a personal command body or hook script —
# exactly the content this repo exists to commit. Secret scanning at the
# provider, or a pre-commit hook in the overlay repo itself, is the real
# answer if that ever becomes a live concern.
OVERLAY_GITIGNORE = """# Managed by `flow setup user --overlay-repo`.
# The overlay is version-controlled so personal commands, agents, and hooks
# survive a lost machine. These patterns stay out of it.
#
# This list cannot catch a credential pasted inline into a command body or
# hook script. It covers the file-shaped hazards only.
*.local.*
*.local
.env
.env.*
.envrc
.netrc
keys/
secrets/
*.pem
*.key
*.p12
*.token
*credentials*
id_rsa*
id_ed25519*
.DS_Store
"""

# Ambient git environment variables that would redirect a cwd-relative command
# at the wrong repository — set inside git hooks, and by some tooling. Stripped
# rather than wiping the whole environment: git needs HOME to read
# ~/.gitconfig, and without it `status` ignores the user's own
# core.excludesFile and reports files their git would not call dirty.
_GIT_ENV_OVERRIDES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_COUNT",
)

# Per-call ceiling. `doctor` is expected to be instant; these are local reads
# that take milliseconds, so a couple of seconds is already pathological and
# waiting longer only makes a hung git look like a hung flow.
_GIT_TIMEOUT_SEC = 2.0


def git_env() -> dict:
    """The environment for read-only overlay git calls."""
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_OVERRIDES}
    # No credential prompts (nothing here needs the network, so a prompt would
    # only ever be a hang) and no index writes from a read.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def _git(overlay_dir: Path, *args: str) -> tuple[int, str]:
    """Run one git command in the overlay, returning (returncode, stdout).

    A failure is reported as a failure, never raised — an unreadable overlay
    is a status to print, not a crash. Callers distinguish "git said no" from
    "git never ran" by checking the returncode, so a missing git binary and a
    corrupt repo both surface as an error rather than as an innocent-looking
    default.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=overlay_dir,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SEC,
            env=git_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def _parse_status_branch(header: str) -> tuple[str | None, int | None]:
    """(branch, unpushed) from `git status --porcelain --branch`'s `##` line.

    One call covers branch name and ahead-count, and it answers correctly in
    the two states `rev-parse --abbrev-ref HEAD` gets wrong: a repo with no
    commits yet (where rev-parse fails outright) and a detached HEAD (where
    rev-parse returns the literal string "HEAD" and would be reported as a
    branch by that name).

    Shapes:
      `## main...origin/main [ahead 2]`  -> ("main", 2)
      `## main...origin/main`            -> ("main", 0)
      `## main`                          -> ("main", None)   no upstream
      `## No commits yet on main`        -> ("main", None)   unborn branch
      `## HEAD (no branch)`              -> (None, None)     detached
    """
    body = header.removeprefix("## ").strip()
    if body.startswith("HEAD (no branch)"):
        return None, None
    if body.startswith("No commits yet on "):
        return body.removeprefix("No commits yet on ").split()[0], None

    unpushed = None
    if "[" in body:
        tracking = body[body.index("[") + 1 : body.rindex("]")] if "]" in body else ""
        body = body[: body.index("[")].strip()
        for part in tracking.split(","):
            part = part.strip()
            if part.startswith("ahead "):
                count = part.removeprefix("ahead ").strip()
                unpushed = int(count) if count.isdigit() else None

    if "..." in body:
        branch = body.split("...", 1)[0]
        # An upstream exists; no `[ahead N]` means level with it.
        return (branch or None), (unpushed if unpushed is not None else 0)
    return (body or None), None


def overlay_vcs_status(overlay_dir: Path) -> dict:
    """Version-control status for the overlay directory.

    Returns `{"present", "tracked", "error", "branch", "remote", "dirty",
    "unpushed"}`.

    - `present` False means there is no overlay at all — the opt-in default,
      not a problem.
    - `tracked` False with `present` True is the state this whole feature
      exists to surface: authored content with no history and no backup.
    - `error` True means git could not be read at all. Reported as such
      rather than synthesized into a plausible-looking clean/detached status,
      because a diagnostic that states a false condition is worse than one
      that admits it does not know.
    - `unpushed` is None when the branch has no upstream — distinct from 0,
      which means an upstream exists and is level.

    Two git calls, both local, both bounded. `status --porcelain --branch`
    carries the dirty list, the branch, and the ahead-count together.
    """
    status = {
        "present": overlay_dir.is_dir(),
        "tracked": False,
        "error": False,
        "branch": None,
        "remote": None,
        "dirty": [],
        "unpushed": None,
    }
    if not status["present"] or not (overlay_dir / ".git").exists():
        return status
    status["tracked"] = True

    rc, out = _git(overlay_dir, "status", "--porcelain", "--branch")
    if rc != 0:
        status["error"] = True
        return status

    lines = out.splitlines()
    if lines and lines[0].startswith("## "):
        status["branch"], status["unpushed"] = _parse_status_branch(lines[0])
        lines = lines[1:]
    status["dirty"] = [line[3:] for line in lines if line.strip()]

    rc, out = _git(overlay_dir, "config", "--get", "remote.origin.url")
    if rc == 0 and out:
        status["remote"] = out

    return status


def format_overlay_vcs(status: dict) -> str:
    """One line for `doctor`. Names the fix when there is one to name."""
    if not status["present"]:
        return "n/a (no overlay)"
    if not status["tracked"]:
        return "untracked — run `flow setup user --overlay-repo <url>` to give it history"
    if status["error"]:
        return "unreadable (git error)"

    parts = []
    if status["dirty"]:
        parts.append(f"{len(status['dirty'])} uncommitted")
    if status["remote"] is None:
        parts.append("no remote")
    elif status["unpushed"] is None:
        parts.append("no upstream")
    elif status["unpushed"]:
        parts.append(f"{status['unpushed']} unpushed")
    if not parts:
        parts.append("clean")

    where = status["branch"] or "detached"
    return f"{', '.join(parts)} ({where})"
