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
)
from paths import (
    GENERATED_MARKER,
    HOME,
    SCAFFOLD_DIR,
    SOURCE_DIR,
    USER_OVERLAY_DIR,
)
from render import (
    build_managed_manifest,
    codex_hook_command_for,
    codex_skill_dir,
    hook_command_for,
    manifest_ref_for,
    render_claude_agent,
    render_codex_agent,
    render_codex_skill,
    render_skill_from_command,
    routing_hints_for,
    source_ref_for,
)


def _contained(root: Path, raw: str) -> Path | None:
    """Join a managed-manifest path against the root, or refuse it.

    `root / raw` is not safe on its own: pathlib discards the left operand when
    the right is absolute, so a manifest entry of `/etc/passwd` yields exactly
    `/etc/passwd`, and `../../x` walks out of the repo. Every path returned by
    the readers below is handed to `sync_outputs`, which unlinks whatever it
    considers stale — so an entry outside the root is a delete outside the root.

    The managed manifest is a generated file, but it is a generated file
    sitting in the user's repo where anything can edit it, and `flow project
    migrate` now consumes it specifically in order to delete. Refused rather
    than sanitized: a path that escaped was never a path flow wrote.
    """
    candidate = root / raw
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(root.resolve()):
        print(f"ignoring managed path outside the root: {raw}")
        return None
    return candidate


def read_managed_paths(root: Path, path: Path) -> set[Path]:
    if not path.exists():
        return set()
    data = read_toml(path)
    files = data.get("files", [])
    found = (_contained(root, entry["path"]) for entry in files if "path" in entry)
    return {p for p in found if p is not None}


def read_managed_merge_paths(root: Path, path: Path) -> set[Path]:
    """Managed paths whose sync_mode is `merge` — files flow writes INTO
    rather than owns (.claude/settings.json, .codex/hooks.json).

    These must never be unlinked as "stale": dropping the runtime's
    settings/hooks config from the manifest makes the file stop appearing
    in `desired`, and treating that like any other stale managed file
    would delete the user's own unmanaged content along with flow's —
    directly violating the preserve-unmanaged contract the same manifest
    advertises.
    """
    if not path.exists():
        return set()
    data = read_toml(path)
    files = data.get("files", [])
    found = (
        _contained(root, entry["path"])
        for entry in files
        if "path" in entry and entry.get("sync_mode") == "merge"
    )
    return {p for p in found if p is not None}


def _tag_entries(entries: list, root: Path, origin: str) -> None:
    """Annotate command/agent entries with their source root and origin."""
    for entry in entries:
        entry["_root"] = root
        entry["_origin"] = origin


def shared_agents(manifest: dict) -> list:
    return manifest.get("agents", [])


def runtime_policy_for_agent(manifest: dict, target: str, agent: dict) -> dict:
    tiers = manifest.get("model_tiers", {})
    tier = agent.get("model_tier")
    policy = dict(tiers.get(tier, {}).get(target, {}))

    runtime_override = agent.get(target)
    if isinstance(runtime_override, dict):
        policy.update(runtime_override)

    for key in ("model", "effort", "model_reasoning_effort"):
        if key in agent:
            policy[key] = agent[key]

    return policy


def merge_user_overlay(framework_dir: Path) -> tuple[Path, dict]:
    """Load the framework manifest and merge in `~/.flow/user/flow.toml` if it exists.

    Each `[[claude.commands]]`, `[[codex.commands]]`, and `[[agents]]`
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
    convention documented in `FRAMEWORK.md` (user overlay > framework default),
    not this merge step. Projects hold neither.
    """
    framework_manifest_path = framework_dir / "flow.toml"
    if not framework_manifest_path.exists():
        raise FileNotFoundError(f"missing manifest: {framework_manifest_path}")
    manifest = read_toml(framework_manifest_path)

    _tag_entries(manifest.get("agents", []), framework_dir, "framework")
    if "claude" in manifest:
        _tag_entries(manifest["claude"].get("commands", []), framework_dir, "framework")
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
        manifest["claude"]["hooks"] = merge_named(
            manifest["claude"].get("hooks", []),
            user_manifest.get("claude", {}).get("hooks", []),
        )
    if "codex" in manifest:
        manifest["codex"]["commands"] = merge_named(
            manifest["codex"].get("commands", []),
            user_manifest.get("codex", {}).get("commands", []),
        )
        manifest["codex"]["hooks"] = merge_named(
            manifest["codex"].get("hooks", []),
            user_manifest.get("codex", {}).get("hooks", []),
        )
    manifest["agents"] = merge_named(
        manifest.get("agents", []),
        user_manifest.get("agents", []),
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


def _hook_handler(hook: dict, command: str) -> dict:
    """One handler entry for a settings/hooks file, shared by both runtimes.

    `timeout` and `status_message` are optional manifest fields passed
    through when present — both runtimes' hook schemas accept them and the
    builders should not silently drop what the manifest declares.
    """
    handler = {"type": hook["type"], "command": command}
    if hook.get("timeout") is not None:
        handler["timeout"] = hook["timeout"]
    if hook.get("status_message"):
        handler["statusMessage"] = hook["status_message"]
    return handler


def build_claude_settings(root: Path, runtime: dict) -> str:
    settings_path = root / runtime["settings_file"]
    settings = remove_managed_flow_hooks(read_json(settings_path))
    hooks = settings.setdefault("hooks", {})

    for hook in runtime.get("hooks", []):
        event = hook["event"]
        groups = hooks.setdefault(event, [])
        group: dict = {}
        if hook.get("matcher") is not None:
            group["matcher"] = hook["matcher"]
        group["hooks"] = [_hook_handler(hook, hook_command_for(hook["script"]))]
        groups.append(group)

    if not hooks:
        settings.pop("hooks", None)

    return json.dumps(settings, indent=2, sort_keys=True) + "\n"


def remove_managed_codex_hooks(doc: dict) -> dict:
    """Strip flow-managed handlers from a Codex hooks.json document.

    Same shape and same rule as `remove_managed_flow_hooks`, against the
    Codex path marker: a handler whose command points into `/.codex/hooks/`
    at a `flow-` script is flow's to manage; everything else — including
    hand-authored handlers sharing an event with flow's — is preserved
    verbatim. The two functions stay separate rather than parameterized on
    the marker because their input documents genuinely differ (Claude's is
    a whole settings file; Codex's is a dedicated hooks file with its own
    top-level `hooks` key and optional `description`).
    """
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        return doc

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
                if handler.get("type") == "command" and "/.codex/hooks/flow-" in command:
                    continue
                kept_handlers.append(handler)
            if kept_handlers:
                updated = dict(group)
                updated["hooks"] = kept_handlers
                cleaned_groups.append(updated)
        if cleaned_groups:
            cleaned_events[event] = cleaned_groups

    if cleaned_events:
        doc["hooks"] = cleaned_events
    else:
        doc.pop("hooks", None)
    return doc


def build_codex_hooks_file(root: Path, runtime: dict) -> str:
    """Codex twin of `build_claude_settings`, against `.codex/hooks.json`.

    hooks.json rather than config.toml on purpose: Codex loads hooks from
    either, but config.toml is a dense, user-owned file (model, plugins,
    MCP servers, the desktop app's own `notify` key) with no stdlib TOML
    writer to round-trip it safely — while hooks.json is a dedicated JSON
    file this module's existing read-merge-write machinery handles exactly
    like Claude's settings. Flow never touches config.toml at all.
    """
    hooks_path = root / runtime["hooks_file"]
    doc = remove_managed_codex_hooks(read_json(hooks_path))
    hooks = doc.setdefault("hooks", {})

    for hook in runtime.get("hooks", []):
        event = hook["event"]
        groups = hooks.setdefault(event, [])
        group: dict = {}
        if hook.get("matcher") is not None:
            # Codex treats an absent matcher as match-everything; emitting
            # an empty string instead would be equivalent but noisier.
            group["matcher"] = hook["matcher"]
        group["hooks"] = [_hook_handler(hook, codex_hook_command_for(hook["script"]))]
        groups.append(group)

    if not hooks:
        # No flow hooks registered and nothing unmanaged survived the strip:
        # don't leave a dangling empty "hooks" key in the document.
        doc.pop("hooks", None)

    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def validate_hook_script_name(hook: dict) -> None:
    """Reject hook scripts not named `flow-*` before any output is built.

    The preserve-unmanaged strip identifies flow's own handlers by the
    `/.{claude,codex}/hooks/flow-` path marker. A script named outside
    that convention would survive the strip and be re-appended on every
    sync — duplicating its handler without bound — and deregistering it
    would remove the script file while leaving the handler pointing at
    nothing. Failing loudly at sync time is the cheap, permanent fix.
    """
    script = hook.get("script", "")
    if not script.startswith("flow-"):
        raise ValueError(
            f"hook script {script!r} (hook {hook.get('name', '?')!r}) must be named flow-*: "
            "the managed-handler contract identifies flow's handlers by that prefix"
        )


def hook_script_source(hook: dict) -> Path:
    """Where a hook entry's script actually lives, origin-aware.

    Framework hooks ship in the flow repo's `hooks/`; a user-overlay hook's
    script lives beside its overlay manifest in `~/.flow/user/hooks/`.
    """
    if hook.get("_origin") == "user":
        overlay = USER_OVERLAY_DIR / "hooks" / hook["script"]
        if overlay.exists():
            return overlay
        # A user overlay entry may override a FRAMEWORK hook by name just
        # to change its event/matcher/timeout — falling back to the
        # framework script means the override doesn't force copying the
        # script into the overlay.
        return SOURCE_DIR / "hooks" / hook["script"]
    return SOURCE_DIR / "hooks" / hook["script"]


def desired_claude_outputs(
    root: Path, flow_dir: Path, manifest: dict, manifest_rel: str
) -> tuple[dict[Path, str], list[dict], set[Path]]:
    runtime = manifest["claude"]
    skill_defaults = runtime.get("skill_defaults", {})
    agent_defaults = runtime.get("agent_defaults", {})
    agents = shared_agents(manifest)
    routing_hints = routing_hints_for("claude", agents, manifest.get("model_tiers", {}))
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
        content = render_skill_from_command(command_with_body, skill_defaults, routing_hints)
        outputs[target] = content
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "skill",
                "source": source_ref_for(source_rel, entry_origin),
                "sync_mode": "replace",
            }
        )

    for agent in agents:
        source_rel = agent["source"]
        entry_root = agent.get("_root", flow_dir)
        entry_origin = agent.get("_origin", "framework")
        source_path = entry_root / source_rel
        target = root / runtime["agent_dir"] / f'{agent["name"]}.md'
        generation_mode = agent.get("generation_mode", agent_defaults.get("generation_mode", "verbatim"))
        if generation_mode != "verbatim":
            raise ValueError(f"unsupported agent generation mode: {generation_mode}")
        content = render_claude_agent(
            source_ref_for(source_rel, entry_origin),
            source_path.read_text(),
            runtime_policy_for_agent(manifest, "claude", agent),
        )
        outputs[target] = content
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "agent",
                "source": source_ref_for(source_rel, entry_origin),
                "sync_mode": "replace",
            }
        )

    for hook in runtime.get("hooks", []):
        validate_hook_script_name(hook)
        source = hook_script_source(hook)
        target = root / runtime["hook_dir"] / hook["script"]
        content = source.read_text()
        outputs[target] = content
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "hook-script",
                "source": (
                    f'~/.flow/user/hooks/{hook["script"]}'
                    if hook.get("_origin") == "user"
                    else f'flow/hooks/{hook["script"]}'
                ),
                "sync_mode": "replace",
            }
        )

    settings_path = root / runtime["settings_file"]
    outputs[settings_path] = build_claude_settings(root, runtime)
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
    root: Path, flow_dir: Path, manifest: dict, manifest_rel: str
) -> tuple[dict[Path, str], list[dict], set[Path]]:
    runtime = manifest["codex"]
    agents = shared_agents(manifest)
    routing_hints = routing_hints_for("codex", agents, manifest.get("model_tiers", {}))
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
            command["name"],
            command["description"],
            source_ref_for(source_rel, entry_origin),
            source_path.read_text(),
            routing_hints,
        )
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "skill",
                "source": source_ref_for(source_rel, entry_origin),
                "sync_mode": "replace",
            }
        )

    for agent in agents:
        source_rel = agent["source"]
        entry_root = agent.get("_root", flow_dir)
        entry_origin = agent.get("_origin", "framework")
        source_path = entry_root / source_rel
        target = root / runtime["agent_dir"] / f'{agent["name"]}.toml'
        outputs[target] = render_codex_agent(
            agent["name"],
            source_ref_for(source_rel, entry_origin),
            source_path.read_text(),
            runtime_policy_for_agent(manifest, "codex", agent),
        )
        managed_entries.append(
            {
                "path": rel_posix(target, root),
                "kind": "agent",
                "source": source_ref_for(source_rel, entry_origin),
                "sync_mode": "replace",
            }
        )

    # Hook support mirrors desired_claude_outputs exactly, gated on the
    # runtime declaring hook_dir + hooks_file — older manifests without
    # them keep today's skill/agent-only surface untouched.
    if runtime.get("hook_dir") and runtime.get("hooks_file"):
        for hook in runtime.get("hooks", []):
            validate_hook_script_name(hook)
            source = hook_script_source(hook)
            target = root / runtime["hook_dir"] / hook["script"]
            outputs[target] = source.read_text()
            managed_entries.append(
                {
                    "path": rel_posix(target, root),
                    "kind": "hook-script",
                    "source": (
                        f'~/.flow/user/hooks/{hook["script"]}'
                        if hook.get("_origin") == "user"
                        else f'flow/hooks/{hook["script"]}'
                    ),
                    "sync_mode": "replace",
                }
            )

        hooks_path = root / runtime["hooks_file"]
        outputs[hooks_path] = build_codex_hooks_file(root, runtime)
        mergeable_paths.add(hooks_path)
        managed_entries.append(
            {
                "path": rel_posix(hooks_path, root),
                "kind": "hooks-file",
                "source": manifest_rel,
                "sync_mode": "merge",
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
    root: Path, flow_dir: Path, manifest_path: Path, manifest: dict, target: str
) -> tuple[str, bool]:
    runtime = manifest.get(target)
    if not isinstance(runtime, dict):
        return "n/a", False

    managed_path = root / runtime["managed_manifest"]
    managed_ok = managed_path.exists()
    try:
        previous_managed = read_managed_paths(root, managed_path)
        desired, _managed_entries, mergeable_paths = desired_outputs_for_target(
            target, root, flow_dir, manifest, manifest_ref_for()
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
    merge_protected: set[Path] | None = None,
) -> int:
    merge_protected = merge_protected or set()
    conflicts, changed, stale = analyze_sync(desired, previous_managed, mergeable_paths)
    removed: list[Path] = []

    if conflicts:
        print(f"sync {target_name} found unmanaged conflicts:")
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
        if path in merge_protected:
            # A merge-mode file (settings.json, hooks.json) holds the
            # user's own content alongside flow's; never delete it, just
            # stop managing it. Flow's handlers remain until the user
            # removes them or re-registers hooks.
            print(f"- unmanaged (kept, contains user content): {rel_posix(path, root)}")
            continue
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
    target: str, root: Path, flow_dir: Path, manifest: dict, manifest_rel: str
) -> tuple[dict[Path, str], list[dict], set[Path]]:
    if target == "claude":
        return desired_claude_outputs(root, flow_dir, manifest, manifest_rel)
    if target == "codex":
        return desired_codex_outputs(root, flow_dir, manifest, manifest_rel)
    raise ValueError(f"unsupported sync target: {target}")


def sync_target(target: str, check: bool = False, user_mode: bool = False) -> int:
    """Generate a runtime's adapters from the framework scaffold.

    User level only. Project-level sync existed to regenerate adapters from a
    project's own copies of the framework's commands and agents, and projects
    no longer hold copies. `flow project migrate` removes the adapters an
    earlier project-level sync left behind.

    Exits 1 rather than 0 without `--user`. Printing a pointer and succeeding
    would be indistinguishable from having synced, and any caller checking the
    exit code would carry on believing its adapters were current.
    """
    if not user_mode:
        print("project-level sync was retired; runtime surfaces are user-level")
        print(f"run `flow sync {target} --user` instead")
        print("to remove a repo's leftover project adapters, run `flow project migrate`")
        return 1

    root = HOME
    flow_dir = SCAFFOLD_DIR
    if not flow_dir.exists():
        print("framework scaffold missing; re-run install-flow.sh first")
        return 1
    scope_label = "user-level"

    try:
        # Reads the framework scaffold and layers in ~/.flow/user/flow.toml
        # if present.
        manifest_path, manifest = merge_user_overlay(flow_dir)
    except FileNotFoundError as err:
        print(str(err))
        return 1

    runtime = manifest.get(target)
    if not isinstance(runtime, dict):
        print(f"sync target is not configured in scaffold flow.toml: {target}")
        return 1

    previous_managed = read_managed_paths(root, root / runtime["managed_manifest"])
    merge_protected = read_managed_merge_paths(root, root / runtime["managed_manifest"])
    try:
        desired, _managed_entries, mergeable_paths = desired_outputs_for_target(
            target, root, flow_dir, manifest, manifest_ref_for()
        )
    except (ValueError, FileNotFoundError) as err:
        # A misnamed hook script (must be flow-*) or a hook script missing
        # from its source dir — fail loudly before anything is written.
        print(str(err))
        return 1
    result = sync_outputs(
        root, target, desired, previous_managed, mergeable_paths, check=check, merge_protected=merge_protected
    )
    if result == 0:
        verb = "check" if check else "sync"
        print(f"{scope_label} {target} {verb} complete from {manifest_path}")
    return result
