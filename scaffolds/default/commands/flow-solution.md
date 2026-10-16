# flow-solution

Inspect the project and propose an approach, alternatives, architecture decisions and risks against the approved requirements.

Flow owns lifecycle state, artifacts and approval gates. The current native host
owns definition, solution and planning coordination; OpenHands owns implementation.

## Enter and execute in the current host

Use the Flow agents installed in the current Claude or Codex host. Do not launch
an ACP coordinator or choose implementation providers during this stage.
Start new work with `flow workflow init <work-id>` when needed; preserve historical runs.
Enter the legal stage with `flow run transition <work-id> start-solution`.
Inspect approved prior artifacts and project instructions before delegation.

## Composition

Always delegate the technical work to the native `solution-architect` Flow agent, using
its entry in the generated Flow Agent Routing table. The host remains the
coordinator and reconciles the specialist's evidence; do not merely adopt its persona.
Conditional specialists: architect for cross-component boundaries; data-engineer for persistent state; security-reviewer for authentication or sensitive data.
Preserve the native agent's model, effort, skills and permissions. If the host
cannot invoke a required agent, report that limitation rather than claiming a pass.

The optional explicit SDK CLI remains available for deliberately configured workflows:
`flow workflow execute <work-id> --stage solution --task-file <task.md> --profile <profile>`.
It is not the default path for this slash command. A native handoff can prepare
context for another host session without transferring approval authority.

## Durable outputs

Write these files under `.flow/runs/<work-id>/`:

- `solution.md`

Use specialist roles, project skills, context and existing approved artifacts as
needed. The current host invokes native Flow specialists. Record actual
results and unresolved questions; a model response alone does not approve work.

## Delivery Lead coordination

Once the user explicitly approves the solution, the host assistant assumes
Delivery Lead coordination and initiates `flow-plan` in the active session.
Coordinate specialists and validation through the existing native
session. If another session is required, prepare the plan native handoff and
make the ownership and next action explicit. Approval records lifecycle state;
it does not dispatch an agent or authorize implementation.

## Approval and continuation

After the user/operator has reviewed the outputs:

```sh
flow workflow approve <work-id> --stage solution --disposition risk=accepted
```


Only explicit plan approval authorizes implementation. Do not infer it from
solution approval, completed planning, or specialist validation.

Inspect progress with `flow workflow status`, `flow run history` and SDK outcome
artifacts. Pause/block/resume through ordinary Flow lifecycle transitions.

Use the active runtime memory provider as companion context when available.
Verify material claims against canonical project artifacts and code.
