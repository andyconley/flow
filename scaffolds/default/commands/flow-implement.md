# flow-implement

Implement the approved plan with actual code and appropriate tests. Report evidence, limitations and remaining work in the handback.

Flow owns this workflow stage and its outputs. OpenHands owns execution, tools,
conversation history, retries and specialist delegation. Do not rebuild a Flow
manager, file broker, provider loop, token/rate gate or execution ledger.

## Enter and execute

For a configured self-hosted profile:

```sh
flow workflow execute <work-id> --stage implement --task-file <task.md>
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
does not enable automated ACP permission handling.

```sh
flow workflow native-handoff <work-id> --stage implement --profile <codex-or-claude-profile> --task-file <task.md>
```

Use that context artifact in the native session with its existing subscription
and permissions. Automated native profiles use stock OpenHands ACPAgent after
the scoped access decision in docs/native-access-decision.md. Stock ACP can grant
persistent native permissions; defaults leave acknowledgement unset. Native
handoff is a temporary interactive fallback. Do not copy credentials or switch billing.

## Durable outputs

Write these files under `.flow/runs/<work-id>/`:

- `implementation-evidence.md`
- `handback.md`

For verification-v1 workflows, the host runs `flow workflow check` after execution
returns to create `verification.json` and captured logs. Specialists must not
create, edit, or synthesize those host-owned records. Link the expected record
from the handback and state that host verification is pending until it exists.

Use specialist roles, project skills, context and existing approved artifacts as
needed. SDK TaskToolSet handles configured specialist delegation. Record actual
results and unresolved questions; a model response alone does not approve work.

## Approval and continuation

After the user/operator has reviewed the outputs:

```sh
flow workflow approve <work-id> --stage implement
```

Approval records implementation handback and enters review. It does not accept
the review, archive, merge, push or deploy.

Inspect progress with `flow workflow status`, `flow run history` and SDK outcome
artifacts. Pause/block/resume through ordinary Flow lifecycle transitions.

Use the active runtime memory provider as companion context when available.
Verify material claims against canonical project artifacts and code.

Follow `standards/git-commits.md` for any authorized commits.
