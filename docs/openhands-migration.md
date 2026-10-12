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

## Automatic install and update provisioning

Fresh bootstrap installs, release updates and install-mode conversions now
provision the four pinned OpenHands 1.54.0 packages before activating source.
The CLI's inspection commands still support Python 3.10+, but execution needs
an installed Python 3.12+ interpreter. The installer does not install Python.
For example, select it with:

```sh
FLOW_PYTHON=/absolute/path/to/python3.12 ./install-flow.sh --release
```

A pinned-ready explicit `FLOW_PYTHON` takes precedence over the existing
`[flow].python`, which takes precedence over the installer-selected interpreter.
A verified custom interpreter is reused without installing into it. Otherwise
Flow first reuses a ready managed runtime, or uses a compatible Python to create
an isolated virtual environment under `~/.flow/runtimes/openhands/`. The managed
`current.json` pointer and launcher refer to its verified interpreter. Immutable
environments remain available for rollback; repeat installs reuse readiness.
Provisioning uses `runtime/openhands/requirements.txt`; the macOS closure lock
is version-pinned reference evidence, not a cross-platform hash lock.

Package-index access is required only when a new environment needs dependencies.
A failed dependency build is removed and does not change the previous source,
launcher or runtime pointer. Source/launcher activation failure restores those
bindings as well. Runtime profiles, custom TOMLs, credentials, global Python
packages and native provider settings are preserved. No model is called during
readiness checks. Adapter conflicts are reported after source activation and
preserve custom files; reconcile them with the documented sync commands.
For rollback, reinstall the previous release in a coordinated window; retain
its managed environment and restore its pointer/launcher together if manually
restoring backups. Do not change a live installation during an active run.

### Upgrade through a predecessor installer

The pre-OpenHands updater cannot execute provisioning code shipped only in the
new release. It may swap the source first, leaving its prior Python launcher in
place. On the first invocation of the newly installed CLI for `workflow execute`,
explicit `update` (without `--check`), or `bootstrap`, Flow checks that this
is the explicitly installed source and that its OpenHands activation marker is
missing. It provisions/binds the pinned SDK, then re-executes the requested
command with the verified interpreter. Running a project checkout does not
activate this bridge, and retired execution paths do not trigger it.


Inspection remains free of installation side effects: `workflow status`,
`workflow runtime`, runtime readiness/smoke, and `update --check` report existing
state without provisioning. Workflow init, approve, archive and native-handoff
also do not activate the bridge because they do not require SDK execution.
Readiness reports a missing runtime; use `workflow execute`, explicit
`flow update`, or bootstrap to activate an unmarked installed upgrade.

A bridge failure retains the previous launcher, configuration and managed
runtime pointer. The new standard-library CLI remains inspectable, while
OpenHands-dependent commands report the unavailable runtime. Retry `flow update`
to repair provisioning. User profiles and verified custom pinned Python bindings
are preserved; no provider is started by provisioning itself.

This path has a narrower rollback boundary than a new installer: the predecessor
may already have deleted its old source before the bridge runs. The bridge
cannot restore that source. Restore a reviewed earlier release explicitly in a
coordinated window if needed. New install/update code provisions before source
swap and can restore source, launcher, configuration and runtime pointer on
activation failure; do not apply that full rollback claim to predecessor-driven
upgrades.

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

The stock SDK TaskToolSet handles specialist delegation. Default tools are
`terminal`, `file_editor`, `task`; omitted `specialists` exposes all other merged
roles, and `specialists = []` disables delegation. Explicit role profile bindings
can select local or native children. Unbound local children inherit the SDK's
active LLM. SDK factory names include a project/profile binding suffix and the
agent context maps role names to those identifiers. Native parent execution uses
stock ACP discovery rather than SDK custom tools or condensers. See
[Specialist selection and model routing](#specialist-selection-and-model-routing-v044)
for the configuration and permission contract.

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
| Install/update automatically provisions/activates MAF | Automatic pinned OpenHands runtime provisioning, with first-use bridge for predecessor updaters | Installs bind a verified SDK interpreter without starting providers or changing user profiles |
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

## Specialist selection and model routing (v0.44)

Local OpenHands parents can delegate to local, Claude, and Codex roles in the
same roster. Flow registers SDK factories; OpenHands TaskToolSet/TaskManager
creates, runs, reports and resumes child conversations. A native-bound role
returns the stock ACPAgent and reuses its existing native authentication.
Custom project and user role definitions use the same composition pipeline.
SDK skill discovery composes user/project skills and project instructions.
Nested synced AgentSkills packages are loaded from their `SKILL.md` declarations
with SDK parsers and package exclusions, so their reference Markdown remains
available on demand rather than being injected as permanent instructions.
Project skill precedence and explicit role skill references remain supported;
no global discovery files are rewritten by runtime construction.
The prompt lists each specialist's actual profile and provider kind.

An explicit role profile selects the child's endpoint, including native
providers. An omitted role profile means inheritance; present empty or invalid bindings
are configuration errors. An unbound local child inherits the LLM supplied by the SDK, including
an active model chosen through routing. Child tools and context come from the
child's role. Omitted child rosters follow the normal merged-role default;
`specialists = []` is the explicit way to make a role a leaf. SDK tool/MCP scope
restrictions still apply and reject ACP children when their capabilities cannot
be checked. A roster is discovery guidance, not a security boundary.

Local model routing is optional and uses the pinned SDK's
ClassifyAndSwitchLLMTool with inline resolved LLM profiles. It does not create
saved global profiles or a Flow execution controller. Configure task categories
on the coordinating role in `.flow/runtime.toml`, for example:

```toml
[roles.lead-developer]
specialists = ["test-engineer", "native-reviewer"]

[roles.lead-developer.model_routing]
classifier_profile = "ollama"

[[roles.lead-developer.model_routing.categories]]
description = "Implementing or testing code"
profile = "ollama"

[[roles.lead-developer.model_routing.categories]]
description = "Complex architectural reasoning"
profile = "local-reasoner"

[roles.native-reviewer]
profile = "codex"
file = ".flow/agents/native-reviewer.md"

[roles.test-engineer]
specialists = []
```

Each referenced local profile must define its self-hosted model, endpoint and
context settings in `[profiles.<name>]`. The classifier and every category must
resolve to a local profile. Native harnesses are specialist endpoints, because
SDK LLM switching does not switch ACP sessions. `--profile` preserves an explicit
user selection and suppresses automatic model routing for that role and its
unbound children. Explicit child role bindings still win. Whole-stage native
selection remains supported. Native parents continue to use harness discovery
and generated role model/effort definitions. ACP factory models come from their
native profile; effort remains managed by the native harness configuration.

Model routing runs when the agent calls `route_task_to_model`; the role prompt
instructs it to route near the start or when requirements change. Classification
errors are SDK error observations with no silent default. Stock model switching
updates the summarizing LLM but retains its condenser threshold. Flow therefore
configures one conservative stock threshold across the active model and routing
candidates, honoring their configured caps and available input/output headroom.
A larger-context candidate may summarize earlier than its preferred threshold;
no candidate is excluded and no custom switch/compaction controller is added.
An inherited switched child also uses the named profile cap when available. The active model and
classifier usage are recorded in SDK events/metrics. Profile override intent is
included in routing-enabled session bindings, so resume cannot silently change
that intent. Existing bindings without routing retain their fingerprint format. The prior
v0.43 implicit-leaf factory identifiers remain registered as resume aliases.

Native delegation retains the existing `permission_requests = "stock-openhands"`
acknowledgement, ambient paid-API checks and native session modes. Stock ACP
answers permission requests automatically, including potentially persistent
`allow_always` choices. SDK `AlwaysConfirm` is not a native permission mediator.
Use the existing host containment and native configuration; this integration
adds no filesystem/network grants. Read the native access decision before
choosing these profiles. Validation details and SDK limitations are in
[specialist-validation.md](specialist-validation.md).
