# Validation Plan: Chunk 1

## Deterministic gates

### Contracts

- Canonical Shaper Contract requires identity, scope, authority, evidence, risk, approval, and lineage fields.
- Delivery Charter links exact approved source digests, roster/capabilities, limits, scopes, and verification duties.
- Equivalent canonical inputs produce stable digests; any material mutation changes or invalidates the digest.

### Lifecycle and crash boundaries

- Successful `start-plan` creates exactly one charter, handoff, logical delivery attempt, generation-1 claim, and planning state.
- Identical replay returns the same identities; changed source bytes or stale revision leaves authority unchanged.
- Concurrent `start-plan` calls serialize.
- Test crashes before staging, after staging, before `run.json` replace, after replace, and before/after event append. Only the `run.json` commit point grants authority; event reconciliation is idempotent.

### Ownership fencing and recovery

- Only current generation can mutate or dispatch.
- Resume/supersede increments generation and fences prior owners at the shared send boundary.
- Timeout marks `attention_required` without creating a claim or send.
- Unknown action blocks related successor dispatch until reconciled.
- Use process-level tests and durable event assertions, not thread-only or callback-count-only checks.

### Projection and gateway

- Protocol-v7 envelope links charter, handoff, logical attempt, and owner generation while excluding credentials/session data.
- Unsupported features fail before execution attempt, ledger reservation, or provider send.
- Magentic selection is roster-bound, comparative rationale is nonempty/bounded and fact-valid, and only one producer is accepted.
- Distinct read-only Ollama verifier is selected only after Flow observes the producer diff and targeted test.
- Receipt links charter, handoff, owner generation, source commit, worktree, selection rationale, diff, test, checkpoint, and verifier evidence.

### Zero-send denial matrix

Assert zero `adapter_send_started` events and zero adapter calls for invalid contract, absent handoff, stale revision, duplicate active claim, stale generation, changed digest, out-of-charter provider, unapproved substitution, vague/invalid rationale, verifier-before-evidence, withdrawal/cancellation, malformed legacy record, and v6 execute/resume.

### Inspection and compatibility

- Valid v6: readable, not executable, not resumable, with diagnostic.
- Malformed v6: structured parse diagnostic and no eligibility.
- Digest-mismatched v6: raw/known fields plus integrity diagnostic and no eligibility.
- Current protocol: charter, ownership, attempt, unknown, rationale, and compatibility state displayed in text and JSON.
- Fixtures live under tracked `tests/fixtures/`, not ignored run directories.

### Test commands

- Run focused contract, control, projection, gateway, recovery, inspection, CLI, and documentation tests during development.
- Run `/opt/homebrew/bin/python3.12 -m unittest discover -s tests` before handback.
- Run `git diff --check` and orchestration validation.

## Live handback gate

Run exactly one bounded acceptance job after deterministic gates pass:

1. Create a clean isolated worktree at a pinned source commit.
2. Select and charter the smallest suitable real Flow change.
3. Approve Claude and Codex producer candidates and a distinct Ollama verifier.
4. Let stock Magentic select one producer and record comparative rationale.
5. Require Flow grants for every manager and specialist call.
6. Observe the scoped diff and targeted test before verifier dispatch.
7. Send the bounded diff/test evidence to Ollama.
8. Seal one receipt linked to all canonical and execution evidence.
9. Run the full suite in the resulting worktree.

Acceptance requires a completed two-action receipt, distinct producer/verifier identities, successful targeted and full-suite results, and no unapproved file changes. A timeout, unknown provider result, changed worktree HEAD, missing rationale, verifier failure, or scope violation fails closed and remains historical evidence. Do not repeat the live job unless a concrete implementation defect justifies another bounded attempt.

## Independent review

High-risk acceptance requires a verifier identity distinct from implementation producers and evidence collector, plus review of transition atomicity, generation fencing, zero-send evidence, legacy compatibility, and live receipt provenance.
