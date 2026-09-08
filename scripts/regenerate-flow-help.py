#!/usr/bin/env python3
"""Regenerate Flow help tables from flow.toml.

Tables are generated between `<!-- generated:<name>:begin -->` /
`<!-- generated:<name>:end -->` markers. The command and agent tables live in
flow-help.md; README.md receives the same CLI command table:

  - slash-commands-table — from `[[claude.commands]]` `summary` fields,
    in the order they appear in flow.toml
  - cli-commands-table — from `[[help.cli_commands]]` entries
  - agents-table — from shared `[[agents]]` `summary` fields, sorted by name

Why: the hand-maintained tables drifted twice in successive feature commits
during the v0.4.0 → v0.4.1 cycle. Generating from `flow.toml` makes the
manifest the single source of truth and eliminates the drift class.

Usage:
  python3 scripts/regenerate-flow-help.py            # write changes
  python3 scripts/regenerate-flow-help.py --check    # exit 1 if regeneration would change anything
"""
from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
FLOW_TOML = REPO_ROOT / "scaffolds" / "default" / "flow.toml"
FLOW_HELP = REPO_ROOT / "scaffolds" / "default" / "commands" / "flow-help.md"
README = REPO_ROOT / "README.md"


def read_toml(path: Path) -> dict:
    """Read a manifest using stdlib tomllib.

    Requires Python 3.11+, unlike the CLI, which supports 3.10 and carries a
    fallback parser in `cli/flowtoml.py` for it. This is a dev-only tool that
    rewrites files in `scaffolds/`; it never runs on an end user's machine, so
    it does not have to honour the CLI's supported-interpreter floor. The copy
    of that fallback parser that used to live here was dead code on every
    interpreter that actually ran it.
    """
    return tomllib.loads(path.read_text())


def render_table(rows: list[tuple[str, str]], headers: tuple[str, str]) -> str:
    h1, h2 = headers
    lines = [f"| {h1} | {h2} |", "|---|---|"]
    for col1, col2 in rows:
        lines.append(f"| {col1} | {col2} |")
    return "\n".join(lines)


def build_slash_commands_table(data: dict) -> str:
    commands = data.get("claude", {}).get("commands", [])
    rows: list[tuple[str, str]] = []
    for cmd in commands:
        name = cmd.get("name", "")
        summary = cmd.get("summary")
        if not summary:
            raise SystemExit(
                f"flow.toml [[claude.commands]] entry missing `summary`: name={name!r}\n"
                "add a one-line summary suitable for the flow-help command table."
            )
        rows.append((f"/{name}", summary))
    return render_table(rows, ("Command", "Use when"))


def build_cli_commands_table(data: dict) -> str:
    entries = data.get("help", {}).get("cli_commands", [])
    rows: list[tuple[str, str]] = []
    for entry in entries:
        invocation = entry.get("invocation", "")
        summary = entry.get("summary")
        if not invocation:
            raise SystemExit("flow.toml [[help.cli_commands]] entry missing `invocation`")
        if not summary:
            raise SystemExit(
                f"flow.toml [[help.cli_commands]] entry missing `summary`: invocation={invocation!r}"
            )
        rows.append((f"`{invocation}`", summary))
    return render_table(rows, ("Command", "Use when"))


def build_agents_table(data: dict) -> str:
    agents = data.get("agents", [])
    rows: list[tuple[str, str]] = []
    for agent in sorted(agents, key=lambda a: a.get("name", "")):
        name = agent.get("name", "")
        summary = agent.get("summary")
        if not summary:
            raise SystemExit(
                f"flow.toml [[agents]] entry missing `summary`: name={name!r}\n"
                "add a one-line summary suitable for the flow-help agents table."
            )
        rows.append((name, summary))
    return render_table(rows, ("Agent", "Role"))


BUILDERS = {
    "slash-commands-table": build_slash_commands_table,
    "cli-commands-table": build_cli_commands_table,
    "agents-table": build_agents_table,
}


def replace_section(text: str, marker: str, content: str, *, target: Path = FLOW_HELP) -> str:
    """Replace the body between `<!-- generated:<marker>:begin ... -->` and `<!-- generated:<marker>:end -->`."""
    begin_re = re.compile(rf"(<!-- generated:{re.escape(marker)}:begin[^>]*-->)")
    end_re = re.compile(rf"(<!-- generated:{re.escape(marker)}:end -->)")

    begin_match = begin_re.search(text)
    if not begin_match:
        raise SystemExit(f"could not find begin marker for {marker} in {target.name}")
    end_match = end_re.search(text, begin_match.end())
    if not end_match:
        raise SystemExit(
            f"could not find end marker for {marker} in {target.name} "
            f"(after begin at {begin_match.start()})"
        )

    return (
        text[: begin_match.end()]
        + "\n"
        + content
        + "\n"
        + text[end_match.start():]
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 with a diff if regeneration would change generated help targets; do not write",
    )
    args = parser.parse_args()

    if not FLOW_TOML.exists():
        sys.stderr.write(f"flow.toml not found at {FLOW_TOML}\n")
        return 1
    data = read_toml(FLOW_TOML)
    targets = {
        FLOW_HELP: tuple(BUILDERS),
        README: ("cli-commands-table",),
    }
    stale: list[tuple[Path, str, str]] = []
    for target, markers in targets.items():
        if not target.exists():
            sys.stderr.write(f"generated help target not found at {target}\n")
            return 1
        original = target.read_text()
        rewritten = original
        for marker in markers:
            rewritten = replace_section(
                rewritten, marker, BUILDERS[marker](data), target=target
            )
        if rewritten != original:
            stale.append((target, original, rewritten))

    if not stale:
        for target in targets:
            print(f"{target.relative_to(REPO_ROOT)} is up to date.")
        return 0

    if args.check:
        for target, original, rewritten in stale:
            sys.stderr.write(
                "".join(
                    difflib.unified_diff(
                        original.splitlines(keepends=True),
                        rewritten.splitlines(keepends=True),
                        fromfile=str(target.relative_to(REPO_ROOT)) + " (on disk)",
                        tofile=str(target.relative_to(REPO_ROOT)) + " (regenerated)",
                    )
                )
            )
        sys.stderr.write("\ngenerated Flow help is out of date.\n")
        sys.stderr.write("run `python3 scripts/regenerate-flow-help.py` to apply.\n")
        return 1

    for target, _original, rewritten in stale:
        target.write_text(rewritten)
        print(f"updated {target.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
