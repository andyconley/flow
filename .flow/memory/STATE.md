# Current State

## Active work

- None.

## Recently completed

- `session-model-recommendation` accepted at `62100b7` and archived. Flow now
  provides quality-first advisory parent-model recommendations for boot,
  resume, define, solution, and plan across Claude and Codex. The release proof
  includes 935 repository tests, all ten authenticated entry cells, and all
  eight configured model/effort mappings.

- `archive-legacy-import` stage6 accepted at `e2a2a11` and archived.
  All three review findings are resolved. Delivery is tracked in PR17 and its
  automated release workflow.

- `archive-retrieval` stages 1–5 accepted at `ea92460` and archived; all four acceptance
  findings resolved. Closeout artifacts are in `.flow/runs/archive-retrieval/`.
  Delivery is tracked in PR16 and its release workflow.

- `agent-web-access-policy` implemented, reviewed, validated, and released as
  `v0.23.0` from source commit `b4153ba`.
- Semantic `web_research` policy now grants web tools to all Flow agents by
  default, supports rationale-backed exceptions, and renders fail-closed native
  Claude and Codex configuration.
- The release pipeline validated the exact candidate before publication and
  then verified the public tag, release notes, fresh install, and upgrade.
- `release-validation-gate` was released as `v0.22.0`.
- `orchestration-safety-contract` implemented, reviewed, validated, and released as `v0.21.0`.

## Next step

- Delivery of `62100b7` beyond the local `main` checkout remains a separate
  release action. Re-run the authenticated entry and mapping evidence when
  model mappings, client versions, or account entitlement changes.
- Optional session-model advice follow-up: make the non-JSON context view show
  declared model details and evidence limitations, and render structured
  disposition identifiers as readable prose.
- Capability gap `archive-final-source-artifact` was observed once during
  closeout and awaits an explicit backlog-promotion decision.
- Deferred backlog: runtime memory capability and bounded recall, review rework
  transition (four observations), and runtime evidence completion manifest.
  All three gaps are promoted into `docs/backlog.md`; implementation is deferred.
- Optional follow-up: clearer review-only backfill status.

- No release action remains for `agent-web-access-policy`.
- Optional follow-up: design an approved live-runtime exercise for provider
  entitlement, task-level enforcement, and disclosure behavior.
- Capability gap `no-hermetic-test-standard` has now been observed twice and
  remains open pending an explicit decision to promote it.
