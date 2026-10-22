# Candidate-bound review recovery

`flow --project PROJECT --work WORK status` shows the proposed/default budget
before implementation approval, current remaining/expired budget, pause decisions,
blocker stage/reason/result, and grouped operation evidence. Two immutable result
records (intent and returned outcome) describe one operation; they do not prove two
native executions. Identical nested interrupts are deduplicated; conflicting
values for an interrupt ID are diagnostics requiring inspection.

## Recover an unchanged closed candidate

A closed, blocked review exposes a `recover_review` decision template in status.
Inspect the referenced evidence and actual candidate, then save an explicit approval
as `DECISION.json`. Replace the actor/reason placeholders and choose a bounded new
`budget_seconds` (1–86400). Keep the exact `closure_ref`, `brief_ref`, and
`candidate_revision` from that status:

```json
{
  "action": "recover-review",
  "actor": "ACTUAL APPROVING PERSON",
  "reason": "Why checks and a fresh review are now appropriate",
  "closure_ref": {"path": "EXACT STATUS PATH", "revision": "EXACT STATUS REVISION"},
  "brief_ref": {"path": "EXACT STATUS PATH", "revision": "EXACT STATUS REVISION"},
  "candidate_revision": "EXACT STATUS CANDIDATE",
  "budget_seconds": 600
}
```

Submit only after the host approves that exact candidate and new budget:

```sh
flow --project PROJECT --work WORK resume --decision-file DECISION.json
```

This approval permits independent checks followed by fresh review. Failed checks
or review findings close blocked and require a separately approved successor for
implementation; recovery cannot enter implementation/correction. A later recovery
requires approval naming its new closure. Original briefs, approvals, closures,
results and intents remain immutable. Acceptance remains a separate decision.
Wrong/stale references, changed content, tampered evidence, active operator,
pending execution and live/uncertain native process evidence reject recovery.
Process identities are observed without signaling or stopping processes. Historical
`quiescent=false` or `scope_uncertain` evidence conservatively blocks recovery even
if those processes later disappear; inspect and preserve it for a successor.
`retry-review` keeps its original nonexpired-deadline guard and also cannot correct.
It now requires the same exact closure, brief and candidate references and common
evidence/quiescence validation; a bare actor/reason file is insufficient.

Recovery validates Flow's existing candidate tree digest (file contents excluding
`.git`, `.glg`, and `__pycache__`). It does not certify external dependencies or
unrecorded effects outside that tree. Native scopes lacking sufficient quiescence
evidence remain blocked; this command grants no authority to erase uncertainty.
It is limited to closed blocked reviews, rather than arbitrary failed work.

## Budget and pause policy

New work uses `exclude-permission-scope-pauses-v1`: execution starts after approval;
when a permission/scope blocker reaches its persisted host pause, the remaining
execution time is frozen. Explicit same-scope resume restores only that remainder.
It does not authorize extra execution time. An already exhausted remainder cannot
resume. Intentional `stop` remains available without execution budget.

Uncertain-effect reconciliation retains its original deadline: until actual effects
are known, Flow cannot infer unused execution time. Status explicitly reports this
policy. Human waiting there can exhaust the deadline; inspect the original effect
and preserve evidence, then use a supported closed review recovery or a separately
approved successor. Existing records without the new policy retain their approved
wall-clock deadline, including human waiting; no automatic migration or extension
occurs. Expired CLI resume is rejected before execution transitions or decisions.

## Setup checks

Brief proposal and approval validate Python interpreter paths without executing the
check command; dispatch revalidates. Python checks require an explicit executable
or a project `.venv`/`venv`; ambient Python is never silently selected. Native
operations preflight the coordinator and all bound role recipe providers using
isolated runtime configuration before coordinator dispatch. Failed preflight does
not publish a native invocation intent. Every operation/resume revalidates readiness.
No sign-in, credential copying, model pull or provider switching occurs in preflight.
Account readiness cannot guarantee later quota/model availability; explicit local
Codex configuration validation leaves inference availability to dispatch.

See [predecessor linkage](GLG_PREDECESSORS.md) for dedicated successor history links.
Linkage never imports predecessor approval or overloads artifact supersession.

### Research handoff repair and verification evidence

A stage's substantive research and raw result are immutable work-item artifacts
under `.glg/work/<work>/shaping` and `results`. If its proposed brief is invalid,
Flow pauses with `kind=repair-brief`, field diagnostics, the coordinator's shared
schema, and exact research/repair references. Inspect those references and use
`flow --project PROJECT --work WORK brief --file repaired.json`. Alternatively,
resume with `{"action":"brief","brief_ref":{"path":"...","revision":"..."}}`.
This repairs the failed transition using the completed operation result; it does
not launch the specialists again. Repeated resume without a decision stays paused.
An uncertain operation still requires evidence-based reconciliation before replay.
Revised briefs supersede their predecessors and require approval of the new exact
revision. Approval shows the verification expectations and previous revision.

Definition drafts may use `verification_plan` without an argv through create or
brief revision commands. Implementation approval and plan-stage readiness require a nonempty executable `check_command` argv. Publishing/editing a brief
validates its structure. Approval and execution preflight check the real cwd,
PATH, command executable, project Python selection, and optional `prerequisites`
(executable names/paths). Resolve setup outside the timed check with existing
authorization; Flow performs no implicit install or credential change. A checker
must itself build fresh outputs and assert domain requirements where needed.

Optional `coverage` maps every acceptance criterion exactly once to `automated`,
`manual`, or `uncovered`, with an evidence description. `check_scope` is `smoke`
or `acceptance`; omitted mappings remain uncovered and omitted scope is smoke.
Check evidence retains the exact brief/candidate revision, environment, output,
exit, coverage, manual review and gaps. A passing smoke command is not full
acceptance. Manual criteria require actual human review; closure acceptance
remains a separate exact-revision decision.

Work commands return 2 for invalid briefs or failed/blocked/timed-out outcomes
and 3 for uncertain effects requiring reconciliation. Zero can also mean a
successfully handled command paused awaiting approval: inspect JSON `outcome`,
`pending` and `stage_outcome` before announcing completion. Read-only status is
observational. Flow cannot force external caller wrappers to propagate its exit
status: wrappers must preserve the child status and inspect its structured outcome.
