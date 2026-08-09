"""The sync engine: resolve the manifest, compute desired adapters, reconcile disk.

Sync is a three-stage pipeline, and the stages are deliberately separate:

  desired_*_outputs   what the manifest says should exist, as path -> content
  analyze_sync        how that differs from what is on disk right now
  sync_outputs        write the difference, or report it when check=True

Keeping "what should exist" free of any filesystem writes is what makes
`--check` honest: the check path and the write path compute the same desired
state and diverge only at the last stage. A dry-run implemented as a flag
threaded through write logic would not have that property.

`previous_managed` reconciliation matters as much as the writes. Files this
tool generated previously but the manifest no longer declares get removed;
files it never generated are left alone. That is what `preserve_unmanaged`
means in the emitted manifests, and it is why unmanaged edits in .claude/
survive a sync.
"""

import json
import sys
from pathlib import Path

from flowtoml import read_toml
from fsutil import (
    ensure_dir,
    read_json,
    rel_posix,
    remove_empty_parents,
    repo_root,
)
from paths import (
    GENERATED_MARKER,
    HOME,
    MODE_PROJECT,
    MODE_USER,
    SCAFFOLD_DIR,
    SOURCE_DIR,
    USER_OVERLAY_DIR,
)
from render import (
    build_managed_manifest,
    codex_skill_dir,
    hook_command_for,
    insert_generated_marker,
    manifest_ref_for,
    render_codex_skill,
    render_skill_from_command,
    source_ref_for,
)


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

    # The manifest lists itself, so its own entry has to be appended before the
    # content is built — otherwise the file on disk describes every managed file
    # except the one describing them.
    managed_manifest_path = root / runtime["managed_manifest"]
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

    # See the note in desired_claude_outputs: the manifest lists itself, so its
    # own entry is appended before the content is built.
    managed_manifest_path = root / runtime["managed_manifest"]
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
