# Current State

## Active work

- `chartered-delivery-recovery-1b`: the superseded seal, ledger-backed
  lead guard, successor predecessors, and lineage limits (plan commits 12-13
  of `chartered-delivery-recovery`). Chunk 2 follows as its own linked run.

## Recently completed

- `chartered-delivery-recovery` chunk 1a accepted, merged as PR #26, and
  archived. Interrupted v8 chartered attempts now recover explicitly on the
  same attempt from the latest Flow-bound checkpoint (ADR 0016). The full
  suite passed 1,425 tests and the 11 MAF-gated tests ran locally.

- `v7-pre-send-failure-allow-list` scout archived on branch
  `codex/v7-pre-send-failure-allow-list`. `close_pre_send_failure` now
  releases an unconsumed v7 grant instead of raising over the original
  pre-dispatch error. The full suite passed 1,371 tests.

- `structured-verifier-contract` accepted and archived on branch
  `codex/structured-verifier-contract`. Protocol v8 adds a Flow-evaluated,
  evidence-bound verifier verdict with a Charter-sealed call cap of one or
  two. A contract prompt is appended to the verifier input, receipts recompute
  each evaluation, and v6 and v7 receipts keep their meaning. The full suite
  passed 1,370 tests. Publication and merge remain pending. A controlled live
  Ollama verifier run and v8 resume support are the main follow-ups.

- `shaper-delivery-runtime-contracts` accepted and archived. Flow now projects
  approved Shaper authority into a supervised Magentic Delivery Lead with
  bounded Claude or Codex production, distinct Ollama verification, exact
  policy and runtime limits, and authority-linked receipts. The full suite
  passed 1,321 tests with 1 skipped. Publication and merge remain pending.

- `role-method-differentiation-repair-3` accepted, merged, and released as
  `v0.28.0` at `6055b6b`. Architect, lead-developer, and test-engineer now use
  evidence-backed expertise; product-manager and quality-reviewer remain
  base-only. The 250-check frozen verifier, release workflow, refreshed
  installation, and fresh Claude/Codex checks passed.

- `agent-expertise-join-validation-refinement` accepted at `210bdf7`. It
  completes the teaches-join validation refinement with strict DefinedTerm
  validation, a sync-boundary regression test, and isolated Claude/Codex
  candidate-source proof. The branch is ready for merge; live-client smoke
  checks remain post-install follow-up.

- `archive-retrieval-documentation` accepted at `fadaac3` and archived. Archive
  retrieval is now discoverable in the changelog, README, and generated Claude
  and Codex help. The v0.24 public release body was reconciled, and future
  curated highlights stay inside the exact-SHA semantic-release path. The
  repository and external-state evidence passed independent quality and test
  review.

- `session-model-recommendation` accepted at `62100b7` and archived. Flow now
  provides quality-first advisory parent-model recommendations for boot,
  resume, define, solution, and plan across Claude and Codex. The release proof
  includes 935 repository tests, all ten authenticated entry cells, and all
  eight configured model/effort mappings.

- `v0.26.0` published and passed the release workflow at `6603baf`. The release
  includes session model advice and the archive final-source fix. The final
  repository suite passed 936 tests, both generated adapters were current, and
  runtime smoke reported no failures.

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

- Re-run the authenticated entry and mapping evidence when model mappings,
  client versions, or account entitlement changes.
- Optional session-model advice follow-up: make the non-JSON context view show
  declared model details and evidence limitations, and render structured
  disposition identifiers as readable prose.
- Deferred backlog: runtime memory capability and bounded recall, review rework
  transition, runtime evidence completion manifest, and promoted-gap frequency
  staleness. The first three gaps are promoted into `docs/backlog.md`; the
  frequency-staleness gap is repeated but still open. Implementation is
  deferred.
- Optional follow-up: clearer review-only backfill status.

- No release action remains for `agent-web-access-policy`.
- Optional follow-up: design an approved live-runtime exercise for provider
  entitlement, task-level enforcement, and disclosure behavior.
- Capability gap `no-hermetic-test-standard` has now been observed twice and
  remains open pending an explicit decision to promote it.
