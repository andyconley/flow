# flow-plan

Produce an executable change plan, sequencing, handoff and meaningful verification against the approved outcome.

Flow owns lifecycle state, artifacts and approval gates. The current native host
owns definition, solution and planning coordination; OpenHands owns implementation.

## Enter and execute in the current host

Use the Flow agents installed in the current Claude or Codex host. Do not launch
an ACP coordinator or choose implementation providers during this stage.
Start new work with `flow workflow init <work-id>` when needed; preserve historical runs.
Enter the legal stage with `flow run transition <work-id> start-plan`.
Inspect approved prior artifacts and project instructions before delegation.

## Composition

Always delegate the technical work to the native `lead-developer` Flow agent, using
its entry in the generated Flow Agent Routing table. The host remains the
coordinator and reconciles the specialist's evidence; do not merely adopt its persona.
Conditional specialists: test-engineer for verification design; data-engineer for migrations; sre for deployment or recovery risk.
Preserve the native agent's model, effort, skills and permissions. If the host
cannot invoke a required agent, report that limitation rather than claiming a pass.

The optional explicit SDK CLI remains available for deliberately configured workflows:
`flow workflow execute <work-id> --stage plan --task-file <task.md> --profile <profile>`.
It is not the default path for this slash command. A native handoff can prepare
context for another host session without transferring approval authority.

## Durable outputs

Write these files under `.flow/runs/<work-id>/`:

- `plan.md`
- `handoff.md`
- `validation-plan.md`
- `verification-plan.json` for verification-v1 workflows: approved check IDs,
  criteria references, argv, registered evaluator files and `repair_limit: 2`.

Use specialist roles, project skills, context and existing approved artifacts as
needed. The current host invokes native Flow specialists. Record actual
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
