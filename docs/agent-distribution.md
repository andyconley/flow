# Flow role distribution

Flow's 13 Markdown roles in `scaffolds/default/agents/` remain authoritative.
`[[agents]]` in the scaffold manifest declares the roster. The existing
`~/.flow/user/flow.toml` overlay can replace or add a role and point to a custom
source. Expertise composition still uses the existing `agent_body` pipeline.
No role instructions need three independently maintained copies.

| Runtime | Generated backing definitions | Discovery surface | Format |
| --- | --- | --- | --- |
| Claude ACP 0.63.0 | `~/.flow/generated/agents/claude/<role>.md` | `~/.claude/agents/<role>.md` | YAML metadata + Markdown |
| Codex ACP 1.10.0 / Codex 0.162.0-alpha.17.2 | `~/.flow/generated/agents/codex/<role>.toml` | `~/.codex/agents/<role>.toml` | name, description, developer_instructions, model/reasoning policy |
| OpenHands SDK 1.54.0 | `~/.flow/generated/agents/openhands/<role>.md` | `~/.agents/agents/<role>.md` | SDK Markdown AgentDefinition |

Each `<role>` is one of: architect, solution-architect, business-analyst,
quality-reviewer, data-engineer, lead-developer, product-manager,
security-reviewer, sre, support-lead, tech-writer, test-engineer, ux-specialist.

Discovery files are relative symlinks to Flow's generated directory. A
filesystem that rejects symlinks receives a hash-owned copy instead; later
syncs preserve that installation mode. The generated directory is outside the
source checkout, so release source swaps do not strand discovery links.
Codex sync also explicitly registers those files in a delimited, hash-owned
block in `~/.codex/config.toml`, using `[agents."<role>"]` and `config_file`.
This supplements directory discovery on clients where the generated files are
present but the agent type is unavailable. Registrations point to the stable generated backing files. The existing
discovery symlinks remain intact; the tested Codex build accepted backing-file
registrations while rejecting registrations through those discovery links.
No model, effort, tool, permission, trust, or profile settings are added to the
registration block. Start a fresh native session to load the updated roster.
Existing commands and hooks continue through the same renderers and manifests.
Native skills stay at their existing Claude and `.agents/skills` locations.

## Install and update

`install-flow.sh` renders all three surfaces after installing and checking its
launcher. `flow setup user` also syncs all three. Release updates and mode
conversions always run the newly installed CLI in a fresh subprocess, avoiding
renderers imported from the previous source version. `--resync` remains a
compatibility flag. Develop-mode updates continue to require an explicit git
pull, followed by `flow setup user` or the three sync commands.

```sh
flow sync claude --user
flow sync codex --user
flow sync openhands --user
```

Add `--check` to inspect drift without writes. Every target produces a
`translation-report.json` next to its backing definitions, with one entry per
role and the source fields it cannot translate. The CLI prints these warnings;
JSON mode leaves the report in the proposed/generated artifact rather than
mixing prose into diagnostic JSON.

### Runtime activation during an older-release upgrade

Current install/update code provisions the pinned SDK before source activation,
with source/configuration/launcher/runtime-pointer rollback on activation failure.
A predecessor updater may instead replace source first. The new explicitly
installed CLI detects the missing activation marker on `workflow execute`,
explicit `update` (without `--check`), or `bootstrap`, binds the pinned SDK and re-executes the requested
command. It does not activate from a project checkout or retired execution path.
User profiles and verified custom pinned Python remain preserved.

If this bridge fails, the prior launcher/configuration/runtime pointer remain
and stdlib inspection works; OpenHands-dependent commands report failure.
Retry `flow update` to repair. The bridge cannot restore old source already
deleted by the predecessor. See [migration and rollback](openhands-migration.md#upgrade-through-a-predecessor-installer).


Inspection remains free of installation side effects: `workflow status`,
`workflow runtime`, runtime readiness/smoke, and `update --check` report existing
state without provisioning. Workflow init, approve, archive and native-handoff
also do not activate the bridge because they do not require SDK execution.
Readiness reports a missing runtime; use `workflow execute`, explicit
`flow update`, or bootstrap to activate an unmarked installed upgrade.

## Ownership and migration

The existing managed manifest now records SHA-256 hashes for replacement
outputs and the backing path for agent links. An update checks the previous
hash before replacing or removing an owned file. Editing a discovery link's
backing content, editing a managed copy or command skill, or redirecting a link
causes a conflict. A target with any conflict performs no writes for that
runtime. Unrelated custom agents, skills and other files are retained. Merged
settings and hook configuration retain the existing merge behavior.

Codex role registration preserves all text outside its marked block, including
comments, formatting, custom agents and access settings. A compatible user-owned
registration for the same file stays user-owned. A conflicting name, redirected
config symlink, malformed TOML or edited/unowned block stops sync before writes.
Reserved Codex `[agents]` setting names (including compatibility aliases) are
rejected as role names before registration. The managed manifest records current and prior owned-block hashes; it does not claim ownership
of the whole user configuration. Removed Flow roles are removed only from the
owned block. `--check` never creates a backup or writes configuration.

Backing definitions are prepared first, followed by the atomic ownership
receipt, discovery links and registration. The receipt precedes the block;
if receipt persistence fails, prior generated files are restored so their
recorded hashes remain valid for a retry. Unchanged receipts are not rewritten.
its prior-block hash permits retry after an interrupted configuration write
without treating the untouched prior registration as a user edit.

Before a changed configuration is atomically replaced, the original is backed
up with owner-only permissions under
`~/.flow/backups/codex-role-registration/<content-sha256>.toml`. Restore that
backup only after reviewing any later user edits; otherwise remove only the
verified Flow block and retain the surrounding user text. Configuration file
permissions are preserved. Safe registration uses Python's full TOML parser;
the installed pinned OpenHands interpreter meets its Python 3.11+ requirement.

Older manifests have no hashes. If a legacy replacement file differs from the
new desired output, Flow cannot prove it is an unedited old generation and
preserves it as a conflict. The Codex string encoding change can trigger this
on the first migration even when instructions mean the same thing. Review and
back up the reported files, move intentional edits into the user overlay, then
remove only the reviewed generated files and rerun that target's sync. Do not
remove the whole runtime agents or skills directory. There is no force-overwrite
mode and no automatic adoption of modified files.


## Host ownership and delegation

Shaper and Delivery Lead remain responsibilities of the host assistant, not new
specialist personas. Registration lets that host invoke the declared specialist
names through Codex's supported native interface: for example, Shaper can gather
business-analysis or UX evidence, and Delivery Lead can request lead-developer,
test-engineer and quality-reviewer work. The host reconciles the outputs and
retains the existing approval boundaries. Registration neither launches agents
nor changes Flow's OpenHands execution runtime, conversation handling or retries.

## Execution and supported semantics

Claude retains its existing name, description, tools, model/effort, skills and color
metadata. Access/permission-mode metadata is not emitted. Codex uses the existing
runtime model/reasoning policy and native web_search setting; its ignored legacy boolean `[tools].web_search`
is no longer emitted. Source Claude tool
names and aliases are reported as untranslated. Source skill references remain
in its instructions and resolve through native skill discovery. TOML strings
are encoded rather than interpolated, preserving backslashes and quotes.

OpenHands file definitions carry instructions, description, named skills and
`model: inherit`. Claude model aliases are not SDK profile names, and Claude
Read/Write/Grep/Glob lists are not equivalent SDK tools. Generated files therefore
specify no tools: outside Flow, stock file discovery yields an instructions-only
agent. Inside Flow, the stock delegation registry receives contextual factories
using the same renderer, source resolution, expertise, capability guidance, skills and project
context as the selected parent role. Those factories use the configured local
runtime tools and model profile. Default roles expose the SDK task tool and the
full other-role roster; an explicit `specialists` list or `specialists = []`
controls Flow's registered roster and prompt hints; it is not a global SDK
agent allowlist. An empty roster removes the task tool. Explicit tools without
task disable delegation. A configured native
child in a local roster is rejected instead of silently switching providers.

Registry identities include project and selected role/profile fingerprints,
so repeated constructions reuse the same factory and different bindings do not
inherit a previous project's endpoint. Children inherit the parent's selected
local profile unless runtime configuration explicitly selects another local
profile. Implicit child rosters are empty to avoid accidental recursive fan-out;
a child's explicit configured roster is retained.

Native ACP agents continue to use their stock Claude/Codex harnesses and native
role discovery. SDK task tools and condensers are not attached to ACP agents.
Web-research policy remains prompt guidance on OpenHands, not an SDK terminal or
network permission fence. There is no MCP dispatcher, credential copying, provider switch, permission
rule generation, or claim of identical containment between runtimes.

## Pinned evidence

- [Claude ACP 0.63.0 setting sources](https://github.com/agentclientprotocol/claude-agent-acp/blob/v0.63.0/src/acp-agent.ts#L5334-L5450)
- [Codex 0.153.4 role loader](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/agent-roles/src/loader.rs#L23-L117)
- [Codex native web search and ignored legacy boolean](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/config/src/config_toml.rs#L558-L603)
- [Codex role schema](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/agent-roles/src/agent_role_config.rs#L20-L117)
- [Codex filesystem follows symlink entries](https://github.com/openai/codex/blob/rust-v0.153.4/codex-rs/exec-server/src/local_file_system.rs#L618-L643)
- OpenHands 1.54.0 installed `sdk/subagent/schema.py`, `load.py`, and `registry.py`
  were inspected directly. Tests run its parser/discovery and construct stock
  registered factories without invoking a model.

## Coordinated live installation

The implementation worktree is based on `feature/openhands-runtime` commit
`0d3941a`; it does not change that checkout, `~/.flow/source`, or Witmark.
After the concurrent Witmark work has stopped and the installation window is
coordinated, back up the current generated surfaces and install this reviewed
branch using `./install-flow.sh --release`. Resolve any reported legacy conflicts
as described above, rerun `flow setup user`, and run all three sync checks in a
fresh session. Until that coordinated step, the live installation remains on
its existing version. Offline tests do not establish live model/tool execution.

See [the output inventory and validation record](agent-distribution-validation.md)
for new checks, existing regression results and the limits of offline evidence.
