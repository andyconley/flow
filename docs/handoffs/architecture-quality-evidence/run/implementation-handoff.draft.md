# Implementation handoff — awaiting shaping acceptance

Do not begin implementation from this draft. The run remains planning; solution is approved, planning engagement is confirmed, and engineer acceptance of the shaping proposal is pending.

Read solution.md, planning-proposal.md, validation-plan.draft.md, requirements.md and research/planning-baseline.json. Canonical run artifacts stay in `/Users/andyconley/repos/Personal/.flow/runs/architecture-quality-evidence`; implementation belongs in `/Users/andyconley/repos/Personal/flow-architecture-pilot`. Future provider briefs must declare that checkout and exact files. Use `flow run validate-orchestration architecture-quality-evidence --stage dispatch` from the run host before dispatch/mutations; do not hand-edit run.json.

## Starting state

Isolated clone at v0.28.0 / 6055b6b2dd4ca5fe9a9879d61523bbd08fa0736d; clean detached HEAD observed during planning. Create a feature branch there before code changes. Do not modify `/Users/andyconley/personal/flow`, install develop mode, sync installed adapters, publish or change production gates.

## Execution order and ownership

1. Implementing engineer owns contract, snapshot, Python adapter, local viewer and CLI shell. First prove exact Tach source joins and safe local report delivery. Preserve TypeScript-shaped contract fixture as portability test, not actual language support.
2. Same contract owner integrates policy/delta module and fixtures. Andy owns approved rule semantics; independent reviewer validates oracle and fail/inconclusive behavior. Schema/shared entrypoint changes serialize.
3. Quality adapter owner works against stable contract from 1, with no changes to 2's files. Validate mutmut compatibility before broader evidence UI work. If incompatible, document raw failure and propose Cosmic Ray or another existing tool; no fallback is already approved as demonstrated.
4. Coordinator assembles packet, reproduction docs and review link. Independent reviewer checks evidence. Andy completes the four-review exercise and expansion decision; do not simulate his review or invent timings.

## Known limitations to retain

Prior work demonstrated CLI graph extraction plus Radon/coverage on collector tests, not end-to-end pilot completion. Tach's analyzer-only pyproject workaround must remain isolated and fingerprinted. Mutmut, browser interaction and measured reviewer benefit are unverified. Tool locks and transitive hashes must be produced before collection; scripts do not fetch/install silently during evidence generation. Source/version/config cache keys must include tests and mutation settings where relevant; disable mutation result caching for the first proof to reduce stale-result risk.

Stop dependent work for missing source provenance, incompatible mutation execution, unexplained scope gaps or changed requirements. Continue independent documentation/tests where useful. Escalate a concrete alternative decision rather than silently weakening the proof. Missing required evidence is inconclusive.

## Closeout expectations

Produce validation-results.md, candidate-bound packet and local report, review.md link, measured exercise results and expansion decision. Record exact code revision and dirty-diff hash if evidence is generated before commit. Do not mark this pilot complete solely because all automated tests pass. Do not infer implementation, merge, release or publication approval from plan acceptance.
