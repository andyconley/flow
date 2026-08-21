"""Machine, project, and user-level setup, plus the project refresh path.

Every function here is additive by design. `setup project` copies the project
overlay scaffold. `refresh project` copies only missing overlay-core files and
registered local sources by default; `refresh project --all` is the explicit
full-scaffold backfill. Existing files whose content differs become update
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
import sys
from pathlib import Path

import flowtoml
import usage_store
from fsutil import (
    copy_if_missing,
    ensure_dir,
    ensure_file,
    repo_root,
)
from overlay import OVERLAY_GITIGNORE, format_overlay_vcs, git_env, overlay_vcs_status
from paths import (
    FLOW_CONFIG,
    FLOW_HOME,
    HOME,
    SCAFFOLD_DIR,
    SOURCE_DIR,
    USER_BIN_DIR,
    USER_OVERLAY_DIR,
)
from project import declared_sources
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


def setup_project() -> int:
    root = repo_root()
    target = root / ".flow"
    ensure_dir(target)

    for item in SCAFFOLD_DIR.iterdir():
        copy_if_missing(item, target / item.name)

    print(f"project scaffold ready: {target}")
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
    print("2. Optional — populate project-specific overlays where this project")
    print("   differs from the framework defaults:")
    print("   - .flow/project/*.md   (brand, domain, terminology, UX, etc.)")
    print("   - .flow/standards/*.md (only when a project standard must override the framework's)")
    print()
    print("3. Runtime surfaces come from the user-level install")
    print("   (`flow setup user`) and apply in every session. A project does")
    print("   not generate its own; project-level sync was retired.")
    print("   `flow project audit` reports anything this overlay is still")
    print("   carrying that the framework owns.")
    print()
    print("4. Open a fresh Claude Code session in this repo and try `/flow-boot`")
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


_REFRESH_CORE_PATHS = [
    Path("flow.toml"),
    Path("FRAMEWORK.md"),
    Path("PROJECT.md"),
    Path("memory/STATE.md"),
    Path("runs/.gitkeep"),
]


def _safe_scaffold_rel_paths(paths: set[Path]) -> list[Path]:
    safe: list[Path] = []
    for rel in paths:
        if rel.is_absolute() or ".." in rel.parts:
            continue
        if (SCAFFOLD_DIR / rel).exists():
            safe.append(rel)
    return sorted(safe, key=lambda path: path.as_posix())


def _iter_scaffold_files(rel_paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for rel in rel_paths:
        src = SCAFFOLD_DIR / rel
        if src.is_dir():
            for child in src.rglob("*"):
                if child.is_file():
                    files.append(child.relative_to(SCAFFOLD_DIR))
        elif src.is_file():
            files.append(rel)
    return sorted(files, key=lambda path: path.as_posix())


def _prompt_update(rel: Path, prompt: bool, update_all: bool) -> tuple[bool, bool]:
    if update_all:
        return True, True
    if not prompt:
        return False, False

    prompt_text = f"Update .flow/{rel.as_posix()} from framework? [y/N/a/q] "
    answer = ""
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            tty.write(prompt_text)
            tty.flush()
            answer = tty.readline().strip().lower()
    except OSError:
        try:
            answer = input(prompt_text).strip().lower()
        except EOFError:
            answer = ""

    if answer in {"q", "quit"}:
        raise KeyboardInterrupt
    if answer in {"a", "all"}:
        return True, True
    if answer in {"y", "yes"}:
        return True, False
    return False, False


def _refresh_scaffold_files(rel_paths: list[Path], target: Path, prompt: bool) -> dict[str, int]:
    counts = {
        "added": 0,
        "current": 0,
        "updated": 0,
        "changed": 0,
        "conflicts": 0,
    }
    update_all = False
    for rel in _iter_scaffold_files(rel_paths):
        src = SCAFFOLD_DIR / rel
        dest = target / rel
        if not dest.exists():
            ensure_dir(dest.parent)
            shutil.copy2(src, dest)
            counts["added"] += 1
            continue
        if not dest.is_file():
            counts["conflicts"] += 1
            print(f"conflict: .flow/{rel.as_posix()} exists but is not a file")
            continue
        if dest.read_bytes() == src.read_bytes():
            counts["current"] += 1
            continue

        try:
            should_update, update_all = _prompt_update(rel, prompt, update_all)
        except KeyboardInterrupt:
            print()
            print("refresh stopped by user")
            break
        if should_update:
            shutil.copy2(src, dest)
            counts["updated"] += 1
        else:
            counts["changed"] += 1
            print(f"update available: .flow/{rel.as_posix()}")
    return counts


def refresh_project(all_files: bool = False, interactive: bool = False) -> int:
    root = repo_root()
    target = root / ".flow"
    if not target.exists():
        print("repo is missing .flow; run `flow setup project` first")
        return 1

    if all_files:
        # `--all` used to copy every scaffold entry into the project. That is
        # the fork this refactor exists to remove: the copies never update, and
        # the runtime reads the user-level install regardless, so backfilling
        # them produced a directory of files that look authoritative and are
        # not. Refused rather than quietly reinterpreted as a plain refresh —
        # someone who typed `--all` wanted the copies, and should be told they
        # are gone instead of watching the command exit 0 having ignored them.
        print("`flow refresh project --all` was retired: it restored a full copy")
        print("of the framework scaffold, and those copies never update")
        print("run `flow refresh project` to repair this overlay's own core files")
        print("run `flow project audit` to see what it is still carrying")
        return 1

    manifest_path = target / "flow.toml"
    manifest = flowtoml.read_toml(manifest_path) if manifest_path.exists() else {}
    rel_paths = set(_REFRESH_CORE_PATHS)
    # Rejected declarations are dropped here rather than reported: refresh
    # has always silently skipped them (`_safe_scaffold_rel_paths` filters
    # the same two cases), and `flow project audit` is the surface that
    # names them.
    declared, _rejected = declared_sources(manifest)
    rel_paths.update(Path(d.rel) for d in declared)
    rel_paths = _safe_scaffold_rel_paths(rel_paths)
    mode = "overlay core and registered sources"

    prompt = interactive or sys.stdin.isatty()
    counts = _refresh_scaffold_files(rel_paths, target, prompt=prompt)

    print(f"project refresh complete: {target}")
    print(f"mode: {mode}")
    print(f"added missing files: {counts['added']}")
    print(f"already current: {counts['current']}")
    print(f"updated from framework: {counts['updated']}")
    print(f"left changed files unchanged: {counts['changed']}")
    print(f"conflicts: {counts['conflicts']}")
    if counts["changed"] and not prompt:
        print("tip: rerun with `flow refresh project --interactive` to choose updates")
    return 0
