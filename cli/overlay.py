"""User-overlay version-control status: read-only inspection of `~/.flow/user/`.

The overlay is the one authored layer in flow with no home in any repo the
framework ships — it holds personal commands, agent overrides, hook scripts,
and the manifest registering them. Making it a git repo is what gives that
content history and a way back after a lost machine.

This module reports and advises. It never inits, commits, or pushes: `doctor`
consumes the status, and `doctor`'s contract is to observe conditions rather
than repair them (see the usage-store note there for the same reasoning).
Setup handles initialization; the agent that edits overlay files commits
them. The only thing written here is a throttle marker under
`~/.flow/state/`, so that the nudge below can stay quiet without forgetting
that it already spoke.

Kept separate from `diagnostics.py` so the status is unit-testable against a
temporary directory without shelling through the CLI, and so `diagnostics.py`
keeps holding presentation rather than git plumbing.
"""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import hookio
from paths import HOME, USER_OVERLAY_DIR

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


# `_git` returns this when git never ran at all — a missing binary, a
# timeout, a directory that vanished. Distinct from any real git exit code,
# because "git is not here" and "git says this is not a repository" call for
# opposite messages: one is a broken machine, the other is the ordinary
# untracked state with a fix worth naming.
_GIT_DID_NOT_RUN = -1


def _git(overlay_dir: Path, *args: str) -> tuple[int, str]:
    """Run one git command in the overlay, returning (returncode, stdout).

    A failure is reported as a failure, never raised — an unreadable overlay
    is a status to print, not a crash. `_GIT_DID_NOT_RUN` separates "git
    never ran" from "git said no", so a missing git binary cannot be
    mistaken for an innocent-looking untracked directory.
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
        return _GIT_DID_NOT_RUN, ""
    return proc.returncode, proc.stdout.strip()


def display_path(path: Path) -> str:
    """`~`-contracted for display. Never prints the account name, which is
    the same reason nothing this framework writes hardcodes one."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


# Space-separated fields that precede the path on each `--porcelain=v2` entry
# line. Paths routinely contain spaces, so the path has to be split off by
# field count rather than sliced at a fixed offset the way v1's fixed-width
# `XY ` prefix allowed. `!` is absent because `--ignored` is never passed.
_V2_ENTRY_FIELDS = {
    "1": 8,  # 1 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <path>
    "2": 9,  # 2 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <X><score> <path>\t<orig>
    "u": 10,  # u <XY> <sub> <m1> <m2> <m3> <mW> <h1> <h2> <h3> <path>
    "?": 1,  # ? <path>
}


def _v2_entry_path(line: str) -> str | None:
    """The path an entry line refers to, or None if the line is not an entry.

    A rename entry names two paths, tab-separated, new first. The new path is
    the one that is uncommitted, so it is the one reported.
    """
    fields = _V2_ENTRY_FIELDS.get(line[:1])
    if fields is None:
        return None
    parts = line.split(" ", fields)
    if len(parts) <= fields:
        return None
    return parts[fields].split("\t", 1)[0] or None


def _parse_status_v2(out: str) -> tuple[str | None, str | None, int | None, list[str]]:
    """(branch, upstream, unpushed, dirty) from `status --porcelain=v2 --branch`.

    The `--branch` header carries what three separate commands would otherwise
    be spawned for — branch name, upstream ref, ahead count — and it answers
    correctly in the two states `rev-parse --abbrev-ref HEAD` gets wrong: an
    unborn branch, where rev-parse fails outright, and a detached HEAD, where
    it returns the literal string "HEAD" and would be reported as a branch by
    that name.

    Header shapes, all verified against git rather than inferred:
      `# branch.oid <sha>`            or `(initial)` on an unborn branch
      `# branch.head main`            or `(detached)`
      `# branch.upstream origin/main` omitted entirely when unset
      `# branch.ab +2 -0`             omitted entirely when unset

    `unpushed` stays None only when there is no upstream, so the caller can
    read None as "nowhere to push" and 0 as "level". An `+N` that will not
    parse is therefore treated as level, matching what the v1 parser did with
    an unparseable `[ahead N]`.
    """
    branch = upstream = None
    unpushed = None
    dirty = []

    for line in out.splitlines():
        if line.startswith("# "):
            key, _, value = line[2:].partition(" ")
            if key == "branch.head":
                branch = None if value == "(detached)" else (value or None)
            elif key == "branch.upstream":
                upstream = value or None
            elif key == "branch.ab":
                for part in value.split():
                    if part.startswith("+") and part[1:].isdigit():
                        unpushed = int(part[1:])
            continue
        path = _v2_entry_path(line)
        if path:
            dirty.append(path)

    if upstream is not None and unpushed is None:
        unpushed = 0
    return branch, upstream, unpushed, dirty


def overlay_vcs_status(overlay_dir: Path, known_root: str | None = None, quick: bool = False) -> dict:
    """Version-control status for the overlay directory.

    Returns `{"present", "tracked", "ignored", "error", "root", "is_root",
    "branch", "upstream", "remote", "dirty", "unpushed"}`.

    - `present` False means there is no overlay at all — the opt-in default,
      not a problem.
    - `tracked` False with `present` True is the state this whole feature
      exists to surface: authored content with no history and no backup.
    - `ignored` True means the overlay sits inside a repository that
      explicitly excludes it. `tracked` stays False, because content git has
      been told to skip has no more history than content in no repo at all —
      but the fix is different, so it gets its own state.
    - `error` True means git could not be read at all. Reported as such
      rather than synthesized into a plausible-looking clean/detached status,
      because a diagnostic that states a false condition is worse than one
      that admits it does not know.
    - `root` is the work tree's top level, and `is_root` says whether that is
      the overlay itself. When it is not, the overlay is a subdirectory or a
      symlink into a larger repo — a dotfiles home, say — and `dirty` and
      `unpushed` describe that whole repo, which is the intended reading:
      uncommitted work next to the overlay is the same hazard.
    - `unpushed` is None when the branch has no upstream — distinct from 0,
      which means an upstream exists and is level. `upstream` names that ref,
      and is None in exactly the same cases.
    - `remote` is the configured origin URL, and is the one field `quick`
      omits. `quick` is for the per-prompt hook, which needs to know whether
      anything is outstanding and pays for one fewer subprocess by asking
      about the upstream instead of the remote; a caller that reads `remote`
      must not pass it, because None then means "not asked" rather than
      "not configured". `doctor` and `setup` use the full status.

    Membership is asked of git, never inferred from a `.git` directory on
    disk: `.git` exists only at a work tree's root, so the filesystem test
    calls every nested or symlinked overlay untracked while it is fully
    committed. Up to four bounded local calls, or three under `quick`.
    """
    status = {
        "present": overlay_dir.is_dir(),
        "tracked": False,
        "ignored": False,
        "error": False,
        "root": None,
        "is_root": False,
        "branch": None,
        "upstream": None,
        "remote": None,
        "dirty": [],
        "unpushed": None,
    }
    if not status["present"]:
        return status

    if known_root is None:
        rc, out = _git(overlay_dir, "rev-parse", "--show-toplevel")
        if rc == _GIT_DID_NOT_RUN:
            status["error"] = True
            return status
        if rc != 0:
            # Git ran and said this is not a work tree. The ordinary untracked
            # state, and the one `--overlay-repo` exists to fix.
            return status
    else:
        # The hook path already resolved this to decide whether an edit was
        # even relevant. Re-asking cost a second subprocess on the hottest
        # code path in the module.
        out = known_root

    root = Path(out)
    status["root"] = str(root)
    try:
        status["is_root"] = root.resolve() == overlay_dir.resolve()
    except OSError:
        status["is_root"] = False

    # Inside a repo is not the same as kept by it. An overlay under an
    # ignored path would otherwise report a clean, backed-up status while
    # every file in it stays permanently uncommitted.
    if not status["is_root"]:
        # The resolved path, not the symlink: `~/.flow/user` is a link into
        # the dotfiles repo, and git answers "outside repository" (128) for a
        # path that is not under the work tree it can see — which would leave
        # this guard silently inert in exactly the topology it was added for.
        try:
            probe = str(overlay_dir.resolve())
        except OSError:
            probe = str(overlay_dir)
        rc_ignored, _ = _git(overlay_dir, "check-ignore", "--quiet", probe)
        if rc_ignored == 0:
            status["ignored"] = True
            return status

    status["tracked"] = True

    rc, out = _git(overlay_dir, "status", "--porcelain=v2", "--branch")
    if rc != 0:
        status["error"] = True
        return status

    (
        status["branch"],
        status["upstream"],
        status["unpushed"],
        status["dirty"],
    ) = _parse_status_v2(out)

    if not quick:
        rc, out = _git(overlay_dir, "config", "--get", "remote.origin.url")
        if rc == 0 and out:
            status["remote"] = out

    return status


def format_overlay_vcs(status: dict) -> str:
    """One line for `doctor`. Names the fix when there is one to name."""
    if not status["present"]:
        return "n/a (no overlay)"
    if status["error"]:
        return "unreadable (git error)"
    if status["ignored"]:
        root = display_path(Path(status["root"])) if status["root"] else "its repo"
        return f"ignored by {root} — nothing here is committed despite the repo around it"
    if not status["tracked"]:
        return "untracked — run `flow setup user --overlay-repo <url>` to give it history"

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
    line = f"{', '.join(parts)} ({where})"
    if not status["is_root"] and status["root"]:
        # Naming the repo matters once the overlay lives inside a bigger one:
        # the counts above are the whole tree's, not this directory's.
        line += f" — {display_path(Path(status['root']))}"
    return line


# ---------------------------------------------------------------------------
# The nudge
#
# `FRAMEWORK.md` says the agent that edits overlay content commits it in the
# same turn. That convention had no detection: a compaction or a fresh
# session regressed to accumulating uncommitted work, discovered only when
# `doctor` happened to be run.
#
# Two triggers, both advisory, neither ever blocking:
#
#   PostToolUse       — right after a write, so the agent learns the file it
#                       just touched is versioned while the edit is fresh.
#   UserPromptSubmit  — the turn boundary that actually reaches the model.
#                       Stop would be the intuitive choice and is the wrong
#                       one: its stdout lands in the transcript, which is why
#                       `flow-token-verdict.sh` writes a file there instead.
#                       UserPromptSubmit's stdout is injected as context, so
#                       the nudge arrives at the start of the next turn —
#                       one turn later, but somewhere the agent can act on it.
#
# Silent unless the overlay is tracked AND has something outstanding. Someone
# who never opted into an overlay repo must never see this.
# ---------------------------------------------------------------------------

# PostToolUse is bounded by edits, so it only needs to avoid firing once per
# file across a ten-file burst. UserPromptSubmit fires on every prompt and
# needs the longer quiet period. A repo with nowhere to push is a standing
# condition rather than a per-turn one — worth saying, not worth saying often.
NUDGE_THROTTLE_EDIT_SEC = 10 * 60
NUDGE_THROTTLE_PROMPT_SEC = 30 * 60
NUDGE_THROTTLE_STANDING_SEC = 24 * 60 * 60

NUDGE_STATE_DIR = HOME / ".flow" / "state"


def nudge_fingerprint(status: dict) -> str:
    """A stable digest of what there is to commit.

    Lets the prompt-boundary nudge re-fire the moment the outstanding set
    changes, rather than staying quiet for the rest of the throttle window
    while new work piles up behind it.
    """
    # `upstream`, not `remote`: the hook path asks for a `quick` status, where
    # `remote` is always None and so contributes nothing a change could move.
    parts = [status.get("branch") or "", str(status.get("unpushed")), str(status.get("upstream"))]
    parts.extend(sorted(status.get("dirty") or []))
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def _marker_path(root: str, event: str, session_id: str | None = None) -> Path:
    """One marker per (repo, event, session).

    Keying on the repo alone let whichever session fired first silence every
    other one for the whole window — including, most likely, the session that
    actually made the edits, which inverts the point of the nudge. Sessions
    get their own markers; a payload without a usable id falls back to the
    shared key rather than skipping the throttle entirely.

    The repo path is hashed rather than spelled out: nothing this framework
    writes should put an account name in a filename.
    """
    key = hashlib.sha256(root.encode()).hexdigest()[:16]
    if session_id and hookio.safe_key(session_id):
        key = f"{key}-{session_id}"
    return NUDGE_STATE_DIR / f"overlay-nudge-{event}-{key}"


def _within_throttle(root: str, event: str, session_id: str | None, throttle_sec: int) -> bool:
    """Whether this (repo, event, session) spoke recently enough to stay quiet.

    Split out so a caller can consult the throttle before doing the expensive
    work, rather than computing a full status and then discovering it had
    nothing to say. Only sound for branches where `refire_on_change` is False;
    where the fingerprint matters, the status is needed to compute it.
    """
    raw = hookio.read_marker(_marker_path(root, event, session_id))
    if not raw:
        return False
    stamp, _, _ = raw.partition("\t")
    try:
        elapsed = time.time() - float(stamp)
    except ValueError:
        return False
    return 0 <= elapsed < throttle_sec


def should_nudge(
    status: dict,
    event: str,
    *,
    throttle_sec: int,
    refire_on_change: bool,
    session_id: str | None = None,
    now: float | None = None,
) -> bool:
    """Whether to speak, and record having spoken.

    Fires when the throttle window has elapsed, or — for the prompt-boundary
    nudge — as soon as the outstanding set differs from what was last
    reported.

    Every degenerate marker state resolves toward firing rather than toward
    silence, deliberately: an unreadable marker, a partially-written one from
    two sessions racing, a clock that moved backwards. A duplicated advisory
    costs one line; a suppressed one costs the whole feature, and does so
    invisibly.
    """
    now = time.time() if now is None else now
    marker = _marker_path(status["root"] or "", event, session_id)

    raw = hookio.read_marker(marker)
    fingerprint = nudge_fingerprint(status)
    if raw:
        stamp, _, seen = raw.partition("\t")
        try:
            elapsed = now - float(stamp)
        except ValueError:
            elapsed = throttle_sec  # unparseable marker: treat as expired
        if elapsed < 0:
            # A clock that jumped backwards leaves a timestamp in the future.
            # Left alone this suppresses the nudge until real time catches
            # up, and the suppressed branch never rewrites the marker — so it
            # would stay suppressed for as long as the skew lasts.
            elapsed = throttle_sec
        unchanged = seen == fingerprint
        if elapsed < throttle_sec and (unchanged or not refire_on_change):
            return False

    hookio.write_marker(marker, f"{now}\t{fingerprint}")
    _prune_markers(now)
    return True


# Markers are keyed per session, and `~/.flow/state/` is a permanent home
# directory rather than a `/tmp` the OS reaps — so without this, two files
# accumulate per session per repo forever. Pruning rides along on the write
# that just happened: no scheduler, no separate command, and a failure to
# prune costs disk rather than correctness.
NUDGE_MARKER_TTL_SEC = 7 * 24 * 60 * 60


def _prune_markers(now: float) -> None:
    """Best-effort removal of markers older than their usefulness."""
    try:
        for stale in NUDGE_STATE_DIR.glob("overlay-nudge-*"):
            try:
                # follow_symlinks=False so a dangling link is judged on its own
                # mtime. Following it raises, which the `continue` below would
                # swallow, leaving a broken link here permanently.
                if now - stale.lstat().st_mtime > NUDGE_MARKER_TTL_SEC:
                    stale.unlink()
            except OSError:
                continue
    except OSError:
        pass


def nudge_outstanding(status: dict) -> tuple[list[str], bool]:
    """What is outstanding, and whether it is only the standing condition.

    "Nowhere to push" belongs here even though it is not per-turn work: a
    tracked repo with fifty local commits and no upstream has zero copies off
    this machine, which is the exact scenario the overlay got a repo for.
    `unpushed` is None rather than a count in that state, so a truthiness test
    alone stays silent about it.

    Keyed on `upstream` rather than `remote` so this reads correctly under the
    hook's `quick` status, where `remote` is deliberately not asked for. It
    costs a distinction `doctor` still makes: a repo with a remote configured
    but no upstream set reads the same here as one with no remote at all. Both
    mean nothing is pushed, which is the only thing this advisory acts on.
    """
    outstanding = []
    if status["dirty"]:
        n = len(status["dirty"])
        outstanding.append(f"{n} uncommitted file{'s' if n != 1 else ''}")
    if status["unpushed"]:
        outstanding.append(f"{status['unpushed']} unpushed commit{'s' if status['unpushed'] != 1 else ''}")

    standing = []
    if status["upstream"] is None:
        standing.append("no upstream branch, so nothing here exists off this machine")

    return outstanding + standing, (bool(standing) and not outstanding)


def nudge_message(status: dict, event: str, edited: str | None = None) -> str | None:
    """The advisory line, or None when there is nothing worth saying.

    Phrased as a condition, and scoped as narrowly as the trigger allows.
    The counts describe the whole repository while the session reading this
    line may own none of it — so an unconditional "commit and push" would
    tell a runtime that pre-authorizes `git push` to publish files it did
    not touch and cannot evaluate. When the trigger knows which path was
    edited, the line names it, so resolving the advisory does not mean
    `git add -A`.
    """
    outstanding, _ = nudge_outstanding(status)
    if not outstanding:
        return None

    where = display_path(Path(status["root"])) if status["root"] else "the overlay repo"
    if edited:
        what = (
            f"Commit and push just {display_path(Path(edited))} — the count above is the whole "
            "repository, so do not stage the rest of it"
        )
    else:
        what = (
            "If this session made those changes, commit and push only the paths it edited "
            "before finishing; if it did not, leave them alone — another session may own that work"
        )
    return (
        f"flow advisory: {where} has {' and '.join(outstanding)}. "
        f"{what} (see FRAMEWORK.md, 'Committing user-overlay edits'). "
        "(Informational only — nothing is blocked.)"
    )


def _edit_touches_repo(payload: dict, root: str) -> bool | None:
    """Whether the edited path lies inside the repo.

    None means the runtime did not say. Claude's PostToolUse payload carries
    `tool_input.file_path`; Codex's shape is unverified, so an absent path
    must degrade to the plain outstanding-work check rather than silently
    disabling the hook on one runtime.
    """
    tool_input = payload.get("tool_input")
    path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if not isinstance(path, str) or not path:
        return None
    if not Path(path).is_absolute():
        # A relative path would resolve against the hook process's cwd, which
        # is not necessarily the runtime's. Claude always sends an absolute
        # path; rather than guess for a runtime that might not, say "unknown"
        # and let the caller fall back.
        return None
    try:
        return Path(root).resolve() in Path(path).resolve().parents
    except OSError:
        return None


def overlay_check_command() -> int:
    """`flow overlay check --hook`. Always exits 0, prints at most one line.

    Every failure mode here is swallowed on purpose. A hook that errors on
    every prompt of every session is the loudest possible failure of a
    feature whose whole premise is staying quiet.
    """
    try:
        payload = hookio.read_hook_stdin()
        if payload is None:
            return 0
        event = payload.get("hook_event_name")
        if event not in ("PostToolUse", "UserPromptSubmit"):
            return 0

        # PostToolUse fires after every qualifying tool call, most of which
        # have nothing to do with the overlay. Resolve the repo root first —
        # one cheap call — and discard irrelevant edits before paying for
        # `status` and `config`. Claude narrows to Write|Edit by matcher;
        # Codex is registered without one, because its tool names are `exec`
        # and friends rather than Claude's, so this filter is the only thing
        # bounding the cost there.
        edited = None
        root = None
        if event == "PostToolUse":
            rc, out = _git(USER_OVERLAY_DIR, "rev-parse", "--show-toplevel")
            if rc != 0 or not out:
                return 0
            root = out
            inside = _edit_touches_repo(payload, out)
            if inside is False:
                return 0
            if inside is True:
                tool_input = payload.get("tool_input") or {}
                edited = tool_input.get("file_path") if isinstance(tool_input, dict) else None

            # Check the throttle BEFORE paying for status. Codex has no
            # per-tool matcher and its tool calls carry no single file_path,
            # so `inside` is None for every `exec` and the old ordering fell
            # through to four more git calls — measured at ~194ms per tool
            # call, roughly 12s of added wall clock across a Codex session —
            # only to decide it had nothing to say. `refire_on_change` is
            # False on this branch, so elapsed time alone decides and this
            # skips no advisory the full path would have produced.
            if _within_throttle(root, event, payload.get("session_id"), NUDGE_THROTTLE_EDIT_SEC):
                return 0

        # `quick`: the advisory acts on "is anything outstanding", which the
        # `status` header answers via the upstream ref. Asking `config --get
        # remote.origin.url` as well cost a fourth subprocess (~45ms) on every
        # prompt to sharpen wording nobody reads at that moment — `doctor`
        # still draws the full distinction.
        status = overlay_vcs_status(USER_OVERLAY_DIR, known_root=root, quick=True)
        if not status["tracked"] or status["error"]:
            # An untracked or unreadable overlay is `doctor`'s business.
            # Repeating it on every prompt would be noise aimed at someone
            # who may never have opted in.
            return 0

        message = nudge_message(status, event, edited)
        if message is None:
            return 0

        _, standing_only = nudge_outstanding(status)
        if standing_only:
            # A repo with nowhere to push is a property of the repo, not of any
            # session's work — so it must NOT be keyed per session. Keyed
            # that way, every new session and every /clear starts markerless
            # and re-fires, turning a once-a-day note into two lines per
            # session forever for anyone running a deliberately local-only
            # overlay. That is the noise this module says belongs in `doctor`.
            #
            # Its own marker namespace, though: session=None is also the
            # fallback key when a payload carries no session_id, which is the
            # Codex case. Sharing it meant a 24h standing marker suppressed
            # genuine edit nudges for the whole edit window.
            marker_event = f"standing-{event}"
            throttle, refire, session = NUDGE_THROTTLE_STANDING_SEC, False, None
        elif event == "PostToolUse":
            marker_event = event
            throttle, refire = NUDGE_THROTTLE_EDIT_SEC, False
            session = payload.get("session_id")
        else:
            marker_event = event
            throttle, refire = NUDGE_THROTTLE_PROMPT_SEC, True
            session = payload.get("session_id")
        if not should_nudge(
            status,
            marker_event,
            throttle_sec=throttle,
            refire_on_change=refire,
            session_id=session,
        ):
            return 0

        # Only `UserPromptSubmit` and `SessionStart` add plain stdout to the
        # model's context. A `PostToolUse` hook has to wrap its text in the
        # JSON envelope or the line reaches the transcript and nothing else —
        # see hooks/flow-managed-write-reminder.sh, which does the same.
        if event == "PostToolUse":
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": message,
                        }
                    }
                )
            )
        else:
            print(message)
        return 0
    except Exception as exc:
        hookio.log_hook_error("overlay-nudge", exc)
        return 0


def overlay_status_command() -> int:
    """`flow overlay status`. The `doctor` line, standalone."""
    status = overlay_vcs_status(USER_OVERLAY_DIR)
    print(f"overlay:  {display_path(USER_OVERLAY_DIR)}")
    if status["root"] and not status["is_root"]:
        # Without this the dirty paths below look like overlay paths when
        # they are the enclosing repository's, which is misleading in exactly
        # the arrangement that makes this command worth having.
        print(f"repo:     {display_path(Path(status['root']))}")
    print(f"vcs:      {format_overlay_vcs(status)}")
    if status["remote"]:
        print(f"remote:   {status['remote']}")
    for path in status["dirty"]:
        print(f"  dirty:  {path}")
    return 0
