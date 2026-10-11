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

Roles resolve from project `.flow/agents`, project `.agents/agents`, the user
Flow overlay, then framework defaults. `roles.<name>.file` selects another
Markdown definition. OpenHands parses the file's role body. Flow's historical
Claude `model` and `tools` hints are not translated into new grants: the profile
and SDK tool selection are explicit runtime settings. Configured context files,
`.flow/PROJECT.md`, project `.agents/skills` and `.flow/skills` enter AgentContext.
Configured skill files retain SDK triggers and resource discovery. Public skills
are not downloaded implicitly.

Each role can select its own profile. The SDK TaskToolSet handles a role's
configured specialist roster; Flow does not run a second manager loop. Native specialists use stock ACPAgent after the explicit native access decision
described below. A `task` tool is required when a role declares a specialist roster. SDK factory
names include a project/profile binding suffix; the agent context maps configured
role names to those identifiers. Repeated construction reuses the SDK registry
without confusing different project profiles.

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
no credentials. Live Codex execution and same-session resume passed in the approved disposable
acceptance. Claude remains unvalidated; see docs/acceptance/codex-native/.

Stock SDK selects the first permission option; the pinned Claude adapter puts
`allow_always` first. This can create permission rules. Before enabling
`permission_requests="stock-openhands"`, approve the exact scoped access decision
in [native-access-decision.md](native-access-decision.md) and independently enforce
its workspace containment. The setting acknowledges SDK behavior; it creates no
OS sandbox or network grant. No profile enables it by default. Flow does not patch
private SDK callbacks or implement a replacement transport.

`flow workflow native-handoff` prepares a context artifact for an existing native
session as a temporary fallback. It is not automated native acceptance. Further native execution requires its actual host access and the documented
acknowledgement; Claude still needs a visible official subscription login and its
separate permission decision. No paid model API fallback is used.

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
| Automated native invocation with broad defaults | Stock ACPAgent with explicit modes and scoped access acknowledgement | Live native validation awaits the documented permission decision |
| Current run.json plus separate execution state systems | Flow stage state plus SDK conversation persistence | Sessions are references, not another checkpoint/receipt ledger |

Historical modules remain for reading and testing old records. They are not used
by the replacement execution path. No existing run is silently converted.

## Validation

- Repository tests: `python3.12 -m unittest discover -s tests`.
- Replacement contracts: `python3.12 -m unittest discover -s tests -p test_openhands_workflow.py`.
- Real SDK integration: `.venv-openhands/bin/python tests/openhands_runtime_eval.py`.
  The deterministic loopback endpoint drives SDK tool calls, all stages, SDK
  resume and archive in disposable directories. It is not a quality benchmark
  or a production local/native provider test.
- Shell syntax, bytecode compilation, generated help consistency and diff checks.

Official references: [architecture](https://docs.openhands.dev/sdk/arch/overview),
[file-based agents](https://docs.openhands.dev/sdk/guides/agent-file-based),
[skills](https://docs.openhands.dev/sdk/guides/skill),
[ACP](https://docs.openhands.dev/sdk/guides/agent-acp), and
[local models](https://docs.openhands.dev/openhands/usage/llms/local-llms).
Moving docs are explanatory; the pinned installed APIs are the implementation
contract.
