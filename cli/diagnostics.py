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

from diagnostic_model import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    STATUS_FAILED,
    STATUS_NOT_APPLICABLE,
    STATUS_OK,
    STATUS_WARNING,
    diagnostic,
    exit_code,
    print_json,
    support_payload,
)
import usage_store
import telemetry_freshness
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
from project import (
    REPLACE_ABSENT,
    REPLACE_OK,
    REPLACE_UNKNOWN,
    audit_project,
    declared_replaces,
    printable,
    has_legacy_active_standards_heading,
    resolve_replaces,
)
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


def runtime_smoke_line(label: str) -> str:
    try:
        from runtime_smoke import smoke_payload

        payload = smoke_payload(label)
    except Exception:  # noqa: BLE001 - doctor must survive broken installs.
        return "unavailable — run `flow runtime smoke --target all`"
    status = "static ok" if payload.get("ok") else f"{payload.get('failed', 0)} static failure(s)"
    return (
        f"{status}; {payload.get('manual_required', 0)} manual check(s) required — "
        f"run `flow runtime smoke --target {label}`"
    )


def _doctor_diagnostics(
    root: Path,
    flow_dir: Path,
    root_is_flow_home: bool,
    project_overlay_ok: bool,
    project_manifest_ok: bool,
    overlay_line: str,
    drifted_line,
    replaces_error,
    user_claude_managed_ok: bool,
    user_claude_drift: str,
    user_codex_managed_ok: bool,
    user_codex_drift: str,
    user_claude_agent_policy: str,
    user_codex_agent_policy: str,
) -> list:
    items = [
        diagnostic(
            "machine.source",
            STATUS_OK if SOURCE_DIR.exists() else STATUS_FAILED,
            SEVERITY_INFO if SOURCE_DIR.exists() else SEVERITY_ERROR,
            "ok" if SOURCE_DIR.exists() else "missing",
            "framework source is present" if SOURCE_DIR.exists() else "framework source is missing",
            path=SOURCE_DIR,
            next_action=None if SOURCE_DIR.exists() else "re-run install-flow.sh",
        ),
        diagnostic(
            "machine.scaffold",
            STATUS_OK if SCAFFOLD_DIR.exists() else STATUS_FAILED,
            SEVERITY_INFO if SCAFFOLD_DIR.exists() else SEVERITY_ERROR,
            "ok" if SCAFFOLD_DIR.exists() else "missing",
            "framework scaffold is present" if SCAFFOLD_DIR.exists() else "framework scaffold is missing",
            path=SCAFFOLD_DIR,
            next_action=None if SCAFFOLD_DIR.exists() else "re-run install-flow.sh",
        ),
        diagnostic(
            "machine.config",
            STATUS_OK if FLOW_CONFIG.exists() else STATUS_FAILED,
            SEVERITY_INFO if FLOW_CONFIG.exists() else SEVERITY_ERROR,
            "ok" if FLOW_CONFIG.exists() else "missing",
            "flow config is present" if FLOW_CONFIG.exists() else "flow config is missing",
            path=FLOW_CONFIG,
            next_action=None if FLOW_CONFIG.exists() else "run flow setup machine",
        ),
        diagnostic(
            "machine.launcher",
            STATUS_OK if (USER_BIN_DIR / "flow").exists() else STATUS_FAILED,
            SEVERITY_INFO if (USER_BIN_DIR / "flow").exists() else SEVERITY_ERROR,
            "ok" if (USER_BIN_DIR / "flow").exists() else "missing",
            "flow launcher is present" if (USER_BIN_DIR / "flow").exists() else "flow launcher is missing",
            path=USER_BIN_DIR / "flow",
            next_action=None if (USER_BIN_DIR / "flow").exists() else "run flow setup machine",
        ),
    ]

    install = read_install_config()
    mode = install.get("mode", "unknown")
    items.append(
        diagnostic(
            "install.mode",
            STATUS_OK if mode in (INSTALL_MODE_DEVELOP, INSTALL_MODE_RELEASE) else STATUS_FAILED,
            SEVERITY_INFO if mode in (INSTALL_MODE_DEVELOP, INSTALL_MODE_RELEASE) else SEVERITY_ERROR,
            "ok" if mode in (INSTALL_MODE_DEVELOP, INSTALL_MODE_RELEASE) else "missing",
            f"install mode is {mode}",
            next_action=None if mode in (INSTALL_MODE_DEVELOP, INSTALL_MODE_RELEASE) else "re-run install-flow.sh to stamp install metadata",
        )
    )

    for target, managed_ok, drift, policy in (
        ("claude", user_claude_managed_ok, user_claude_drift, user_claude_agent_policy),
        ("codex", user_codex_managed_ok, user_codex_drift, user_codex_agent_policy),
    ):
        items.append(
            diagnostic(
                f"user.{target}.sync",
                STATUS_OK if managed_ok else STATUS_FAILED,
                SEVERITY_INFO if managed_ok else SEVERITY_ERROR,
                "ok" if managed_ok else "missing",
                f"{target} managed manifest is present" if managed_ok else f"{target} managed manifest is missing",
                target=target,
                next_action=None if managed_ok else f"flow sync {target} --user",
            )
        )
        drift_ok = drift == "clean"
        items.append(
            diagnostic(
                f"user.{target}.drift",
                STATUS_OK if drift_ok else STATUS_FAILED,
                SEVERITY_INFO if drift_ok else SEVERITY_ERROR,
                "ok" if drift_ok else ("managed_conflict" if drift == "conflict" else "drift" if drift == "stale" else "manifest_invalid"),
                f"{target} generated surface drift is {drift}",
                target=target,
                next_action=None if drift_ok else f"flow sync {target} --user --check",
            )
        )
        policy_ok = policy.startswith("ok ")
        items.append(
            diagnostic(
                f"user.{target}.agent_policy",
                STATUS_OK if policy_ok else STATUS_FAILED,
                SEVERITY_INFO if policy_ok else SEVERITY_ERROR,
                "ok" if policy_ok else "stale",
                f"{target} agent policy: {policy}",
                target=target,
                next_action=None if policy_ok else f"flow sync {target} --user",
            )
        )
        smoke_line = runtime_smoke_line(target)
        smoke_ok = smoke_line.startswith("static ok")
        items.append(
            diagnostic(
                f"user.{target}.runtime_smoke",
                STATUS_WARNING if smoke_ok and "manual check" in smoke_line else STATUS_FAILED,
                SEVERITY_WARNING if smoke_ok else SEVERITY_ERROR,
                "manual_required" if smoke_ok else "runtime_not_found",
                smoke_line,
                target=target,
                next_action=f"flow runtime smoke --target {target}",
            )
        )

    if root_is_flow_home:
        items.append(
            diagnostic(
                "project.overlay",
                STATUS_NOT_APPLICABLE,
                SEVERITY_INFO,
                "ok",
                "not running inside a project overlay",
                path=flow_dir,
                next_action="run doctor from inside a repo to check a project",
            )
        )
    else:
        items.append(
            diagnostic(
                "project.overlay",
                STATUS_OK if project_overlay_ok else STATUS_FAILED,
                SEVERITY_INFO if project_overlay_ok else SEVERITY_ERROR,
                "ok" if project_overlay_ok else "missing",
                "project overlay is present" if project_overlay_ok else "project overlay is missing",
                path=flow_dir,
                next_action=None if project_overlay_ok else "flow setup project",
            )
        )
        items.append(
            diagnostic(
                "project.manifest",
                STATUS_OK if project_manifest_ok else STATUS_FAILED,
                SEVERITY_INFO if project_manifest_ok else SEVERITY_ERROR,
                "ok" if project_manifest_ok else "missing",
                "project manifest is present" if project_manifest_ok else "project manifest is missing",
                path=flow_dir / "flow.toml",
                next_action=None if project_manifest_ok else "flow setup project",
            )
        )
        items.append(
            diagnostic(
                "project.framework_copies",
                STATUS_OK if overlay_line == "clean" or overlay_line == "n/a" else STATUS_WARNING,
                SEVERITY_INFO if overlay_line == "clean" or overlay_line == "n/a" else SEVERITY_WARNING,
                "ok" if overlay_line == "clean" or overlay_line == "n/a" else "stale",
                f"project overlay: {overlay_line}",
                path=flow_dir,
                next_action=None if overlay_line == "clean" or overlay_line == "n/a" else "flow project migrate",
            )
        )
        if drifted_line is not None:
            items.append(
                diagnostic(
                    "project.framework_drift",
                    STATUS_WARNING,
                    SEVERITY_WARNING,
                    "drift",
                    f"{drifted_line} project file(s) differ from the framework",
                    path=flow_dir,
                    next_action="flow project audit",
                )
            )
        if replaces_error is not None:
            items.append(
                diagnostic(
                    "project.replaces",
                    STATUS_FAILED,
                    SEVERITY_ERROR,
                    "parse_error",
                    f"replacement wiring cannot be read: {replaces_error}",
                    path=flow_dir / "flow.toml",
                )
            )

    return items


def doctor(as_json: bool = False, check: bool = False) -> int:
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
    #
    # Two numbers, not one. `identical + orphaned` is exactly what `flow
    # project migrate` drives to zero, which is what lets that line name that
    # command. Drift is not clearable the same way — removing a drifted file
    # is opt-in and may destroy a customization — so summing it in would
    # produce a count the named remedy cannot reach zero, and doctor would nag
    # permanently about a state that is not a fault.
    overlay_line = "n/a"
    drifted_line = None
    if project_overlay_ok and SCAFFOLD_DIR.exists():
        try:
            report = audit_project(flow_dir, SCAFFOLD_DIR)
            counts = report.counts()
            copies = counts["identical"] + counts["orphaned"]
            overlay_line = (
                "clean"
                if copies == 0
                else f"{copies} framework copy/declaration(s) — run `flow project migrate`"
            )
            # `project-only` and `unreadable` stay out of both counts: the
            # first is the project's own content and the second could not be
            # compared, so neither is framework carryover. `conflict` is a
            # type mismatch, not drift.
            if counts["differs"]:
                drifted_line = counts["differs"]
        except Exception:
            overlay_line = "error"

    # Wrapped like the block above, and for the same reason: doctor is what
    # someone runs when their install is already broken, so a malformed
    # manifest must produce a line rather than a traceback.
    replaces_resolved: list = []
    replaces_rejected: list = []
    replaces_error = None
    if project_manifest_ok:
        try:
            wirings, replaces_rejected = declared_replaces(read_toml(flow_dir / "flow.toml"))
        except Exception as err:  # noqa: BLE001 — a bad manifest is a line, not a traceback
            # Said out loud. `manifest:` above is an existence check, so a
            # corrupt file already reports `ok` there; staying silent here too
            # would make it indistinguishable from a project with no wirings.
            replaces_error = err
        else:
            if SCAFFOLD_DIR.exists():
                replaces_resolved = resolve_replaces(wirings, SCAFFOLD_DIR, USER_OVERLAY_DIR)
            elif wirings:
                # Without a scaffold every `default` would look unresolvable
                # and every wiring would be reported as a typo.
                replaces_error = "framework scaffold missing — cannot check"

    legacy_heading = False
    if project_overlay_ok:
        project_md = flow_dir / "PROJECT.md"
        try:
            legacy_heading = project_md.is_file() and has_legacy_active_standards_heading(
                project_md.read_text()
            )
        except OSError:
            legacy_heading = False

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

    diagnostics = _doctor_diagnostics(
        root,
        flow_dir,
        root_is_flow_home,
        project_overlay_ok,
        project_manifest_ok,
        overlay_line,
        drifted_line,
        replaces_error,
        user_claude_managed_ok,
        user_claude_drift,
        user_codex_managed_ok,
        user_codex_drift,
        user_claude_agent_policy,
        user_codex_agent_policy,
    )
    store_path = usage_store.default_store_path(HOME)
    if store_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(f"file:{store_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            try:
                usage_freshness = telemetry_freshness.usage_freshness(conn)
                diagnostics.extend(telemetry_freshness.usage_diagnostics(usage_freshness))
                try:
                    import plugin_usage

                    plugin_payload = plugin_usage.usage_payload(
                        conn, home=HOME, project_root=Path.cwd()
                    )
                    diagnostics.append(
                        telemetry_freshness.plugin_diagnostic(
                            telemetry_freshness.plugin_freshness(plugin_payload)
                        )
                    )
                except Exception as err:  # noqa: BLE001 - doctor must survive broken stores.
                    diagnostics.append(
                        diagnostic(
                            "telemetry.plugin_usage",
                            STATUS_WARNING,
                            SEVERITY_WARNING,
                            "stale",
                            "plugin usage freshness could not be determined",
                            detail=str(err),
                            next_action="flow setup machine",
                        )
                    )
            finally:
                conn.close()
        except Exception as err:  # noqa: BLE001 - doctor must survive broken stores.
            diagnostics.append(
                diagnostic(
                    "telemetry.usage.status",
                    STATUS_FAILED,
                    SEVERITY_ERROR,
                    "parse_error",
                    "usage freshness could not be determined",
                    detail=str(err),
                )
            )
    else:
        diagnostics.append(
            diagnostic(
                "telemetry.usage.empty",
                STATUS_WARNING,
                SEVERITY_WARNING,
                "missing",
                "usage store has not been created",
                path=store_path,
                next_action="flow setup machine",
            )
        )
        diagnostics.append(
            diagnostic(
                "telemetry.plugin_usage",
                STATUS_WARNING,
                SEVERITY_WARNING,
                "missing",
                "plugin usage snapshots are unavailable until the usage store exists",
                next_action="flow setup machine",
            )
        )
    if as_json:
        print_json(support_payload("doctor", root, diagnostics, install=read_install_config()))
        return exit_code(diagnostics, check=check, fail_on_warnings=True)

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
    print(f"claude smoke:     {runtime_smoke_line('claude')}")
    print(f"codex sync:       {'ok' if user_codex_managed_ok else 'missing'}")
    print(f"codex drift:      {user_codex_drift}")
    print(f"codex skills:     {'ok' if user_codex_skills_dir.exists() else 'missing'}")
    print(f"codex agents:     {user_codex_agent_policy}")
    print(f"codex smoke:      {runtime_smoke_line('codex')}")

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
        return exit_code(diagnostics, check=check, fail_on_warnings=True)
    print(f"repo .flow:       {'ok' if project_overlay_ok else 'missing'}")
    print(f"manifest:         {'ok' if project_manifest_ok else 'missing'}")
    print(f"overlay:          {overlay_line}")
    if drifted_line is not None:
        print(f"drifted:          {drifted_line} file(s) differ from the framework")
        print("                  customized or stale — nothing local can tell which")
        print("                  `flow project audit` lists them")
    _print_replaces(replaces_resolved, replaces_rejected, replaces_error)
    if legacy_heading:
        print("PROJECT.md:       carries the retired `## Active project standards` section")
        print("                  the files it lists are not part of an overlay any more")
    print()
    print(_usage_section())
    return exit_code(diagnostics, check=check, fail_on_warnings=True)


def _print_replaces(resolved: list, rejected: list, error) -> None:
    """Render the `[[replaces]]` block, or nothing at all when there is none.

    Silent rather than `replaces: none` when a project declares no wirings:
    almost no project will, and a header announcing the absence of an optional
    feature on every `flow doctor` run is the kind of line people learn to
    skip past — which is how the lines that do matter get skipped too.

    `absent` is worded as a gap in *this user's* overlay, never as a fault in
    the project. A committed `.flow/flow.toml` names a path under
    `~/.flow/user/` that the author has and a teammate may not; telling the
    teammate their repo is broken would be both wrong and unactionable.
    """
    if error is not None:
        print(f"replaces:         cannot be read ({error})")
        return
    if not resolved and not rejected:
        return

    # Rejected entries are counted separately: an entry that failed validation
    # is precisely the thing that is *not* wired.
    print(f"replaces:         {len(resolved)} wired, {len(rejected)} invalid"
          if rejected else f"replaces:         {len(resolved)} wired")
    for entry in resolved:
        wiring = entry.wiring
        default = printable(wiring.default)
        with_ = printable(wiring.with_)
        if entry.status == REPLACE_OK:
            print(f"  ok       {default} -> {with_}")
        elif entry.status == REPLACE_ABSENT:
            print(f"  absent   {default} -> {with_}")
            print(f"           not in your {USER_OVERLAY_DIR}/{printable(str(Path(wiring.with_).parent))}/")
        elif entry.status == REPLACE_UNKNOWN:
            print(f"  unknown  {default}")
            print("           nothing resolves that name in the framework or your overlay")
    for entry in rejected:
        print(f"  invalid  {printable(entry.declared_by)}: {entry.reason}")


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
        payload["freshness"] = telemetry_freshness.plugin_freshness(payload)
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

    # `FRAMEWORK.md` is not required: a project stopped holding one when the
    # scaffold was thinned. It is still in `CAPABILITY_PATHS` so that `flow
    # project audit` can classify a legacy copy left over from before that
    # change — required-here and classifiable-there are different questions.
    required = [
        flow_dir / "flow.toml",
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
    print("next: run `flow doctor` or `flow project audit`")
    return 0
