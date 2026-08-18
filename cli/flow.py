#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime
from pathlib import Path

# Sibling modules. The launcher runs cli/flow.py directly, which puts cli/ on
# sys.path — but importing this file programmatically (importlib, as the test
# suite does) does not. Append our own directory so the import holds either way.
# Appended rather than prepended so stdlib still wins on any name collision.
sys.path.append(str(Path(__file__).resolve().parent))

# Every command is implemented in a sibling module; this file owns only the
# argparse declaration and the dispatch that maps parsed args onto them.
#
# The `# noqa: E402` markers are load-bearing, not decoration: these imports
# have to follow the sys.path append above, so they cannot sit at the top of
# the file where E402 expects them.
from baseline import baseline_command  # noqa: E402
from cost import (  # noqa: E402
    BUCKET_DAY,
    BUCKET_WEEK,
    DEFAULT_ACTIVE_WITHIN_MINUTES,
    DEFAULT_SESSIONS_LIMIT,
    DEFAULT_WINDOW_DAYS,
    cost_active_command,
    cost_sessions_command,
    cost_summary_command,
    cost_trend_command,
    cost_verdict_command,
    cost_warn_command,
)
from diagnostics import bootstrap, doctor, help_command  # noqa: E402
from harvest import harvest_claude_command, harvest_codex_command  # noqa: E402
from lifecycle import install_command, update_command  # noqa: E402
from normalize import normalize_command  # noqa: E402
from overlay import overlay_check_command, overlay_status_command  # noqa: E402
from plugin_usage import (  # noqa: E402
    plugin_usage_show_command,
    plugin_usage_snapshot_command,
)
from setup import (  # noqa: E402
    refresh_project,
    setup_machine,
    setup_project,
    setup_user,
)
from sync import sync_target  # noqa: E402


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
        description="Copy the project overlay scaffold into repo/.flow without touching existing files.",
    )
    setup_user_parser = setup_sub.add_parser(
        "user",
        help="install flow at the user level so it is active in every supported runtime session",
        description="Generate user-level Claude and Codex skills, agents, hooks, and managed manifests from the framework scaffold.",
    )
    setup_user_parser.add_argument(
        "--overlay-repo",
        metavar="URL",
        help="give ~/.flow/user/ a git home at URL: clone it when the overlay is absent, or init in place and add the remote when it already has content (never clobbers existing files, never commits)",
    )

    refresh = sub.add_parser(
        "refresh",
        help="repair missing files in an existing repo/.flow",
        description="Refresh an existing repo-local .flow without overwriting local edits.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Example:\n  flow refresh project\n",
    )
    refresh_sub = refresh.add_subparsers(dest="refresh_target", required=True, title="refresh targets")
    refresh_project_parser = refresh_sub.add_parser(
        "project",
        help="copy missing overlay files into repo/.flow",
        description=(
            "Bring an existing project overlay forward without overwriting local edits. "
            "By default this refreshes only overlay core files plus command, agent, "
            "and standard sources registered in .flow/flow.toml. Existing files whose "
            "content differs are reported as update candidates; use --interactive to choose updates."
        ),
    )
    refresh_project_parser.add_argument(
        "--all",
        action="store_true",
        help="backfill the full framework scaffold, including commands, agents, standards, and templates",
    )
    refresh_project_parser.add_argument(
        "--interactive",
        action="store_true",
        help="prompt before replacing existing files whose content differs from the framework",
    )

    harvest = sub.add_parser(
        "harvest",
        help="incrementally read a harness's local session transcripts into the usage store",
        description="Read a harness's local session transcripts into ~/.flow/usage.db, resuming from the last-read position per file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  flow harvest codex\n"
            "  flow harvest claude\n"
            "  flow harvest claude --rescan --since 2026-08-01 --dry-run\n"
            "  flow harvest claude --rescan --since 2026-08-01\n"
        ),
    )
    harvest_sub = harvest.add_subparsers(dest="harvest_target", required=True, title="harvest targets")
    harvest_sub.add_parser(
        "codex",
        help="harvest ~/.codex/sessions/ into the usage store",
        description="Incrementally read Codex session transcripts, writing session and turn records into the usage store's raw layer.",
    )
    harvest_claude_parser = harvest_sub.add_parser(
        "claude",
        help="harvest ~/.claude/projects/ into the usage store",
        description="Incrementally read Claude Code session transcripts, writing session and turn records into the usage store's raw layer.",
    )
    harvest_claude_parser.add_argument(
        "--rescan",
        action="store_true",
        help="rewind already-recorded files' watermarks first and re-read them from the start, so already-harvested sessions pick up corrected output token counts, compaction events, titles, cwd, and title provenance retroactively",
    )
    harvest_claude_parser.add_argument(
        # The original name for this flag, from when title capture was all it
        # did. Kept working rather than removed: it is in muscle memory and
        # possibly in scripts, and the behaviour it names is a strict subset
        # of what --rescan now does. Hidden so help output teaches one name.
        "--backfill",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    harvest_claude_parser.add_argument(
        "--since",
        metavar="DATE",
        help="with --rescan, only rewind files modified on or after DATE (YYYY-MM-DD or a full ISO timestamp)",
    )
    harvest_claude_parser.add_argument(
        "--session",
        metavar="ID",
        help="with --rescan, only rewind files whose path contains ID — a session uuid reaches that session's main transcript and its subagent files together",
    )
    harvest_claude_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --rescan, report how many files and stored turns are in scope and exit without writing anything",
    )

    sub.add_parser(
        "normalize",
        help="recompute the usage store's normalized layer from raw records",
        description="Project every harness's raw turn records into one shared token convention. Only rows without a current-version normalized counterpart are recomputed.",
    )

    cost = sub.add_parser(
        "cost",
        help="read token usage back out of the usage store",
        description="Read `~/.flow/usage.db`'s normalized layer (ensuring the store's schema exists first, like every other command). `summary` and `sessions` never touch turn_raw, turn_norm, or session data; `active` runs the incremental Claude harvest and a normalize pass first so its answer is current.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  flow cost summary\n  flow cost summary --all --json\n  flow cost sessions --days 30\n  flow cost active\n  flow cost active --within 180\n  flow cost trend --days 30 --bucket week\n  flow cost baseline --all\n",
    )
    cost_sub = cost.add_subparsers(dest="cost_target", required=True, title="cost views")

    cost_summary_parser = cost_sub.add_parser(
        "summary",
        help="token totals by harness/model, plus Codex's capacity gauge",
        description="Token totals grouped by harness and model within the window, plus the most recent Codex capacity reading as a separate gauge line.",
    )
    cost_sessions_parser = cost_sub.add_parser(
        "sessions",
        help="token totals by session, most recently active first",
        description="Token totals grouped by session, within the window, most recently active first.",
    )
    cost_trend_parser = cost_sub.add_parser(
        "trend",
        help="efficiency per time bucket — is session hygiene actually working",
        description="One row per time bucket and harness: main-agent turns, distinct sessions, mean context per turn, input:output, weighted tokens per 1,000 output, subagent share, and compaction events split by trigger. Weighted columns are Claude-only; see data/token_weights.json.",
    )
    cost_trend_parser.add_argument(
        "--bucket",
        choices=(BUCKET_DAY, BUCKET_WEEK),
        default=BUCKET_DAY,
        help=f"bucket size (default: {BUCKET_DAY})",
    )
    cost_trend_parser.add_argument(
        "--harness",
        choices=("claude", "codex"),
        help="restrict to one harness (default: both, one row per bucket per harness)",
    )
    cost_baseline_parser = cost_sub.add_parser(
        "baseline",
        help="the always-on token floor, and when it moved",
        description="The static prefix every session pays before any work — system prompt, tool definitions, MCP instructions, agent and skill descriptions, CLAUDE.md, memory files. Estimated from cache_read_tokens on a session's first turn, where no conversation exists yet, and reported with the changes that cleared threshold. Detects deliberate reconfiguration, not gradual drift; see data/baseline_thresholds.json.",
    )
    cost_baseline_parser.add_argument(
        "--harness",
        choices=("claude", "codex"),
        help="restrict to one harness (default: both, one block each)",
    )
    cost_baseline_parser.add_argument(
        "--by-cwd",
        action="store_true",
        help="estimate per working directory instead of pooling (thins buckets sharply)",
    )
    cost_active_parser = cost_sub.add_parser(
        "active",
        help="context status + /clear-or-/compact recommendation per active session",
        description="Per-active-session context percentage, carry above session start, idle time, and a /clear-or-/compact recommendation — worst carry first. Harvests and normalizes incrementally before answering. Supersedes token-report --active.",
    )
    cost_active_parser.add_argument(
        "--within",
        type=int,
        default=DEFAULT_ACTIVE_WITHIN_MINUTES,
        metavar="N",
        help=f"count a session as active if its latest turn is within N minutes (default: {DEFAULT_ACTIVE_WITHIN_MINUTES})",
    )
    cost_active_parser.add_argument(
        "--json",
        action="store_true",
        help="print the same result as JSON instead of an aligned table",
    )
    cost_verdict_parser = cost_sub.add_parser(
        "verdict",
        help="live /clear-or-/compact judgment for one transcript (Stop-hook engine)",
        description="Live judgment for one session: incrementally harvests the transcript, normalizes, and judges carry from the store. --hook reads the runtime's hook JSON on stdin and writes/removes the verdict file silently; --transcript prints the judgment line. Supersedes token-report --verdict.",
    )
    verdict_mode = cost_verdict_parser.add_mutually_exclusive_group(required=True)
    verdict_mode.add_argument(
        "--transcript",
        metavar="PATH",
        help="print the judgment line for this transcript (silence = nothing to say)",
    )
    verdict_mode.add_argument(
        "--hook",
        action="store_true",
        help="Stop-hook mode: read hook JSON from stdin, write/remove the verdict file, print nothing",
    )
    cost_warn_parser = cost_sub.add_parser(
        "warn",
        help="pre-execution context warning (UserPromptSubmit-hook engine)",
        description="Reads the verdict file the Stop hook last wrote — no computation at prompt time — and prints a one-line advisory only when carry is heavy and has grown since the last warning. Informational only; always exits 0.",
    )
    cost_warn_parser.add_argument(
        "--hook",
        action="store_true",
        required=True,
        help="UserPromptSubmit-hook mode: read hook JSON from stdin",
    )
    plugin_usage_parser = sub.add_parser(
        "plugin-usage",
        help="sample and report which installed plugins and skills are actually used",
        description="Samples the plugin and skill usage counters the harness maintains in its own config into flow's store, and reports movement over time. Separate from `flow doctor`, which renders the same read model but never writes: doctor is read-only by contract.",
    )
    plugin_usage_sub = plugin_usage_parser.add_subparsers(
        dest="plugin_usage_target", required=True
    )
    plugin_usage_snapshot_parser = plugin_usage_sub.add_parser(
        "snapshot",
        help="record the current counters if they have moved since the last look",
        description="Stats the harness config, compares it against the recorded watermark, and stores any state not already held. Safe to run concurrently with `flow harvest`: observations are keyed by their content, so two writers seeing one revision collapse to a single row.",
    )
    plugin_usage_snapshot_parser.add_argument(
        "--hook",
        action="store_true",
        help="SessionStart-hook mode: shorter busy timeout, prints nothing, always exits 0",
    )
    plugin_usage_show_parser = plugin_usage_sub.add_parser(
        "show",
        help="print the usage report `flow doctor` renders as a section",
        description="The same read model doctor renders, standalone. Hook-registering plugins are reported separately from deliberate invocations: the harness increments a plugin's counter once per hook firing, so those numbers measure how many hook events a plugin declares rather than anything a person did.",
    )
    plugin_usage_show_parser.add_argument(
        "--json",
        action="store_true",
        help="emit the payload as JSON instead of the rendered section",
    )
    overlay_parser = sub.add_parser(
        "overlay",
        help="inspect the user overlay's version-control state",
        description="Report and advise on `~/.flow/user/`'s version control. Read-only apart from the nudge's throttle marker; initialization lives in `flow setup user --overlay-repo`.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  flow overlay status\n",
    )
    overlay_sub = overlay_parser.add_subparsers(dest="overlay_target", required=True, title="overlay views")
    overlay_sub.add_parser(
        "status",
        help="version-control state of the user overlay",
        description="The `doctor` overlay line on its own, plus the remote and the uncommitted paths behind its counts.",
    )
    overlay_check_parser = overlay_sub.add_parser(
        "check",
        help="overlay-commit nudge (PostToolUse / UserPromptSubmit hook engine)",
        description="Prints one advisory line when the overlay's repository has uncommitted or unpushed work, throttled per event. Silent when the overlay is untracked, clean, or absent. Informational only; always exits 0.",
    )
    overlay_check_parser.add_argument(
        "--hook",
        action="store_true",
        required=True,
        help="hook mode: read hook JSON from stdin and branch on hook_event_name",
    )

    for cost_parser in (
        cost_summary_parser,
        cost_sessions_parser,
        cost_trend_parser,
        cost_baseline_parser,
    ):
        window = cost_parser.add_mutually_exclusive_group()
        window.add_argument(
            "--days",
            type=int,
            default=DEFAULT_WINDOW_DAYS,
            metavar="N",
            help=f"show the last N days (default: {DEFAULT_WINDOW_DAYS})",
        )
        window.add_argument(
            "--all",
            action="store_true",
            help="show every row ever normalized (cannot be combined with --days)",
        )
        cost_parser.add_argument(
            "--json",
            action="store_true",
            help="print the same result as JSON instead of an aligned table",
        )
    cost_sessions_parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_SESSIONS_LIMIT,
        metavar="N",
        help=f"cap the number of sessions shown, most recently active first (default: {DEFAULT_SESSIONS_LIMIT}; 0 = unlimited)",
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
            "  codex   Generate .agents skills, .codex agents, hooks, hooks.json, and a managed manifest.\n\n"
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
        help="convert an existing install between develop and release modes",
        description=(
            "Mode conversion for an existing install. Convert ~/.flow/source between "
            "develop mode (symlink to a clone) and release mode (real directory of "
            "copied content). The clone is never deleted; switching to release mode "
            "is non-destructive to the source repo."
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
        help="update a release install to the latest tagged release",
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
        return setup_user(overlay_repo=args.overlay_repo)
    if args.command == "refresh" and args.refresh_target == "project":
        return refresh_project(all_files=args.all, interactive=args.interactive)
    if args.command == "harvest" and args.harvest_target == "codex":
        return harvest_codex_command()
    if args.command == "harvest" and args.harvest_target == "claude":
        rescan = args.rescan or args.backfill
        # The narrowing flags do nothing without a rescan to narrow, so
        # accepting them alone would silently run a plain incremental harvest
        # while the caller believed they had scoped something — including
        # `--dry-run`, which would then write. Refused rather than ignored.
        if not rescan and (args.since or args.session or args.dry_run):
            parser.error("--since, --session, and --dry-run require --rescan")
        if args.since is not None:
            # Parsed here rather than left to blow up inside the command: an
            # unparseable date is a usage error, and a raw ValueError
            # traceback reads as a crash in the tool rather than a typo.
            try:
                datetime.fromisoformat(args.since)
            except ValueError:
                parser.error(
                    f"--since: {args.since!r} is not a date — "
                    f"use YYYY-MM-DD or a full ISO timestamp"
                )
        return harvest_claude_command(
            rescan=rescan,
            since=args.since,
            session=args.session,
            dry_run=args.dry_run,
        )
    if args.command == "normalize":
        return normalize_command()
    if args.command == "cost" and args.cost_target == "summary":
        return cost_summary_command(days=args.days, show_all=args.all, as_json=args.json)
    if args.command == "cost" and args.cost_target == "sessions":
        return cost_sessions_command(days=args.days, show_all=args.all, as_json=args.json, limit=args.limit)
    if args.command == "cost" and args.cost_target == "trend":
        return cost_trend_command(
            days=args.days,
            show_all=args.all,
            bucket=args.bucket,
            harness=args.harness,
            as_json=args.json,
        )
    if args.command == "cost" and args.cost_target == "baseline":
        return baseline_command(
            days=args.days,
            show_all=args.all,
            harness=args.harness,
            by_cwd=args.by_cwd,
            as_json=args.json,
        )
    if args.command == "cost" and args.cost_target == "active":
        return cost_active_command(within=args.within, as_json=args.json)
    if args.command == "cost" and args.cost_target == "verdict":
        return cost_verdict_command(transcript=args.transcript, hook=args.hook)
    if args.command == "cost" and args.cost_target == "warn":
        return cost_warn_command()
    if args.command == "plugin-usage" and args.plugin_usage_target == "snapshot":
        return plugin_usage_snapshot_command(hook=args.hook)
    if args.command == "plugin-usage" and args.plugin_usage_target == "show":
        return plugin_usage_show_command(as_json=args.json)
    if args.command == "overlay" and args.overlay_target == "status":
        return overlay_status_command()
    if args.command == "overlay" and args.overlay_target == "check":
        return overlay_check_command()
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
