# flow-define

Use research and evidence to clarify the requested outcome, stakeholders, constraints, non-goals and testable acceptance criteria. Surface consequential ambiguity to the user.

Flow owns lifecycle state, artifacts and approval gates. The current native host
owns definition, solution and planning coordination; OpenHands owns implementation.

## Enter and execute in the current host

Use the Flow agents installed in the current Claude or Codex host. Do not launch
an ACP coordinator or choose implementation providers during this stage.
Start new work with `flow workflow init <work-id>` when needed; preserve historical runs.
Initialization already enters definition; do not repeat `start-definition` for that run.
Inspect approved prior artifacts and project instructions before delegation.

## Composition

Always delegate the technical work to the native `business-analyst` Flow agent, using
its entry in the generated Flow Agent Routing table. The host remains the
coordinator and reconciles the specialist's evidence; do not merely adopt its persona.
Conditional specialists: product-manager for consequential scope decisions; ux-specialist when user experience affects acceptance.
Preserve the native agent's model, effort, skills and permissions. If the host
cannot invoke a required agent, report that limitation rather than claiming a pass.

The optional explicit SDK CLI remains available for deliberately configured workflows:
`flow workflow execute <work-id> --stage define --task-file <task.md> --profile <profile>`.
It is not the default path for this slash command. A native handoff can prepare
context for another host session without transferring approval authority.

## Durable outputs

Write these files under `.flow/runs/<work-id>/`:

- `requirements.md`
- `acceptance-criteria.md`

Use specialist roles, project skills, context and existing approved artifacts as
needed. The current host invokes native Flow specialists. Record actual
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
