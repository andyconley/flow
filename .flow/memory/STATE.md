# Current State

## Active work

- None.

## Recently completed

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

- Separate delivery: stage 6 reviewed legacy import.
- Deferred backlog: runtime memory capability and bounded recall, review rework
  transition (three observations), and runtime evidence completion manifest.
  All three gaps are promoted into `docs/backlog.md`; implementation is deferred.
- Optional follow-up: clearer review-only backfill status.

- No release action remains for `agent-web-access-policy`.
- Optional follow-up: design an approved live-runtime exercise for provider
  entitlement, task-level enforcement, and disclosure behavior.
- Capability gap `no-hermetic-test-standard` has now been observed twice and
  remains open pending an explicit decision to promote it.
