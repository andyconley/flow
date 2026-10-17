# Native ACP access decision

## Current default: stock OpenHands with interactive opt-out

The October 17 approved defaults amendment makes omitted native permission policy
inherit `permission_requests="stock-openhands"`. This uses the supported ACPAgent
path audited below, including possible persistent native permission rules. It
does not grant filesystem/network access beyond the actual outer environment.
SDK dispatch inherits its native `NeverConfirm` default; explicit
`workspace.confirmation="always"` remains interactive, and a resumed conversation
re-asserts this current default rather than trusting a persisted policy from an
older binding. Existing explicit permission policies are removed by default on
install/update so the scope inherits this automatic default; `flow defaults-review
--check` previews the pending removal, and recovering a run's backup is the
explicit opt-out, not an interactive per-setting choice.

With `permission_requests="interactive"`, Flow launches
the unchanged pinned adapter through `cli/acp_permissions.py`, using the public
ACP command boundary. The proxy intercepts `session/request_permission` before
it reaches the stock automatic callback. It displays the complete escaped request
and actual option kinds on the controlling terminal and returns only an explicit
human choice. Empty/invalid input, EOF, errors, timeout or session cancellation
return `cancelled`; no terminal fails before workflow stage entry or native launch.
Prompts are terminal-only, not Codex/Claude desktop approval dialogs. A profile
with explicit interactive permission handling uses this route; existing
configuration is not rewritten. Omitted handling uses the stock behavior audited below.

The default response deadline is 120 seconds including time waiting for the
terminal lock. Prompts are serialized across concurrent proxies on the same tty.
Intercepted permission requests are displayed only on the terminal, never logged
or forwarded upstream by the proxy. Ordinary tool notifications are relayed
unchanged and can still contain arguments under the SDK's existing policy. Native
stderr is suppressed by the proxy because it may contain sensitive requests.
The proxy uses a project cache under `.flow/runs/.acp-cache/npm`; it does not
grant that cache, native-state or network access. Outer permissions still apply.
Human selection of `allow_always` can have the persistent effects described below;
Flow neither preselects nor silently rewrites that choice. Adapter/session
initialization and operations that native policies already permit may happen
without a new permission request. This proxy is not a new sandbox.

All protocol messages other than permission requests are relayed, including
unknown extension fields. Invalid protocol, duplicate outstanding request IDs,
overlarge messages or excess pending permissions stop the proxy. Host EOF and
cancellation terminate the adapter process group; no background approval worker
is retained. SDK files and private callbacks remain unmodified.

The remaining sections record the previous stock-path audit and historical
approvals. They do not require stock automatic approval for the interactive route.

Native automation uses stock `ACPAgent`. **Live Codex and Claude acceptance passed** under
their subsequently approved launcher scopes. Interactive
handoff is a temporary fallback, not the final architecture. This document keeps
the pinned permission audit and chronological access decisions; the final section
records successful native artifacts and same-session resume.

## Verified versions and behavior

- OpenHands SDK `1.54.0` installed from PyPI.
- Its official npm catalog pins `@agentclientprotocol/codex-acp@1.10.0` and
  `@agentclientprotocol/claude-agent-acp@0.63.0`.
- The exact registry tarballs were inspected without launching native agents.
- Flow sets Codex `acp_session_mode="agent"`. The pinned adapter maps it to
  `workspaceWrite`, `networkAccess=false`, `approvalPolicy=on-request`,
  `approvalsReviewer=auto_review`, no additional writable roots, and ordinary
  temporary directory access. It does not select `agent-full-access`.
- Flow sets Claude `acp_session_mode="default"`, not `bypassPermissions`.
- OpenHands' stock permission callback chooses the **first** offered option.
  In the pinned Claude bridge, an ordinary tool permission request offers
  `allow_always` first. That returns the native SDK's permission suggestions or
  adds a tool allow rule with `destination="session"`. ExitPlanMode can offer
  an `auto` mode change first. Native suggestions may target other native
  permission settings; the initial mode alone does not stop these updates.
- Codex ACP also handles requests for additional sandbox permissions. Stock
  OpenHands answers them automatically; only the independently enforced outer
  execution containment can prevent an actual access expansion.

These are concrete native grant implications, not an architectural preference
for retaining Flow's old controls. Flow does not patch the SDK callback, build an
ACP transport, or recreate its old approval/dispatch machinery.

## Current containment and login observations

The execution environment grants read access to the filesystem and write access
only to this task's workspace and temporary directories. Network is restricted.
SDK/native children inherit that containment when launched through ordinary
sandboxed execution. Elevating the whole Python/native process would remove
that boundary and is **not** an equivalent scoped approval.

The existing Codex saved login reports `auth_mode=chatgpt`, subscription tokens
present, and no saved API key. Values were not printed, copied or modified.
The user Codex config says `danger-full-access`/`approval_policy=never`; Flow
explicitly selects the narrower stock ACP `agent` mode instead.

Installed Claude Code is `2.1.296`. A harmless `claude auth status` in this
restricted environment reported `loggedIn=false`, `authMethod=none` and
`apiProvider=firstParty`. This does not prove that another host/session lacks a
subscription; it means a login is not visible to this execution environment.
The current Claude default permission mode is `auto`. Flow selects `default`.
No native login, token export or credential copying was attempted.

## Smallest approval: Codex only, nonpersistent

The pinned Codex adapter sorts command options with `allow_once` before
`allow_always`; file edits offer `allow_once` first. Additional permissions offer
“grant these permissions for this turn” first. The stock OpenHands callback thus
selects one-time/turn-scoped approvals on these paths, not persistent allow rules.
This is a supported nonpersistent path. It still automatically approves requested
access for that turn; independent outer containment is required.

Suggested concrete question:

**May I enable stock OpenHands ACP permission handling for one Codex-only live
acceptance run in
`/Users/andyconley/Documents/Codex/2026-10-11/task-3/flow-openhands`, using the
existing ChatGPT Codex login and `agent` mode, with one-time/turn-scoped native
approvals, code writes confined to a disposable test project under that worktree,
and no persistent permission rules, global settings changes or broader host
access?**

This approval covers the native callback behavior only. It does not grant new OS
filesystem/network access. The current managed sandbox remains in force; do not
run the whole Python/native process with unrestricted elevation. If native startup
requires currently denied native session/log or subscription network access,
identify the exact denied path/domain and obtain that scoped access separately.
No blanket native-home write grant or all-network approval is requested now.
Original source, installed Flow, Witmark worktrees and preserved candidate patches
remain excluded from writes. Existing native authentication is read in place; no
credentials are copied, exported or replaced and no paid model API is used.

After approval, set `permission_requests="stock-openhands"` only in the temporary
Codex test profile. The acknowledgement is not a sandbox or OS grant. The template
leaves it unset. Native session history/logs and SDK test artifacts may persist;
persistent native permission/settings edits are outside this Codex approval.

## Separate Claude decision

Current stock Claude execution cannot guarantee one-time-only tool permission
answers: its first ordinary option is `allow_always`. The fallback rule destination
is `session` (not necessarily an on-disk permanent rule), but permission suggestions
may target persistent settings. Therefore it is inaccurate both to claim every
`allow_always` lasts permanently and to promise this path has no persistent effects.
ExitPlanMode can also change permission mode. No public stock bridge callback or
option-selection setting was found that chooses Claude's `allow_once` instead.

Claude live acceptance remains pending a separate scoped decision covering these
possible rule/mode effects and a visible official login. It is not included in the
Codex-only question. Do not enable `bypassPermissions`, forward credentials,
change global native settings or remove outer containment as a shortcut.

If appropriate confinement cannot be enforced, leave live acceptance pending or
use an already authorized workspace that can enforce it. This branch has created
no such workspace, host grant or native login.

## Verification completed independently

The real SDK runs local coding conversations/tools and persists/resumes sessions.
A deterministic ACP protocol peer tests the real stock SDK transport, explicit
Codex/Claude modes, permission callback and resume in disposable directories.
That test does not use real native credentials or constitute live native
subscription acceptance. A real native stage remains pending the access decision.

## Deterministic tests versus live acceptance

`tests/openhands_acp_eval.py` replaces only the SDK catalog launch executable with
a disposable deterministic ACP peer. Both profile tests use the same peer, which
advertises the requested modes, offers `allow_once` first, writes a proof file,
returns a fixed response and resumes the same session. It exercises stock SDK
stdio transport, explicit mode selection, first-option permission handling,
response capture and persisted resume. It does **not** exercise the real npm
adapters, native authentication, subscription inference, provider sandbox or
Claude's actual `allow_always` behavior. Those behavior findings are source audits
of the pinned published adapters.

The proposed live acceptance is one actual Codex-native Flow `define` stage plus
a continuation of the same SDK conversation in a disposable project under the
worktree. The task is to inspect a small fixture, produce requirements and
acceptance-criteria artifacts, and finish. Verify native subscription execution,
project artifacts, response/metrics capture, SDK persistence and same-session
resume. It is not a mixed-model benchmark or work on Witmark. Native execution
must remain blocked until the scoped prerequisites are established. No live
acceptance was run while preparing this memo.

## Approved Codex-only attempt: blocked before native startup

Andy approved the scoped Codex-only acceptance on 2026-10-11. The attempt used
ordinary managed sandbox execution, existing ChatGPT authentication in place,
`agent` mode, and a disposable project inside the isolated worktree:
`.venv-openhands/codex-acceptance-462uaigk`.

Stock SDK startup tried to provision `@agentclientprotocol/codex-acp@1.10.0`
into the project's SDK npm cache. Requests to
`https://registry.npmjs.org/@agentclientprotocol%2fcodex-acp` failed with
`getaddrinfo ENOTFOUND registry.npmjs.org`; npm's own metadata request to
`https://registry.npmjs.org/npm` also failed. SDK warm-cache startup failed and
the normal npx retry encountered the same DNS restriction. The task was
interrupted rather than rerun with unrestricted elevation.

The required scoped prerequisite is HTTPS/DNS access to `registry.npmjs.org`
for provisioning the pinned adapter and its dependencies into this worktree-local
cache, or an already provisioned equivalent. No such access was enabled. This is
not a request for subscription network, all-network access, native-home writes or
persistent permission rules. Those later prerequisites are untested.

Workflow state remains `defining`; session
`e4d2689d-afdf-4bfb-b3a0-9d7d5b28799d` is recorded as `interrupted`.
Neither requirements.md nor acceptance-criteria.md exists. Native authentication,
inference and actual session resume were not reached. No native acceptance pass
is claimed. Task/provider processes are stopped; no existing provider was touched.

Preserved evidence lives in the ignored disposable project under
`.flow/runs/native-acceptance/openhands/npm-cache/_logs/` and the Flow session
reference/outcome. No credential material was copied. The approved callback
acknowledgement exists only in this disposable test profile.

## Dependency provisioning allowed; restricted retry reached Codex

The normal reviewer allowed dependency provisioning only. The official pinned
`@agentclientprotocol/codex-acp@1.10.0` and its dependencies were installed into
the disposable project's SDK npm cache from `registry.npmjs.org`, using the SDK's
cache-warming form (empty Node code, no native adapter execution). The installed
native dependency reports `@openai/codex@0.153.4`.

Acceptance was then retried in the original restricted context, without elevation.
The SDK reloaded its existing conversation reference and launched the real pinned
adapter/native process. Codex exited with:

> Error: failed to initialize sqlite state runtime under /Users/andyconley/.codex

It also warned that PATH alias creation was not permitted. Existing native-home
file names include `state_5.sqlite` and WAL/SHM sidecars, log databases, and
`tmp/arg0`; the error identifies the native-home runtime root, not an exact denied
file. No broad native-home grant was requested or enabled. No credential values,
SQLite contents or user session contents were inspected/copied.

The native task did not reach subscription inference, artifact creation or actual
native session resume. Workflow remains `defining`, SDK reference is now `error`
with `RequestError`, and both requirements artifacts remain absent. Task/native
processes have exited. Subscription network and later state-write prerequisites
remain untested. The successful dependency provisioning is not native acceptance.

The installed binary contains the standard `CODEX_SQLITE_HOME` option; relocating
SQLite bookkeeping to the already writable disposable workspace is a candidate
for avoiding shared-home database writes, not an additional host grant. That
option was not enabled in this retry and its complete startup behavior here is
unverified. Do not infer that access to the whole `.codex` home is necessary from
the root-level error. Further scoped startup configuration or access needs must
preserve in-place native authentication and the existing outer restrictions.

## SQLite relocation verified; remaining native-home startup write

Pinned official Codex `rust-v0.153.4` source confirms `CODEX_SQLITE_HOME` is used
when no `sqlite_home` configuration overrides it. There is no such override in
the existing user config. The restricted retry set that variable only for the
test process to the disposable project's `.native-sqlite`; native SQLite
databases were successfully created there. No shared native-home database write
was granted and no authentication/credential home was relocated.

Startup then exited with `Operation not permitted`. The pinned startup source
unconditionally calls `resolve_installation_id(&config.codex_home)` after SQLite
initialization. Its implementation opens `<codex_home>/installation_id` with
read/write/create, locks it, can normalize mode to 0644, and writes a new UUID if
contents are absent/invalid. The existing file's presence was checked without
reading its value. This mandatory operation needs access beyond the current
write scope; the exact failed syscall is not emitted by the native error, so
attribution of that generic error to this next required write is a source-backed
inference, not a syscall trace. There is no distinct installation-ID path override
in this implementation.

Smallest identified new access: native read/write/lock access to
`/Users/andyconley/.codex/installation_id` for the acceptance process, with the
above possible mode/identifier effects. This is not approval to write all of the
native home, native permission settings or credentials. It has not been granted
or attempted outside the sandbox. Later session/history/network needs are still
untested and cannot be assumed covered.

PATH aliases are rooted at `<CODEX_HOME>/tmp/arg0` in the pinned implementation.
Alias failure is expressly nonfatal and startup continues; no alias-home write
grant is requested as a cure for the fatal startup error. No supported separate
alias-root override was found. The task did not relocate the login/credential
home, copy credentials, patch native code, or create a command wrapper.

Both requirements outputs are still absent. Native acceptance and actual resume
remain incomplete. The attempt exited on its own; no provider remains running.

Official pinned sources:
- https://raw.githubusercontent.com/openai/codex/rust-v0.153.4/codex-rs/core/src/config/mod.rs
- https://raw.githubusercontent.com/openai/codex/rust-v0.153.4/codex-rs/app-server/src/lib.rs
- https://raw.githubusercontent.com/openai/codex/rust-v0.153.4/codex-rs/core/src/installation_id.rs
- https://raw.githubusercontent.com/openai/codex/rust-v0.153.4/codex-rs/arg0/src/lib.rs

## Installation-ID access approved; tooling cannot apply the narrow grant

Andy explicitly approved read/write/lock access to the existing
`/Users/andyconley/.codex/installation_id` and its described possible effects.
That authorization is retained; no repeated user approval is required.

The available execution interface has only `sandbox_permissions="use_default"`
(the existing managed sandbox) and `"require_escalated"` (unsandboxed command
execution). It has no additional-writable-file parameter, and the available tool
inventory exposes no host filesystem grant operation. The task's current write
roots still exclude the approved installation-ID file.

Elevating a single-file helper could authorize that helper's own operation but
would not extend the later native child's inherited sandbox. Changing file mode
would not change the managed sandbox policy. Elevating the entire acceptance
process is explicitly outside the approved scope and was not attempted.

The actual remaining requirement is for the execution host/task sandbox to expose
the approved single-file read/write/lock capability while preserving existing
filesystem and network restrictions. The tool interface cannot apply that policy
change. Native acceptance was not retried under unchanged access, and no file
contents, credentials, global settings or native home grants were modified.

## Live Codex acceptance passed under the subsequently approved launcher scope

Andy approved one normally reviewed acceptance outside the outer sandbox while
retaining native Codex `agent` mode. The normal reviewer admitted the launch.
The existing disposable project and project-local SQLite were reused; no
credential copy, paid API route, global configuration edit, Claude run or live
Flow replacement was performed.

The pinned real adapter initialized and authenticated through `chat-gpt`. The
saved default `gpt-6.1-sol` was rejected by this native ChatGPT path. A profile-only
selection of `gpt-6-astra`, advertised by the native session model catalog,
succeeded. The prior failed reference was retained and an explicit new SDK
conversation was used for the changed profile binding. This was repair of the
same acceptance task, not a model benchmark. Global model settings were untouched.

Verified:
- Both actual requirements and acceptance-criteria artifacts were written.
- The second execution reloaded SDK conversation
  `c6a06974-7ad2-412b-8c45-5ba569e0db93` and the same native session
  (native identifier retained in SDK storage; repository evidence contains its SHA-256).
- Continuation read and confirmed the existing artifacts without changing them.
- The test harness then approved definition, and Flow run verification passed.
- The fixture implementation remained byte-for-byte unchanged.
- SDK responses, token/cache metrics and SDK-reported cost estimates persisted.
  Cost estimates are tracking data, not evidence of paid API billing.
- Observed native tool calls read project files and edit the two run artifacts;
  no stock ACP permission callback request was logged during this successful run.
- The acceptance/native processes exited. Existing checkouts remained clean.

Reviewable artifact copies and bounded outcome data are in
`docs/acceptance/codex-native/`. Original SDK history remains in the ignored
disposable project. Claude live acceptance and remote deployment are still
unvalidated. This host's restricted outer context still cannot run native startup
without the separately approved launcher scope; success does not erase that
operational limitation or authorize unrestricted future runs.

## Claude preparation after Codex success

Official host `claude auth status` now confirms an existing first-party
`claude.ai` Team login; the restricted status check remains unable to see it.
No Claude model was called and no permissions/settings changed. See
[claude-native-acceptance-preparation.md](claude-native-acceptance-preparation.md)
for pinned configuration, session versus persistent rule effects, unverified
native containment, and one concrete approval question for the actual stock path.

## Live Claude acceptance passed after explicit approval

Andy approved the disclosed stock Claude scope, including a normally reviewed
run outside the outer sandbox and possible automatic permission effects. The
reviewer admitted the bounded fixture/resume command. Real adapter `0.63.0`,
bundled `@anthropic-ai/claude-agent-sdk@0.3.220`, and OpenHands `1.54.0` ran using
existing first-party Team authentication and explicit `default` mode. Native
model was the existing/default `opus[1m]`; no API key or routing override was used.

Both requirements and acceptance-criteria artifacts were produced. SDK
conversation `68d34ad7-1342-4924-92e1-86b0d65f2eec` and the same native Claude
session resumed successfully; repository evidence retains only a fingerprint
of the native identifier. The continuation read the existing artifacts. Fixture
source stayed byte-for-byte unchanged. Harness definition approval and Flow run
verification passed. Response/token/cache/SDK cost-estimate tracking persisted;
those estimates are not evidence of paid API billing.

Observed effects:
- User `.claude/settings.json` and its permission-rule projection were unchanged.
- Neither project `.claude/settings.json` nor `.claude/settings.local.json` was
  created.
- Existing `.claude.json` changed. Only its before/after fingerprint was captured;
  exact changed fields were not determined. Do not assert it was solely harmless
  bookkeeping or attribute every change to this process rather than concurrency.
- No stock ACP permission request callback was logged in this successful run.
  This does not invalidate the audited allow-always behavior or guarantee that
  another task cannot create persistent grants.
- Observed tool calls read the fixture/run/project files, executed local listing
  and search commands, and wrote/edited the two requested artifacts. No native
  explicit bypass/plan-mode transition, deployment or original/live-install edit
  was observed.
- Acceptance/native processes exited; original source and branch worktrees are
  clean. No credentials were copied or exposed in the saved evidence.

Reviewable outcomes are in `docs/acceptance/claude-native/`. Raw SDK persistence
and diagnostics remain in the ignored disposable project. This success does not
establish independent workspace confinement for Claude, authorize future host
runs or remove the documented stock permission caveat. Remote deployment and a
production self-hosted model remain unvalidated; the actual local SDK/tool path
and both native acceptance paths have now been exercised.
