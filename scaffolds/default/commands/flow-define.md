# flow-define

Use research and evidence to clarify the requested outcome, stakeholders, constraints, non-goals and testable acceptance criteria. Surface consequential ambiguity to the user.

Flow owns this workflow stage and its outputs. OpenHands owns execution, tools,
conversation history, retries and specialist delegation. Do not rebuild a Flow
manager, file broker, provider loop, token/rate gate or execution ledger.

## Enter and execute

Start new work with `flow workflow init <work-id>`. Historical runs stay intact;
reference their artifacts in the new task rather than migrating checkpoints.

For a configured self-hosted profile:

```sh
flow workflow execute <work-id> --stage define --task-file <task.md>
```

The command enters a legal stage from the prior approved state and resumes the
stage/role's SDK conversation. Use `--role` and `--profile` for a specialist or
different self-hosted endpoint. Profile and role settings live in `.flow/runtime.toml`
and the user overlay. The installed OpenHands packages must match the pinned
runtime requirements. Actual workspace permissions still apply.

For an existing official native Codex/Claude session, select `--profile codex`
or `--profile claude`. Install/update provisions these interactive profiles only
when no user runtime configuration exists; existing configuration is preserved.
Inspect `flow workflow runtime --json` for resolved roles and missing setup.
SDK readiness is not execution readiness; never bypass a missing profile by
implementing directly in the host. Native handoff uses existing permissions and
does not enable automatic ACP permission handling. `workflow execute` with a native
profile uses terminal approvals by default: run it from a human-controlled terminal;
headless execution fails closed. These are terminal prompts, not desktop dialogs.

```sh
flow workflow native-handoff <work-id> --stage define --profile <codex-or-claude-profile> --task-file <task.md>
```

Use that context artifact in the native session with its existing subscription
and permissions. Native execution uses OpenHands ACPAgent through Flow's terminal permission proxy.
Every native permission request requires explicit human selection; timeout, EOF or
missing terminal denies it. Selecting a persistent option can change native rules.
The legacy `stock-openhands` option automatically answers requests and requires
a separate access decision; it is never selected by default. Native handoff
is a temporary interactive fallback. Do not copy credentials or switch billing.

## Durable outputs

Write these files under `.flow/runs/<work-id>/`:

- `requirements.md`
- `acceptance-criteria.md`

Use specialist roles, project skills, context and existing approved artifacts as
needed. SDK TaskToolSet handles configured specialist delegation. Record actual
results and unresolved questions; a model response alone does not approve work.

## Approval and continuation

After the user/operator has reviewed the outputs:

```sh
flow workflow approve <work-id> --stage define
```


Inspect progress with `flow workflow status`, `flow run history` and SDK outcome
artifacts. Pause/block/resume through ordinary Flow lifecycle transitions.

Use the active runtime memory provider as companion context when available.
Verify material claims against canonical project artifacts and code.
