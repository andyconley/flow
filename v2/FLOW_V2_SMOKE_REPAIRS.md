# Native smoke-run investigation

This source change repairs reproducible runtime defects. It is not a successful
live delivery qualification and does not authorize retrying or accepting an
existing blocked work item. OpenHands execution is deprecated in the user-facing
documentation; its execution code, permission handling and installed state were
not changed. Legacy expertise runtime allowlisting, stage-skill defaults and
automatic v2 cutover remain outside this repair; v2 selection stays explicit.
The bundled Goose now includes source-bound
delegation enforcement, built in a separate Studio checkout; original build
sources, executables, stamps and active installations remain preserved.

## Reproduced and repaired

- `status` previously acquired the same exclusive operator lock as approval and
  delivery. It now reads a consistent, committed SQLite snapshot into memory,
  labels that view, and reports whether an operator remains active. Mutations
  still require the original exclusive lock. Status does not invoke workers or
  write the source checkpoint.
- Legacy replacement retains registrations sourced from ~/.flow/user, including
  generated overlay commands such as session-hygiene, and protects shared alias
  targets. Dry-run/inventory lists preserved_overlay_commands. Existing missing
  registrations are not reconstructed from a previously destructive cutover;
  restore those from that cutover's backup before selecting again.
- Publishing new .glg state creates a local .glg/.gitignore containing `*`, so
  private records do not appear in Git status. Project .gitignore and Git metadata
  are untouched. Existing custom ignore files and already tracked records remain
  under user control.
- Workers in linked Git worktrees could not read metadata outside the approved
  worktree directory. The sandbox now permits reads of Git's resolved metadata
  and common directory, with optional Git index refresh writes disabled. This
  does not grant writes to the shared repository metadata.
- Worker Python caches and shell temporary files lacked writable locations.
  Each attempt now receives a scoped home, Python bytecode cache, TMPDIR and zsh
  TMPPREFIX. A macOS sandbox probe exercises Git status, Python compilation and
  a large heredoc while retaining denial of unrelated home writes.
- Claude's temporary directory used a guessed workspace slug that mismatched
  paths containing dots. The worker now sets the documented CLAUDE_CODE_TMPDIR
  to a per-run writable directory, independent of slug derivation. See the
  [Claude environment-variable reference](https://code.claude.com/docs/en/env-vars).
- Delegates omitted required task/context parameters. Each attempt now gets a
  copy of the role bundle with approved task/context defaults. The distributed
  templates remain unchanged. Explicit assignment parameters still work. Literal
  template syntax in task text is escaped in the default scalar and preserved
  as data; offline tests render with the actual qualified Goose executable.
- Attempt-local recipes, the Claude wrapper and Goose child limit share a
  12-turn cap, replacing the four-turn execution cap. The coordinator's eight
  turns and the original approved job deadline remain unchanged. The coordinator
  supplies FLOW_V2_ROLE_SOURCES naming the converted recipes. Goose adds a
  required source enum to the delegate schema and checks it before creating a
  child. Missing/unknown sources and malformed policies are refused. Ad-hoc
  stock Goose delegation remains available when the Flow policy is absent.
- The qualified Codex adapter now distinguishes a finished command from a tool
  operation failure using its commandEnd facts and integer exit code. A nonzero
  exit retains its output, exit code and original native status in rawOutput;
  it does not poison a later valid native result. Missing exit codes, failed
  edits and existing permission boundaries still fail. Terminal commands retain
  rawOutput as well as terminal exit metadata. Replay tests exercise the actual
  adapter definitions and the unchanged Goose completion guard over ACP.
  Typed native command status declined becomes NATIVE_COMMAND_DECLINED with a
  permission_required boundary. Interrupted commands remain failed even when
  they include an exit code. Neither distinction depends on shell-output text.
- Workers and independent checks use the same project Python: an explicit
  interpreter path in the approved check_command, otherwise .venv/venv. Generic
  Python checks without a project interpreter stop with scope_required before
  dispatch. Workers receive python/python3 wrappers and read access to a selected
  external venv, without installing dependencies or changing global PATH.
  Attempt-local zsh/bash login profiles retain that PATH after macOS path_helper;
  actual login-shell regressions verify both shells select the project Python.
- Claude uses a private 0700 runtime/claude-home configuration directory. Its
  config, backups and locks can be written there; global account files remain
  read-only. A native auth-status preflight runs before each worker session.
  Failure writes a private typed AUTH_REQUIRED record, stops the execution scope
  and pauses for the operator instead of retrying, signing in or copying tokens.

## Remaining limits

The existing native-completion guard continues to reject observed failed-tool
operations even when a later report claims success. Command exit status is
preserved separately; final reports still require valid success/schema/terminal
evidence and independent project checks plus fresh review. The historical database stripped rawOutput, and the
available rollout cannot establish which live ACP completion path was used.
The policy-rejected command never reached ACP and cannot explain Goose's failed
tool evidence. Plain non-zero exits and shell denials have no reliable typed
distinction in these records. Shell-level failures without a typed marker are
recoverable command results, not proof that a permission boundary was absent.
This patch does not add denial matching on shell text or observe Codex-internal
policy rejections. The existing narrow Python PermissionError guard remains;
broader typed denial propagation still requires native-client support.

Future Codex workers capture actual server-side ACP tool_call/tool_call_update
JSON-RPC frames, preserving rawOutput and terminal metadata when present.
The attempt record's native_evidence_directory points to native-runtime/acp-evidence.
Each adapter process writes a unique 0600 JSONL file inside a 0700 directory.
Transport bytes, stdin, stderr and exit status remain unchanged. Authentication
and conversation frames are excluded; tool output can still contain sensitive
project data, so keep these ignored runtime files private and inspect/redact
before sharing. Files stop at 16 MiB and frames over 256 KiB produce an explicit
capture_gap; capture failures warn on stderr without stopping transport.
This cannot reconstruct historical frames, observe Codex-internal policy
rejections, or supply typed seatbelt denial evidence that the adapter lacks.

The private Claude configuration may need a human native sign-in before the
first live worker. From the source checkout, run
`CLAUDE_CONFIG_DIR="$PWD/v2/runtime/claude-home" claude auth login`, inspect
`claude auth status --json` with that same environment, then explicitly resume
the paused successor. Flow never starts login itself. Authentication/session
state remains native-client owned. Successful existing-account reuse under this
new directory has not been live-qualified; no credentials were copied.

The successor brief should name its intended interpreter and establish project
dependencies. This patch does not install pytest/Markdown or claim those
prerequisites are present. For example, use an approved check_command beginning
with `/absolute/project/.venv/bin/python -m pytest` as an argument array.

Preserve blocked-run evidence and existing partial edits. A successor requires
fresh exact-revision approval and quiescence of the old execution. Passing a
manually invoked test suite does not retroactively accept the original run.

## Validation

All 127 offline v2 tests pass on the Mac Studio with zero skips. Goose checks
pass for 41 delegation tests, 18 native-completion tests and 117 ACP-provider
tests; formatting and the locked offline binary build pass. Tests use disposable
state and no inference. Transport tests verify byte preservation, actual frame
capture, private permissions, size limits, gaps, separate process files, stdin
forwarding and capture-failure behavior. The tests use disposable projects, linked worktrees,
checkpoint databases and scratch directories. Actual Goose execution is limited
to recipe rendering, with no inference. Distribution checks and git diff --check
pass. Active installations, account files and the reported application worktree
were not modified.
