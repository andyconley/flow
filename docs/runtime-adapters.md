# Runtime adapters

Flow keeps authoritative role instructions in Markdown with YAML metadata under
`scaffolds/default/agents/`. Shared `[[agents]]` entries in `flow.toml` declare
the 13 shipped roles, sources and semantic model tiers. Registered entries in
`~/.flow/user/flow.toml` replace same-name entries or add roles. The existing
`agent_body` pipeline composes expertise and instructions before rendering.
Project `.flow/` supplies context and artifacts; project adapter sync is retired.

## Generated formats and discovery

| Target | Flow backing definition | User discovery |
| --- | --- | --- |
| Claude ACP 0.63.0 | `~/.flow/generated/agents/claude/<role>.md` | `~/.claude/agents/<role>.md` |
| Codex ACP 1.10.0 / Codex 0.153.4 | `~/.flow/generated/agents/codex/<role>.toml` | `~/.codex/agents/<role>.toml` |
| OpenHands SDK 1.54.0 | `~/.flow/generated/agents/openhands/<role>.md` | `~/.agents/agents/<role>.md` |

Discovery files use relative symlinks, or managed copies when symlinks cannot
be created. Backing definitions survive source checkout swaps. Claude retains
supported name, description, tools, model/effort, skills and color metadata.
Permission mode metadata is not generated. Codex receives name, description,
encoded `developer_instructions`, supported model/reasoning policy and native
`web_search`; the ignored legacy `[tools].web_search` boolean is omitted.
Claude tool aliases are not Codex permissions and are reported as untranslated.
Skill references remain in instructions and native skill discovery.

OpenHands definitions carry description, instructions, named skills and
`model: inherit`, with `tools: []`. Stock external discovery therefore yields
instructions-only agents. Within Flow, contextual factories register the same
composed roles with stock SDK delegation, configured local tools and profiles,
project context and skills. Default task-enabled parents expose the other-role
roster; explicit lists control Flow factory registration and prompt hints; `specialists = []` removes the task tool. Implicit
child rosters are empty. Native parents use stock ACP/native discovery. ACP does
not receive SDK custom tools or condensers. Unsupported fields are recorded in
per-target `translation-report.json`; translation is not identical containment.

## Skills and hooks

Claude commands generate `~/.claude/skills/flow-*/SKILL.md`. Codex commands
generate `~/.agents/skills/flow-*/SKILL.md`, with required name/description
metadata. Existing native skill locations remain unchanged. Claude and Codex
hook scripts and hook settings continue through their existing renderers and
merge behavior; unrelated settings and handlers are preserved. Flow supplies no
new global permissions, credentials or cross-provider MCP dispatcher.

## Install, update and ownership

```sh
flow setup user
flow sync claude --user --check
flow sync codex --user --check
flow sync openhands --user --check
```

Remove `--check` to apply a target sync. Bootstrap installation, mode conversion
and release update sync all three targets using a fresh process from the newly
installed source. `flow update --resync` remains compatible; automatic syncing
also occurs without the flag. Develop mode requires explicit pull and sync.

Runtime manifests (`~/.claude/flow.managed.toml`,
`~/.codex/flow.managed.toml`, `~/.agents/flow-managed-agents.toml`) record ownership,
source, SHA-256 hashes and agent backing/link information. Replacement and
removal check previous hashes. Edited copies, modified backing definitions,
redirected links and unrelated/custom files are preserved. Any conflict stops
writes for that runtime. Hook/settings merges retain existing behavior.

Older hashless outputs that differ from the new output cannot be proven safe
and require review. Back up reported files, move intended edits into registered
user sources, then remove only reviewed generated files and resync. Do not delete
whole agent/skill directories or assume a force-overwrite mode exists.

See [the complete distribution contract](agent-distribution.md) for supported
fields, pinned parser/discovery evidence and coordinated live migration. See
[the migration guide](openhands-migration.md) for runtime selection, workspace
access and rollback. Offline tests verify parsing, discovery and registered
factories without live model calls; live runtime behavior remains separate
acceptance evidence.
