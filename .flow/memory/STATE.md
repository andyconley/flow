# Current State

## Active work

- No other work in flight. All other runs are archived, blocked as superseded, or (for
  `agent-expertise-rag-retrieval`) paused; `20260809-105804-agent-model-routing`
  is a legacy record.
- `local-verifier-json-contract` (scout) is archived. The change is on
  `codex/local-verifier-json-contract`, merged as PR #35 and released in v0.35.2.
  - The first live check (2026-09-25) had every local verifier reply judged
    `unusable`. The models followed the role's markdown output format instead
    of the JSON contract.
  - The fix: a v8 verifier now gets derived system instructions, which are the
    role body without its Output Format section plus Flow's contract. Ollama
    verifier calls also send the verdict JSON schema as `format`. The parser
    stays strict.
  - The re-check through Flow's real dispatch path passed: gemma4:26b 6/6 and
    llama3.1:8b 6/6, each usable and correct.

## Recently completed

- `edit-worker-stream-cap` (scout) archived 2026-09-26 and merged as PR #38.
  - Fixes D1: the Claude edit worker's cap rises to 16 MiB, partial messages
    are dropped, and the debug trace is truncated rather than aborting.
  - Fixes D2: the help generator escapes `|`.
  - Promotes three gaps to the backlog.
  - Full suite: 1,543 tests OK, 0 skipped. Next: release v0.36.1, then
    `v8-live-validation-2`, whose job test must expect escaped `\|` rows.
- `v8-live-validation` archived 2026-09-26 as "validation found defects"
  (run artifacts only; merged as PR #39).
  - The first live v8 chartered job (v0.36.0, real Claude) proved sealed
    authority, preparation, 3 gated manager calls and a granted edit.
  - It was interrupted at 137 s by D1 (the edit worker's 1 MiB stream cap).
  - The expansion chain was not reached.
  - D2: the help generator emitted raw `|` in table cells.
  - Both are fixed by `edit-worker-stream-cap`. The worktree
    `~/src/flow-v8-live-job` can be removed once `v8-live-validation-2`
    creates its own.

- `shaper-expansion-approval` (MAF adoption step 5, slice 1) accepted and archived
  2026-09-26 on `codex/step5-shaper-approval-design` (one PR). v8 delegated
  expansion (ADR 0017):
  - the Shaper seals headroom for five limits, bounded by the runner ceilings;
  - requests within headroom are granted automatically, and anything beyond
    pauses for `flow run decide-expansion`;
  - `recover-delivery-lead` replays the paused proposal under the decision.

  The full suite passed 1,538 tests with 0 skipped; there were 5 MAF-gated
  end-to-end cases and 10 mutation checks. The first live run found defects (see
  `v8-live-validation`). Next: the fix run and a second validation run, then the rest of step 5 (cancellation,
  trace correlation, MCP handback, token cap).

- v8 chartered delivery recovery merged and released as v0.35.0 (PRs #26,
  #29, #30).

- `chartered-delivery-recovery-2` accepted and archived. An interrupted v8
  attempt whose producer or verifier response Flow already stored is completed
  with `resolve-execution --expected-generation N` then `recover-delivery-lead`,
  with zero resends; manager calls and unobserved actions are abandon-only.
  The full suite passed 1,465 tests with 0 skipped.

- `chartered-delivery-recovery-1b` accepted and archived. A Delivery Lead
  resume or supersede now seals started v8 attempts as `superseded` behind a
  ledger-backed guard, and successor attempts link their predecessors and
  share the charter caps; the seal checks `lineage_usage` against the ledger.
  The full suite passed 1,443 tests with 0 skipped and the 11 MAF-gated tests
  ran locally.

- `chartered-delivery-recovery` chunk 1a accepted, merged as PR #26, and
  archived. Interrupted v8 chartered attempts now recover explicitly on the
  same attempt from the latest Flow-bound checkpoint (ADR 0016). The full
  suite passed 1,425 tests and the 11 MAF-gated tests ran locally.

- `v7-pre-send-failure-allow-list` scout archived and merged as PR #27. `close_pre_send_failure` now
  releases an unconsumed v7 grant instead of raising over the original
  pre-dispatch error. The full suite passed 1,371 tests.

- `structured-verifier-contract` accepted, archived, and merged as PR #25. Protocol v8 adds a Flow-evaluated,
  evidence-bound verifier verdict with a Charter-sealed call cap of one or
  two. A contract prompt is appended to the verifier input, receipts recompute
  each evaluation, and v6 and v7 receipts keep their meaning. The full suite
  passed 1,370 tests. v8 resume shipped in chunk 1a; a controlled live Ollama
  verifier run remains the main follow-up.

- `shaper-delivery-runtime-contracts` accepted and archived. Flow now projects
  approved Shaper authority into a supervised Magentic Delivery Lead with
  bounded Claude or Codex production, distinct Ollama verification, exact
  policy and runtime limits, and authority-linked receipts. The full suite
  passed 1,321 tests with 1 skipped. Merged as PR #24.

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
