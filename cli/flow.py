#!/usr/bin/env python3
import argparse
import sys
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
from cost import DEFAULT_WINDOW_DAYS, cost_sessions_command, cost_summary_command  # noqa: E402
from diagnostics import bootstrap, doctor, help_command  # noqa: E402
from harvest import harvest_claude_command, harvest_codex_command  # noqa: E402
from lifecycle import install_command, update_command  # noqa: E402
from normalize import normalize_command  # noqa: E402
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

    harvest = sub.add_parser(
        "harvest",
        help="incrementally read a harness's local session transcripts into the usage store",
        description="Read a harness's local session transcripts into ~/.flow/usage.db, resuming from the last-read position per file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  flow harvest codex\n  flow harvest claude\n",
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
        "--backfill-titles",
        action="store_true",
        help="rewind every already-recorded file's watermark first, so sessions harvested before title capture existed pick up session.title retroactively",
    )

    sub.add_parser(
        "normalize",
        help="recompute the usage store's normalized layer from raw records",
        description="Project every harness's raw turn records into one shared token convention. Only rows without a current-version normalized counterpart are recomputed.",
    )

    cost = sub.add_parser(
        "cost",
        help="read token usage back out of the usage store",
        description="Read `~/.flow/usage.db`'s normalized layer (ensuring the store's schema exists first, like every other command). Never touches turn_raw, turn_norm, or session data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n  flow cost summary\n  flow cost summary --all --json\n  flow cost sessions --days 30\n",
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
    for cost_parser in (cost_summary_parser, cost_sessions_parser):
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
    if args.command == "harvest" and args.harvest_target == "codex":
        return harvest_codex_command()
    if args.command == "harvest" and args.harvest_target == "claude":
        return harvest_claude_command(backfill_titles=args.backfill_titles)
    if args.command == "normalize":
        return normalize_command()
    if args.command == "cost" and args.cost_target == "summary":
        return cost_summary_command(days=args.days, show_all=args.all, as_json=args.json)
    if args.command == "cost" and args.cost_target == "sessions":
        return cost_sessions_command(days=args.days, show_all=args.all, as_json=args.json)
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
