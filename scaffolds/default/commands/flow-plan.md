# flow-plan

Produce an executable change plan, sequencing, handoff and meaningful verification against the approved outcome.

Flow owns this workflow stage and its outputs. OpenHands owns execution, tools,
conversation history, retries and specialist delegation. Do not rebuild a Flow
manager, file broker, provider loop, token/rate gate or execution ledger.

## Enter and execute

For a configured self-hosted profile:

```sh
flow workflow execute <work-id> --stage plan --task-file <task.md>
```

The command enters a legal stage from the prior approved state and resumes the
stage/role's SDK conversation. Use `--role` and `--profile` for a specialist or
different self-hosted endpoint. Profile and role settings live in `.flow/runtime.toml`
and the user overlay. The installed OpenHands packages must match the pinned
runtime requirements. Actual workspace permissions still apply.

For an existing official native Codex/Claude session:

```sh
flow workflow native-handoff <work-id> --stage plan --profile <codex-or-claude-profile> --task-file <task.md>
```

Use that context artifact in the native session with its existing subscription
and permissions. Automated native profiles use stock OpenHands ACPAgent after
the scoped access decision in docs/native-access-decision.md. Stock ACP can grant
persistent native permissions; defaults leave acknowledgement unset. Native
handoff is a temporary interactive fallback. Do not copy credentials or switch billing.

## Durable outputs

Write these files under `.flow/runs/<work-id>/`:

- `plan.md`
- `handoff.md`
- `validation-plan.md`
- `verification-plan.json` for verification-v1 workflows: approved check IDs,
  criteria references, argv, registered evaluator files and `repair_limit: 2`.

Use specialist roles, project skills, context and existing approved artifacts as
needed. SDK TaskToolSet handles configured specialist delegation. Record actual
results and unresolved questions; a model response alone does not approve work.

## Delivery Lead coordination

The host assistant owns Delivery Lead coordination for this stage. Initiate
planning from the approved solution when available, otherwise the approved
definition (the solution stage is optional), coordinate technical specialists and
validation, and reconcile their evidence into the durable outputs listed above.
The lead-developer specialist supplies technical planning expertise; the host
retains coordination ownership. Present the plan and validation approach to
the user for explicit approval before beginning implementation.

## Approval and continuation

After the user/operator has reviewed the outputs:

```sh
flow workflow approve <work-id> --stage plan
```


Only explicit plan approval authorizes implementation. Do not infer it from
solution approval, completed planning, or specialist validation.

Inspect progress with `flow workflow status`, `flow run history` and SDK outcome
artifacts. Pause/block/resume through ordinary Flow lifecycle transitions.

Use the active runtime memory provider as companion context when available.
Verify material claims against canonical project artifacts and code.
