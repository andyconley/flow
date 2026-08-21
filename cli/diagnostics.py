"""Read-only reporting: doctor, help, and bootstrap.

These three never write. `doctor` in particular is a diagnosis, not a repair —
it reports what is missing and names the command that fixes it, rather than
fixing anything itself. A reporting command that silently repairs makes the
next run look healthy for the wrong reason, and hides how the machine drifted.

Every state renders a line, including the healthy and the absent ones. An
omitted section reads as "checked and fine" when it may mean "never checked."
"""

import sys
from pathlib import Path

import usage_store
from flowtoml import read_toml
from fsutil import repo_root
from lifecycle import read_install_config
from overlay import format_overlay_vcs, overlay_vcs_status
from paths import (
    CAPABILITY_DIRS,
    CODEX_SKILL_DIR,
    DEFAULT_REMOTE,
    FLOW_CONFIG,
    FLOW_HOME,
    HOME,
    INSTALL_MODE_DEVELOP,
    INSTALL_MODE_RELEASE,
    SCAFFOLD_DIR,
    SOURCE_DIR,
    USER_BIN_DIR,
    USER_OVERLAY_DIR,
)
from render import codex_skill_dir
from project import audit_project
from sync import merge_user_overlay, runtime_status, shared_agents


def agent_policy_status(root, manifest: dict, target: str) -> str:
    agents = shared_agents(manifest)
    if not agents:
        return "n/a"

    if target == "claude":
        runtime = manifest.get("claude", {})
        agent_dir = root / runtime.get("agent_dir", ".claude/agents")
        extension = ".md"
        required_fields = ("model:", "effort:")
    elif target == "codex":
        runtime = manifest.get("codex", {})
        agent_dir = root / runtime.get("agent_dir", ".codex/agents")
        extension = ".toml"
        required_fields = ("model =", "model_reasoning_effort =")
    else:
        return "n/a"

    expected = len(agents)
    present = 0
    configured = 0
    for agent in agents:
        path = agent_dir / f'{agent.get("name", "")}{extension}'
        if not path.exists():
            continue
        present += 1
        text = path.read_text()
        if all(field in text for field in required_fields):
            configured += 1

    if present == expected and configured == expected:
        return f"ok ({configured}/{expected} configured)"
    return f"stale ({present}/{expected} present, {configured}/{expected} configured)"


def print_smoke_test_hint(label: str) -> None:
    print(f"{label} smoke:     manually invoke support-lead and confirm the runtime transcript/logs show the configured model and effort")


def doctor() -> int:
    root = repo_root()
    flow_dir = root / ".flow"
    # Run from $HOME, `repo_root` finds no project and falls back to the working
    # directory, so `flow_dir` becomes flow's own home. Reporting that as a
    # project overlay turns "you are not in a project" into a project whose
    # manifest is missing and whose sync checks never ran -- twelve lines that
    # read as a broken install. Resolved on both sides because `root` is
    # resolved and `FLOW_HOME` is not.
    root_is_flow_home = flow_dir.resolve() == FLOW_HOME.resolve()
    project_overlay_ok = flow_dir.exists() and not root_is_flow_home
    project_manifest_ok = project_overlay_ok and (flow_dir / "flow.toml").exists()

    # Six sync and drift lines used to live here. They reported whether this
    # repo's own generated adapters matched its own copies of the framework,
    # and both halves of that are gone: project-level sync is retired and
    # projects no longer hold copies. What replaces them is one line derived
    # from the same classifier `flow project audit` uses, because the question
    # a project can still answer is not "are your adapters current" but "are
    # you still carrying framework files nobody updates".
    overlay_line = "n/a"
    if project_overlay_ok and SCAFFOLD_DIR.exists():
        try:
            report = audit_project(flow_dir, SCAFFOLD_DIR)
            copies = report.counts()["identical"] + report.counts()["orphaned"]
            overlay_line = (
                "clean"
                if copies == 0
                else f"{copies} framework copy/declaration(s) — run `flow project migrate`"
            )
        except Exception:
            overlay_line = "error"

    user_claude_managed_ok = False
    user_claude_drift = "n/a"
    user_codex_managed_ok = False
    user_codex_drift = "n/a"
    user_claude_agent_policy = "n/a"
    user_codex_agent_policy = "n/a"
    user_skills_dir = HOME / ".claude" / "skills"
    user_agents_dir = HOME / ".claude" / "agents"
    user_codex_skills_dir = HOME / CODEX_SKILL_DIR
    if SCAFFOLD_DIR.exists():
        try:
            user_manifest_path, user_manifest = merge_user_overlay(SCAFFOLD_DIR)
            user_claude_drift, user_claude_managed_ok = runtime_status(
                HOME, SCAFFOLD_DIR, user_manifest_path, user_manifest, "claude"
            )
            user_codex_drift, user_codex_managed_ok = runtime_status(
                HOME, SCAFFOLD_DIR, user_manifest_path, user_manifest, "codex"
            )
            user_codex_skills_dir = HOME / codex_skill_dir(user_manifest["codex"])
            user_claude_agent_policy = agent_policy_status(HOME, user_manifest, "claude")
            user_codex_agent_policy = agent_policy_status(HOME, user_manifest, "codex")
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
    print("-- user-level (active in every supported runtime session) --")
    print(f"claude sync:      {'ok' if user_claude_managed_ok else 'missing'}")
    print(f"claude drift:     {user_claude_drift}")
    print(f"skills dir:       {'ok' if user_skills_dir.exists() else 'missing'}")
    print(f"agents dir:       {'ok' if user_agents_dir.exists() else 'missing'}")
    print(f"agent policy:     {user_claude_agent_policy}")
    print_smoke_test_hint("claude")
    print(f"codex sync:       {'ok' if user_codex_managed_ok else 'missing'}")
    print(f"codex drift:      {user_codex_drift}")
    print(f"codex skills:     {'ok' if user_codex_skills_dir.exists() else 'missing'}")
    print(f"codex agents:     {user_codex_agent_policy}")
    print_smoke_test_hint("codex")

    # User overlay: report whether ~/.flow/user/flow.toml is present and what it
    # declares. Customizations apply at sync time via merge_user_overlay.
    user_overlay_manifest = USER_OVERLAY_DIR / "flow.toml"
    if user_overlay_manifest.exists():
        try:
            overlay = read_toml(user_overlay_manifest)
            user_commands = overlay.get("claude", {}).get("commands", []) + overlay.get("codex", {}).get("commands", [])
            user_agents = overlay.get("agents", [])
            user_hooks = overlay.get("claude", {}).get("hooks", []) + overlay.get("codex", {}).get("hooks", [])
            print(f"user overlay:     {user_overlay_manifest}")
            if user_commands:
                names = ", ".join(c.get("name", "<unnamed>") for c in user_commands)
                print(f"  commands:       {len(user_commands)} ({names})")
            if user_agents:
                names = ", ".join(a.get("name", "<unnamed>") for a in user_agents)
                print(f"  agents:         {len(user_agents)} ({names})")
            if user_hooks:
                names = ", ".join(h.get("name", "<unnamed>") for h in user_hooks)
                print(f"  hooks:          {len(user_hooks)} ({names})")
            if not user_commands and not user_agents and not user_hooks:
                print("  entries:        (manifest present but declares no commands, agents, or hooks)")
        except Exception as err:
            print(f"user overlay:     {user_overlay_manifest} (parse error: {err})")
    else:
        print(f"user overlay:     none ({user_overlay_manifest} absent)")
    # The overlay is authored content with no home in any repo flow ships, so
    # whether it has history at all is worth stating every time.
    print(f"  vcs:            {format_overlay_vcs(overlay_vcs_status(USER_OVERLAY_DIR))}")
    print()
    print(f"-- project: {root} --")
    if root_is_flow_home:
        # One accurate line instead of twelve misleading ones.
        print("not a flow project: that .flow is flow's own home, not a project overlay")
        print("                  run doctor from inside a repo to check a project")
        print()
        print(_usage_section())
        return 0
    print(f"repo .flow:       {'ok' if project_overlay_ok else 'missing'}")
    print(f"manifest:         {'ok' if project_manifest_ok else 'missing'}")
    print(f"overlay:          {overlay_line}")
    print()
    print(_usage_section())
    return 0


def _usage_section() -> str:
    """Render the plugin/skill usage section, and never let it break doctor.

    Read-only like the rest of doctor: it opens the store but never creates or
    migrates it, so an unmigrated store reports its state instead of being
    silently repaired — the same reasoning the store-status line above follows.

    Wrapped in a bare except because this section is the newest and least
    load-bearing thing doctor prints, and doctor is what someone runs when their
    install is already broken. A diagnostic that cannot survive a broken machine
    is worth less than the line it would have printed.
    """
    try:
        import sqlite3

        import plugin_usage

        store = usage_store.default_store_path(HOME)
        if not store.exists():
            return "-- usage: skills & plugins --\n  no usage store yet — run `flow setup machine`"
        conn = sqlite3.connect(store)
        try:
            payload = plugin_usage.usage_payload(conn, home=HOME, project_root=Path.cwd())
        finally:
            conn.close()
        return plugin_usage.render_usage_section(payload)
    except Exception:  # noqa: BLE001 — see docstring
        return "-- usage: skills & plugins --\n  unavailable on this install"


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
    # Same confusion doctor guards against: from $HOME this is flow's own home,
    # and without the check bootstrap walks into it and reports the framework
    # files it will never contain as missing from a project that does not exist.
    if flow_dir.resolve() == FLOW_HOME.resolve():
        print("not inside a flow project; run `flow setup project` in a repo")
        return 1
    if not flow_dir.exists():
        print("repo is missing .flow; run `flow setup project` first")
        return 1

    required = [
        flow_dir / "flow.toml",
        flow_dir / "FRAMEWORK.md",
        flow_dir / "PROJECT.md",
        flow_dir / "memory",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("bootstrap found missing framework paths:")
        for path in missing:
            print(f"- {path}")
        return 1

    # Shared with the project audit rather than spelled out again here: two
    # independent lists of "which directories are framework capability" drift,
    # and the audit's consumers delete based on that answer.
    missing_optional = [
        name for name in CAPABILITY_DIRS if not (flow_dir / name).exists()
    ]
    print(f"bootstrap ok: {flow_dir}")
    if missing_optional:
        print(f"optional framework dirs absent: {', '.join(missing_optional)}")
        print("user-level install provides framework commands and agents unless this project overrides them")
    print("next: run `flow doctor` or `flow sync claude`")
    return 0
