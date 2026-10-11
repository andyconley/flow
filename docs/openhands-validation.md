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
