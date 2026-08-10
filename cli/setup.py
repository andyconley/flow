"""Machine, project, and user-level setup, plus the project refresh path.

Every function here is additive by design. `setup project` and `refresh project`
copy only files that are missing, so re-running them on a repo with hand-edited
.flow content never overwrites the edits — that is the whole reason `refresh`
exists as a separate verb from a hypothetical re-scaffold.

`_ensure_usage_store` lives here rather than in usage_store.py because it is the
flow-layout-aware wrapper: it knows where ~/.flow/usage.db and the shipped
capability seed live. usage_store.py takes every path as an argument
specifically so it stays ignorant of that layout. lifecycle.py imports this
function for the post-update path, which is the one edge from lifecycle into
setup; nothing here reaches back into lifecycle, so the two stay acyclic.
"""

import subprocess

import usage_store
from fsutil import (
    copy_if_missing,
    ensure_dir,
    ensure_file,
    repo_root,
    sync_missing_tree,
)
from overlay import OVERLAY_GITIGNORE, format_overlay_vcs, overlay_vcs_status
from paths import (
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
    print("3. Project-level `flow sync claude` / `flow sync codex` is only")
    print("   needed when this project has uniquely-shaped Claude tooling")
    print("   (custom agents, hooks, or settings). If you only need the")
    print("   framework's universal surfaces, the user-level install")
    print("   (`flow setup user`) already covers them everywhere.")
    print()
    print("4. Open a fresh Claude Code session in this repo and try `/flow-boot`")
    print("   to verify the overlay is being read.")
    return 0


def _attach_overlay_repo(url: str) -> int:
    """Give `~/.flow/user/` a git home, without ever clobbering what is there.

    Three cases, because the overlay may already exist with authored content
    (the common case for anyone who has used it before this shipped):

    - already a repo: report and leave alone. Re-pointing a remote is a
      deliberate act, not something `setup user` should do behind your back.
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

    if (USER_OVERLAY_DIR / ".git").exists():
        status = overlay_vcs_status(USER_OVERLAY_DIR)
        print(f"user overlay:     already a git repo ({format_overlay_vcs(status)})")
        if status["remote"] and status["remote"] != url:
            print(f"  note:           remote is {status['remote']}, not {url} — left as-is")
        if not gitignore.exists():
            gitignore.write_text(OVERLAY_GITIGNORE)
            print("  wrote:          .gitignore")
        return 0

    has_content = any(p.name != ".git" for p in USER_OVERLAY_DIR.iterdir())
    if not has_content:
        rc = subprocess.run(
            ["git", "clone", url, str(USER_OVERLAY_DIR)],
            capture_output=True,
            text=True,
        )
        if rc.returncode != 0:
            print(f"user overlay:     clone failed: {rc.stderr.strip()}")
            return 1
        print(f"user overlay:     cloned {url}")
        if not gitignore.exists():
            gitignore.write_text(OVERLAY_GITIGNORE)
            print("  wrote:          .gitignore (commit it when convenient)")
        return 0

    for args, label in (
        (["init"], "initialized"),
        (["remote", "add", "origin", url], f"remote origin -> {url}"),
    ):
        rc = subprocess.run(["git", *args], cwd=USER_OVERLAY_DIR, capture_output=True, text=True)
        if rc.returncode != 0:
            print(f"user overlay:     git {args[0]} failed: {rc.stderr.strip()}")
            return 1
        print(f"user overlay:     {label}")
    if not gitignore.exists():
        gitignore.write_text(OVERLAY_GITIGNORE)
        print("  wrote:          .gitignore")
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

    if overlay_repo:
        if _attach_overlay_repo(overlay_repo) != 0:
            return 1
        print()

    print("Installing flow at user level…")
    print()
    claude_result = sync_target("claude", check=False, user_mode=True)
    print()
    codex_result = sync_target("codex", check=False, user_mode=True)
    print()
    if claude_result != 0 or codex_result != 0:
        print("user-level setup completed with errors; review output above")
        return 1
    print("user-level setup complete")
    print("next: open a fresh Claude Code session anywhere and try `/flow-boot`")
    return 0


def refresh_project() -> int:
    root = repo_root()
    target = root / ".flow"
    if not target.exists():
        print("repo is missing .flow; run `flow setup project` first")
        return 1

    added = 0
    skipped = 0
    for item in SCAFFOLD_DIR.iterdir():
        item_added, item_skipped = sync_missing_tree(item, target / item.name)
        added += item_added
        skipped += item_skipped

    print(f"project refresh complete: {target}")
    print(f"added missing files: {added}")
    print(f"left existing files unchanged: {skipped}")
    return 0
