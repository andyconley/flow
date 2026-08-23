"""Runtime-neutral smoke checks for generated Flow adapter surfaces.

The command proves what local files can prove: generated commands, agents,
hooks, managed manifests, and configured model/effort policy. It deliberately
does not pretend to prove that a Claude or Codex client honored those files at
runtime; those checks are emitted as manual-required evidence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paths import HOME, SCAFFOLD_DIR
from render import codex_skill_dir, manifest_ref_for
from sync import (
    desired_outputs_for_target,
    merge_user_overlay,
    read_managed_paths,
    runtime_status,
    runtime_policy_for_agent,
    shared_agents,
)


TARGETS = ("claude", "codex")
C_LITE_COMMAND_NEEDLES = {
    "flow-define": "flow run transition <work-id> start-definition",
    "flow-solution": "flow run transition <work-id> start-solution",
    "flow-plan": "flow run transition <work-id> start-plan",
    "flow-implement": "flow run transition <work-id> start-implementation",
    "flow-review": "flow run transition <work-id> start-review",
    "flow-archive": "flow run transition <work-id> archive",
    "flow-scout": "flow run transition <work-id> archive-scout",
    "flow-status": "flow run list",
    "flow-resume": "flow run verify",
}


def _rel(path: Path, root: Path = HOME) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _check(name: str, status: str, detail: str = "", path: Path | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"name": name, "status": status}
    if detail:
        row["detail"] = detail
    if path is not None:
        row["path"] = _rel(path)
    return row


def _skill_dir_for(root: Path, runtime: dict[str, Any], target: str) -> Path:
    if target == "codex":
        return root / codex_skill_dir(runtime)
    return root / runtime.get("skill_dir", f".{target}/skills")


def _agent_path(root: Path, runtime: dict[str, Any], target: str, agent_name: str) -> Path:
    extension = ".toml" if target == "codex" else ".md"
    return root / runtime.get("agent_dir", f".{target}/agents") / f"{agent_name}{extension}"


def _agent_policy_needles(target: str, policy: dict[str, Any]) -> tuple[str, str]:
    if target == "codex":
        return (
            f'model = "{policy.get("model", "")}"',
            f'model_reasoning_effort = "{policy.get("model_reasoning_effort", "")}"',
        )
    return (
        f"model: {policy.get('model', '')}",
        f"effort: {policy.get('effort', '')}",
    )


def _check_target(root: Path, manifest_path: Path, manifest: dict[str, Any], target: str) -> dict[str, Any]:
    runtime = manifest.get(target)
    if not isinstance(runtime, dict):
        return {
            "target": target,
            "static": [_check("runtime configured", "failed", "target missing from manifest")],
            "manual": [],
        }

    static: list[dict[str, Any]] = []
    manual: list[dict[str, Any]] = []
    managed_path = root / runtime["managed_manifest"]
    if managed_path.exists():
        static.append(_check("managed manifest", "passed", path=managed_path))
    else:
        static.append(_check("managed manifest", "failed", "missing", managed_path))
    drift, _managed_ok = runtime_status(root, SCAFFOLD_DIR, manifest_path, manifest, target)
    static.append(
        _check(
            "generated surface freshness",
            "passed" if drift == "clean" else "failed",
            drift,
        )
    )

    try:
        desired, _managed_entries, _mergeable_paths = desired_outputs_for_target(
            target, root, SCAFFOLD_DIR, manifest, manifest_ref_for()
        )
    except Exception as exc:  # noqa: BLE001 - smoke should report, not crash.
        static.append(_check("desired output build", "failed", str(exc)))
        desired = {}

    if managed_path.exists():
        try:
            managed_paths = read_managed_paths(root, managed_path)
            desired_paths = set(desired)
            if desired_paths.issubset(managed_paths):
                static.append(_check("managed manifest coverage", "passed"))
            else:
                missing = ", ".join(sorted(_rel(p) for p in desired_paths - managed_paths))
                static.append(_check("managed manifest coverage", "failed", missing))
        except Exception as exc:  # noqa: BLE001
            static.append(_check("managed manifest coverage", "failed", str(exc)))

    skill_dir = _skill_dir_for(root, runtime, target)
    for command in runtime.get("commands", []):
        name = command.get("name", "")
        skill_path = skill_dir / name / "SKILL.md"
        if not skill_path.exists():
            static.append(_check(f"command {name}", "failed", "generated skill missing", skill_path))
            continue
        text = skill_path.read_text()
        if "Flow Agent Routing" in text:
            static.append(_check(f"command {name}", "passed", "generated skill and routing table present", skill_path))
        else:
            static.append(_check(f"command {name}", "failed", "routing table missing", skill_path))
        needle = C_LITE_COMMAND_NEEDLES.get(name)
        if needle:
            status = "passed" if needle in text else "failed"
            detail = "C-lite protocol present" if status == "passed" else f"missing {needle}"
            static.append(_check(f"command {name} C-lite protocol", status, detail, skill_path))

    for agent in shared_agents(manifest):
        name = agent.get("name", "")
        agent_path = _agent_path(root, runtime, target, name)
        if not agent_path.exists():
            static.append(_check(f"agent {name}", "failed", "generated agent missing", agent_path))
            continue
        text = agent_path.read_text()
        policy = runtime_policy_for_agent(manifest, target, agent)
        needles = _agent_policy_needles(target, policy)
        if all(needle and needle in text for needle in needles):
            static.append(
                _check(f"agent {name}", "passed", f"model/effort policy present: {', '.join(needles)}", agent_path)
            )
        else:
            static.append(
                _check(f"agent {name}", "failed", f"missing model/effort policy: {', '.join(needles)}", agent_path)
            )

    hook_dir = root / runtime.get("hook_dir", f".{target}/hooks")
    seen_hooks: set[tuple[str, str]] = set()
    for hook in runtime.get("hooks", []):
        hook_key = (hook.get("name", ""), hook.get("script", ""))
        if hook_key in seen_hooks:
            continue
        seen_hooks.add(hook_key)
        hook_path = hook_dir / hook.get("script", "")
        status = "passed" if hook_path.exists() else "failed"
        detail = "generated hook present" if status == "passed" else "generated hook missing"
        static.append(_check(f"hook {hook.get('name', '')}", status, detail, hook_path))

    command_probe = "/flow-status" if target == "claude" else "$flow-status skill"
    manual.append(
        _check(
            "command discovery",
            "manual_required",
            f"invoke {command_probe} in {target} and confirm the generated command loads",
        )
    )
    manual.append(
        _check(
            "role agent invocation",
            "manual_required",
            f"invoke support-lead in {target} and inspect transcript/log evidence for configured model and effort",
        )
    )
    return {"target": target, "static": static, "manual": manual}


def smoke_payload(target: str = "all", root: Path = HOME) -> dict[str, Any]:
    if target not in (*TARGETS, "all"):
        raise ValueError(f"unsupported target: {target}")
    manifest_path, manifest = merge_user_overlay(SCAFFOLD_DIR)
    targets = TARGETS if target == "all" else (target,)
    results = [_check_target(root, manifest_path, manifest, item) for item in targets]
    failed = sum(1 for result in results for row in result["static"] if row["status"] == "failed")
    manual_required = sum(1 for result in results for row in result["manual"] if row["status"] == "manual_required")
    return {
        "ok": failed == 0,
        "failed": failed,
        "manual_required": manual_required,
        "targets": results,
    }


def _render_target(result: dict[str, Any]) -> list[str]:
    lines = [f"-- {result['target']} --"]
    for row in result["static"]:
        suffix = f" ({row['detail']})" if row.get("detail") else ""
        path = f" [{row['path']}]" if row.get("path") else ""
        lines.append(f"{row['status']}: {row['name']}{path}{suffix}")
    for row in result["manual"]:
        lines.append(f"manual_required: {row['name']} ({row['detail']})")
    return lines


def cmd_smoke(args) -> int:
    try:
        payload = smoke_payload(args.target)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    print("runtime smoke")
    for result in payload["targets"]:
        for line in _render_target(result):
            print(line)
    print(f"summary: failed={payload['failed']} manual_required={payload['manual_required']}")
    return 0 if payload["ok"] else 1
