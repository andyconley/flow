"""Plumbing shared by flow's runtime hook entry points.

Both supported runtimes hand a hook the same thing: one JSON object on
stdin, carrying at least `session_id`, `transcript_path`, `cwd`, and
`hook_event_name`. And every flow hook owes the runtime the same discipline
in return — read that object defensively, and never let an advisory feature
turn into a failure the user has to debug.

Extracted here once a second hook family needed it, on the same reasoning
that moved `jsonl_watermark` and `session_lookup` out of the collectors: two
copies of an error-swallowing helper drift, and the copy that drifts is the
one that stops writing the log nobody reads until something breaks.

Deliberately dependency-free beyond `paths`. The intent is that a hook
firing on every prompt should not drag the usage store in behind it — though
today `cli/flow.py` imports every command module eagerly, so the SQLite
import happens regardless of which subcommand runs. Keeping this module
clean is what makes lazy dispatch a possible future change rather than a
rewrite; it is not a saving that has been realized yet.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from paths import HOME

# Hook stdin is machine-generated, but it is still input from outside the
# process. A value that reaches a filename must be constrained before it
# gets anywhere near `Path(...)` or `unlink`.
_SAFE_KEY = r"[A-Za-z0-9._-]{1,128}"


def read_hook_stdin() -> dict | None:
    """The hook payload, or None if stdin held anything else.

    Returns None rather than raising: a hook handed garbage should decline
    to act, not produce a traceback in the middle of someone's turn.
    """
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def safe_key(value) -> bool:
    """Whether a value is fit to appear in a marker filename.

    Both runtimes generate UUID session ids today, and nothing guarantees
    that forever — a value containing a path separator must never reach
    path construction.
    """
    import re

    if not isinstance(value, str) or value in (".", ".."):
        # The charset alone admits both as whole values. Harmless where the
        # result is only ever a filename suffix, but this function is sold as
        # the guard against a value reaching path construction, and the next
        # caller may use it as a whole component.
        return False
    return re.fullmatch(_SAFE_KEY, value) is not None


def log_hook_error(kind: str, exc: Exception) -> None:
    """One breadcrumb line per swallowed hook error, so silent-by-design
    doesn't become invisible-forever. Best-effort: logging must never make
    the hook fail."""
    try:
        log_dir = HOME / ".flow" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "hook-errors.log").open("a") as fh:
            fh.write(f"{datetime.now(timezone.utc).isoformat()}\t{kind}\t{type(exc).__name__}: {exc}\n")
    except OSError:
        pass


def read_marker(path: Path) -> str | None:
    """A throttle marker's contents, or None when it is unreadable."""
    try:
        return path.read_text().strip()
    except OSError:
        return None


def write_marker(path: Path, value: str) -> None:
    """Best-effort marker write. A throttle that cannot persist degrades to
    firing again next time, which is the safe direction for an advisory."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    except OSError:
        pass
