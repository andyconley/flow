# Requirements: step5-operational-handback

MAF adoption step 5, the last slice, without MCP handback (`docs/maf-adoption-design.md`, "Step 5, not built yet"). This is revision 2. It folds in the adversarial architecture review (F1–F21) and the product review (P-F1–P-F9); `definition-dispositions.md` maps each finding.

## Problem

A chartered v8 attempt leaves a record that is correct but hard to audit, and nothing bounds its token spend.

- **Correlation breaks at the manager.**
  - The manager observation drops the provider's `session_id`, `thread_id` and `input_sha256` (`delivery_gateway.py:1509-1511`).
  - The manager's request is kept only as a digest.
  - Rotated and released grant ids are overwritten.
  - Recorded process groups don't name the call they served.
  - The recovery actor is hard-coded to `codex-assisted-recovery`.
- **Timings need a script.** Per-call timings and correlation exist only in the ledger, so reading them takes a hand-written script (`delivery-per-call-timings`).
- **Receipts can't be verified.** Nothing checks a sealed receipt against its sources:
  - `inspect-delivery` compares one file hash;
  - the v8 seal compares only the lineage, expansion and manager-progress blocks;
  - `v8-live-validation-3` needed a 119-line `receipt_check.py`, whose first version passed vacuously (`runtime-evidence-completion-manifest`, seen 11 times).
- **Token spend is unbounded.** Usage is parsed and stored per call, but never summed, and the charter seals no token limit.

## Audience

- **Andy,** auditing a finished or stuck attempt from the CLI.
- **The Shaper,** sealing a token budget and its expansion headroom.
- **Reviewers of a live-validation run,** who today hand-write the receipt check.

## Desired outcome

- **Trace in one command.** One command shows the full chain for every call:
  - Flow ids and grant history;
  - the provider session;
  - the MAF checkpoint;
  - the process group;
  - timings and usage.

  For a stuck attempt, it leads with why the attempt is stuck.
- **Verify offline in one command.** One read-only command verifies a sealed receipt against the ledger, the sealed authority, the checkpoints and the on-disk evidence. Each failure shows what differs, and the command states what it couldn't verify offline.
- **The token budget is enforced.** The charter seals a lineage token budget, and Flow checks it before every paid grant:
  - within headroom, expansion is automatic;
  - beyond headroom, it escalates to Andy;
  - the overshoot bound is exact and documented.

## Engineer decisions (2026-09-27)

| # | Decision |
|---|---|
| E1 | One run, one PR, ordered commits. MCP handback is out. |
| E2 | The token cap is cumulative over the lineage and checked before each paid grant. Once charged usage reaches the cap, Flow refuses, or escalates through delegated expansion. The overshoot is documented honestly. |
| E3 | `flow run verify-receipt` works offline. It recomputes from the ledger, the sealed authority, the checkpoints and the on-disk evidence digests. It calls no provider, doesn't re-apply the diff, and doesn't re-run the test. |

## Proposed decisions (Andy to confirm at definition approval)

| # | Question | Proposal |
|---|---|---|
| P1 | Token unit | **`charged_v1`** = uncached input + cache writes + output. For Codex, uncached input is `input_tokens − cached_input_tokens`. Cache reads are recorded and reported, but not charged. This is a stable budget unit, **not a cost proxy** (F19). |
| P2 | Charging | **By row status only** (F2), from data the receipt carries:<br>• `completed` or `failed` with recognised usage: the observed charge;<br>• any other sent row (`started`, `unknown`, or `completed`/`failed` without recognised usage): the sealed `unobserved_send_tokens`;<br>• `allowed`, `denied` or `not_dispatched`: 0. |
| P3 | Token expansion | **Tranches counted as units** (F1). `tokens` is an expandable, lineage-scoped counter of tranches with a sealed base of 0. Only the token predicate turns tranches into tokens. Every existing +1 path stays unchanged. |
| P3a | A shortfall needing more than one tranche | **A hard `token_cap` refusal,** never expandable (F1). A charter rule `token_tranche ≥ unobserved_send_tokens` means one unknown send can never cause it. With a calibrated tranche (P10) it takes a single call larger than the tranche. |
| P4 | Ollama verifier tokens | Reported, and excluded from the cap. |
| P5 | Manager request text | **Stored** as canonical `{call_id, prompt_digest, messages}` files (F11). P-F1 proposed cutting this; the recommendation is to keep it. With F11 it is small, it closes `manager-prompt-text-inspection`, and it lets V10 bind Claude's `input_sha256`. |
| P6 | Seal comparison | `finish_attempt` compares full rows (with exact key sets) through one pure function shared with `seal_terminal_uncertain` and V3. |
| P7 | W3C `traceparent` into MAF | Out of scope. |
| P8 | Verifier scope | Walks the predecessor lineage by default. Worktree drift is not checked. |
| P9 | Attempts sealed before this release | Refused as `unsupported_receipt`. Supported or not is decided from the **ledger's sealed envelope contract version**, never from the receipt's contents (F7). |
| P10 | Defaults and ceilings | Derived from the live run `v8-live-validation-3` (P-F2, P-F4):<br>• its lineage charged 133,898 tokens: six Claude manager calls of 5,971–10,695 each, and one Claude editor call of 82,376;<br>• defaults: `max_lineage_tokens` 200,000, `token_tranche` 100,000, `unobserved_send_tokens` 100,000 (the largest observed call plus about 20%);<br>• ceilings: `MAX_TOKEN_TRANCHES` 10, `MAX_LINEAGE_TOKENS` 2,000,000.<br>ADR 0020 records this derivation, and notes that it rests on one lineage. |
| P11 | Concurrent paid grants | **Allowed, as today** (Andy, 2026-09-27; F5 proposed serialising them). Grants aren't serialised, so R12 states the concurrent bound, and it reduces to one call when `max_concurrent` is 1. |

## Requirements

### Trace correlation

#### R1. Manager provider identity

- The manager observation keeps the provider identity, as the editor observation does:
  - Claude `session_id`, `input_sha256` and `num_turns`;
  - Codex `thread_id`.
- `validate_receipt` requires, per provider, the identity fields its adapter produces.

#### R2. Manager request files (P5)

- **When it is written.** For each `allowed` manager call, the gateway writes `manager-requests/<call_id>.json` inside `send_lock`, after `assert_owner` and **before** `consume_manager_grant`.
- **How it is written.** A temp file is then `os.link`ed into place, so a file is never overwritten or left partly written.
- **What it holds.** Only the canonical JSON `{call_id, prompt_digest, messages}`, with no timestamps. The file mode is 0600.
- **Refusals.** If `digest(messages) ≠ prompt_digest`, the send is refused. If an existing file's bytes differ, the send is refused and the file is left unchanged.
- **Replays.** A replay of a never-sent grant has the same `call_id` (derived from `prompt_digest`), so it produces identical bytes and reuses the file.
- **Prompt rendering.** The manager prompt is rendered by a pure function `render_manager_prompt(messages)`, factored out of `_default_manager_adapter`, so the Claude `input_sha256` can be recomputed offline.

#### R3. Grant history

- **The event.** Every write that changes a grant appends a new `grant_changed` event in the same transaction. Its detail is canonical JSON `{grant_id, row_id, kind, owner_generation, op, reason}`, where `op` is one of `issue`, `rotate`, `release`, `consume`, `expire`, `deny`.
- **The paths it covers** (F12):
  - `decide`, `decide_manager_call`, both regrants and both reissues;
  - consumption for actions, manager calls and the verifier;
  - expiry;
  - the release in `close_pre_send_failure`;
  - the superseded, terminal-seal and recovery releases;
  - `resolved_not_dispatched`.
- **Existing events** and their `detail` strings are unchanged.

#### R4. Process groups name their call

- Each group line carries `action_id` or `call_id` for a provider group, and `null` for the MAF and test groups.
- The registrar receives the id from the adapter.

#### R5. Checkpoint parent

- Each checkpoint link records `previous_checkpoint_id`, read from the file at bind time.
- It is informational. MAF forks the chain on restore, and bound checkpoints' parents are usually unbound, so no unbroken-chain rule is enforced (F8).

#### R6. Recovery actor

- `recover-delivery-lead` requires `--actor`.
- The default `codex-assisted-recovery` is removed from `recover_delivery` (`delivery_gateway.py:1132`), from the CLI (`flow.py:1079`), and from every other in-repo caller.

#### R7. `flow run trace <work-id> [--attempt ID] [--json]`

- **Read-only and v8-only.** An attempt from v5–v7 prints `unsupported_protocol` and the next attempt continues. The default is the latest attempt with its predecessors.
- **Status banner first (P-F6).**
  - **For an attempt that isn't terminal,** a one-line banner names what it is waiting on:
    - the reason, for example `expansion_paused: token_cap`, `reconciliation_required`, `lead attention_required` or `recovery_in_progress`;
    - since which event seq and time;
    - on which row;
    - the next command (the same one `flow run stuck` gives).
  - **For a terminal attempt,** the banner shows the status, the cause and the receipt digest.
- **Per attempt:**
  - status;
  - owner generations;
  - control records.
- **Per manager call and action, in ledger seq order:**
  - id, kind, phase and round, provider and model, status;
  - grant history (R3);
  - provider session or thread id, and `input_sha256`;
  - request file and digest match (R2);
  - pgid (R4);
  - bound checkpoint and its parent (R5);
  - send-start, observed and duration;
  - usage as charged, cache read and raw.
- **Expansions** are interleaved in seq order.
- **Token counts are absolute (P-F3).**
  - The totals and cap state show charged, cap, remaining and headroom as absolute token numbers.
  - The tranche count is secondary.
  - The totals are given per attempt and per lineage.
- **Output and exit.** The JSON schema is pinned. Exit code 0 unless the run, the attempt or the ledger is unreadable. The CLI reference documents `--json | jq` for long lineages (P-F9).

### Token cap

#### R8. Sealed token budget (P1, P3, P3a, P10)

- **New fields.** `budget_safety_envelope.enforceable` gains three required integers, each ≥ 1:
  - `max_lineage_tokens`;
  - `token_tranche`;
  - `unobserved_send_tokens`.
- **Charter rules:**
  - `token_tranche ≥ unobserved_send_tokens`;
  - `unobserved_send_tokens ≤ max_lineage_tokens`;
  - `max_lineage_tokens + headroom.tokens × token_tranche ≤ MAX_LINEAGE_TOKENS`.
- **Headroom.** `expansion_headroom.tokens` counts tranches and is bounded by `MAX_TOKEN_TRANCHES`.
- **Tranches as an expandable limit.** `tokens` joins:
  - `EXPANSION_LIMIT_KEYS` and `EXPANSION_CEILINGS` (base 0, ceiling `MAX_TOKEN_TRANCHES`);
  - `LINEAGE_SCOPED_LIMITS`;
  - `_expansion_receipt.predecessor_lineage_grants`;
  - the lineage key set in `_validate_expansion` (`execution_contracts.py:430`).
- **Envelope.** The envelope `limits` projects all three fields.
- **Version.** The contract version is bumped. There is no back-compat, so older charters are refused at prepare.

#### R9. Charged usage (P1, P2)

- **One pure per-row function** in the contracts module: `charge(row, provider, unobserved_send_tokens) → {charged, cache_read, recognised}`.
- **Tolerant normalisation (F3).**
  - The known keys must be non-negative integers.
  - Extra keys are ignored.
  - A missing or unrecognised shape is never an error at record time. It is charged `unobserved_send_tokens` and marked `recognised: false`.
- **Lineage total.** `lineage_charged(ledger, envelope)` sums the charges of the paid actions, and of the manager calls when the manager is paid, across the lineage. The gate, both seals, `validate_receipt` (from receipt rows), trace and verify-receipt all use this one function.

#### R10. Pre-grant check (F1, F5, F6)

- **The predicate.** `token_cap` fails when `charged ≥ max_lineage_tokens + effective_tranches × token_tranche`.
- **Units.** `units = floor((charged − effective_tokens) / token_tranche) + 1`. It is expandable only when `units = 1` and the tranche ceiling allows it.
- **Per path:**
  - **`decide` / `decide_manager_call`:** ADR 0017 expansion. A tranche within the lineage headroom is granted automatically, as `charter_headroom`. Beyond headroom the attempt pauses for `decide-expansion`. With no headroom, or when `units > 1`, the grant is refused hard.
  - **`regrant_recovered_action`, `regrant_expanded_action`, `reissue_expanded_manager_grant`:** the token check runs. On failure the grant is a hard `token_cap` denial, with the same state change each path makes today for a limit failure. It never expands.
  - **`reissue_recovered_manager_grant`:** gains the full manager checks: calls, rounds and the token cap. It excludes its own row from the counts. On failure the row is denied with `grant_changed op=deny`, and the gateway fails the attempt instead of assuming success.
- **A shared helper.** The manager checks are folded into one `_v8_manager_checks`, used by `decide_manager_call` and both reissues.
- **Hard `token_cap` on the manager** fails the attempt, as other hard manager denials do.
- **Unpaid calls.** The Ollama verifier and an unpaid manager are never token-checked.

#### R11. Receipt token block (F2, F18)

- **The block.** v8 receipts gain `token_usage`:
  - `unit: "charged_v1"`;
  - `maximum` (in tokens, effective);
  - `tranches_granted`;
  - `observed_charged`;
  - `unobserved_sends`, `unobserved_charged`;
  - `unrecognised_usage`;
  - `charged_total`, which includes the predecessors;
  - `overshoot = max(0, charged_total − maximum)`;
  - `cache_read_total` and `verifier_tokens`, both reported only.
- **Predecessors.** `lineage_usage` gains `predecessor_charged`. As today, the block is present only when there are predecessors; otherwise the value is implicitly 0.
- **Validation.** `validate_receipt` recomputes `token_usage` from the receipt's rows and `lineage_usage`.
- **Seal.** Both seals compare it with R9 in the ledger.

#### R12. Honest overshoot (P11)

ADR 0020 and the docs state:
- **Usage is observed after a call.** New grants are blocked only while a row is `started` or `unknown`. Grants that are `allowed` but not yet consumed don't block, and consumption doesn't re-check limits (F5).
- **The bound.** A lineage can exceed `maximum` by at most the charged usage of the paid calls already granted when the cap was reached: up to `max_concurrent` paid actions plus one paid manager call.
- **Serial attempts.** When `max_concurrent` is 1 and the manager is unpaid, the bound is one call.
- **No per-call cap.** Each call's usage is itself unbounded.
- **Unobserved sends** count at their sealed charge, not at their true usage.

The design doc's "no token stop" line is replaced.

### Receipt verification

#### R13. `flow run verify-receipt <work-id> [--attempt ID] [--no-lineage] [--json]`

- **Read-only and offline.**
  - All ledger reads happen in one read transaction on a read-only connection. No lock or lock file is taken.
  - Only files under the run directory are read.
  - No provider, network or subprocess call is made. No diff is applied and no test runs.
  - Nothing is written.
- **Target.** The default is the latest sealed attempt.
  - An attempt that isn't sealed gives `attempt_not_sealed` (exit 2).
  - A pre-release contract version (P9) gives `unsupported_receipt` (exit 2).
- **Output.** A list of `{check, status, compared, detail}`, where `status` is one of:
  - `pass`;
  - `fail`;
  - `not_applicable`, allowed only where the R14 table says `if-present` or `n/a`, with a fixed reason;
  - `unverifiable_offline`, only for the fixed R15 items.
- **Diagnosis (P-F5).** A `fail` detail names the row id and field, with both the expected and the found values. For long values it gives both digests and the first differing key path.
- **No vacuous passes.** `pass` requires `compared ≥ 1`, except where the table marks a block legitimately empty for that status.
- **Exit code.** 0 when no check fails; 1 on any failure; 2 when verification can't run.

#### R14. Checks

| # | Check | Source |
|---|---|---|
| V1 | `sha256(receipt.json) == attempts.sealed_receipt_sha256`; `receipt_path` names the file; the attempt status is terminal and equals `receipt.status` | ledger |
| V2 | `envelope.json` equals the ledger envelope; `validate_receipt(envelope, receipt)` passes | ledger, attempt directory |
| V3 | `actions`, `manager_calls`, `replans`, `checkpoints`, `verifier_inputs`, `verifier_evaluations`, `verifier_usage` equal the ledger snapshot row by row, with exact key sets, through the shared P6 function | ledger |
| V4 | `lineage_usage`, `expansion`, `manager_progress`, `token_usage` equal the seal's functions | ledger |
| V5 | `recovery` equals the rebuilt block; `termination` equals the ledger reason | ledger |
| V6 | Each sealed predecessor's `receipt_sha256` equals its sealed digest and file hash, verified recursively unless `--no-lineage`; a superseded predecessor with no receipt is `not_applicable` and is charged from the ledger only; the lineage order equals the ledger's; each sealed predecessor's own charges sum to the successor's `predecessor_charged` | ledger, predecessor receipts |
| V7 | The Shaper contract, delivery charter and handoff files recompute their own digests and equal the envelope's; the envelope's lead claim equals a sealed `lead-claim-g{n}-*.json` whose digest recomputes, and the `supersedes` chain from the current claim back to it is unbroken; the charter's limit projection equals the envelope's `limits` and `expansion_headroom`. `run.json` is used only to find the current claim (F4) | `delivery/` files |
| V8 | The requirements, acceptance and manifest snapshot digests equal `charter_sources` and `manifest_digest`; `charter_digest` is recomputed | attempt directory |
| V9 | Every bound checkpoint link's file exists in `checkpoints/` or `checkpoints-quarantine/`; its sha, size, id, workflow name, pending key and recorded `previous_checkpoint_id` match the file | checkpoint files |
| V10 | Every manager call from `allowed` onward has its request file with canonical content, and `digest(messages) == prompt_digest`; for Claude, `sha256(render_manager_prompt(messages)) == result.input_sha256`; any request file with no matching row fails. The file mode is reported as a separate informational item, excluded from the exit code, because git doesn't keep 0600 (F16) | `manager-requests/` |
| V11 | `sha256(repair.diff)` equals `evidence.edit.diff_sha256`, the **final** verifier input's diff digest and the final evaluation's; that input's `provider_task` equals `_verifier_provider_task(task, repair.diff, …)` recomputed; changed files ⊆ write paths | `repair.diff`, ledger |
| V12 | `evidence.tests.output_sha256` equals the final verifier input's and evaluation's test digest; the command equals the job's test argv | ledger |
| V13 | `baseline.json` equals `evidence.baseline`; the regression-diff digest equals the job's | attempt directory, envelope |
| V14 | The `diagnostic_trace` and `event_trace` sha and bytes match their files | attempt directory |
| V15 | Every sent row has exactly one send-start event of its kind (`manager_send_started`, `worker_dispatched`, `verifier_send_claimed`), so nothing was resent; every consumed expansion grant has its consumption event; each row's `grant_changed` history ends at its final grant state (released: NULL; expired: denied, grant kept); each checkpoint link's `ledger_seq` precedes its bound event; no manager or paid send falls within a pending-escalation window, defined by seq from `expansion_requested` to the decision or cancellation | ledger events |
| V16 | Every provider group line names a receipt row; every sent Claude or Codex row has a group line in its owner generation's control file (`not_applicable` for Ollama). This is a consistency check only (F17) | control records |
| V17 | **Token gate replay** (F15): walking the lineage events in seq order, at every paid grant event the charged total of the rows sent before it is below the effective maximum from the tranches consumed before it | ledger events |

**Requiredness by terminal status** (F14). Each cell is `R` (required; missing is a fail), `P` (checked if present, otherwise `not_applicable` with a fixed reason) or `—` (`not_applicable`).

| Check | completed | failed | cancelled | abandoned |
|---|---|---|---|---|
| V1–V4, V7, V8, V15, V17 | R | R | R | R |
| V5 recovery / termination | P / — | P / — | P / R | P / R |
| V6 | R if predecessors | R if predecessors | R if predecessors | R if predecessors |
| V9 | R | P | P | P |
| V10 | R | R if any manager call was allowed | P | P |
| V11, V12 | R | P | P | P |
| V13 | R | R | P | P |
| V14 | R if a Claude editor was sent | same | P | P |
| V16 | R | R | P | P |

"Required" for V3 means the ledger has the rows. A completed attempt with no action rows fails.

#### R15. Declared unverifiable

Always reported as `unverifiable_offline`, each with a fixed text:
- that a provider actually ran, and what it billed;
- the outcome of an `unknown` send;
- the test output bytes;
- the current worktree;
- the bytes of a replaced draft receipt;
- the truth of ledger timestamps.

ADR 0020 states that verification is a consistency check, not a signature. Anyone who can write `.flow` can rewrite every source consistently.

#### R16. The seal uses the shared comparison (F13)

- **Gateway.** The gateway re-takes the snapshot under the `send_lock` hold that seals, after `close_expansions`, and builds the receipt from it.
- **`finish_attempt`.** Inside its transaction, it compares every V3 block and every R11 block against `_snapshot_locked`.
- **`seal_terminal_uncertain`.** It does the same.
- **A mismatch refuses the seal.**
- **One function.** The comparison is one pure function, imported by both seals and V3.

### Docs

#### R17. ADR 0020 and docs

**ADR 0020** records:
- the `charged_v1` unit, and that it is not a cost proxy;
- charging by status;
- tranche expansion, and the hard stop when more than one tranche is needed;
- the concurrent overshoot bound (R12);
- the calibration of the defaults;
- request files and the rendering function;
- `grant_changed`;
- verify-receipt's guarantees and limits.

These are updated:
- `docs/maf-adoption-design.md` step 5;
- `docs/cli-reference.md`, `README.md` and `flow-help` for `trace`, `verify-receipt` and `--actor`;
- the default Shaper intent template, if one exists, with the P10 values;
- `scaffolds/default/flow.toml`, if a command list names these.

## Success criteria

- **Verify-receipt passes on a clean fixture.** On a hermetic v8 lineage, `verify-receipt` passes every applicable check. The lineage is an abandoned attempt with an `unknown` paid send, followed by a successor that completes after an automatic tranche, an escalation with an answer-mode recovery, and a D5-style recovery.
- **Tampering with any one source** fails exactly the declared set of checks, each with a diagnostic detail. The sources are the receipt, a ledger row, a checkpoint, a request file, `repair.diff`, a trace, a predecessor receipt, the charter, and an event.
- **`flow run trace`** leads with the blocking reason for a paused attempt. For every call it shows grant history, provider session, checkpoint, pgid, timings and charged usage in absolute tokens, with no script needed.
- **The token cap is enforced hermetically:**
  - reaching `max_lineage_tokens` refuses the next paid grant;
  - with headroom, one tranche is granted;
  - beyond headroom, the attempt pauses for `decide-expansion`;
  - a shortfall of more than one tranche is a hard stop;
  - an `unknown` paid send counts at its sealed charge;
  - the overshoot with concurrent grants stays within the R12 bound.
- **`receipt_check.py` is superseded.** The mapping in `reconciliation.md` shows each of its generic checks covered. Only its run-specific checks remain: the stub scan and the chartered-facts text search.

## Non-goals

- MCP handback (E1).
- W3C `traceparent`, and OpenTelemetry export (P7).
- Dollar costs, and billing reconciliation.
- A per-call token cap, and mid-call cancel on tokens.
- Verifying pre-release receipts or v5–v7 receipts (P9).
- Re-running tests, re-applying diffs, or checking worktree drift (E3, P8).
- Signing receipts.
- An unbroken checkpoint-chain rule (F8).
- The per-job charter digest (`job-charter-sealed-digest`). The per-job charter isn't in the sealed authority, so covering it needs a contract change of its own; it is a follow-up (P-F7).
- Symlink hygiene in attempt evidence (`run-evidence-symlink-hygiene`), a separate follow-up (P-F7).
- The Claude trace-file naming for a second editor turn.
- A live provider run. `v8-live-validation-4` will exercise this slice separately.

## Constraints

- There is no back-compat, and older attempts are not migrated.
- Tests are hermetic: stub providers with scripted usage, the pinned stock Magentic runner where end-to-end coverage is needed, and no paid or live calls.
- The ledger and the existing fences stay authoritative, and the lock order is unchanged. The token check adds no new lock.
- `trace` and `verify-receipt` never write. This is tested by comparing digests of every file before and after.
- Commit order (F21):
  1. the actor, identity, group ids, grant events and request files;
  2. trace;
  3. the token contract and charge function;
  4. the gate;
  5. the receipt block and the shared seal comparison;
  6. verify-receipt;
  7. docs.

## Assumptions

- Claude reports cache fields that are disjoint from input; Codex reports cached input as a subset of input (observed, research §2.1).
- MAF checkpoint files carry `previous_checkpoint_id` (observed in the pinned MAF).
- The P10 defaults rest on one live lineage (observed, `v8-live-validation-3` receipt).

## Evidence and research implications

- `research/current-state.md` §1 → R1–R7; §2 → R8–R12; §3 → R13–R16.
- `adversarial-review.md` F1–F21 and `adversarial-product.md` P-F1–P-F9 → revision 2 (`definition-dispositions.md`).
- `v8-live-validation-3`'s receipt and `receipt_check.py`, read from branch `codex/v8-live-validation-3` → P10 and the `reconciliation.md` mapping.
- Gaps closed:
  - `runtime-evidence-completion-manifest` (receipts);
  - `delivery-per-call-timings`;
  - `manager-prompt-text-inspection`;
  - `recovery-actor-provenance`.

## Open questions (for planning; blocking before implementation)

- **Codex reasoning tokens (F19).** Are `reasoning_output_tokens` separate from `output_tokens` or included in them? Settle it with a captured fixture checked into tests.
- **Claude editor usage (F19).** Does a multi-turn Claude editor's `usage` cover the whole session or only the last turn? Settle it with a captured fixture (the `v8-live-validation-3` editor result may answer it).

## Approval status

Approved by Andy on 2026-09-27 (revision 2), with his answers: keep R2, hard stop for a shortfall of more than one tranche, concurrency allowed, and the P10 defaults.
