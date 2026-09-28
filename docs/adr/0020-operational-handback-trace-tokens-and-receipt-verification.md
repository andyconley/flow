# ADR 0020: Trace correlation, a sealed lineage token budget, and offline receipt verification

- Status: accepted
- Date: 2026-09-27
- Amends:
  - ADR 0017: `tokens` joins the expandable limits, counted in tranches.
  - ADR 0019: both seals compare full rows instead of ids and statuses.
  - The v8 envelope, receipt and Shaper Contract / Delivery Charter (v4) shapes.

## Context

A sealed v8 attempt was correct but hard to audit, and nothing bounded its token spend.

- **Correlation broke at the manager.**
  - The manager observation dropped the provider session identity, and only a digest of its request was kept.
  - A regranted or released grant overwrote its id.
  - A recorded process group did not name the call it served.
  - The recovery actor was hard-coded.
- **Nothing verified a sealed receipt against its sources.**
  - `inspect-delivery` compared one file hash.
  - The v8 seal compared three derived blocks and no rows.
  - The live validation needed a hand-written script, whose first version passed vacuously.
- **Usage was parsed per call but never summed.** The charter sealed no token limit.

## Decision

### Trace correlation

- **Manager identity.** A paid v8 manager observation keeps the provider's session identity:
  - Claude: `session_id`, `input_sha256`, `num_turns`;
  - Codex: `thread_id`.

  A reply without it is recorded as `unknown`. `validate_receipt` requires it on completed rows.
- **Manager request files.**
  - **What is written.** For each allowed manager call, the gateway writes `manager-requests/<call_id>.json`: the canonical `{call_id, messages, prompt_digest}`, mode 0600, with no timestamps.
  - **When.** Under `send_lock`, before the grant is consumed, as a temporary file linked into place, followed by a directory fsync. Every call that might have been sent therefore has its file.
  - **Replays.** A replay of a never-sent grant produces identical bytes, because `call_id` derives from `prompt_digest`. Different bytes refuse.
  - **Offline Claude check.** `render_manager_prompt` is the pure renderer, so Claude's `input_sha256` can be recomputed offline.
- **Grant history.**
  - Every v8 grant change writes a `grant_changed` event in the same transaction, just before the event that already described it, with detail `{grant_id, row_id, kind, owner_generation, op, reason}`.
  - The ops are `issue`, `rotate`, `consume`, `expire`, `release` and `deny`.
  - Existing event details, and v5–v7 event streams, are unchanged.
  - A structural test classifies every SQL write to `actions` and `manager_calls`.
- **Other correlation.**
  - Process-group lines name the call they served (`row_id`).
  - v8 checkpoint links record MAF's `previous_checkpoint_id`. This is informational: MAF forks the chain on restore, so no unbroken-chain rule is enforced.
  - `recover-delivery-lead` requires `--actor`.
- **`flow run trace`** shows every call of an attempt and its lineage in ledger order:
  - grant history, provider session, request file, process groups, checkpoint;
  - timings;
  - raw and charged usage;
  - interleaved expansion events.

  It leads with a banner naming why a stuck attempt is stuck and the same next command `flow run stuck` gives. Token numbers are absolute: charged, maximum, remaining and headroom, with tranche counts second.

### The sealed lineage token budget

- **Contract version 4.**
  - The Shaper Contract and Delivery Charter seal `max_lineage_tokens`, `token_tranche` and `unobserved_send_tokens`, plus `expansion_headroom.tokens`, counted in tranches.
  - Charter rules: `token_tranche ≥ unobserved_send_tokens`, `unobserved_send_tokens ≤ max_lineage_tokens`, and the budget plus every tranche ≤ `MAX_LINEAGE_TOKENS` (2,000,000). Headroom ≤ `MAX_TOKEN_TRANCHES` (10).
  - v1–v3 records stay readable.
- **Calibration.** `DEFAULT_TOKEN_BUDGET` is 200,000 / 100,000 / 100,000, calibrated on the one completed live lineage (`v8-live-validation-3`):
  - the lineage charged 133,898 tokens: six Claude manager calls of 5,971–10,695 each, and one Claude editor call of 82,376;
  - the tranche and the unobserved charge sit about 20% above the largest observed call, so one unknown send never needs more than one tranche;
  - the calibration rests on a single lineage and should be revisited as more live runs accumulate.
- **The unit, `charged_v1`.**
  - It is uncached input plus cache writes plus output.
  - For Codex, uncached input is `input_tokens − cached_input_tokens`, and reasoning tokens are already inside `output_tokens`.
  - Cache reads are reported, never charged. Codex `cache_write_input_tokens`, observed only as 0, is reported in trace's raw usage only.
  - **It is a stable budget unit, not a cost proxy.** Claude cache reads dominate real spend and are excluded by design.
- **Charging is by row status only,** from data the receipt carries:

  | Row | Charge |
  | --- | --- |
  | Completed or failed paid row with recognised usage | the observed usage |
  | Completed or failed paid row with usage Flow cannot normalise | the largest of `unobserved_send_tokens`, a reported `total_tokens`, and the sum of the chargeable counters present |
  | Started or unknown paid row | `unobserved_send_tokens` |
  | Unsent row, or unpaid provider (the Ollama verifier, an unpaid manager) | nothing |

  One pure function computes this, and the gate, both seals, `validate_receipt`, trace and verify-receipt all use it. The conservative rule means a provider that changes its usage shape can't make its calls cheaper than it reported. A usage block with no readable counter at all still charges the sealed amount; it is counted in `unrecognised_usage`, and trace shows it. Record-time usage checks validate only the counters Flow reads. A key a newer provider CLI adds is kept and ignored; it never turns a paid call into an unresolvable unknown.
- **The gate.** Before every grant that can lead to a paid send, `token_cap` fails when `charged ≥ max_lineage_tokens + tranches × token_tranche`. The grants checked are the decisions, both regrants and both manager reissues. The tranches counted are those granted across the lineage.
  - **At the first decision:** ADR 0017 applies with the tranche as the unit. A shortfall one tranche clears is granted automatically within the lineage's headroom. Otherwise the attempt pauses for `decide-expansion`, including at zero headroom, like every other expandable limit.
  - **Hard refusals:** a shortfall needing more than one tranche, or a tranche past `MAX_LINEAGE_TOKENS`. Engineer grants are held to the same ceiling. An approved tranche that later lapses stays counted toward it, which is conservative.
  - **Regrants and reissues:** a hard denial; they never expand.
  - **`reissue_recovered_manager_grant`:** now checks every manager limit, leaving its own row out of the counts. A denial releases the grant, and the gateway fails the attempt without sending.
- **The overshoot bound.** Usage is observed only after a call, and consumption does not re-check limits. Paid grants are not serialised, so a lineage can exceed its maximum by at most the charged usage of the paid calls already granted when the cap was reached: up to `max_concurrent` paid actions plus one paid manager call.
  - With `max_concurrent` 1 and an unpaid manager, that is one call.
  - A call's own usage is unbounded, because there is no per-call cap.
  - An unobserved send counts at its sealed charge, not its true usage.

  Receipts report the actual `overshoot`.
- **The receipt block.** v8 receipts under a sealed budget carry `token_usage`, recomputed by `validate_receipt` from the receipt's own rows and `lineage_usage.predecessor_charged`. Whether it is required is read from the envelope, never from the receipt.
  - The block repeats `predecessor_charged`, so it reads on its own.
  - `cache_read_total` and `verifier_tokens` cover the attempt's own rows only. `verifier_tokens` sums every unpaid sent row: the Ollama verifier, and an unpaid manager when there is one.

### Full-row seals

`receipt_compare.compare_receipt_rows` is the one comparison. `finish_attempt`, `seal_terminal_uncertain` and verify-receipt all use it.

- **What it compares:** every row block (actions, manager calls, replans, checkpoints, verifier inputs, evaluations and usage), index by index with exact key sets, after the derived blocks (lineage, expansion, manager progress, tokens).
- **What a mismatch reports:** the first differing row, the key path, and both values. Long values are given by digest.
- **Snapshot timing.** The gateway builds the v8 receipt from `seal_view`, a snapshot taken under the same `send_lock` hold that closes expansions and seals. `finish_attempt` reads the receipt inside its transaction.

### Pre-release attempts

- **Detection.** A v8 envelope without the token keys predates this ADR. `handback_supported` tells the two apart from the envelope alone.
- **Read-compatible.** Such an attempt stays readable by `inspect-delivery`, `stuck` and `trace`, and it can be abandoned: the seal blocks never raise for it.
- **Write-refusing.** Prepare refuses a charter without a token budget, `create_attempt` refuses the envelope, and the gate and the normal seal refuse to advance a pre-release started attempt.

### `flow run verify-receipt`

- **Read-only and offline.** It reads the ledger in one read transaction and only files under the run directory. It makes no provider, subprocess or network call, and writes nothing.
- **Seventeen checks:**
  - V1–V4: the sealed digest; the envelope and `validate_receipt`; the rows through the shared comparison; the derived blocks.
  - V5–V6: recovery and termination; predecessors, verified recursively, with their charges cross-checked.
  - V7–V8: the sealed authority files, the lead-claim `supersedes` chain and the shared limits projection; the source snapshots.
  - V9–V10: bound checkpoints (in `checkpoints/` or quarantine); manager request files and the Claude `input_sha256`.
  - V11–V14: the edit, test, baseline and trace chains.
  - V15: events. That covers one send start per sent row, legal grant transitions, checkpoint order, and no send inside a pending escalation (by seq).
  - V16: process groups.
  - V17: a replay of the token gate.
- **No vacuous passes.** A requiredness table per terminal status decides when missing input fails, and a pass must count at least one compared fact.
- **Always reported as unverifiable offline:**
  - that a provider ran, and what it billed;
  - the outcome of an unknown send;
  - the test output bytes;
  - the current worktree;
  - the bytes of a replaced draft;
  - the truth of ledger timestamps.
- **Exit codes:** 0 when nothing fails; 1 on any failure; 2 when verification cannot run (`attempt_not_sealed`, `unsupported_receipt`, `run_unreadable`).
  - A sealed attempt whose receipt file is missing fails V1; it does not exit 2.
  - A malformed source fails its own check and never crashes the report.
  - A v8 attempt never seals `denied`, so such a receipt is `unsupported_receipt`. Whether a receipt is supported is decided from the ledger envelope. A supported `envelope.json` over a pre-release ledger envelope is a V2 failure, not `unsupported_receipt`.
- **A consistency check, not a signature.** Anyone who can write `.flow` can rewrite every source consistently.

## Consequences

- **The hand-written live check is superseded.**
  - The receipt check from `v8-live-validation-3` is covered by named verify-receipt and trace checks, apart from three run-specific items:
    - the stub scan;
    - the D1 event-log content shape;
    - the chartered-facts text search, which becomes a plain `grep` over request files.
  - Per-call timings no longer need a script.
- **Request files are sensitive.** They hold the full manager prompt: charter facts, task text and diffs, up to 32 KB per call. They are 0600 in a 0700 directory, and `.flow/` is excluded from git. A run directory committed as evidence with `git add -f` carries them too, so review before committing one.
- **Charters must seal a token budget.**
  - Old runs keep their evidence, but continuing a pre-release run needs a new sealed charter.
  - The budget is a lineage cap on `charged_v1` tokens. Operators still watch provider limits and costs themselves.
- **Fixture churn in the tests.** Manager stubs return session identity, receipts are full-row, and legacy-version fixtures strip the token keys.

## Rejected alternatives

- **General expansion amounts (`amount > 1`).** It would have touched every replay and validator path. A hard stop when more than one tranche is needed, with a tranche sized above the largest observed call, keeps ADR 0017's one-unit machinery.
- **Serial paid dispatch.** The engineer chose to keep concurrency and document the concurrent bound instead.
- **Charging unobserved sends zero, or treating one as "cap reached".** The first lets every lost send overshoot. The second stops the lineage on one lost send.
- **Rebuilding the receipt byte for byte.** It carries runtime evidence and `created_at` that are not in the ledger, so verification is block by block.
- **A W3C `traceparent` into MAF.** The OpenTelemetry SDK is not installed, and the benefit is unverified. Correlation uses Flow, checkpoint and provider identities.
