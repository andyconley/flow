#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

# Sibling modules. The launcher runs cli/flow.py directly, which puts cli/ on
# sys.path — but importing this file programmatically (importlib, as the test
# suite does) does not. Append our own directory so the import holds either way.
# Appended rather than prepended so stdlib still wins on any name collision.
sys.path.append(str(Path(__file__).resolve().parent))

# Constants come in by name rather than as `paths.X` so that every function body
# below stays byte-identical to its pre-split form. That is what lets the
# CLI-boundary test suite stand as proof the split changed no behavior.
from paths import (  # noqa: E402 — must follow the sys.path append above
    CLI_REQUIRED_SIBLINGS,
    CODEX_SKILL_DIR,
    DEFAULT_REMOTE,
    FLOW_CONFIG,
    FLOW_HOME,
    GENERATED_MARKER,
    HOME,
    INSTALL_MODE_DEVELOP,
    INSTALL_MODE_RELEASE,
    LEGACY_CODEX_SKILL_DIR,
    MODE_PROJECT,
    MODE_USER,
    RELEASE_EXCLUDE_DIRS,
    RELEASE_EXCLUDE_FILE_PATTERNS,
    RELEASE_EXCLUDE_TOP_LEVEL,
    SCAFFOLD_DIR,
    SEMVER_TAG_RE,
    SOURCE_DIR,
    USER_BIN_DIR,
    USER_OVERLAY_DIR,
)
from flowtoml import read_toml  # noqa: E402
from fsutil import (  # noqa: E402
    _remove_path,
    copy_if_missing,
    ensure_dir,
    ensure_file,
    read_json,
    rel_posix,
    remove_empty_parents,
    repo_root,
    sync_missing_tree,
)
import usage_store  # noqa: E402 — must follow the sys.path append above


def hook_command_for(mode: str, script: str) -> str:
    """Return the absolute hook command path for a given sync mode."""
    if mode == MODE_USER:
        return f'"$HOME"/.claude/hooks/{script}'
    return f'"$CLAUDE_PROJECT_DIR"/.claude/hooks/{script}'


def source_ref_for(mode: str, source_rel: str, origin: str = "framework") -> str:
    """Return the source-of-truth reference string used in managed manifests.

    `origin` is "framework" for entries from `scaffolds/default/flow.toml` and
    "user" for entries that came from the `~/.flow/user/` user overlay (see
    `merge_user_overlay`). The reference path differs so a reader of the
    managed manifest can tell at a glance which entries are user-customized.
    """
    if mode == MODE_USER:
        if origin == "user":
            return f'~/.flow/user/{source_rel}'
        return f'~/.flow/source/scaffolds/default/{source_rel}'
    return f'.flow/{source_rel}'


def manifest_ref_for(mode: str, manifest_path: Path, root: Path) -> str:
    """Return the source_manifest reference used in managed manifests."""
    if mode == MODE_USER:
        return '~/.flow/source/scaffolds/default/flow.toml'
    return rel_posix(manifest_path, root)


def render_skill(name: str, description: str, source_path: str, body: str) -> str:
    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
        "---",
        "",
        f"<!-- {GENERATED_MARKER} Edit `.flow/{source_path}` and run `flow sync claude`. -->",
        "",
        body.rstrip(),
        "",
        "## Invocation Arguments",
        "",
        "If arguments were provided after the skill name, treat them as the specific focus for this run:",
        "",
        "`$ARGUMENTS`",
        "",
    ]
    return "\n".join(lines)


def render_codex_skill(name: str, description: str, source_path: str, body: str) -> str:
    lines = [
        "---",
        f"name: {name}",
        f"description: {json.dumps(description)}",
        "---",
        "",
        f"<!-- {GENERATED_MARKER} Edit `.flow/{source_path}` and rerun `flow sync codex`. -->",
        "",
        body.rstrip(),
        "",
        "## Invocation Arguments",
        "",
        "If arguments were provided after the skill name, treat them as the specific focus for this run:",
        "",
        "`$ARGUMENTS`",
        "",
    ]
    return "\n".join(lines)


def codex_skill_dir(runtime: dict) -> Path:
    """Return the current Codex skill directory, migrating legacy manifests."""
    configured = runtime.get("skill_dir", CODEX_SKILL_DIR)
    if configured == LEGACY_CODEX_SKILL_DIR:
        return Path(CODEX_SKILL_DIR)
    return Path(configured)


def build_skill_frontmatter(name: str, command: dict, skill_defaults: dict) -> list[str]:
    frontmatter = {
        "name": name,
        "description": command["description"],
    }

    merged = dict(skill_defaults)
    merged.update(command)

    field_map = [
        ("when_to_use", "when-to-use"),
        ("argument_hint", "argument-hint"),
        ("disable_model_invocation", "disable-model-invocation"),
        ("user_invocable", "user-invocable"),
        ("allowed_tools", "allowed-tools"),
        ("model", "model"),
        ("effort", "effort"),
        ("context", "context"),
        ("agent", "agent"),
    ]
    for source_key, target_key in field_map:
        if source_key in merged:
            frontmatter[target_key] = merged[source_key]

    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return lines


def render_skill_from_command(command: dict, skill_defaults: dict) -> str:
    source_path = command["source"]
    body = command["_body"]
    lines = build_skill_frontmatter(command["name"], command, skill_defaults)
    lines.extend(
        [
            "",
            f"<!-- {GENERATED_MARKER} Edit `.flow/{source_path}` and run `flow sync claude`. -->",
            "",
            body.rstrip(),
            "",
            "## Invocation Arguments",
            "",
            "If arguments were provided after the skill name, treat them as the specific focus for this run:",
            "",
            "`$ARGUMENTS`",
            "",
        ]
    )
    return "\n".join(lines)


def insert_generated_marker(source_path: str, body: str) -> str:
    marker = f"<!-- {GENERATED_MARKER} Edit `.flow/{source_path}` and run `flow sync claude`. -->"
    if body.startswith("---\n"):
        closing = body.find("\n---\n", 4)
        if closing != -1:
            insert_at = closing + 5
            return body[:insert_at] + "\n" + marker + "\n" + body[insert_at:].lstrip("\n")
    return marker + "\n\n" + body


def build_managed_manifest(target_name: str, entries: list[dict]) -> str:
    lines = [
        "[managed]",
        'generator = "flow"',
        "version = 2",
        f'target = "{target_name}"',
        'source_manifest = ".flow/flow.toml"',
        'preserve_unmanaged = true',
        "",
    ]
    for entry in entries:
        lines.extend(
            [
                "[[files]]",
                f'path = "{entry["path"]}"',
                f'kind = "{entry["kind"]}"',
                f'source = "{entry["source"]}"',
                f'sync_mode = "{entry["sync_mode"]}"',
                "",
            ]
        )
    return "\n".join(lines)


def read_managed_paths(root: Path, path: Path) -> set[Path]:
    if not path.exists():
        return set()
    data = read_toml(path)
    files = data.get("files", [])
    return {root / entry["path"] for entry in files if "path" in entry}


def load_flow_manifest(flow_dir: Path) -> tuple[Path, dict]:
    manifest_path = flow_dir / "flow.toml"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    return manifest_path, read_toml(manifest_path)


def _tag_entries(entries: list, root: Path, origin: str) -> None:
    """Annotate command/agent entries with their source root and origin."""
    for entry in entries:
        entry["_root"] = root
        entry["_origin"] = origin


def merge_user_overlay(framework_dir: Path) -> tuple[Path, dict]:
    """Load the framework manifest and merge in `~/.flow/user/flow.toml` if it exists.

    Each `[[claude.commands]]`, `[[claude.agents]]`, and `[[codex.commands]]`
    entry in the returned manifest carries two synthetic fields:

      `_root`   — Path the entry's `source` field is relative to
                  (either `framework_dir` or `USER_OVERLAY_DIR`)
      `_origin` — "framework" or "user"

    Merge rules:
      - User entries with the same `name` as a framework entry **replace** that
        entry in-place (override), preserving order.
      - User entries with a new `name` are **appended** (addition).

    User-overlay support is intentionally scoped to commands and agents — the
    embedded surfaces. Standards and templates are *referenced* by name at
    runtime; user customization for those follows the resolution-order
    convention documented in `FRAMEWORK.md` (project overlay > user overlay >
    framework default), not this merge step.
    """
    framework_manifest_path = framework_dir / "flow.toml"
    if not framework_manifest_path.exists():
        raise FileNotFoundError(f"missing manifest: {framework_manifest_path}")
    manifest = read_toml(framework_manifest_path)

    if "claude" in manifest:
        _tag_entries(manifest["claude"].get("commands", []), framework_dir, "framework")
        _tag_entries(manifest["claude"].get("agents", []), framework_dir, "framework")
    if "codex" in manifest:
        _tag_entries(manifest["codex"].get("commands", []), framework_dir, "framework")

    user_manifest_path = USER_OVERLAY_DIR / "flow.toml"
    if not user_manifest_path.exists():
        return framework_manifest_path, manifest

    try:
        user_manifest = read_toml(user_manifest_path)
    except Exception as err:
        sys.stderr.write(
            f"warning: failed to parse user overlay {user_manifest_path}: {err}\n"
            "proceeding with framework-only manifest\n"
        )
        return framework_manifest_path, manifest

    def merge_named(framework_list: list, user_list: list) -> list:
        if not user_list:
            return framework_list
        _tag_entries(user_list, USER_OVERLAY_DIR, "user")
        result = list(framework_list)
        framework_by_name = {entry.get("name"): idx for idx, entry in enumerate(result) if "name" in entry}
        for entry in user_list:
            name = entry.get("name")
            if name and name in framework_by_name:
                result[framework_by_name[name]] = entry
            else:
                result.append(entry)
        return result

    if "claude" in manifest:
        manifest["claude"]["commands"] = merge_named(
            manifest["claude"].get("commands", []),
            user_manifest.get("claude", {}).get("commands", []),
        )
        manifest["claude"]["agents"] = merge_named(
            manifest["claude"].get("agents", []),
            user_manifest.get("claude", {}).get("agents", []),
        )
    if "codex" in manifest:
        manifest["codex"]["commands"] = merge_named(
            manifest["codex"].get("commands", []),
            user_manifest.get("codex", {}).get("commands", []),
        )

    return framework_manifest_path, manifest


def remove_managed_flow_hooks(settings: dict) -> dict:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings

    cleaned_events: dict[str, list] = {}
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        cleaned_groups = []
        for group in groups:
            handlers = group.get("hooks", [])
            kept_handlers = []
            for handler in handlers:
                command = handler.get("command", "")
                if handler.get("type") == "command" and "/.claude/hooks/flow-" in command:
                    continue
                kept_handlers.append(handler)
            if kept_handlers:
                updated = dict(group)
                updated["hooks"] = kept_handlers
                cleaned_groups.append(updated)
        if cleaned_groups:
            cleaned_events[event] = cleaned_groups

    if cleaned_events:
        settings["hooks"] = cleaned_events
    else:
        settings.pop("hooks", None)
    return settings


def build_claude_settings(root: Path, runtime: dict, mode: str = MODE_PROJECT) -> str:
    settings_path = root / runtime["settings_file"]
    settings = remove_managed_flow_hooks(read_json(settings_path))
    hooks = settings.setdefault("hooks", {})

    for hook in runtime.get("hooks", []):
        event = hook["event"]
        groups = hooks.setdefault(event, [])
        groups.append(
            {
                "matcher": hook["matcher"],
                "hooks": [
                    {
                        "type": hook["type"],
                        "command": hook_command_for(mode, hook["script"]),
                    }
                ],
            }
        )

    return json.dumps(settings, indent=2, sort_keys=True) + "\n"


def desired_claude_outputs(
    root: Path, flow_dir: Path, manifest: dict, manifest_rel: str, mode: str = MODE_PROJECT
) -> tuple[dict[Path, str], list[dict], set[Path]]:
    runtime = manifest["claude"]
    skill_defaults = runtime.get("skill_defaults", {})
    agent_defaults = runtime.get("agent_defaults", {})
    outputs: dict[Path, str] = {}
    managed_entries: list[dict] = []
    mergeable_paths: set[Path] = set()

    for command in runtime.get("commands", []):
        source_rel = command["source"]
        entry_root = command.get("_root", flow_dir)
        entry_origin = command.get("_origin", "framework")
        source_path = entry_root / source_rel
        target = root / runtime["skill_dir"] / command["name"] / "SKILL.md"
        command_with_body = dict(command)
        command_with_body["_body"] = source_path.read_text()
        content = render_skill_from_command(command_with_body, skill_defaults)
        outputs[target] = content
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "skill",
                "source": source_ref_for(mode, source_rel, entry_origin),
                "sync_mode": "replace",
            }
        )

    for agent in runtime.get("agents", []):
        source_rel = agent["source"]
        entry_root = agent.get("_root", flow_dir)
        entry_origin = agent.get("_origin", "framework")
        source_path = entry_root / source_rel
        target = root / runtime["agent_dir"] / f'{agent["name"]}.md'
        generation_mode = agent.get("generation_mode", agent_defaults.get("generation_mode", "verbatim"))
        if generation_mode != "verbatim":
            raise ValueError(f"unsupported agent generation mode: {generation_mode}")
        content = insert_generated_marker(source_rel, source_path.read_text())
        outputs[target] = content
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "agent",
                "source": source_ref_for(mode, source_rel, entry_origin),
                "sync_mode": "replace",
            }
        )

    for hook in runtime.get("hooks", []):
        source = SOURCE_DIR / "hooks" / hook["script"]
        target = root / runtime["hook_dir"] / hook["script"]
        content = source.read_text()
        outputs[target] = content
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "hook-script",
                "source": f'flow/hooks/{hook["script"]}',
                "sync_mode": "replace",
            }
        )

    settings_path = root / runtime["settings_file"]
    outputs[settings_path] = build_claude_settings(root, runtime, mode)
    mergeable_paths.add(settings_path)
    managed_entries.append(
        {
            "path": rel_posix(settings_path, root),
            "kind": "settings",
            "source": manifest_rel,
            "sync_mode": "merge",
        }
    )

    managed_manifest_path = root / runtime["managed_manifest"]
    outputs[managed_manifest_path] = build_managed_manifest("claude", managed_entries)
    managed_entries.append(
        {
            "path": rel_posix(managed_manifest_path, root),
            "kind": "managed-manifest",
            "source": manifest_rel,
            "sync_mode": "replace",
        }
    )
    outputs[managed_manifest_path] = build_managed_manifest("claude", managed_entries)
    return outputs, managed_entries, mergeable_paths


def desired_codex_outputs(
    root: Path, flow_dir: Path, manifest: dict, manifest_rel: str, mode: str = MODE_PROJECT
) -> tuple[dict[Path, str], list[dict], set[Path]]:
    runtime = manifest["codex"]
    outputs: dict[Path, str] = {}
    managed_entries: list[dict] = []
    mergeable_paths: set[Path] = set()

    for command in runtime.get("commands", []):
        source_rel = command["source"]
        entry_root = command.get("_root", flow_dir)
        entry_origin = command.get("_origin", "framework")
        source_path = entry_root / source_rel
        target = root / codex_skill_dir(runtime) / command["name"] / "SKILL.md"
        outputs[target] = render_codex_skill(
            command["name"], command["description"], source_rel, source_path.read_text()
        )
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "skill",
                "source": source_ref_for(mode, source_rel, entry_origin),
                "sync_mode": "replace",
            }
        )

    managed_manifest_path = root / runtime["managed_manifest"]
    outputs[managed_manifest_path] = build_managed_manifest("codex", managed_entries)
    managed_entries.append(
        {
            "path": rel_posix(managed_manifest_path, root),
            "kind": "managed-manifest",
            "source": manifest_rel,
            "sync_mode": "replace",
        }
    )
    outputs[managed_manifest_path] = build_managed_manifest("codex", managed_entries)
    return outputs, managed_entries, mergeable_paths


def analyze_sync(
    desired: dict[Path, str], previous_managed: set[Path], mergeable_paths: set[Path]
) -> tuple[list[Path], list[Path], list[Path]]:
    desired_paths = set(desired)
    conflicts: list[Path] = []
    changed: list[Path] = []

    for target, content in desired.items():
        if target.exists():
            current = target.read_text()
            if current == content:
                continue
            if (
                target not in previous_managed
                and target not in mergeable_paths
                and GENERATED_MARKER not in current
            ):
                conflicts.append(target)
                continue
        changed.append(target)

    stale = [path for path in previous_managed if path not in desired_paths and path.exists()]
    return conflicts, changed, stale


def runtime_status(
    root: Path, flow_dir: Path, manifest_path: Path, manifest: dict, target: str, mode: str = MODE_PROJECT
) -> tuple[str, bool]:
    runtime = manifest.get(target)
    if not isinstance(runtime, dict):
        return "n/a", False

    managed_path = root / runtime["managed_manifest"]
    managed_ok = managed_path.exists()
    try:
        previous_managed = read_managed_paths(root, managed_path)
        desired, _managed_entries, mergeable_paths = desired_outputs_for_target(
            target, root, flow_dir, manifest, manifest_ref_for(mode, manifest_path, root), mode
        )
        conflicts, changed, stale = analyze_sync(desired, previous_managed, mergeable_paths)
        if conflicts:
            return "conflict", managed_ok
        if changed or stale:
            return "stale", managed_ok
        return "clean", managed_ok
    except Exception:
        return "error", managed_ok


def sync_outputs(
    root: Path,
    target_name: str,
    desired: dict[Path, str],
    previous_managed: set[Path],
    mergeable_paths: set[Path],
    check: bool,
) -> int:
    conflicts, changed, stale = analyze_sync(desired, previous_managed, mergeable_paths)
    removed: list[Path] = []

    if conflicts:
        print("sync claude found unmanaged conflicts:")
        for path in conflicts:
            print(f"- {path}")
        print("resolve them manually or move the source of truth into `.flow/` first")
        return 1

    if check:
        if not changed and not stale:
            print(f"{target_name} sync check: up to date")
            return 0
        print(f"{target_name} sync check: drift detected")
        for path in changed:
            print(f"- update: {path}")
        for path in stale:
            print(f"- remove: {path}")
        return 1

    for path in stale:
        path.unlink()
        remove_empty_parents(path, root)
        removed.append(path)

    for target, content in desired.items():
        ensure_dir(target.parent)
        if not target.exists() or target.read_text() != content:
            target.write_text(content)
        if target.suffix == ".sh":
            target.chmod(0o755)

    print(f"{target_name} sync wrote managed files:")
    for path in changed:
        print(f"- {path}")
    for path in removed:
        print(f"- removed: {path}")
    if not changed and not removed:
        print("- no changes needed")
    return 0


def desired_outputs_for_target(
    target: str, root: Path, flow_dir: Path, manifest: dict, manifest_rel: str, mode: str = MODE_PROJECT
) -> tuple[dict[Path, str], list[dict], set[Path]]:
    if target == "claude":
        return desired_claude_outputs(root, flow_dir, manifest, manifest_rel, mode)
    if target == "codex":
        return desired_codex_outputs(root, flow_dir, manifest, manifest_rel, mode)
    raise ValueError(f"unsupported sync target: {target}")


# ---------------------------------------------------------------------------
# Install-mode helpers
#
# The install layer is the only code that needs to know which mode a machine is
# in. Everything downstream (sync, doctor, adapter generation) resolves through
# the shared path contract `~/.flow/source/`, so the rest of the CLI is
# mode-agnostic.
# ---------------------------------------------------------------------------


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
    (`__pycache__`, `.claude`, `.codex`, `.git`, `*.pyc`, `.DS_Store`) are
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


def _validate_staging(staging: Path) -> str | None:
    """Return None when staging is well-formed, else a human-readable reason."""
    cli_entry = staging / "cli" / "flow.py"
    if not cli_entry.is_file():
        return f"staging is missing cli/flow.py at {cli_entry}"
    # flow.py imports its siblings at module scope, so a release that ships the
    # launcher without them installs cleanly and then fails on every command.
    # Validate the whole cli/ surface, not just the entrypoint.
    for sibling in CLI_REQUIRED_SIBLINGS:
        sibling_path = staging / "cli" / sibling
        if not sibling_path.is_file():
            return f"staging is missing cli/{sibling} at {sibling_path}"
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


def setup_user() -> int:
    """Install flow at the user level: generate ~/.claude/ surfaces from the framework scaffold."""
    if not FLOW_HOME.exists():
        print("flow home missing; run `flow setup machine` first")
        return 1
    if not SCAFFOLD_DIR.exists():
        print("framework scaffold missing; re-run install-flow.sh from the flow repo")
        return 1

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


def doctor() -> int:
    root = repo_root()
    flow_dir = root / ".flow"
    project_manifest_ok = (flow_dir / "flow.toml").exists()
    skills_dir = root / ".claude" / "skills"
    agents_dir = root / ".claude" / "agents"
    claude_managed_ok = False
    claude_drift = "n/a"
    codex_skills_dir = root / CODEX_SKILL_DIR
    codex_managed_ok = False
    codex_drift = "n/a"

    if project_manifest_ok:
        try:
            manifest_path, manifest = load_flow_manifest(flow_dir)
            claude_drift, claude_managed_ok = runtime_status(
                root, flow_dir, manifest_path, manifest, "claude", MODE_PROJECT
            )
            codex_drift, codex_managed_ok = runtime_status(
                root, flow_dir, manifest_path, manifest, "codex", MODE_PROJECT
            )
            codex_skills_dir = root / codex_skill_dir(manifest["codex"])
        except Exception:
            claude_drift = "error"
            codex_drift = "error"

    user_claude_managed_ok = False
    user_claude_drift = "n/a"
    user_codex_managed_ok = False
    user_codex_drift = "n/a"
    user_skills_dir = HOME / ".claude" / "skills"
    user_agents_dir = HOME / ".claude" / "agents"
    user_codex_skills_dir = HOME / CODEX_SKILL_DIR
    if SCAFFOLD_DIR.exists():
        try:
            user_manifest_path, user_manifest = merge_user_overlay(SCAFFOLD_DIR)
            user_claude_drift, user_claude_managed_ok = runtime_status(
                HOME, SCAFFOLD_DIR, user_manifest_path, user_manifest, "claude", MODE_USER
            )
            user_codex_drift, user_codex_managed_ok = runtime_status(
                HOME, SCAFFOLD_DIR, user_manifest_path, user_manifest, "codex", MODE_USER
            )
            user_codex_skills_dir = HOME / codex_skill_dir(user_manifest["codex"])
        except Exception:
            user_claude_drift = "error"
            user_codex_drift = "error"

    print(f"python:           {sys.executable}")
    print(f"flow home:        {FLOW_HOME}")
    print(f"source:           {SOURCE_DIR}")
    print(f"scaffold:         {'ok' if SCAFFOLD_DIR.exists() else 'missing'}")
    print(f"config:           {'ok' if FLOW_CONFIG.exists() else 'missing'}")
    print(f"launcher:         {'ok' if (USER_BIN_DIR / 'flow').exists() else 'missing'}")
    # Read-only. doctor never creates or migrates the store: repairing the
    # condition being reported would make the absent and stale states
    # unobservable. `flow setup machine` is the repair path.
    store_status = usage_store.store_status(usage_store.default_store_path(HOME))
    print(f"usage store:      {usage_store.format_status(store_status)}")
    print()
    print("-- install --")
    install = read_install_config()
    mode = install.get("mode", "unknown")
    print(f"mode:             {mode}")
    if mode == INSTALL_MODE_RELEASE:
        print(f"version:          {install.get('version', 'unknown')}")
        print(f"remote:           {install.get('remote', DEFAULT_REMOTE)}")
    elif mode == INSTALL_MODE_DEVELOP:
        print(f"source target:    {install.get('source_target', '(unknown)')}")
    if install.get("installed_at"):
        print(f"installed at:     {install['installed_at']}")
    if mode == INSTALL_MODE_RELEASE:
        print("update check:     run `flow update --check` to query the remote")
    elif mode == INSTALL_MODE_DEVELOP:
        print("update check:     n/a (develop install — pull the clone manually)")
    else:
        print("note:             install metadata missing; re-run install-flow.sh to stamp")
    print()
    print("-- user-level (active in every Claude session) --")
    print(f"claude sync:      {'ok' if user_claude_managed_ok else 'missing'}")
    print(f"claude drift:     {user_claude_drift}")
    print(f"skills dir:       {'ok' if user_skills_dir.exists() else 'missing'}")
    print(f"agents dir:       {'ok' if user_agents_dir.exists() else 'missing'}")
    print(f"codex sync:       {'ok' if user_codex_managed_ok else 'missing'}")
    print(f"codex drift:      {user_codex_drift}")
    print(f"codex skills:     {'ok' if user_codex_skills_dir.exists() else 'missing'}")

    # User overlay: report whether ~/.flow/user/flow.toml is present and what it
    # declares. Customizations apply at sync time via merge_user_overlay.
    user_overlay_manifest = USER_OVERLAY_DIR / "flow.toml"
    if user_overlay_manifest.exists():
        try:
            overlay = read_toml(user_overlay_manifest)
            user_commands = overlay.get("claude", {}).get("commands", [])
            user_agents = overlay.get("claude", {}).get("agents", [])
            print(f"user overlay:     {user_overlay_manifest}")
            if user_commands:
                names = ", ".join(c.get("name", "<unnamed>") for c in user_commands)
                print(f"  commands:       {len(user_commands)} ({names})")
            if user_agents:
                names = ", ".join(a.get("name", "<unnamed>") for a in user_agents)
                print(f"  agents:         {len(user_agents)} ({names})")
            if not user_commands and not user_agents:
                print("  entries:        (manifest present but declares no commands or agents)")
        except Exception as err:
            print(f"user overlay:     {user_overlay_manifest} (parse error: {err})")
    else:
        print(f"user overlay:     none ({user_overlay_manifest} absent)")
    print()
    print(f"-- project: {root} --")
    print(f"repo .flow:       {'ok' if flow_dir.exists() else 'missing'}")
    print(f"manifest:         {'ok' if project_manifest_ok else 'missing'}")
    print(f"claude sync:      {'ok' if claude_managed_ok else 'missing'}")
    print(f"claude drift:     {claude_drift}")
    print(f"skills dir:       {'ok' if skills_dir.exists() else 'missing'}")
    print(f"agents dir:       {'ok' if agents_dir.exists() else 'missing'}")
    print(f"codex sync:       {'ok' if codex_managed_ok else 'missing'}")
    print(f"codex drift:      {codex_drift}")
    print(f"codex skills:     {'ok' if codex_skills_dir.exists() else 'missing'}")
    return 0


def help_command() -> int:
    """Render the framework overview (same content as the `/flow-help` slash command).

    Reads the rendered output block from scaffolds/default/commands/flow-help.md
    so the CLI and slash-command surfaces stay in lockstep.
    """
    help_source = SCAFFOLD_DIR / "commands" / "flow-help.md"
    if not help_source.exists():
        print(f"help source missing: {help_source}")
        print("re-run install-flow.sh or check that ~/.flow/source resolves correctly")
        return 1

    text = help_source.read_text()
    fence_open = "```md\n"
    fence_close = "```"
    start = text.find(fence_open)
    if start == -1:
        print("could not locate rendered help block in flow-help.md")
        return 1
    body_start = start + len(fence_open)
    end = text.find(fence_close, body_start)
    if end == -1:
        print("could not locate end of rendered help block")
        return 1
    print(text[body_start:end].rstrip())
    return 0


def bootstrap() -> int:
    root = repo_root()
    flow_dir = root / ".flow"
    if not flow_dir.exists():
        print("repo is missing .flow; run `flow setup project` first")
        return 1

    required = [
        flow_dir / "flow.toml",
        flow_dir / "FRAMEWORK.md",
        flow_dir / "PROJECT.md",
        flow_dir / "commands",
        flow_dir / "agents",
        flow_dir / "standards",
        flow_dir / "project",
        flow_dir / "memory",
        flow_dir / "templates",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("bootstrap found missing framework paths:")
        for path in missing:
            print(f"- {path}")
        return 1

    print(f"bootstrap ok: {flow_dir}")
    print("next: run `flow doctor` or `flow sync claude`")
    return 0


def sync_target(target: str, check: bool = False, user_mode: bool = False) -> int:
    if user_mode:
        root = HOME
        flow_dir = SCAFFOLD_DIR
        if not flow_dir.exists():
            print("framework scaffold missing; re-run install-flow.sh first")
            return 1
        scope_label = "user-level"
    else:
        root = repo_root()
        flow_dir = root / ".flow"
        if not flow_dir.exists():
            print("repo is missing .flow; run `flow setup project` first")
            return 1
        scope_label = "project"

    try:
        if user_mode:
            # User mode reads the framework scaffold and layers in
            # ~/.flow/user/flow.toml if present.
            manifest_path, manifest = merge_user_overlay(flow_dir)
        else:
            manifest_path, manifest = load_flow_manifest(flow_dir)
    except FileNotFoundError as err:
        print(str(err))
        return 1

    runtime = manifest.get(target)
    if not isinstance(runtime, dict):
        location = "scaffold flow.toml" if user_mode else ".flow/flow.toml"
        print(f"sync target is not configured in {location}: {target}")
        return 1

    mode = MODE_USER if user_mode else MODE_PROJECT
    previous_managed = read_managed_paths(root, root / runtime["managed_manifest"])
    desired, _managed_entries, mergeable_paths = desired_outputs_for_target(
        target, root, flow_dir, manifest, manifest_ref_for(mode, manifest_path, root), mode
    )
    result = sync_outputs(root, target, desired, previous_managed, mergeable_paths, check=check)
    if result == 0:
        verb = "check" if check else "sync"
        print(f"{scope_label} {target} {verb} complete from {manifest_path}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="flow",
        description="Portable AI workflow framework CLI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Common examples:\n"
            "  flow help                          (framework overview)\n"
            "  flow setup machine\n"
            "  flow setup user                    (install at user level)\n"
            "  flow setup project                 (per-repo overlay)\n"
            "  flow bootstrap\n"
            "  flow sync claude\n"
            "  flow sync codex --check\n"
            "  flow doctor\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, title="commands")

    setup = sub.add_parser(
        "setup",
        help="prepare the machine install or scaffold .flow into the current repo",
        description="Prepare machine-local flow support or scaffold the project-local .flow source of truth.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  flow setup machine\n"
            "  flow setup project\n"
        ),
    )
    setup_sub = setup.add_subparsers(dest="setup_target", required=True, title="setup targets")
    setup_sub.add_parser(
        "machine",
        help="create ~/.flow support directories, config, and launcher expectations",
        description="Create the machine-local flow home, config, and support directories under ~/.flow.",
    )
    setup_sub.add_parser(
        "project",
        help="scaffold .flow into the current repository",
        description="Copy missing framework template files into repo/.flow without touching existing files.",
    )
    setup_sub.add_parser(
        "user",
        help="install flow at the user level so it is active in every Claude session",
        description="Generate ~/.claude/ skills, agents, hooks, and managed settings from the framework scaffold.",
    )

    refresh = sub.add_parser(
        "refresh",
        help="add newly introduced framework files into an existing repo/.flow",
        description="Refresh an existing repo-local .flow by copying only files that are missing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  flow refresh project\n",
    )
    refresh_sub = refresh.add_subparsers(dest="refresh_target", required=True, title="refresh targets")
    refresh_sub.add_parser(
        "project",
        help="copy missing files from the framework template into repo/.flow",
        description="Bring an existing project forward to the latest template surface without overwriting local edits.",
    )

    sub.add_parser(
        "help",
        help="show framework overview (phase machine, commands, agents, architecture)",
        description="Print the framework orientation: workflow phases, slash commands, CLI commands, agents, and architecture. Same content as the `/flow-help` slash command — invoke this at the shell when you are not in a Claude session.",
    )
    sub.add_parser(
        "doctor",
        help="report machine, repo, and runtime sync state",
        description="Inspect the current machine install, repo framework, and generated runtime adapter state.",
    )
    sub.add_parser(
        "bootstrap",
        help="validate that the required repo/.flow structure exists",
        description="Check that the current repository contains the minimum .flow structure needed for sync and workflow use.",
    )
    sync = sub.add_parser(
        "sync",
        help="generate runtime adapters from repo/.flow or the framework scaffold",
        description="Generate runtime-facing adapters from the repo-local .flow source of truth, or from the framework scaffold when --user is set.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Targets:\n"
            "  claude  Generate .claude skills, agents, hooks, settings, and a managed manifest.\n"
            "  codex   Generate .agents skills and a .codex managed manifest.\n\n"
            "Examples:\n"
            "  flow sync claude\n"
            "  flow sync claude --check\n"
            "  flow sync claude --user\n"
            "  flow sync codex\n"
            "  flow sync codex --check\n"
            "  flow sync codex --user\n"
        ),
    )
    sync.add_argument(
        "target",
        choices=["claude", "codex"],
        help="runtime adapter target to generate or check",
    )
    sync.add_argument(
        "--check",
        action="store_true",
        help="report drift without writing files",
    )
    sync.add_argument(
        "--user",
        action="store_true",
        help="sync user-level runtime surfaces from the framework scaffold (instead of the current repo)",
    )

    install_parser = sub.add_parser(
        "install",
        help="convert the current install between develop (symlink) and release (copy) modes",
        description=(
            "Convert ~/.flow/source between develop mode (symlink to a clone) and "
            "release mode (real directory of copied content). The clone is never "
            "deleted; switching to release mode is non-destructive to the source repo."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  flow install --release\n"
            "  flow install --develop /Users/me/personal/flow\n"
        ),
    )
    install_group = install_parser.add_mutually_exclusive_group(required=True)
    install_group.add_argument(
        "--release",
        action="store_true",
        help="convert ~/.flow/source from a symlink to a real copied directory",
    )
    install_group.add_argument(
        "--develop",
        metavar="CLONE_PATH",
        help="convert ~/.flow/source to a symlink pointing at the given clone path",
    )

    update_parser = sub.add_parser(
        "update",
        help="roll forward a release install to the latest tagged release",
        description=(
            "In release mode: fetch the latest semver tag from the configured remote, "
            "stage it, and atomically swap into ~/.flow/source. In develop mode: print "
            "the manual pull-and-resync commands."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  flow update --check\n"
            "  flow update\n"
            "  flow update --resync\n"
        ),
    )
    update_parser.add_argument(
        "--check",
        action="store_true",
        help="report current vs latest tag without applying changes",
    )
    update_parser.add_argument(
        "--resync",
        action="store_true",
        help="after applying, run `flow sync claude --user` and `flow sync codex --user`",
    )
    update_parser.add_argument(
        "--remote",
        metavar="URL",
        help="override the remote URL configured in ~/.flow/config.toml",
    )

    args = parser.parse_args()

    if args.command == "setup" and args.setup_target == "machine":
        return setup_machine()
    if args.command == "setup" and args.setup_target == "project":
        return setup_project()
    if args.command == "setup" and args.setup_target == "user":
        return setup_user()
    if args.command == "refresh" and args.refresh_target == "project":
        return refresh_project()
    if args.command == "help":
        return help_command()
    if args.command == "doctor":
        return doctor()
    if args.command == "bootstrap":
        return bootstrap()
    if args.command == "sync":
        return sync_target(args.target, check=args.check, user_mode=args.user)
    if args.command == "install":
        return install_command(release=args.release, develop_path=args.develop)
    if args.command == "update":
        return update_command(check=args.check, resync=args.resync, remote_override=args.remote)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
