# Isolated implementation validation

Current result: actual Codex, Claude and Ollama fixture/artifact/resume acceptance
passed. Evidence is in `docs/acceptance/`. Source and live installation remain
preserved; all operational access choices and limitations are documented below.
The Ollama test changed no implementation code or global runtime defaults.

Branch: `feature/openhands-runtime`; base:
`ad8d81fb232c569333f468db6a1056bdd6d4220d`.
No deployment, push, live installation replacement or existing provider execution.

The isolated Python 3.12 environment reports all four direct OpenHands packages
at **1.54.0**. Requirements include direct pins and the tested macOS arm64
Python 3.12 dependency snapshot.

Verified:

- Full repository suite: 2,130 tests in 403.222 seconds, **OK**, 65 skipped.
  The eight replacement contracts were rerun separately after the final native
  acknowledgement/response changes.

- Eight replacement contract tests pass (lifecycle/artifacts, native approval
  preflight, endpoint profiles and legacy record preservation).
- 37 focused regression tests pass after updating historical execution/install
  expectations to the replacement architecture.
- `tests/openhands_runtime_eval.py` passes against the installed SDK: real file
  editor tool calls, five workflow stages, same-conversation resume, artifact
  verification, archive and preserved pending-action confirmation; 18 endpoint
  requests. Its loopback endpoint is deterministic, not a model benchmark.
- `tests/openhands_acp_eval.py` passes against stock ACPAgent: Codex `agent` and
  Claude `default` modes, permission callback, response capture and persisted
  resume. The disposable protocol peer uses no subscription or credentials.
- Generated help consistency, shell syntax, Python compilation and diff checks
  pass.

Live native subscription acceptance is incomplete. See
[native-access-decision.md](native-access-decision.md) for the actual approval
choice and containment scope. Native state/network permissions were not broadened;
no permission acknowledgement is enabled in the template. Remote workspace
provisioning/deployment and a production self-hosted model were not run.

## Focused post-implementation review

Eleven focused replacement/SDK construction tests pass after fixing duplicate
SDK specialist registration, project/profile factory identity, waiting-resume
outcome preservation and CLI failure reporting for SDK error status. Nested
rosters are delegated through the SDK rather than rejected by Flow. These tests
make no live model/native calls. The prior full repository result remains the
2,130-test run above; it was not repeated for these narrowly tested fixes.

## Full regression after review fixes

Tested code commit: `f93489a` (`feature/openhands-runtime`).

- `/opt/homebrew/bin/python3.12 -m unittest discover -s tests`: **2,134 run,
  2,067 passed, 67 skipped, zero failures/errors**, 395.376 seconds.
- `.venv-openhands/bin/python -m unittest discover -s tests -p 'test_openhands*.py'`:
  **11 passed, zero skipped/failures/errors**, 2.492 seconds. This independently
  covers SDK construction tests skipped by the standard Python environment.
- No implementation changes were needed and no live provider ran.

Live native acceptance remains on hold pending the explicit Codex-only approval.

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

After this acceptance, the diagnostic metadata reports native automation as
implemented without the stale blanket “not live validated” label. Eleven focused
SDK/replacement tests and the OpenHands diagnostic tests passed after that
metadata-only code adjustment. The prior full suite remains 2,134 run, 67 skipped;
no runtime control or execution behavior changed in this final adjustment.

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

## Actual Ollama local-loop acceptance passed

Andy requested the same fixture/artifact/resume acceptance with the existing
Ollama installation. The normally reviewed command used server `0.32.1` at
`http://127.0.0.1:11434` and existing `gemma4-26b-dev:latest` (Gemma4 25.8B,
Q4_K_M). The exact pre-existing model digest is preserved in the outcome record.
No model was pulled/replaced, and no global/default runtime profile or server
configuration was changed. Only the disposable project profile was configured.

The real OpenHands local Agent/LLM/tool loop made actual Ollama inference calls,
read fixture/task files and created both required artifacts using SDK FileEditor.
A relative-path view was rejected by the editor; the model corrected it to an
absolute project path through the normal SDK loop. There was no manual retry,
provider switch, transport wrapper or benchmark. SDK conversation
`2aaaed19-62aa-48e6-8791-a7820ae991b7` resumed from persistence, read both artifacts
and confirmed their content. Artifact hashes and fixture source stayed unchanged
on resume. Harness definition approval and Flow run verification passed.

Model capabilities reported completion, vision, tools and thinking; only the
coding/text/tool path was tested. Ollama's actual loaded context is 32,768; SDK
metric metadata reports the model's 262,144 context. This fixture's prompts were
below the effective server window. Long-context alignment is unverified; do not
interpret the SDK number as the configured host capacity. Draft documents still
leave whitespace and exception semantics unresolved and require operator review;
this acceptance establishes runtime functionality, not implementation quality.

Reviewable artifacts, exact test profile, action projection and model/outcome
metadata are in `docs/acceptance/ollama/`. Raw SDK history/diagnostics remain in
`.venv-openhands/ollama-native-acceptance`. The acceptance client exited; the
pre-existing Ollama server was left running. No paid API routing, Witmark work,
original-source modification, deployment or installed Flow replacement occurred.

Local Ollama inference/tool/persistence and both native acceptance paths are now
verified. Remote deployment and larger production coding tasks remain untested.

## Authorized 64K update

The existing development model now has effective context 65,536, with exact
32K rollback preserved and all other recipe parameters/base weights unchanged.
The branch-specific local profile forwards SDK input 65,536/output 8,192 and
uses stock summarization at 57,344. Real short-call verification passed; observed
model allocation was 16.24 GiB with normal memory pressure. Full repository suite:
2,135 run, 68 skipped, zero failures/errors; 12 focused SDK tests passed. Larger
prompt/actual summary-trigger behavior is untested. See
[setup and rollback](ollama-64k-setup.md). Prior acceptance evidence is unchanged.
