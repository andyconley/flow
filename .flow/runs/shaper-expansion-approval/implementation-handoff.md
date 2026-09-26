# Implementation Handoff: shaper-expansion-approval

- **Branch:** `codex/step5-shaper-approval-design`. It already carries `b8cae87` (the status refresh). There will be one PR.
- **Lane:** `flow-implement`, entered with `flow run transition shaper-expansion-approval start-implementation`.

## Read first

1. `plan.md`: the ordered commits C1–C7, with file-level changes.
2. `validation-plan.md`: the AC mapping, the end-to-end cases and mutations M1–M7.
3. `solution.md`: the Option A design (tables, hooks, recovery modes).
4. `research/resume-mechanics-spike.md`: replay-identity evidence and the requirement that `checkpoint_dir` stays byte-identical.

## Invariants the implementer must hold

- Protocol v8 only. Paths for v5–v7 must not change behavior.
- Authority comes only from the sealed charter and the ledger. Never read headroom, amounts or limits from manager output, envelope overrides or checkpoints.
- The envelope and charter are byte-identical across a pause. Grants live only in the ledger.
- Every ledger write that touches requests or grants happens in one `BEGIN IMMEDIATE`, and is generation-fenced.
- The lock order is recovery, then run, then send, then SQLite (ADR 0016).
- The rationale is display-only, bounded and escaped, and is never parsed.
- The amount is always 1 and is computed by Flow.
- Don't edit `orchestration.json`. It is sealed into delivery authority.

## Known edges

- `tests/shaper_intent_fixture.py` limits sit at the ceilings. Expansion tests need the new lowered-base parameter.
- `runtime/maf_runner/__init__.py` must stay dependency-free. `cli/` loads `limits.py` by path.
- Restart mode needs an identical envelope, including `checkpoint_dir`. MAF may find prior files in that directory, so verify the behavior in C5 and C7, and refuse on any identity mismatch.
- Checkpoints are bound today only when an action is allowed (`delivery_gateway.py` ~1413). A binding at denial is usable only under a decided grant.

## Evidence to produce

- `validation-results.md`: the suite output (counts, 0 skipped), the AC-to-test table and the M1–M7 results.
- `implementation-review.md`: quality and security findings with dispositions.
- `HANDOFF.md`: the durable handback.
