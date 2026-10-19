# Native smoke-run investigation

This source change repairs reproducible runtime defects. It is not a successful
live delivery qualification, does not change the bundled Goose executable, and
does not authorize retrying or accepting an existing blocked work item.

## Reproduced and repaired

- `status` previously acquired the same exclusive operator lock as approval and
  delivery. It now reads a consistent, committed SQLite snapshot into memory,
  labels that view, and reports whether an operator remains active. Mutations
  still require the original exclusive lock. Status does not invoke workers or
  write the source checkpoint.
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
  is explicitly instructed to select a converted role rather than a role-less
  delegate with no development extensions; that instruction is not a new
  enforcement mechanism inside Goose.

## Remaining limits

The existing native-completion guard rejects observed failed-tool evidence even
when a later report claims success. Failed tests during test-first work can be
legitimate, but a policy rejection or unresolved permission boundary must not be
silently treated as success. The historical database stripped rawOutput, and the
available rollout cannot establish which live ACP completion path was used.
The policy-rejected command never reached ACP and cannot explain Goose's failed
tool evidence. Plain non-zero exits and shell denials have no reliable typed
distinction in these records. This patch does not clear failed-tool evidence,
infer denial from shell text, bypass permission decisions, or rebuild Goose.

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

The Claude wrapper still uses the existing native account configuration. Its
attempted global config-lock writes can remain denied; no blanket home/config
write permission or account-copying workaround was added. Per-run configuration
isolation needs separate authentication qualification.

A generic `python3` check command can select a different interpreter on a GUI
host's PATH. The successor brief should name the intended project interpreter
and establish its dependencies. This patch does not guess a replacement Python,
install pytest/Markdown, or claim those project prerequisites are present.

Preserve blocked-run evidence and existing partial edits. A successor requires
fresh exact-revision approval and quiescence of the old execution. Passing a
manually invoked test suite does not retroactively accept the original run.

## Validation

All 117 offline v2 tests pass on the Mac Studio with zero skips, including
three additional transport tests verifying byte preservation, actual frame
capture, private permissions, size limits, gaps, separate process files, stdin
forwarding and capture-failure behavior. The tests use disposable projects, linked worktrees,
checkpoint databases and scratch directories. Actual Goose execution is limited
to recipe rendering, with no inference. Distribution checks and git diff --check
pass. Active installations, account files and the reported application worktree
were not modified.
