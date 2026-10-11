# Isolated implementation validation

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
