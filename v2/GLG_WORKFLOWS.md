# Flow v2.0 workflow contracts

For normal installation, selection, native skills and update/rollback see [FLOW_V2_INSTALL.md](FLOW_V2_INSTALL.md). The internal module remains poc.glg and existing .glg artifacts keep their names.

The native host shapes work; LangGraph owns workflow state; Goose owns delivery coordination and specialist/provider choices. The 13 existing roles, expertise, broad tools and native signed-in adapters are reused. This isolated implementation leaves the Flow installation and historical records in place. The workflow implementation itself does not install anything; the separate opt-in installer is documented in the installation guide.

Use the existing Python environment from this repository:

```sh
.venv/bin/python -m poc.glg --project /absolute/project --work work-id create --request 'The problem to investigate'
.venv/bin/python -m poc.glg --project /absolute/project --work work-id status
```

Creating a request, publishing shaping artifacts, or viewing status never launches inference. Only explicit implementation approval enters delivery; resuming an approved delivery can also execute pending work. There is no implicit approval, credential setup, API billing fallback, migration, merge, push or deployment.

## Shape in the native host

Start with the current native host's project instructions and connected research tools. Discover evidence, ask consequential questions, delegate useful specialist questions, and reconcile findings there. The CLI records those handoffs; it does not pretend to have researched or launch a second shaping coordinator.

```sh
.venv/bin/python -m poc.glg --project /absolute/project --work work-id assign --stage define --question 'Which user outcomes and constraints are supported by current evidence?'
```

Status now links an exact assignment revision. Read that file and its context/brief references. The native host can delegate it using the existing business-analyst role; conditional specialists remain available. `workflow-recipes/define.yaml`, `solution.yaml` and `plan.yaml` provide reusable specialist assignments for Goose/native-host use, referencing the existing role bundle instead of copying expertise. They retain common developer/skills tools and normal credential/external-action boundaries. Research connector access remains with the host/tool installation actually providing it.

Record the returned substantive result:

```sh
.venv/bin/python -m poc.glg --project /absolute/project --work work-id stage --stage define --file /absolute/definition-and-evidence.md
```

Use optional `solution` assignments/results for alternatives and architecture, and `plan` for implementation steps/checks. Small, clear work may skip these stages. Direct host-authored stage output is allowed without a delegated assignment; it must not claim an unperformed delegation.

Separate explicit decisions are available where warranted:

```sh
.venv/bin/python -m poc.glg --project /absolute/project --work work-id approve-stage --stage solution --actor Andy --reason 'Approach accepted; implementation remains unapproved'
```

That records stage approval and returns to shaping. It does not authorize implementation. Repeating `assign` or `stage` explicitly supersedes its previous controlled revision. New work after final implementation approval uses a successor work ID, with historical references to the original.

## Publish and approve the canonical brief

Prepare JSON with at least:

```json
{
  "goal": "Concrete user outcome",
  "scope": ["The approved change boundary"],
  "non_goals": ["Excluded work"],
  "acceptance_criteria": ["Observable required behavior"],
  "steps": ["Implementation and validation approach"],
  "check_command": ["python3", "-m", "unittest", "discover", "-s", "tests"],
  "risks": [],
  "sources": [],
  "historical_references": [".flow/runs/prior-work/requirements.md"]
}
```

Choose actual project checks; the check command is an argv array executed in the project workspace under existing permissions. The native host should resolve open questions before asking for approval. A single compact final approval is the routine path.

```sh
.venv/bin/python -m poc.glg --project /absolute/project --work work-id brief --file /absolute/brief.json
.venv/bin/python -m poc.glg --project /absolute/project --work work-id status
.venv/bin/python -m poc.glg --project /absolute/project --work work-id approve --actor Andy --revision EXACT_BRIEF_REVISION_FROM_STATUS
```

**The last command starts real delivery and may consume the existing native subscription/local model resources.** Use it only after the human has approved that exact brief. Actor names record a host-asserted decision; the local CLI is not a multiuser authentication service.

To refine before approval, edit the source brief and run `brief` again. GLG publishes a new revision explicitly superseding the prior one, then pauses for approval again. Previous revisions remain readable. `create --brief-file /absolute/brief.json` is the direct small-task/scout path, still requiring final approval. `stop --actor Andy --reason '...'` stops unapproved work.

Creation accepts `--provider`, `--model` and `--budget-seconds`; defaults retain the existing native parent coordinator configuration (`chatgpt_codex`, `gpt-5.6-sol`, 600 seconds). Goose selects useful workers among configured roles/providers. This does not require every task to use Ollama, Claude and Codex. Existing role/provider bindings are retained. No new credential or model installation occurs.

## Controlled files and ownership

```text
<project>/.glg/work/<work-id>/
  contexts/project-<revision>.json
  briefs/brief-<revision>.json
  assignments/<operation>-<revision>.json
  shaping/<stage>-<revision>.json
  decisions/<decision>-<revision>.json
  results/<operation>-<revision>.json
  closures/closure-<revision>.json
<project>/.glg/INDEX.md                   # optional rebuildable closure view
<isolated GLG repo>/artifacts/glg-state/<project-key>/<work-id>/workflow.sqlite
```

Each file is readable JSON with schema version, work ID, kind, record ID, payload and explicit `supersedes` reference. Revision-specific paths and ordinary content identities detect accidental edits. There is no signing/sealing ceremony or parallel lifecycle manifest. Referenced revisions are published atomically and are not overwritten. Brief/decision/assignment/result references are persisted in LangGraph checkpoints before or after their corresponding boundaries. `.glg` records and `.git` are excluded from the delivery candidate hash; actual source changes still affect candidate identity.

The host records project context, canonical brief and human decisions. Goose creates implementation/review assignments at graph-owned dispatch boundaries; workers return real evidence. Checks use the approved argv. The handoff layer records invocation intents/results without becoming another scheduler. Assignment results describe completion of that invocation, including any reported limitations; they do not claim an exhaustive transaction log of every tool the native worker used.

Project context snapshots applicable ancestor/project AGENTS.md, CODEX.md, CLAUDE.md, existing Flow PROJECT.md, optional GLG PROJECT.md, transient Flow STATE.md, and Git identity/dirty state. Most-specific project instructions take precedence; native-client instructions remain authoritative. Transient state is marked companion context. Role expertise stays in the existing role bundle/Flow content resolver. Context is intentionally pinned for the work item; changed instructions or scope should be reviewed in a successor work item rather than silently substituted.

## Status, recovery and pause/resume

```sh
.venv/bin/python -m poc.glg --project /absolute/project --work work-id status
.venv/bin/python -m poc.glg --project /absolute/project --work work-id resume
.venv/bin/python -m poc.glg --project /absolute/project --work work-id resume --decision-file /absolute/decision.json
```

Status is derived from the graph checkpoint, including nested delivery interrupts and exact artifact references. It reports altered/missing revisions rather than substituting the newest file. A completed graph resumes without another worker invocation. An operator lock prevents two CLI writers for the same work item; distinct work items still require sensible separate-worktree/user coordination.

A real scope/permission pause accepts a decision file such as:

Explicit native permission/scope errors are preserved through the adapter, stop the Goose coordinator before another worker dispatch, and enter this graph pause. The original diagnostic stays in the controlled result/job record. Generic failures and absent telemetry are not reclassified as permission evidence; see [GLG_NATIVE_ERRORS.md](GLG_NATIVE_ERRORS.md).

```json
{"action": "resume", "actor": "Andy", "reason": "The reported permission issue was resolved; continue the same approved scope"}
```

Use `action: stop` to stop it. Material scope or acceptance changes require a new approved successor brief/work item. Corrections within the original scope remain automatic: initial implementation plus up to three correction rounds, followed by concise findings/blocker if unresolved.

External invocation intents are recorded before execution. A crash before a result checkpoint can leave:

- **Completed:** reuse the exact recorded result, without a duplicate invocation.
- **Pending:** inspect/reattach the identified existing job; do not start another copy.
- **Uncertain:** inspect the actual workspace/job; do not infer failure and replay it.

For an uncertain/pending effect, `status` links the assignment and result. Inspect actual evidence, then submit one of:

```json
{"actor": "Andy", "effect": "completed", "evidence": "Specific inspected job/workspace evidence", "result": {"status": "completed", "findings": [], "test_results": {}}}
```

```json
{"actor": "Andy", "effect": "not_started", "evidence": "Specific evidence that this assigned action did not start"}
```

The first records a recovered implementation result without replay. Check/review recovery instead needs its real `passed` boolean and, for review, the assigned `candidate` identity. The second permits the same authorized operation to execute. A running job must remain pending until its outcome can be inspected. Recovery decisions become controlled files too. Resume never invents native-client session continuation; the existing runtime may expose job evidence, while graph state/artifact context survive independently.

The delivery wall-clock budget starts at final approval and persists through pause/restart. It is not silently extended; choose an appropriate budget at creation. Check timeouts or unresolved native effects need inspection. This local entry has no background job monitor or general live-job reattachment UI.

For a closed blocked review caused by a repaired adapter/runtime problem, `resume --decision-file` also accepts `{"action":"retry-review","actor":"Andy","reason":"Specific repaired problem; recheck the unchanged candidate"}`. It requires the identical candidate and remaining original budget, records a decision against the blocked closure, and reruns only checks and fresh review. It does not repeat implementation or reset the deadline. The successor closure explicitly supersedes the blocked one. Changed candidates or approved scope require a successor work item instead.

## Closure and acceptance

Delivery produces a closure with technical outcome, exact input/decision/result references, candidate, findings, checks and historical links. `reviewed-and-ready` does not claim user acceptance or deployment. A blocker also produces a concise closure. Closure is a regular graph node and recovers without re-running delivery.

```sh
.venv/bin/python -m poc.glg --project /absolute/project --work work-id accept --actor Andy --revision EXACT_CLOSURE_REVISION_FROM_STATUS
.venv/bin/python -m poc.glg --project /absolute/project --work work-id index
```

Acceptance records a new decision and closure revision and leaves the prior record intact. It is only available for reviewed-and-ready work. The optional index is rebuilt from immutable closure artifacts and is never used to schedule/resume work. It does not crawl or rewrite historical Flow runs. The project decides whether to commit its `.glg` artifacts; this implementation does not automatically commit application work or publish it externally.

## Verification and current limits

Offline tests cover native-host request/shaping/approval, exact revision rejection and refinement, delivery integration, three invocation records, SQLite close/reopen, uncertain-effect reconciliation, completed-result reuse across a checkpoint gap, changed-candidate checks, context precedence, acceptance and closure indexing. Existing role/native adapter tests remain in use. No new live-model proof campaign was run.

The separate opt-in installer now provides the Flow v2 launcher and native-host entry skills; see FLOW_V2_INSTALL.md for selection, managed legacy cleanup and rollback. It is source-bound to the existing Mac runtime, not a clean-machine dependency bootstrap or production migration. Shaping research remains host-driven; connected-tool access is not copied to a new service. Existing Flow composition remains a content dependency. There is no cross-host sync, authenticated approval service, old-run state import, semantic archive search, automatic native session restore, or merge/deploy action. Historical references and existing user tools remain available.
