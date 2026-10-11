# Native ACP access decision

Native automation is implemented using stock `ACPAgent`, but live native
acceptance is **incomplete**. Interactive handoff is a temporary fallback, not
the final architecture. This document records the actual decision needed before
running a native subscription session from this environment.

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
