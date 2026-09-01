# Orchestration Safety Contract Acceptance Criteria

## Contract and artifacts

- A canonical standard defines brief fields, claim classes, reconciliation, shared-state safety, deterministic risk classification, and verification independence.
- Templates exist for a complete agent brief, versioned orchestration manifest, findings reconciliation, and external mutation record.
- An ADR records the decision to keep orchestration artifacts separate from lifecycle projection.

## CLI enforcement

- `flow run validate-orchestration <work-id> --stage dispatch|handback|acceptance` supports text and JSON output.
- Dispatch validation catches incomplete briefs, capability mismatches, output/write-scope mismatch, and unsafe concurrent overlap before mutation.
- Handback validation catches missing declared outputs, reconciliation, baseline, readback, comparison, recovery, and unexpected-delta dispositions.
- Acceptance validation catches incomplete provenance and refuses high-risk work without a distinct verifier and verification artifact.
- A failed validation or lifecycle gate does not modify `run.json` or `events.jsonl`.
- The calculated risk classification cannot be overridden by inconsistent free text.

## Compatibility

- New runs record a protocol revision.
- Revision-1 and `legacy/inferred` runs retain their current behavior and remain verifiable.
- Unknown additive manifest fields are tolerated; unknown controlled-vocabulary values and missing required fields fail closed.
- Project-level prose replacements cannot weaken CLI-enforced minimums.

## Test coverage

- Tests cover every hard trigger, the zero/one/two aggravating-factor boundary, and inconsistent classification.
- Tests cover confirmed, missing, and unknown capabilities.
- Tests accept disjoint concurrent writes and declared serialization while rejecting unsafe overlap.
- Tests cover structural-versus-additive shared mutations, external baselines, readback, recovery, and unexpected deltas.
- Tests reject high-risk verifier identity conflicts and allow standard-risk work without mandatory independent review.
- Tests cover material claim classifications and reconciliation linkage.
- A complete revision-2 lifecycle and a high-risk external-mutation simulation pass.
- The full existing test suite remains green.

## Runtime and release

- Claude and Codex generated surfaces contain equivalent orchestration guidance and valid agent routing.
- Help generation, sync checks, `flow doctor`, runtime smoke, release staging, and `git diff --check` pass.
- Changes are committed without the unrelated canonical-checkout backlog edits.
- `main` is pushed only after confirming the remote.
- Semantic-release creates the expected new minor tag, GitHub release, changelog entry, and non-empty release notes.
- A clean release installation or update from the new tag succeeds and passes runtime smoke.
