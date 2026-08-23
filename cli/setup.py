"""Machine, project, and user-level setup, plus the project refresh path.

Every function here is additive by design. `setup project` creates the four
paths a project actually owns — see `_PROJECT_SCAFFOLD_PATHS`. `refresh
project` repairs those same paths plus any local sources the manifest
registers; `refresh project --all`, which used to backfill the whole framework
scaffold, is retired. Existing files whose content differs become update
candidates; none are overwritten without an explicit interactive choice.

`_ensure_usage_store` lives here rather than in usage_store.py because it is the
flow-layout-aware wrapper: it knows where ~/.flow/usage.db and the shipped
capability seed live. usage_store.py takes every path as an argument
specifically so it stays ignorant of that layout. lifecycle.py imports this
function for the post-update path, which is the one edge from lifecycle into
setup; nothing here reaches back into lifecycle, so the two stay acyclic.
"""

import shutil
import subprocess
from pathlib import Path

import usage_store
from fsutil import (
    copy_if_missing,
    ensure_dir,
    ensure_file,
    repo_root,
)
from overlay import OVERLAY_GITIGNORE, format_overlay_vcs, git_env, overlay_vcs_status
from paths import (
    CAPABILITY_DIRS,
    FLOW_CONFIG,
    FLOW_HOME,
    HOME,
    SCAFFOLD_DIR,
    SOURCE_DIR,
    USER_BIN_DIR,
    USER_OVERLAY_DIR,
)
from sync import sync_target


def setup_machine() -> int:
    ensure_dir(FLOW_HOME)
    ensure_dir(USER_BIN_DIR)
    ensure_dir(FLOW_HOME / "hooks")
    ensure_dir(FLOW_HOME / "user")
    ensure_dir(FLOW_HOME / "logs")
    ensure_file(
        FLOW_CONFIG,
        "[flow]\nsource_home = \"~/.flow/source\"\nlauncher = \"~/.local/bin/flow\"\n",
    )
    print(f"flow home ready: {FLOW_HOME}")
    print(f"config:     {FLOW_CONFIG}")
    _ensure_usage_store()
    print("next: run `flow setup project` inside a repository")
    return 0


def _ensure_usage_store() -> None:
    """Create the usage store if absent and apply pending migrations.

    Idempotent, so this is also the repair path. `flow update` covers release
    installs; develop installs short-circuit that command, which leaves
    `setup machine` as the only place a develop machine can pick up a schema
    change. Re-running it is the expected usage, not a fallback.

    `doctor` deliberately does not call this — a diagnostic that repairs the
    condition it reports can never report it.
    """
    store = usage_store.default_store_path(HOME)
    caps = usage_store.default_capabilities_path(SOURCE_DIR)
    try:
        created, applied = usage_store.ensure_store(store, caps)
    except Exception as exc:  # noqa: BLE001 — never block machine setup on the store
        print(f"usage store: error — {exc}")
        return
    if created:
        print(f"usage store: created {store} (schema v{usage_store.SCHEMA_VERSION})")
    elif applied:
        print(f"usage store: migrated to v{applied[-1]}")
    else:
        print(f"usage store: current (schema v{usage_store.SCHEMA_VERSION})")


# What a new project overlay actually holds. Everything absent from this list
# is framework capability, served by the user-level install: copying it here
# produced a fork that never updated and that the runtime never read.
#
# `flow.toml` is not here because it is not copied from the scaffold at all —
# the scaffold's manifest is the *framework's* 465-line sync configuration,
# and a project's is the handful of lines below. Sharing a filename is not
# sharing a document.
_PROJECT_SCAFFOLD_PATHS = (
    Path("PROJECT.md"),
    Path("memory/STATE.md"),
    Path("runs/.gitkeep"),
)

# Written verbatim into a new project. The commented `[[replaces]]` block is
# the only thing this file is for; it is commented rather than omitted so the
# shape is discoverable without reaching for the docs.
#
# `kind` exists so the two documents named `flow.toml` do not open identically.
# The framework's manifest at `scaffolds/default/flow.toml` starts with the
# same `[framework] name/version` pair, and without a discriminator a project
# manifest reads as that file truncated — which is exactly the confusion this
# split was supposed to end. Nothing consumes `kind` yet; it is here so that
# anything which needs to tell the two apart later can, without having to
# infer it from length or from which tables happen to be absent.
_PROJECT_MANIFEST_TEMPLATE = """\
[framework]
name = "flow"
version = 1
kind = "project"

# Point a role at your own standard instead of the
# framework default. `with` resolves in the user
# overlay — the project names the file, never holds it.
# Only standards/ and templates/ can be wired.
#
# [[replaces]]
# default = "standards/testing.md"
# with    = "standards/hypr-testing.md"
# why     = "pytest only, no BDD layer"
"""


def _write_project_manifest(target: Path) -> str:
    """Create the project manifest if absent. Never touch an existing one.

    Returns `"written"`, `"present"`, or `"refused"`. The manifest is project
    state — `flow project audit` lists it in `NOT_SCANNED` alongside
    `PROJECT.md` and `memory/` for the same reason — so repairing a missing
    one is in scope and reconciling a present one against the framework's
    manifest is not.

    Refuses on an overlay that still carries framework capability directories.
    Writing the short template there would be worse than doing nothing: a
    legacy manifest declares the project's registered sources, and
    `migrate.runtime_managed_paths` reads `[claude] managed_manifest` out of it
    to find the generated adapters. Replace it with eleven lines naming
    neither and `flow refresh project` quietly stops repairing those sources,
    while `flow project migrate` can no longer see `.claude/skills`,
    `.claude/agents`, or `.claude/hooks` at all — orphaning them permanently,
    which is the outcome acceptance criterion 3 exists to prevent.

    `is_symlink` is checked separately because `exists()` follows links and
    reports False for a dangling one — `write_text` would then write *through*
    the link to wherever it points, outside the overlay. `capability_entries`
    in `project.py` guards the same way for the same reason.
    """
    manifest = target / "flow.toml"
    if manifest.exists() or manifest.is_symlink():
        return "present"
    if any((target / name).is_dir() for name in CAPABILITY_DIRS):
        return "refused"
    ensure_dir(target)
    manifest.write_text(_PROJECT_MANIFEST_TEMPLATE)
    return "written"


def setup_project() -> int:
    root = repo_root()
    target = root / ".flow"
    ensure_dir(target)

    for rel in _PROJECT_SCAFFOLD_PATHS:
        ensure_dir((target / rel).parent)
        copy_if_missing(SCAFFOLD_DIR / rel, target / rel)
    # `setup project` is also run against directories that already hold an
    # overlay, so the refusal path is reachable here too and must not be
    # swallowed — it is the difference between a repaired overlay and one
    # whose registered sources silently stopped being repaired.
    if _write_project_manifest(target) == "refused":
        print(f"project overlay ready: {target}")
        print()
        print("no .flow/flow.toml was written: this overlay already carries")
        print("framework directories, and a short manifest would hide the")
        print("sources and generated adapters the old one named")
        print("run `flow project audit` to see what is here")
        return 0

    print(f"project overlay ready: {target}")
    print()
    print("This overlay holds this project's own work — its context, its state,")
    print("and its run artifacts. Commands, agents, standards, and templates")
    print("come from the user-level install and are not copied here.")
    print()
    print("Next steps:")
    print()
    print("1. Run `/flow-init-project` in a Claude session in this repo —")
    print("   it walks you through filling in .flow/PROJECT.md with")
    print("   proposals inferred from your CLAUDE.md, git history, and")
    print("   file structure. Section by section, you confirm or adjust.")
    print()
    print("   (Or edit .flow/PROJECT.md by hand if you prefer.)")
    print()
    print("2. Runtime surfaces come from the user-level install")
    print("   (`flow setup user`) and apply in every session. A project does")
    print("   not generate its own; project-level sync was retired.")
    print()
    print("3. Open a fresh Claude Code session in this repo and try `/flow-boot`")
    print("   to verify the overlay is being read.")
    return 0


# Files that do not count as "the overlay has content." `.git` is the state
# being decided about; `.DS_Store` is Finder/Spotlight noise that lands in any
# directory on macOS and would otherwise push a genuinely fresh machine down
# the init-in-place path — producing an unrelated empty history pointed at a
# seeded remote, whose first push then needs --allow-unrelated-histories.
# `.gitignore` is flow's own, written by an earlier attempt.
_OVERLAY_NON_CONTENT = {".git", ".DS_Store", ".gitignore"}


def _scrub_url(url: str) -> str:
    """Hide credentials embedded in a remote URL before printing it.

    `https://user:token@host/repo.git` is a legitimate thing to pass, and
    echoing it to the terminal (and into scrollback, and into any transcript)
    is not.
    """
    if "@" not in url or "//" not in url:
        return url
    scheme, _, rest = url.partition("//")
    userinfo, _, host = rest.rpartition("@")
    if not userinfo:
        return url
    return f"{scheme}//<credentials>@{host}"


def _run_git(args: list[str], cwd: Path | None = None, timeout: float = 120.0):
    """Run a git command that may touch the network.

    Deliberately does NOT capture output: a clone against a private HTTPS
    remote with no credential helper prompts, and capturing that prompt while
    leaving stdin attached turns a fixable authentication step into a silent
    hang with no visible reason. Progress and prompts go to the user's
    terminal; the timeout is the backstop for a genuinely stuck operation.
    """
    env = git_env()
    # An interactive prompt is fine here (unlike the read-only status path) —
    # it is visible, and the timeout bounds it either way.
    env.pop("GIT_TERMINAL_PROMPT", None)
    try:
        return subprocess.run(["git", *args], cwd=cwd, env=env, timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        print(f"user overlay:     git {args[0]} timed out after {int(timeout)}s")
        return 1
    except OSError as err:
        print(f"user overlay:     could not run git: {err}")
        return 1


def _attach_overlay_repo(url: str) -> int:
    """Give `~/.flow/user/` a git home, without ever clobbering what is there.

    Three cases, because the overlay may already exist with authored content
    (the common case for anyone who has used it before this shipped):

    - already a repo: report and leave alone. Re-pointing an existing remote
      is a deliberate act, not something `setup user` should do behind your
      back. A repo with NO remote is the exception — adding one there
      completes an attach that failed partway, rather than overriding a
      choice, and without it a half-attached overlay would be permanently
      stuck reporting "no remote" with no path forward.
    - absent or empty: clone. The remote is the source of truth, which is
      what makes this the new-machine path.
    - has content, no `.git`: init in place and add the remote. Never clone
      over it — that would either fail or discard local work. The first
      commit is deliberately NOT made here; see the convention note below.

    Setup initializes; it does not commit. Committing overlay content is the
    job of whichever agent edits it, in the same turn as the edit — the
    person who owns this content is not the one typing in the directory, so
    a model that waits for them to notice pending changes would leave work
    uncommitted indefinitely.
    """
    USER_OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    gitignore = USER_OVERLAY_DIR / ".gitignore"
    shown = _scrub_url(url)

    def write_gitignore(note: str = "") -> None:
        if not gitignore.exists():
            gitignore.write_text(OVERLAY_GITIGNORE)
            print(f"  wrote:          .gitignore{note}")

    if (USER_OVERLAY_DIR / ".git").exists():
        status = overlay_vcs_status(USER_OVERLAY_DIR)
        print(f"user overlay:     already a git repo ({format_overlay_vcs(status)})")
        if status["remote"] is None:
            if _run_git(["remote", "add", "origin", url], cwd=USER_OVERLAY_DIR) != 0:
                return 1
            print(f"  added:          remote origin -> {shown}")
        elif status["remote"] != url:
            print(f"  note:           remote is {_scrub_url(status['remote'])}, not {shown} — left as-is")
        write_gitignore()
        return 0

    has_content = any(p.name not in _OVERLAY_NON_CONTENT for p in USER_OVERLAY_DIR.iterdir())
    if not has_content:
        # Clone to a sibling and move the result in, rather than cloning
        # straight into USER_OVERLAY_DIR. git refuses to clone into a
        # directory that is not *literally* empty, and this one routinely
        # holds a `.DS_Store` — which is exactly the noise we just decided
        # should not count as content. Moving in preserves that decision
        # instead of letting Finder dictate which branch runs.
        staging = USER_OVERLAY_DIR.parent / f"{USER_OVERLAY_DIR.name}.clone-tmp"
        shutil.rmtree(staging, ignore_errors=True)
        if _run_git(["clone", url, str(staging)]) != 0:
            shutil.rmtree(staging, ignore_errors=True)
            print(f"user overlay:     clone of {shown} failed — nothing written")
            return 1
        for item in staging.iterdir():
            shutil.move(str(item), str(USER_OVERLAY_DIR / item.name))
        staging.rmdir()
        print(f"user overlay:     cloned {shown}")
        write_gitignore(" (commit it when convenient)")
        return 0

    # `-b main` rather than inheriting init.defaultBranch: an unset default
    # produces `master` plus hint noise, which then mismatches a `main` remote.
    if _run_git(["init", "-b", "main"], cwd=USER_OVERLAY_DIR) != 0:
        return 1
    print("user overlay:     initialized (branch main)")
    if _run_git(["remote", "add", "origin", url], cwd=USER_OVERLAY_DIR) != 0:
        # The repo exists but has no remote. Re-running this command completes
        # it via the no-remote branch above, so say so rather than leaving the
        # user to guess.
        print("  note:           repo created without a remote; re-run this command to finish")
        return 1
    print(f"user overlay:     remote origin -> {shown}")
    write_gitignore()
    print("  next:           commit the existing overlay content and push")
    return 0


def setup_user(overlay_repo: str | None = None) -> int:
    """Install flow at the user level: generate ~/.claude/ surfaces from the framework scaffold."""
    if not FLOW_HOME.exists():
        print("flow home missing; run `flow setup machine` first")
        return 1
    if not SCAFFOLD_DIR.exists():
        print("framework scaffold missing; re-run install-flow.sh from the flow repo")
        return 1

    # An attach failure does not abort the install. A mistyped URL would
    # otherwise leave the machine with no user-level surfaces at all, which is
    # worse than surfaces missing the overlay's personal extras — and sync
    # reads the overlay manifest directly, so whatever is on disk still
    # applies. The failure is carried into the exit code below.
    overlay_result = _attach_overlay_repo(overlay_repo) if overlay_repo else 0
    if overlay_repo:
        print()

    print("Installing flow at user level…")
    print()
    claude_result = sync_target("claude", check=False, user_mode=True)
    print()
    codex_result = sync_target("codex", check=False, user_mode=True)
    print()
    if claude_result != 0 or codex_result != 0 or overlay_result != 0:
        print("user-level setup completed with errors; review output above")
        return 1
    print("user-level setup complete")
    print("next: open a fresh Claude Code session anywhere and try `/flow-boot`")
    return 0

def refresh_project(all_files: bool = False, interactive: bool = False) -> int:
    """Retired. Every job this had is either gone or lives elsewhere now.

    It repaired a missing manifest and missing core files — both of which
    `flow setup project` already does idempotently — and restored
    manifest-declared sources from the scaffold, which is fork restoration in
    miniature and the thing `flow project migrate` exists to undo.

    The one capability with no successor is updating an *existing* core file
    from the framework: `copy_if_missing` never touches a file that is there.
    Named in the message rather than left to be discovered, though in practice
    all three core files are authored project content from the moment the
    project is initialized, and the right answer to "overwrite your PROJECT.md
    from the template?" was always no.

    Refused before any filesystem check, including whether `.flow` exists.
    Someone typing a retired command needs to hear that it is retired, not a
    setup error about a directory the command would no longer have touched.
    """
    print("`flow refresh project` was retired.")
    print("")
    print("A project overlay no longer holds framework files, so there is")
    print("nothing here to refresh from the scaffold. What it used to do:")
    print("")
    print("  missing flow.toml or core files  ->  flow setup project")
    print("  framework copies still present   ->  flow project audit")
    print("                                       flow project migrate")
    print("")
    print("Updating an existing PROJECT.md or STATE.md from the framework")
    print("template has no replacement. Those are your files once the project")
    print("exists; edit them directly.")
    return 1
