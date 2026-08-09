"""Rendering of generated runtime adapters: skills, frontmatter, manifests.

Everything a sync target writes to disk is produced here. The module is pure
string-building — it takes manifest dicts and command bodies and returns text.
It never touches the filesystem, which is why the sync engine can diff proposed
output against what is already on disk without a dry-run mode.

Claude skills go through `render_skill_from_command`, which builds frontmatter
from the manifest entry. Codex gets its own renderer rather than a parameter on
that one: it needs its description JSON-encoded and points at a different resync
command, and collapsing the two has repeatedly produced output subtly wrong for
one runtime.
"""

import json
from pathlib import Path

from fsutil import rel_posix
from paths import (
    CODEX_SKILL_DIR,
    GENERATED_MARKER,
    LEGACY_CODEX_SKILL_DIR,
    MODE_USER,
)


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
