"""Two-mode install, release staging, and the update path.

flow installs one of two ways, and this module owns the conversion between
them. Develop mode points ~/.flow/source at a git clone via symlink; release
mode makes it a real directory of copied content. `flow install --release` and
`--develop` move between the two without ever deleting the clone.

This is the only layer that needs to know which mode a machine is in.
Everything downstream — sync, doctor, adapter generation — resolves through the
shared path contract `~/.flow/source/`, so the rest of the CLI is mode-agnostic.

Updating is deliberately staged rather than in-place: fetch the tag into a
staging directory, validate that it is a well-formed install, then swap it into
position with renames, restoring the old source if the swap fails. A partially
written ~/.flow/source is the one outcome worth real effort to avoid, because
the tool that would repair it lives inside it.

The one import from setup.py is `_ensure_usage_store`, called after a release
lands so a new schema version applies without waiting for the next
`flow setup machine`. Nothing in setup.py reaches back here.
"""

import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from flowtoml import read_toml
from fsutil import _remove_path, ensure_dir
from paths import (
    DEFAULT_REMOTE,
    FLOW_CONFIG,
    FLOW_HOME,
    INSTALL_MODE_DEVELOP,
    INSTALL_MODE_RELEASE,
    RELEASE_EXCLUDE_DIRS,
    RELEASE_EXCLUDE_FILE_PATTERNS,
    RELEASE_EXCLUDE_TOP_LEVEL,
    SEMVER_TAG_RE,
    SOURCE_DIR,
)
from setup import _ensure_usage_store
from sync import sync_target


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_git(*args: str, cwd: Path | None = None) -> tuple[int, str, str]:
    """Run git and return (returncode, stdout, stderr). Never raises on git failures."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", "git not found on PATH"
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def read_install_config() -> dict:
    """Return the `[install]` section of `~/.flow/config.toml`.

    If the section is missing (legacy installs that predate two-mode install),
    fall back to inspecting `~/.flow/source` and inferring mode.
    """
    if FLOW_CONFIG.exists():
        try:
            data = read_toml(FLOW_CONFIG)
        except Exception:
            data = {}
        install = data.get("install")
        if isinstance(install, dict) and install.get("mode"):
            return dict(install)

    # Inference fallback so legacy installs still report something useful.
    if SOURCE_DIR.is_symlink():
        try:
            target = SOURCE_DIR.resolve(strict=False)
        except OSError:
            target = SOURCE_DIR
        return {"mode": INSTALL_MODE_DEVELOP, "source_target": str(target)}
    if SOURCE_DIR.is_dir():
        return {"mode": INSTALL_MODE_RELEASE, "version": "unknown"}
    return {}


def write_install_config(install: dict) -> None:
    """Replace the `[install]` section, preserving any existing `[flow]` section."""
    flow_section: dict[str, str] = {
        "source_home": "~/.flow/source",
        "launcher": "~/.local/bin/flow",
    }
    if FLOW_CONFIG.exists():
        try:
            data = read_toml(FLOW_CONFIG)
        except Exception:
            data = {}
        existing_flow = data.get("flow")
        if isinstance(existing_flow, dict):
            for key, value in existing_flow.items():
                if isinstance(value, (str, int, bool)):
                    flow_section[key] = value

    ensure_dir(FLOW_CONFIG.parent)
    lines: list[str] = ["[flow]"]
    for key, value in flow_section.items():
        lines.append(f'{key} = "{value}"')
    lines.extend(["", "[install]"])
    # Stable key order keeps diffs readable.
    for key in ("mode", "version", "remote", "source_target", "installed_at"):
        if key in install:
            lines.append(f'{key} = "{install[key]}"')
    lines.append("")
    FLOW_CONFIG.write_text("\n".join(lines))


def install_mode() -> str:
    return read_install_config().get("mode", "unknown")


def _populate_release_dir(src_root: Path, dest_root: Path) -> None:
    """Copy `src_root` into `dest_root`, applying the release blacklist.

    Top-level entries are included by default. Excluded:
      - dotfiles / dot-dirs (anything whose name starts with `.`)
      - names listed in `RELEASE_EXCLUDE_TOP_LEVEL` (currently: tests/,
        install-flow.sh, install.sh)

    After the top-level copy, dev-only artifacts inside subdirectories
    (`__pycache__`, `.agents`, `.claude`, `.codex`, `.git`, `*.pyc`, `.DS_Store`) are
    cleaned up recursively.

    Blacklist semantics make the roster forward-compatible: any new top-level
    file added to the framework in a future version is automatically included
    in releases produced by *this* version of the code. See backlog P8 for the
    failure mode this design avoids.
    """
    ensure_dir(dest_root)
    for entry in sorted(src_root.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.name in RELEASE_EXCLUDE_TOP_LEVEL:
            continue
        target = dest_root / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target, symlinks=False)
        elif entry.is_file():
            shutil.copy2(entry, target)
        # silently skip anything else (symlinks pointing outside the tree, etc.)
    for excluded in RELEASE_EXCLUDE_DIRS:
        for path in list(dest_root.rglob(excluded)):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
    for pattern in RELEASE_EXCLUDE_FILE_PATTERNS:
        for path in list(dest_root.rglob(pattern)):
            try:
                path.unlink()
            except OSError:
                pass


def _resolve_version_from_clone(clone: Path) -> str:
    """Mirror install-flow.sh: prefer exact tag, then base-tag+dev, then main@sha."""
    rc, out, _ = _run_git("describe", "--tags", "--exact-match", "HEAD", cwd=clone)
    if rc == 0 and out:
        return out
    rc, base_tag, _ = _run_git("describe", "--tags", "--abbrev=0", cwd=clone)
    if rc == 0 and base_tag:
        _rc, sha, _ = _run_git("rev-parse", "--short", "HEAD", cwd=clone)
        return f"{base_tag}+dev.{sha or 'unknown'}"
    _rc, sha, _ = _run_git("rev-parse", "--short", "HEAD", cwd=clone)
    return f"main@{sha or 'unknown'}"


def _resolve_remote_from_clone(clone: Path) -> str:
    rc, out, _ = _run_git("config", "--get", "remote.origin.url", cwd=clone)
    if rc == 0 and out:
        return out
    return DEFAULT_REMOTE


def _semver_key(tag: str) -> tuple:
    """Sort key for semver-ish tags. Pre-release suffixes sort before plain tags of the same core."""
    match = SEMVER_TAG_RE.match(tag)
    if not match:
        return ((0, 0, 0), 1, tag)
    major, minor, patch = (int(g) for g in match.groups())
    # An unsuffixed tag (e.g. v1.2.3) should outrank a pre-release of the same core (v1.2.3-rc.1).
    has_suffix = 1 if ("-" in tag or "+" in tag.split("v", 1)[1]) else 0
    return ((major, minor, patch), 1 - has_suffix, tag)


def _latest_remote_tag(remote: str) -> tuple[str, str] | None:
    """Return (tag, sha) of the highest semver-ish tag on the remote, or None."""
    rc, stdout, _stderr = _run_git("ls-remote", "--tags", "--refs", remote)
    if rc != 0:
        return None
    candidates: list[tuple[str, str]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            sha, ref = line.split("\t", 1)
        except ValueError:
            continue
        tag = ref.removeprefix("refs/tags/")
        if SEMVER_TAG_RE.match(tag):
            candidates.append((tag, sha))
    if not candidates:
        return None
    candidates.sort(key=lambda item: _semver_key(item[0]))
    return candidates[-1]


def _extract_changelog_section(text: str, version: str) -> str | None:
    """Return the section for `## [<version>]` from a Keep-a-Changelog document.

    Matches the section header including version (with or without `v` prefix)
    and returns the header line plus the body up to the next `## ` or EOF.
    Returns None when the section isn't present.
    """
    needle = version.lstrip("v")
    pattern = re.compile(
        rf"^## \[{re.escape(needle)}\][^\n]*\n.*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    return match.group(0).rstrip()


def _fetch_changelog_at(remote: str, tag: str) -> str | None:
    """Fetch CHANGELOG.md from `remote` at `tag`. Returns the file's text, or None.

    Uses git's partial-clone + sparse-checkout to avoid downloading the whole
    repo just to read one file. Best effort — returns None on any failure
    (missing file, network error, unsupported git version, etc.) so the caller
    can fall back gracefully.
    """
    with tempfile.TemporaryDirectory(prefix="flow-changelog-") as tmp_str:
        clone_dir = Path(tmp_str) / "clone"
        # --filter=blob:none + --no-checkout + --sparse downloads metadata only;
        # we then check out just CHANGELOG.md.
        rc, _out, _err = _run_git(
            "clone",
            "--depth", "1",
            "--branch", tag,
            "--filter=blob:none",
            "--no-checkout",
            "--sparse",
            "--quiet",
            remote,
            str(clone_dir),
        )
        if rc != 0:
            return None
        rc, _out, _err = _run_git("sparse-checkout", "set", "CHANGELOG.md", cwd=clone_dir)
        if rc != 0:
            return None
        rc, _out, _err = _run_git("checkout", "--quiet", cwd=clone_dir)
        if rc != 0:
            return None
        changelog_path = clone_dir / "CHANGELOG.md"
        if not changelog_path.is_file():
            return None
        try:
            return changelog_path.read_text()
        except OSError:
            return None


def _stage_path(suffix: str) -> Path:
    return FLOW_HOME / f"source.{suffix}"


def _module_scope_imports(path: Path, stdlib: frozenset) -> list[str]:
    """Non-stdlib module names imported at module scope by one file.

    Parsed, never imported. The staged tree is freshly downloaded content, and
    running it to discover what it needs would be both circular and a poor idea.

    Only module-scope imports count. An import nested inside a function or a
    `try:`/`except ModuleNotFoundError:` guard is optional by construction — it
    is not what makes the CLI fail to start, which is the failure this check
    exists to catch.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        # A sibling that will not parse is a broken release, but not one this
        # function can describe — it reports which files are *absent*. The
        # entrypoint is checked separately by _validate_staging, where an
        # unparseable file becomes a rejection rather than an empty result.
        # UnicodeDecodeError subclasses ValueError; Python source is UTF-8 by
        # definition, so decode it that way rather than by locale.
        return []

    names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module.split(".")[0])
    return [n for n in dict.fromkeys(names) if n not in stdlib]


def _declared_sibling_imports(cli_entry: Path) -> list[str]:
    """Every sibling module a staged flow.py needs, following imports transitively.

    Transitive, not one level. flow.py imports four modules directly, but those
    four pull in paths, fsutil, render, and flowtoml. A release missing
    cli/paths.py would satisfy a direct-imports-only check and then die on the
    first command — the exact failure this validation exists to prevent, so
    stopping at depth one would leave the check looking thorough while missing
    most of the surface.

    Standard-library names are filtered via `sys.stdlib_module_names`, present
    on every interpreter flow supports (added in 3.10; the installer enforces
    3.10 as the floor). If it is somehow absent, the sibling check is skipped
    rather than guessed at: under-validating can only let a bad release through,
    while guessing could reject a good one.

    Modules that are named but absent are still reported. That is the point —
    the caller turns them into the rejection reason.

    This treats every non-stdlib module-scope import as a required sibling,
    which rests on cli/ having no third-party runtime dependencies. That is a
    real invariant of this CLI — it runs straight off ~/.flow/source with no
    virtualenv — and `test_cli_modules_import_only_stdlib_and_siblings` enforces
    it. Taking a runtime dependency without changing this check first would make
    every release after it unupdatable from an older client, because the code
    doing the rejecting is the old code. If flow ever needs one, this function
    has to learn about it in a release that ships *before* the dependency does.
    """
    stdlib = getattr(sys, "stdlib_module_names", None)
    if stdlib is None:
        return []

    cli_dir = cli_entry.parent
    required: list[str] = []
    seen = {cli_entry.stem}
    queue = _module_scope_imports(cli_entry, stdlib)

    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        required.append(name)
        candidate = cli_dir / f"{name}.py"
        if candidate.is_file():
            queue.extend(_module_scope_imports(candidate, stdlib))
    return required


def _validate_staging(staging: Path) -> str | None:
    """Return None when staging is well-formed, else a human-readable reason."""
    cli_entry = staging / "cli" / "flow.py"
    if not cli_entry.is_file():
        return f"staging is missing cli/flow.py at {cli_entry}"
    # An entrypoint that will not parse must be rejected, not tolerated. The
    # sibling walk returns an empty list for anything it cannot read, so without
    # this a truncated or corrupt flow.py would validate clean and get swapped
    # into ~/.flow/source — leaving the machine with no working flow, and the
    # tool that would repair it living inside the tree that just broke.
    try:
        ast.parse(cli_entry.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError) as err:
        return f"staged cli/flow.py does not parse: {err}"
    # flow.py imports its siblings at module scope, so a release that ships the
    # launcher without them installs cleanly and then fails on every command.
    # The required set is read out of the staged entrypoint itself rather than
    # from a roster maintained here: this code runs from the *old* install while
    # validating a *newer* tree, so any hand-kept list is by definition behind.
    # Same reasoning as the release roster's blacklist (see paths.py).
    for sibling in _declared_sibling_imports(cli_entry):
        sibling_path = staging / "cli" / f"{sibling}.py"
        if not sibling_path.is_file():
            return f"staging is missing cli/{sibling}.py at {sibling_path}"
    capabilities = staging / "data" / "harness_capabilities.json"
    if not capabilities.is_file():
        return f"staging is missing data/harness_capabilities.json at {capabilities}"
    scaffold_manifest = staging / "scaffolds" / "default" / "flow.toml"
    if not scaffold_manifest.is_file():
        return f"staging is missing scaffolds/default/flow.toml at {scaffold_manifest}"
    return None


def _swap_source_with_staging(staging: Path) -> str | None:
    """Atomically swap ~/.flow/source/ with staging. Returns None on success or an error string.

    Strategy: rename current source aside, then rename staging into place. On a
    rename-into-place failure we restore the old source so the user is never
    left without an install.
    """
    old_dir = _stage_path("old")
    # Symlink-aware cleanup — shutil.rmtree silently no-ops on symlinks (see _remove_path).
    _remove_path(old_dir)
    moved_existing = False
    if SOURCE_DIR.exists() or SOURCE_DIR.is_symlink():
        try:
            os.rename(SOURCE_DIR, old_dir)
            moved_existing = True
        except OSError as err:
            return f"could not move existing install aside: {err}"
    try:
        os.rename(staging, SOURCE_DIR)
    except OSError as err:
        if moved_existing:
            try:
                os.rename(old_dir, SOURCE_DIR)
            except OSError:
                return (
                    f"rename failed ({err}) and rollback failed; install is inconsistent. "
                    f"previous install at {old_dir}; staging at {staging}"
                )
        return f"rename failed: {err}"
    if moved_existing:
        # The renamed-aside entry may have been a symlink (develop→release case) — use
        # the symlink-aware helper so it actually gets cleaned up rather than silently leaked.
        _remove_path(old_dir)
    return None


def _print_resync_hint(prefix: str = "") -> None:
    if prefix:
        print(prefix)
    print("Re-sync user-level adapters to pick up any new commands, agents, or hooks:")
    print("  flow sync claude --user")
    print("  flow sync codex --user")


def install_command(release: bool, develop_path: str | None) -> int:
    if release and develop_path is not None:
        print("--release and --develop are mutually exclusive")
        return 2
    if release:
        return _convert_to_release()
    if develop_path is not None:
        clone = Path(develop_path).expanduser()
        try:
            clone = clone.resolve(strict=True)
        except FileNotFoundError:
            print(f"clone path does not exist: {develop_path}")
            return 1
        return _convert_to_develop(clone)
    print("flow install requires --release or --develop <clone-path>")
    return 2


def _convert_to_release() -> int:
    current = read_install_config()
    current_mode = current.get("mode", "unknown")
    if current_mode == INSTALL_MODE_RELEASE:
        print("install is already in release mode")
        print("to roll forward to a newer tag, run `flow update`")
        return 0

    if not SOURCE_DIR.is_symlink():
        print(f"{SOURCE_DIR} is not a symlink; nothing to convert")
        print("re-run install-flow.sh --release from a clone to install in release mode")
        return 1

    try:
        clone = SOURCE_DIR.resolve(strict=True)
    except FileNotFoundError:
        print(f"symlink at {SOURCE_DIR} points to a missing path; cannot convert")
        return 1

    print(f"converting develop -> release using clone at: {clone}")
    print("the clone will not be deleted; you can remove it yourself afterward")

    version = _resolve_version_from_clone(clone)
    remote = _resolve_remote_from_clone(clone)

    staging = _stage_path("new")
    _remove_path(staging)
    try:
        _populate_release_dir(clone, staging)
    except Exception as err:
        _remove_path(staging)
        print(f"failed to populate staging: {err}")
        return 1

    invalid = _validate_staging(staging)
    if invalid:
        _remove_path(staging)
        print(invalid)
        return 1

    swap_err = _swap_source_with_staging(staging)
    if swap_err:
        print(swap_err)
        return 1

    write_install_config(
        {
            "mode": INSTALL_MODE_RELEASE,
            "version": version,
            "remote": remote,
            "installed_at": _now_utc_iso(),
        }
    )
    print(f"converted to release mode (version: {version})")
    print(f"clone preserved at: {clone}")
    return 0


def _convert_to_develop(clone: Path) -> int:
    if not (clone / "cli" / "flow.py").is_file():
        print(f"path is not a flow checkout: {clone}")
        print("(expected to find cli/flow.py)")
        return 1

    current = read_install_config()
    if (
        current.get("mode") == INSTALL_MODE_DEVELOP
        and SOURCE_DIR.is_symlink()
    ):
        try:
            existing = SOURCE_DIR.resolve(strict=False)
        except OSError:
            existing = None
        if existing == clone:
            print(f"already in develop mode pointing at {clone}")
            return 0

    print(f"converting -> develop, symlink target: {clone}")

    # Replace the existing source — directory or symlink — with a symlink to the clone.
    if SOURCE_DIR.is_symlink() or SOURCE_DIR.is_file():
        try:
            SOURCE_DIR.unlink()
        except OSError as err:
            print(f"could not remove existing source link: {err}")
            return 1
    elif SOURCE_DIR.is_dir():
        shutil.rmtree(SOURCE_DIR, ignore_errors=True)

    try:
        os.symlink(str(clone), str(SOURCE_DIR))
    except OSError as err:
        print(f"could not create symlink: {err}")
        return 1

    write_install_config(
        {
            "mode": INSTALL_MODE_DEVELOP,
            "source_target": str(clone),
            "installed_at": _now_utc_iso(),
        }
    )
    print(f"converted to develop mode (source: {clone})")
    return 0


def update_command(check: bool, resync: bool, remote_override: str | None) -> int:
    install = read_install_config()
    mode = install.get("mode", "unknown")

    if mode == INSTALL_MODE_DEVELOP:
        target = install.get("source_target", "<clone>")
        print("develop install — flow update does not apply.")
        print("To roll forward in develop mode, pull and re-sync manually:")
        print(f"  git -C {target} pull --ff-only")
        print("  flow sync claude --user")
        print("  flow sync codex --user")
        return 0

    if mode != INSTALL_MODE_RELEASE:
        print(f"install mode is {mode!r}; cannot run flow update")
        print("re-run install-flow.sh to stamp install metadata, then try again")
        return 1

    current_version = install.get("version", "unknown")
    remote = remote_override or install.get("remote") or DEFAULT_REMOTE

    print(f"current: {current_version}")
    print(f"remote:  {remote}")

    latest = _latest_remote_tag(remote)
    if latest is None:
        print("could not determine latest tag (no semver tags found, or remote unreachable)")
        return 1

    latest_tag, _latest_sha = latest
    print(f"latest:  {latest_tag}")

    if latest_tag == current_version:
        print("already at the latest tag")
        return 0

    if check:
        print(f"update available: {current_version} -> {latest_tag}")
        # Best-effort preview of what's in the available version: fetch
        # CHANGELOG.md from the remote at `latest_tag` and print the section
        # for that version. Failure is silent — the version comparison is the
        # primary signal and shouldn't be blocked by changelog issues.
        changelog_text = _fetch_changelog_at(remote, latest_tag)
        if changelog_text:
            section = _extract_changelog_section(changelog_text, latest_tag)
            if section:
                print()
                print(section)
        return 0

    apply_rc = _apply_release_update(remote, latest_tag, install)
    if apply_rc != 0:
        return apply_rc

    # Create-if-missing, not just migrate. A machine that ran `setup machine`
    # before the store existed will never re-run it in a state where the store
    # is absent, so without this an existing install never gets one.
    print()
    _ensure_usage_store()

    if resync:
        print()
        claude_rc = sync_target("claude", check=False, user_mode=True)
        codex_rc = sync_target("codex", check=False, user_mode=True)
        if claude_rc != 0 or codex_rc != 0:
            print("re-sync completed with errors; review output above")
            return 1
    else:
        print()
        _print_resync_hint()
    return 0


def _apply_release_update(remote: str, tag: str, install: dict) -> int:
    print(f"fetching {tag} from {remote}…")
    with tempfile.TemporaryDirectory(prefix="flow-update-") as tmp_str:
        clone_dir = Path(tmp_str) / "clone"
        rc, _out, stderr = _run_git(
            "clone", "--depth", "1", "--branch", tag, remote, str(clone_dir)
        )
        if rc != 0:
            print("git clone failed:")
            if stderr:
                print(stderr)
            return 1

        staging = _stage_path("new")
        _remove_path(staging)
        try:
            _populate_release_dir(clone_dir, staging)
        except Exception as err:
            _remove_path(staging)
            print(f"failed to populate staging: {err}")
            return 1

        invalid = _validate_staging(staging)
        if invalid:
            _remove_path(staging)
            print(invalid)
            return 1

        swap_err = _swap_source_with_staging(staging)
        if swap_err:
            print(swap_err)
            return 1

    new_install = dict(install)
    new_install["mode"] = INSTALL_MODE_RELEASE
    new_install["version"] = tag
    new_install["remote"] = remote
    new_install["installed_at"] = _now_utc_iso()
    write_install_config(new_install)

    print(f"updated to {tag}")
    return 0
