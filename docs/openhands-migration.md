# Flow over OpenHands

This branch replaces Flow's execution architecture. Flow owns the stages,
approvals, specialist definitions, skills, project context and durable outputs.
OpenHands owns the model-driven loop, tools, delegation, workspace operations,
conversation persistence and execution metrics.

The original source, installed runtime, provider runs and other worktrees are
not migrated. Start new work on this branch; reference prior artifacts as inputs.

## Run this branch without installing it

Python 3.12 is required for the execution environment. The stdlib Flow commands
remain usable with the existing supported interpreter.

```sh
python3.12 -m venv .venv-openhands
.venv-openhands/bin/python -m pip install -r runtime/openhands/requirements.txt
.venv-openhands/bin/python cli/flow.py workflow runtime --json
```

Use the isolated interpreter and `cli/flow.py` for all examples below. Do not run
`install-flow.sh --develop` against a live installation to preview this branch.
OpenHands SDK, tools, workspace and agent-server are pinned to **1.54.0**.
The macOS arm64 Python 3.12 dependency closure is recorded in
`runtime/openhands/requirements-macos-arm64-py312.lock`.
The integration was checked against these installed PyPI packages, including
`ACPAgent.acp_session_mode`, its permission callback, `AgentDefinition.load`,
`AgentContext`, `Conversation`, `RemoteWorkspace`, SDK skill loaders and tools.

## Configure self-hosted coding profiles

Copy `templates/openhands-runtime.toml` to a project's `.flow/runtime.toml` and
edit its endpoints and model names. The user overlay at
`~/.flow/user/runtime.toml` supplies defaults; project settings override them.
A profile is explicit: there is no automatic cloud model or billing fallback.
Ollama, llama.cpp, vLLM, LM Studio and compatible hosts use the SDK's LLM
interface. Model capability and tool support remain the selected host's concern.
For OpenAI-compatible servers use `model="openai/<served-model>"` with its
explicit `/v1` endpoint. For Ollama use `ollama_chat/<model>` and its native URL.

An authenticated self-hosted host can name a dedicated `api_key_env`; credentials
are never stored in Flow configuration or copied from Codex/Claude. Native API
credential variables and direct paid OpenAI/Anthropic endpoints are rejected.

Runtime configuration recursively merges `~/.flow/user/runtime.toml`, then
project `.flow/runtime.toml`; project values win and lists replace lists. Role
selection is `--role` > stage role > built-in stage role. Profile selection is
`--profile` > role profile > stage profile > `default_profile`. There is no
fallback if the selected profile is missing or invalid.

Role source precedence is `roles.<name>.file` (relative to the project root) >
project `.flow/agents/<role>.md` > project `.agents/agents/<role>.md` >
user overlay `agents/<role>.md` > merged shared-manifest source > framework
`agents/<role>.md`. This execution resolution is separate from user-level
adapter generation, which merges the framework and registered user manifest. OpenHands parses the file's role body. Flow's historical
Claude `model` and `tools` hints are not translated into new grants: the profile
and SDK tool selection are explicit runtime settings. Configured context files,
`.flow/PROJECT.md`, user `.agents/skills`, project `.agents/skills` and
`.flow/skills` enter AgentContext.
Configured skill files retain SDK triggers and resource discovery. Public skills
are not downloaded implicitly.

The stock SDK TaskToolSet handles local delegation. Default tools are
`terminal`, `file_editor`, `task`; omitted `specialists` exposes all other merged
roles. Explicit `specialists = []` disables delegation, and an explicit list
controls Flow factory registration and prompt hints, rather than an enforceable SDK
allowlist. Implicit children receive an empty roster to prevent recursive
fan-out; explicitly configured child rosters remain. Children inherit the
parent's local profile unless runtime configuration selects another local
profile. A native child in a local roster is rejected, preventing an implicit
provider switch. Native parent execution uses stock ACP discovery for delegated
roles, rather than SDK custom tools or condensers. A `task` tool is required when a role declares a specialist roster. SDK factory
names include a project/profile binding suffix; the agent context maps configured
role names to those identifiers. Repeated construction reuses the SDK registry
without confusing different project profiles.

## Generated discovery and installation

All 13 source roles are distributed to Claude `.claude/agents/*.md`, Codex
`.codex/agents/*.toml`, and OpenHands `.agents/agents/*.md` at user level.
Relative symlinks point into `~/.flow/generated/agents/`; managed copies are the
fallback. `flow setup user`, bootstrap install, release updates and mode
conversions refresh all three using the newly installed CLI. Develop updates
require a manual pull and `flow setup user`. `flow sync openhands --user --check`
checks drift without writing, alongside Claude/Codex checks.

OpenHands external file discovery is instructions-only (`tools: []`); local
Flow factories supply configured tools, profiles, project context and skills.
Native discovery translates only supported metadata. Hash-based ownership
preserves custom files and modified outputs; older hashless differences stop
sync for review. See [role distribution](agent-distribution.md) for reports,
conflict recovery and the coordinated installation step.

## Workflow

```sh
flow_preview() { .venv-openhands/bin/python cli/flow.py "$@"; }
flow_preview workflow init my-change --project-root /path/to/project
flow_preview workflow execute my-change --stage define --task-file task.md --project-root /path/to/project
flow_preview workflow approve my-change --stage define --project-root /path/to/project
flow_preview workflow execute my-change --stage solution --task-file task.md --project-root /path/to/project
flow_preview workflow approve my-change --stage solution --disposition risk=accepted --project-root /path/to/project
flow_preview workflow execute my-change --stage plan --task-file task.md --project-root /path/to/project
flow_preview workflow approve my-change --stage plan --project-root /path/to/project
flow_preview workflow execute my-change --stage implement --task-file task.md --project-root /path/to/project
flow_preview workflow approve my-change --stage implement --project-root /path/to/project
flow_preview workflow execute my-change --stage review --task-file task.md --project-root /path/to/project
flow_preview workflow approve my-change --stage review --project-root /path/to/project
flow_preview workflow archive my-change --disposition memory=recorded --disposition capability_gaps=none --project-root /path/to/project
```

`approve` is a user/operator action after reviewing outputs, never an automatic
model decision. Implementation approval records handback and enters review;
review approval accepts the result. Solution may be skipped by executing plan
after approved definition, as the existing workflow permits. Use the existing
`flow run transition` for pause, resume, block or review refinement.

Outputs live in `.flow/runs/<work-id>/`: requirements, acceptance criteria,
solution, plan, handoff, validation plan, implementation evidence, handback and
review. Approval requires existing nonempty files inside the run. Existing
`flow run list/status/history/verify`, archive retrieval, cost collection,
capability gap and memory tools remain available.

`execute` continues the stage/role's SDK conversation. `--role` and `--profile`
select a specialist and endpoint. Changing a persisted role/provider/workspace
requires `--new-session`; previous session references and SDK history remain.
SDK storage lives under `openhands/`. Flow stores only its session reference,
last response, SDK metrics and elapsed time in `run.json` and an outcome artifact.
Errors/interruption preserve the reference; replay is the SDK's responsibility.
An execution response does not prove the acceptance criteria or approve a stage.

## Native subscriptions and the access decision

Profiles `kind="codex"` and `kind="claude"` execute through stock OpenHands
ACPAgent and the pinned official adapters. Flow explicitly selects Codex `agent`
and Claude `default` modes, reuses native authentication in place, and materializes
no credentials. Live Codex and Claude execution and same-session resume passed in their explicitly
approved disposable acceptances; see docs/acceptance/.

Stock SDK selects the first permission option; the pinned Claude adapter puts
`allow_always` first. This can create permission rules. Before enabling
`permission_requests="stock-openhands"`, approve the exact scoped access decision
in [native-access-decision.md](native-access-decision.md) and establish the intended execution environment access. The setting acknowledges SDK behavior; it creates no
OS sandbox or network grant. No profile enables it by default. Flow does not patch
private SDK callbacks or implement a replacement transport.

`flow workflow native-handoff` prepares a context artifact for an existing native
session as a temporary fallback. It is not automated native acceptance. Further native execution requires its actual host access and the documented
acknowledgement; Claude uses its visible official subscription login and retains the separate
stock permission caveat described in the access memo. No paid model API fallback is used.

## Workspaces and actual permissions

LocalWorkspace uses the process's inherited filesystem/network access; its working
directory is **not** a sandbox. Run it under the existing managed execution
permissions. Flow creates no OS grant and does not bypass an inherited sandbox.
For an already provisioned OpenHands agent-server, select workspace `kind="remote"`
with its explicit host and working directory. SDK RemoteWorkspace owns transport
and server-side conversation persistence. This branch does not provision a server,
mount additional directories or forward native credentials to it. The server's
own actual access restrictions apply. Remote deployment is not validated locally.
SDK action confirmation can be requested with `confirmation="always"`; pending
SDK actions remain pending until explicitly continued with `--confirm-pending`
or rejected with `--reject-pending REASON`, after inspecting status. This uses
the SDK confirmation API. Flow does not add a homegrown permission system.

## Decisions and migration log

| Previous behavior | Adopted behavior | User-visible consequence |
|---|---|---|
| MAF/Magentic manager plus Flow provider dispatch, ledgers and generation fences | OpenHands Agent/Conversation and SDK TaskToolSet | New execution uses `flow workflow`; old execution commands refuse to start/resume providers |
| Custom command/file brokers and local model wrappers | SDK terminal/file editor tools and LLM interface | Compatible self-hosted hosts can perform coding, not just verifier tasks |
| Flow-owned model budgets, rate gates, checkpoints and retries | SDK execution, persistence and metrics | No duplicated token/rate controller or converted old checkpoints |
| Sealed orchestration manifests and charters required for new runs | Revision 3 reuses Flow lifecycle and actual stage artifacts | Stage approvals remain; old execution-control artifacts are not required |
| Install/update automatically provisions/activates MAF | Explicit isolated pinned OpenHands dependencies | Installing core Flow does not start providers or replace a runtime selection |
| Agent metadata assumed Claude tools/models | OpenHands file parsing plus explicit runtime profile/tools | Old role bodies remain useful; endpoint/tool selection moves to runtime.toml |
| Automated native invocation with broad defaults | Stock ACPAgent with explicit modes and scoped access acknowledgement | Scoped disposable native acceptance passed; future execution still requires the documented access decision |
| Current run.json plus separate execution state systems | Flow stage state plus SDK conversation persistence | Sessions are references, not another checkpoint/receipt ledger |

Historical modules remain for reading and testing old records. They are not used
by the replacement execution path. No existing run is silently converted.

## Validation

- Repository tests: `python3.12 -m unittest discover -s tests`.
- Replacement contracts: `python3.12 -m unittest discover -s tests -p test_openhands_workflow.py`.
- Real SDK integration: `.venv-openhands/bin/python tests/openhands_runtime_eval.py`.
  The deterministic loopback endpoint drives SDK tool calls, all stages, SDK
  resume and archive in disposable directories. It is not a quality benchmark
  or a production local/native provider test. Actual approved native and Ollama
  fixture executions are separately recorded under `docs/acceptance/`.
- Shell syntax, bytecode compilation, generated help consistency and diff checks.

Official references: [architecture](https://docs.openhands.dev/sdk/arch/overview),
[file-based agents](https://docs.openhands.dev/sdk/guides/agent-file-based),
[skills](https://docs.openhands.dev/sdk/guides/skill),
[ACP](https://docs.openhands.dev/sdk/guides/agent-acp), and
[local models](https://docs.openhands.dev/openhands/usage/llms/local-llms).
Moving docs are explanatory; the pinned installed APIs are the implementation
contract.

## Effective local context settings

Local profiles may supply the SDK's `max_input_tokens` and `max_output_tokens`.
`condenser_max_tokens` selects the stock SDK LLMSummarizingCondenser with that
summary threshold; Flow neither counts tokens nor implements its own compaction.
Absent fields retain SDK defaults. The isolated branch project's current profile
selects the existing Ollama development model with context 65,536, output 8,192
and summary threshold 57,344. No global/user profile is changed. See
[64K setup and rollback](ollama-64k-setup.md).

## Coordinated migration and rollback

Keep active Witmark/native sessions and `~/.flow/source` untouched while testing
a candidate. Run installer/update tests in isolated homes and coordinate the
live window after active work stops. Back up runtime managed manifests, backing
definitions and discovery files. Install the reviewed source with
`./install-flow.sh --release`, review any conflicts, then run `flow setup user`
and all three `--check` commands in a fresh session. A source swap can succeed
while a target sync reports a conflict; inspect both outcomes.

For rollback, select the reviewed earlier checkout and rerun its release
installer during a coordinated window. Restore only backed-up owned files after
review; preserve custom files and edits. `flow update` selects the latest remote
tag and is not an older-tag selector. Historical run artifacts are retained;
new runtime workflows do not reinterpret old MAF receipts. Provider profiles
remain explicit and no migration authorizes new access or model calls.
