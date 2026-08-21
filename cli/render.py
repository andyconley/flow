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
)


def parse_frontmatter(body: str) -> tuple[dict, str]:
    """Parse the simple YAML frontmatter shape used by Flow source files."""
    if not body.startswith("---\n"):
        return {}, body
    closing = body.find("\n---\n", 4)
    if closing == -1:
        return {}, body

    raw = body[4:closing]
    content = body[closing + 5 :].lstrip("\n")
    frontmatter: dict[str, object] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    list_key: str | None = None

    def flush_multiline() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            frontmatter[current_key] = " ".join(line.strip() for line in current_lines).strip()
            current_key = None
            current_lines = []

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if current_key is not None:
            if line.startswith(" ") or stripped.startswith("- "):
                current_lines.append(stripped[2:] if stripped.startswith("- ") else stripped)
                continue
            flush_multiline()
        if stripped.startswith("- ") and list_key:
            current = frontmatter.setdefault(list_key, [])
            if isinstance(current, list):
                current.append(stripped[2:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        list_key = None
        if value == ">":
            current_key = key
            current_lines = []
        elif value == "":
            frontmatter[key] = []
            list_key = key
        else:
            frontmatter[key] = value.strip('"')
    flush_multiline()
    return frontmatter, content


def render_yaml_frontmatter(frontmatter: dict) -> list[str]:
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return lines


def toml_string(value: str) -> str:
    return json.dumps(value)


def routing_hints_for(target: str, agents: list[dict], model_tiers: dict) -> str:
    if not agents:
        return ""
    lines = [
        "## Flow Agent Routing",
        "",
        "When this command's Composition section calls for role agents, use these Flow-managed runtime agents and keep the task bounded to the role.",
        "",
        "| Agent | Tier | Runtime model | Effort |",
        "|---|---|---|---|",
    ]
    for agent in sorted(agents, key=lambda a: a.get("name", "")):
        tier = agent.get("model_tier", "")
        runtime_policy = model_tiers.get(tier, {}).get(target, {})
        effort = runtime_policy.get("model_reasoning_effort", runtime_policy.get("effort", ""))
        lines.append(
            f"| {agent.get('name', '')} | {tier} | {runtime_policy.get('model', '')} | {effort} |"
        )
    lines.extend(
        [
            "",
            "These hints are generated from `flow.toml`. If a runtime ignores configured subagent models, use the named agent anyway and verify with the manual smoke test from `flow doctor`.",
            "",
        ]
    )
    return "\n".join(lines)


def hook_command_for(script: str) -> str:
    """The absolute hook command path.

    Took a `mode` until project-level sync was retired. Adapters are only ever
    generated at user level now, so `$CLAUDE_PROJECT_DIR` — which resolved to
    whichever repo a session was launched in — has nothing left to point at.
    """
    return f'"$HOME"/.claude/hooks/{script}'


def codex_hook_command_for(script: str) -> str:
    """Codex twin of `hook_command_for`.

    The project form used `$(git rev-parse --show-toplevel)`, because Codex has
    no `$CLAUDE_PROJECT_DIR` equivalent. It went with project sync.
    """
    return f'"$HOME"/.codex/hooks/{script}'


def source_ref_for(source_rel: str, origin: str = "framework") -> str:
    """The source-of-truth reference string used in managed manifests.

    `origin` is "framework" for entries from `scaffolds/default/flow.toml` and
    "user" for entries that came from the `~/.flow/user/` user overlay (see
    `merge_user_overlay`). The reference path differs so a reader of the
    managed manifest can tell at a glance which entries are user-customized.
    """
    if origin == "user":
        return f'~/.flow/user/{source_rel}'
    return f'~/.flow/source/scaffolds/default/{source_rel}'


def manifest_ref_for() -> str:
    """The source_manifest reference used in managed manifests."""
    return '~/.flow/source/scaffolds/default/flow.toml'


def render_codex_skill(
    name: str,
    description: str,
    source_ref: str,
    body: str,
    routing_hints: str = "",
) -> str:
    lines = [
        "---",
        f"name: {name}",
        f"description: {json.dumps(description)}",
        "---",
        "",
        f"<!-- {GENERATED_MARKER} Edit `{source_ref}` and rerun `flow sync codex --user`. -->",
        "",
        body.rstrip(),
        "",
    ]
    if routing_hints:
        lines.extend([routing_hints.rstrip(), ""])
    lines.extend(
        [
            "## Invocation Arguments",
            "",
            "If arguments were provided after the skill name, treat them as the specific focus for this run:",
            "",
            "`$ARGUMENTS`",
            "",
        ]
    )
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


def render_skill_from_command(
    command: dict, skill_defaults: dict, routing_hints: str = ""
) -> str:
    source_path = command["source"]
    body = command["_body"]
    # The edit hint must point at a file that actually exists, which depends
    # on origin: a user-overlay command's source lives under ~/.flow/user/,
    # while a framework command's lives under the installed scaffold
    # under ~/.flow/source/scaffolds/default/ (there is no `.flow/` anywhere
    # near ~/.claude/skills/); only project mode's `.flow/<source>` matches
    # the classic hint. `source_ref_for` already encodes exactly this
    # decision for the managed manifest — reuse it rather than restate it.
    source_ref = source_ref_for(source_path, command.get("_origin", "framework"))
    resync = "flow sync claude --user"
    edit_hint = f"Edit `{source_ref}` and run `{resync}`."
    lines = build_skill_frontmatter(command["name"], command, skill_defaults)
    lines.extend(
        [
            "",
            f"<!-- {GENERATED_MARKER} {edit_hint} -->",
            "",
            body.rstrip(),
            "",
        ]
    )
    if routing_hints:
        lines.extend([routing_hints.rstrip(), ""])
    lines.extend(
        [
            "## Invocation Arguments",
            "",
            "If arguments were provided after the skill name, treat them as the specific focus for this run:",
            "",
            "`$ARGUMENTS`",
            "",
        ]
    )
    return "\n".join(lines)


def render_claude_agent(source_ref: str, body: str, policy: dict) -> str:
    frontmatter, content = parse_frontmatter(body)
    for key, value in policy.items():
        if value:
            frontmatter[key] = value
    marker = f"<!-- {GENERATED_MARKER} Edit `{source_ref}` and run `flow sync claude --user`. -->"
    lines = render_yaml_frontmatter(frontmatter)
    lines.extend(["", marker, "", content.rstrip(), ""])
    return "\n".join(lines)


def render_codex_agent(name: str, source_ref: str, body: str, policy: dict) -> str:
    frontmatter, content = parse_frontmatter(body)
    description = str(frontmatter.get("description", f"Flow agent: {name}"))
    safe_body = content.rstrip().replace('"""', '""\\"')
    lines = [
        f"name = {toml_string(name)}",
        f"description = {toml_string(description)}",
        f'developer_instructions = """{safe_body}\n"""',
    ]
    model = policy.get("model")
    if model:
        lines.append(f"model = {toml_string(model)}")
    effort = policy.get("model_reasoning_effort")
    if effort:
        lines.append(f"model_reasoning_effort = {toml_string(effort)}")
    lines.extend(
        [
            "",
            f"# {GENERATED_MARKER} Edit `{source_ref}` and run `flow sync codex --user`.",
            "",
        ]
    )
    return "\n".join(lines)


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
