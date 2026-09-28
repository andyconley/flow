# Current state: trace correlation, token cap, receipt verification

Run: `step5-operational-handback`. Repo: `~/src/flow` (main, v0.38.1). Pinned MAF: `agent-framework-core 1.19.0` and `agent-framework-orchestrations 1.2.0` in `~/.flow/venvs/maf`.

Tags:

- **[O] observed:** read directly in the cited code.
- **[I] inferred:** follows from the code but was not executed.

Line numbers are for the current working tree.

**Not available:** `.flow/runs/v8-live-validation-3/scripts/receipt_check.py` is not on disk. The run directory exists only on the unmerged branch `codex/v8-live-validation-3` (`.git/logs/HEAD:294-310`). No copy exists under `~/src`, `~/.flow` or `/private/tmp`. Section 3.4 therefore infers what it checked from the capability-gap log (`~/.flow/user/capability-gaps.jsonl:81,91,92,97`) and from the v8-live-validation-2 scripts that did survive.

---

## 1. Trace correlation

### 1.1 Identifiers Flow records per v8 attempt

| Identifier | Origin | Where it is stored | In the receipt? |
|---|---|---|---|
| `work_id`, `attempt_id` | Flow; `attempt_id` is hex | `attempts` columns (`execution_ledger.py:75-82`); `envelope.json`; `events.attempt_id` | yes, as top-level fields [O] |
| `envelope_digest` | `execution_contracts.envelope_digest` | recomputed, not stored as a column | yes (`delivery_gateway.py:1308`) [O] |
| `action_id` | deterministic digest (`expected_magentic_action_id`, `execution_contracts.py:670`) | `actions.action_id` (`execution_ledger.py:83-89`); `events.action_id` | yes, in `actions[]` [O] |
| manager `call_id` | deterministic digest of attempt, envelope, sequence, phase, round and `prompt_digest` (`execution_contracts.py:742-747`), computed in the child (`runtime/maf_runner/delivery_lead.py:207-211`) | `manager_calls.call_id` (`execution_ledger.py:96-101`); stored in `events.action_id` too, since that column is shared | yes, in `manager_calls[]` [O] |
| `grant_id` (action or manager) | `uuid.uuid4().hex` (`execution_ledger.py:1326,1453`) | `actions.grant_id` and `manager_calls.grant_id`, **latest value only**. A regrant overwrites it (`:1071,1123,1150,1168`) and a release sets it to NULL (`:730,781`). Event `detail` records the reason, not the grant id (`:1328,1456`) | yes, the latest value only [O] |
| expansion `request_id` / `grant_id` | digest `exp-…` / `expg-…` (`execution_ledger.py:485,501`) | `expansion_requests` and `expansion_grants` (`:184-198`) | yes, in the `expansion` block (`:604-626`) [O] |
| `owner_generation`, `owner_actor` | lead claim, then bumped by recovery or seal | `attempts` (`:79-80`); copied into most evidence rows (observations, verifier rows, checkpoint links, resolutions, interruptions) | yes, in the evidence rows and in `recovery` and `termination` [O] |
| `recovery_id` | `attempt_recoveries` (`:176-183`) | `attempt_recoveries` table | yes, in `recovery.recoveries[]` (`execution_contracts.py:555-563`) [O] |
| `interruption_id` | `attempt_interruptions` (`:170-175`) | same table | yes, in `recovery.interruptions[]` [O] |
| `resolution_id` | `recovery_resolutions` (`:118-124`) | same table | yes, in `recovery.resolutions[]` [O] |
| recovery actor | CLI argument; `recover_delivery` defaults to the hard-coded `actor="codex-assisted-recovery"` (`delivery_gateway.py:1132`), and `flow run recover…` does not pass an actor (`flow.py:1079`) | `attempt_recoveries.actor`, `attempts.owner_actor` | yes [O]. This is the `recovery-actor-provenance` gap |
| MAF `checkpoint_id` | MAF `uuid4` (`agent_framework/_workflows/_checkpoint.py:89`), with a `previous_checkpoint_id` chain (`:90`) | `magentic_checkpoint_links(attempt_id, pending_kind, pending_id → checkpoint_id, ledger_seq, path, file_sha256, file_size, owner_generation)` (`execution_ledger.py:102-109`); event `magentic_checkpoint_bound` includes the checkpoint id (`:2162`) | yes, as `checkpoints` = `snapshot["magentic_checkpoints"]` (`delivery_gateway.py:1312`) [O] |
| `checkpoint_position_links` | v2–v4 only (`execution_ledger.py:2072-2073`) | table `:131-140` | not used by v8 [O] |
| MAF workflow name | `flow-magentic-delivery-v8` (`delivery_lead.py:129`) | inside the checkpoint JSON; checked at bind and read time (`execution_ledger.py:2143,2180`) | no, implicit [O] |
| MAF `Workflow.id` | fresh `uuid4` per build (`_workflows/_workflow.py:370`), put on the OTel run span (`:559-565`) | **not captured** | no [O]. It changes on every resume because the child rebuilds the workflow [I] |
| Claude `session_id` (editor) | `claude_edit_worker._result` (`claude_edit_worker.py:43-58`) | whole result in `actions.result_json` and `response_observations.result_json` (`execution_ledger.py:1776,1795`), together with `usage`, `num_turns` and `input_sha256` | yes, in `actions[].result` [O]. The worker's `validate_result` requires it (`execution_contracts.py:844`) |
| Claude `session_id` (manager) | `claude_worker._parse_result` (`claude_worker.py:88-100`) | **dropped.** The gateway builds the observation from `output`, `output_sha256` and `usage` only (`delivery_gateway.py:1509-1515`) | no [O] |
| Codex `thread_id` (editor) | `codex_worker._parse_events` (`codex_worker.py:45-69`) | whole result in `actions.result_json` | yes [O] |
| Codex `thread_id` (manager) | same | **dropped** (`delivery_gateway.py:1509-1511`) | no [O] |
| `input_sha256` (sha256 of the exact prompt bytes) | `claude_worker.py:215`, `claude_edit_worker.py:175` | editor: kept in the result. Manager: **dropped**. Codex worker: never produced | editor only [O] |
| Ollama identity | none. Flow sends `X-Flow-Correlation-Id: <action_id>` (`local_worker.py:81`); the result keeps `response_created_at` and the reported `model` (`:119-123`) | `actions.result_json` | yes, `response_created_at` only [O] |
| provider session persistence | Claude runs with `--no-session-persistence` (`claude_worker.py:145`, `claude_edit_worker.py:102`); Codex with `--ephemeral` (`codex_worker.py:102`) | — | The ids are correlation labels only. No local transcript exists for `harvest`/`session_lookup` to join [I] |
| process and control records | `control-g{gen}.json` (pid, start_time, machine_id, host) and `control-g{gen}.groups.jsonl` with `{pgid, leader_start, kind ∈ maf/provider/test, at}` (`process_identity.py:179-199`) | attempt directory files | not in the receipt. **A group line carries no `action_id` or `call_id`** (`:194`), so a pgid can be tied to a call only by timestamp [O] |
| Claude traces | `claude-implementer.debug.log` and `claude-implementer.events.ndjson` in the attempt directory, created with O_EXCL (`claude_edit_worker.py:99-117`) | files | yes, `evidence.diagnostic_trace` and `evidence.event_trace` as `{path, sha256, bytes}` (`delivery_gateway.py:1342-1357`) [O]. The names are fixed per attempt and not keyed to `action_id`. A second Claude editor turn in the same attempt would hit `FileExistsError` [I] |
| per-call timings | `events.at` for `manager_send_started`, `adapter_send_started`, `verifier_send_claimed`, `*_observed` and so on; `manager_calls.observed_at`; `response_observations.observed_at` | ledger only | not in the receipt, and not shown by `inspect-delivery` [O] (`delivery-per-call-timings`; the script is `v8-live-validation-2/scripts/ledger_timings.py`) |

### 1.2 Where the chain breaks

1. **Manager request text** [O]. Only `prompt_digest = digest(messages)` (the canonical JSON of the messages) is kept, in `manager_calls.request_json` (`delivery_gateway.py:497-509`, `execution_contracts.py:753-758`). It is reused as the expansion `proposal_digest` (`execution_ledger.py:1449`). The prompt text exists only transiently in `_default_manager_adapter` (`delivery_gateway.py:1768-1780`). The provider's own `input_sha256` digests the joined prompt text, which is a different digest, and is dropped.
2. **Manager provider session** [O]. `session_id`, `thread_id` and `input_sha256` are dropped at `delivery_gateway.py:1509-1511`, so a manager call cannot be joined to a provider session.
3. **Manager calls have no checkpoint link** [O]. `bind_magentic_checkpoint` is called only with `pending_kind="worker"` (`delivery_gateway.py:1563,1578,1595`). The `"manager"` branch exists in the ledger (`execution_ledger.py:2127`) but is unused in v8.
4. **Grant history** [O]. There is one `grant_id` column per row, so released and rotated grants lose their ids.
5. **Process groups to calls** [O]. As noted in the table, group lines have no `action_id` or `call_id`.
6. **MAF run identity** [O]. `Workflow.id` is not captured. The checkpoint `previous_checkpoint_id` chain is on disk but not recorded in the ledger.

### 1.3 MAF / OpenTelemetry hooks

- MAF instruments workflows with an OTel run span that carries `workflow.id`, `workflow.name` and `conversation_id` (`agent_framework/_workflows/_workflow.py:559-565`, `observability.py:3632-3679`). Messages carry W3C `trace_contexts`, injected in `_workflow_context.py:343-346` and serialised into runner context and checkpoints (`_runner_context.py:49-93`) [O].
- Instrumentation is enabled by default (`observability.py:1107`). However, **only `opentelemetry-api` is installed**: there is no `opentelemetry/sdk` in the venv [O]. The child also runs with `env={"PYTHONPATH": ...}` only (`maf_supervisor.py:465`), so no `OTEL_*` variables reach it [O]. The result is no-op spans with invalid (zero) span contexts, so MAF currently emits **no usable trace or span ids** [I].
- Option [I]: Flow could mint a W3C `traceparent` per attempt, or per owner generation, and pass it in the start/resume message. The child would attach it as the parent context. The API's no-op tracer propagates a parent span context, so MAF would carry Flow's trace id through the message `trace_contexts` without the SDK. This needs a small experiment to confirm.

---

## 2. Token usage and caps

### 2.1 Where usage is parsed

| Call | Parser | Usage fields | Stored |
|---|---|---|---|
| Claude manager | `claude_worker._normalized_usage` (`claude_worker.py:49-65`) | `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` (Claude's cache fields are **disjoint** from its input tokens) | `manager_calls.result_json.usage` (`delivery_gateway.py:1511` → `execution_ledger.py:1478-1499`; the shape is checked at `:1485`) [O] |
| Codex manager | `codex_worker._parse_events` (`codex_worker.py:57-63`) | the raw `turn.completed.usage` dict, any integer keys (typically `input_tokens`, `cached_input_tokens` ⊂ input, `output_tokens`) | `manager_calls.result_json.usage` [O]; cached ⊂ input per `usage_store.py:13-18` and `normalize.py:85-102` |
| Claude editor | `claude_edit_worker._result` reusing `_normalized_usage` (`claude_edit_worker.py:50-53`) | as the Claude manager | `actions.result_json.usage` and `response_observations` [O] |
| Codex editor | `codex_worker` | raw dict | `actions.result_json.usage` [O] |
| Ollama verifier | `local_worker.py:111-117` | `prompt_eval_count`, `eval_count` | `actions.result_json.usage` [O]; free, local |

- **Nothing sums usage per attempt or lineage** [O]. The only consumers are the shape validators: `execution_contracts.py:846-849`, `verifier_contracts.py:302-305` and `execution_ledger.py:1485`.
- `cost.py` and `usage_store.py` sum harvested **harness transcripts** in `~/.flow/usage.db`, which is a separate pipeline. Ephemeral and non-persistent provider calls are unlikely to appear there [I].
- `usage` is optional (`None` is allowed) for every provider [O]. An `unknown`, `failed` or timed-out send has **no observed usage** [O/I]. A `resolved_completed` recovery resolution may carry a `result_json` with usage (`execution_ledger.py:122`) [I].

### 2.2 What counts as "paid" today [O]

- **Actions:** provider in `{"codex","claude"}` (`execution_ledger.py:522,548`; for lineage, `:416-419`).
- **Manager calls:** paid only when `envelope["manager"]["provider"] ∈ {codex, claude}`. `manager_call_cap` applies only when paid (`:1436-1437`).
- **Ollama:** never paid. It is counted under `verifier_calls` only.

### 2.3 Limits, grants and headroom today [O]

- **Charter:** the Shaper intent's `budget_safety_envelope = {enforceable, observations}`. `enforceable` must have **exactly** `ENFORCEABLE_LIMIT_FIELDS` (`delivery_contracts.py:33-37,176-183`). `observations` is a free-form list (`:200`).
- **Projection:** `build_delivery_charter` builds `limits` (`delivery_contracts.py:259-263`). The envelope `limits` must have an **exact** key set for v8 (`execution_contracts.py:252-260`), projected at `delivery_gateway.py:470-484`. `expansion_headroom` is projected only when non-zero (`:481-484`).
- **Expandable limits:** `EXPANSION_LIMIT_KEYS` covers `delegations`, `paid_worker_calls`, `verifier_calls`, `manager_calls` and `manager_rounds`, each mapped to a runner ceiling (`execution_contracts.py:351-357`). `EXPANSION_CEILINGS` mirrors it (`delivery_contracts.py:40-46`), and `validate_expansion_headroom` bounds base plus headroom (`:104-121`). `LINEAGE_SCOPED_LIMITS = {paid_worker_calls, verifier_calls}`; the rest are per attempt (`execution_ledger.py:48`).
- **Action grant:** `decide` → `_v8_action_checks` (`execution_ledger.py:509-560`). Its checks list (`:542-553`) is `(reason, failing, expandable_limit|None, units)`. A limit is expandable only if `units == 1` and effective + 1 ≤ ceiling (`:558-559`). Then `_expand_locked` (`:476-507`) always grants **amount 1 per limit**, automatically within `charter_headroom`, or leaves a `pending` request for `decide-expansion`.
- **Manager grant:** `decide_manager_call` (`:1380-1458`), with inline call and round units at `:1435-1447`.
- **Re-grant paths** that re-evaluate limits: `regrant_recovered_action` (`:1043-1075`, via `_v8_limit_reason`) and `regrant_expanded_action` (`:1096-1125`). `reissue_expanded_manager_grant` duplicates the manager limit logic (`:1143-1148`). **`reissue_recovered_manager_grant` rotates a grant with no limit check** (`:1154-1170`).
- **Lineage accounting:** `_lineage_usage` counts predecessor *sends* (not tokens) → `{predecessor_paid_calls, predecessor_verifier_sends}` (`:406-421`). It is embedded as `receipt.lineage_usage` (`delivery_gateway.py:1322-1323`), bounded by `_validate_lineage_usage` (`execution_contracts.py:500-528`) and equality-checked at seal by `_assert_receipt_lineage` (`execution_ledger.py:562-577`).
- **Receipt expansion validation** hard-codes `amount == 1` (`execution_contracts.py:453,467`) and one unit per consumed grant (`:490-491`).
- **Child backstop:** the MAF process guard bounds manager calls and actions at the runner ceilings for v8 (`maf_supervisor.py:472-476`). It has no token concept.

### 2.4 Where a pre-grant cumulative token check would slot in [I]

- **One helper** `_lineage_tokens(db, envelope)` would sum normalised usage across `_lineage_attempts(envelope)`. It would cover `actions.result_json` for paid providers and `manager_calls.result_json` when the manager is paid, plus `response_observations` for rows still `started`, if they have been observed. It needs one normalisation rule, because Codex cached input is a subset of input while Claude's cache fields are disjoint. Candidate: input + output + cache_creation, reusing the convention in `normalize.py`, rather than inventing a new one.
- **Actions:** add a check row to `_v8_action_checks` (`execution_ledger.py:542-553`), for example `("token_cap", provider in paid and tokens >= effective["tokens"], "tokens"|None, units)`. Placing it after `paid_call_cap` keeps the historical reason order. Both `regrant_*` paths pick it up for free.
- **Manager calls:** add it in `decide_manager_call` beside `call_units` (`:1435-1447`) and in `reissue_expanded_manager_grant` (`:1143-1148`). Decide whether `reissue_recovered_manager_grant` must re-check too; today it does not check anything.
- **Charter:** a new sealed field is needed (for example `enforceable.max_lineage_tokens`). The field sets are exact (`delivery_contracts.py:33-37,357-363`; `execution_contracts.py:254`), so this is a Shaper/Charter version and envelope-limits change. It is acceptable because Andy has no back-compat users.
- **Delegated expansion:** the current machinery assumes integer counters that grow by exactly 1 unit. A token limit fits only if a unit is defined as a sealed **tranche** (for example `token_expansion_tranche`, with headroom counted in tranches) and a new key is added to `EXPANSION_LIMIT_KEYS`/`EXPANSION_CEILINGS`. The alternative is to generalise `amount` beyond 1, which touches `_expand_locked`, `_granted_units`, `_validate_expansion`, the `units != 1` hard rule and `decide_expansion`.
- **Lineage scope:** `tokens` would join `LINEAGE_SCOPED_LIMITS`, and `lineage_usage` would gain a `predecessor_tokens` field, checked by `_assert_receipt_lineage` and bounded in `_validate_lineage_usage`.
- **Receipt:** `verifier_usage` is recomputed from receipt rows by the pure validator. A token usage block (`{maximum, observed, unobserved_sends}`) can be recomputed the same way from `actions[].result.usage` and `manager_calls[].result.usage`, and seal-compared like `expansion`.

---

## 3. Receipt verification

### 3.1 What `validate_receipt` checks (pure, from the receipt and envelope only) [O]

The entry point is `execution_contracts.py:852-855`, which dispatches to `_validate_magentic_receipt` at `:1003-1190`.

- **Links:** required fields, 512 KiB cap, protocol and status set, and the links `work_id`, `attempt_id`, `charter_digest`, `manifest_digest`, `envelope_digest`, `charter_sources`, `run_protocol_revision` and `roster`. For delivery receipts it also links the shaper, charter, handoff and lead-claim digests (`:1017-1020`), and checks `evidence.source_commit`, `worktree` and `allowed_paths` against the envelope.
- **Evidence shapes:** trace and event-trace shapes with fixed names (≤1 MiB) and the continuation evidence shape.
- **Manager calls:** each request is re-validated (identity digest), ids are unique, statuses are valid, and a completed call has a result. `manager_progress` is recomputed from the receipt's own manager calls (`:988-1000`).
- **Actions:** `validate_action` and unique ids. A completed non-verifier action's result is validated, including the output digest and the Claude `session_id`.
- **Verifier:** input bindings (input digest recomputed, provider task suffix). Evaluations are **recomputed deterministically** (`evaluate_candidate`, `:1136-1148`), and exactly one evaluation is required per completed verifier. `verifier_usage` is recomputed from the rows (`:1152-1165`).
- **Expansion:** replayed and bounded by headroom and ceilings (`_validate_expansion`, `:406-497`). `lineage_usage` is bounded against the caps (`:500-528`). The recovery-block generation chain is checked, as are released grants and resolutions (`:531-588`). Termination and evidence damage are checked (`:1193-1231`).
- **Completion:** a `valid_pass` bound to `evidence.edit.diff_sha256` and `evidence.tests.output_sha256` (`:1171-1178`). Chartered baseline, edit and test shapes are checked against the job contract (`:1234-1258`).
- **Not checked:** any ledger fact, any file on disk, predecessor receipts, checkpoint files, the actual `repair.diff` bytes, the trace-file bytes, token totals, and events or timings.

### 3.2 What the seal checks against the ledger [O]

- **`finish_attempt`** (`execution_ledger.py:2259-2293`), v8:
  - It reads the receipt bytes before the transaction, then requires `uncertain > 0 ⇔ status == unknown`, and v8 never seals `unknown`.
  - It checks `lineage_usage == _lineage_usage` (`_assert_receipt_lineage`), `expansion == _expansion_receipt(...)` and `manager_progress == _manager_progress_receipt(...)`.
  - It stores `sealed_receipt_sha256`.
  - **It does not compare** actions, manager calls, verifier rows, the recovery block or checkpoints with the ledger.
- **`seal_terminal_uncertain`** (`:745-831`), for cancelled or abandoned attempts:
  - It builds the receipt inside the transaction from `_snapshot_locked`.
  - It compares `(action_id,status)` and `(call_id,status)` lists, termination owner generation, actor and cause, lineage, expansion and `manager_progress`.
  - It writes atomically and stores the sha with a bumped generation.
  - Still status-only for rows: the content of the results is not compared.
- The gateway calls `validate_receipt` before writing (`delivery_gateway.py:1756`) and seals under the send lock (`:1759-1763`).

### 3.3 `inspect-delivery` `sealed_receipt` [O]

`delivery_projection.py:62-87,195-206` reads only `attempt_dir/receipt.json`. It reports:

- `ledger_sha256` and `file_sha256`;
- `matches = ledger_sha is not None and ledger_sha == file_sha`;
- `consistent`, which also requires recovery-block presence to equal "recoveries exist".

It does **not** run `validate_receipt`, recompute any block, or follow predecessors, checkpoints or evidence. `flow.py:1195` prints `consistent`/`INCONSISTENT`.

### 3.4 What the hand-written `receipt_check.py` likely checked [I]

The file is unavailable (see the note at the top). The capability-gap log says checks were "scripted by hand" and the first version had "vacuous-pass shapes found only in review" (`capability-gaps.jsonl:92`). It also says manager guidance was checked by "decoding runtime checkpoints" (`:97`), and that timings needed a separate script (`:91`; the surviving v8-live-validation-2 `ledger_timings.py` derives call durations from `events`). So it plausibly checked, beyond Flow:

- file sha against the ledger sha, plus row-by-row equality with the ledger snapshot;
- the diff, test and verifier binding chain;
- trace digests;
- manager guidance, from checkpoint contents.

Vacuous passes typically come from comparisons over empty lists or absent keys, which an offline verifier must treat as failures when the block is required. **Engineer should supply the file or its checklist.**

### 3.5 What an offline `flow run verify-receipt` must recompute [I]

The receipt carries `created_at` (`delivery_gateway.py:1317`), and its evidence comes from runtime values (`edit_evidence`, `test_evidence`) that aren't in the ledger. So it **cannot be rebuilt byte-for-byte**. It has to be verified block by block against its sources.

| Check | Source |
|---|---|
| `sha256(receipt file) == attempts.sealed_receipt_sha256`; `attempts.receipt_path` names this file; attempt status is terminal and equals `receipt.status` | ledger `attempts` |
| `validate_receipt(envelope_from_ledger, receipt)` passes; `envelope.json` bytes equal the canonical ledger `envelope_json` | ledger, `envelope.json` |
| **full-content** equality of `actions`, `manager_calls`, `replans`, `checkpoints`, `verifier_inputs`, `verifier_evaluations` and `verifier_usage` with `_snapshot_locked` (not just ids and statuses) | ledger snapshot (read-only) |
| `lineage_usage`, `expansion`, `manager_progress`: the same functions the seal uses | ledger |
| `recovery` block == `build_recovery_block(snapshot, replaced_draft_sha256=…)`. The replaced-draft digest can only be checked against `evidence_damage`, because the draft itself is gone | ledger, receipt |
| `termination` == `attempts.reason` (JSON actor, cause, generation) for cancelled or abandoned attempts | ledger |
| predecessors: each `receipt_sha256` equals that attempt's `sealed_receipt_sha256` and its file hash, verified recursively; `lineage` equals `_v8_lineage_locked` order | ledger, predecessor receipts |
| delivery authority: `shaper-contract.json` and `delivery-charter.json` digests equal the envelope digests; the charter's `limits` projection equals the envelope `limits` and `expansion_headroom`; the lead-claim digest matches `run.json` | the run's `delivery/` directory, `run.json` |
| source snapshots: requirements and acceptance snapshot sha equal `charter_sources`; `charter_digest` is recomputed; the manifest snapshot sha equals `manifest_digest` | attempt-directory snapshots |
| checkpoints: for each link, the file exists in `checkpoint_dir`, and sha, size, `checkpoint_id`, `workflow_name` and the pending request key match (the `read_magentic_checkpoint` logic, `execution_ledger.py:2165-2194`); `ledger_seq ≤` the event high-water mark. **Recovery may move files to `checkpoints-quarantine`** (`delivery_gateway.py:875`), so check both locations | checkpoint files |
| edit chain: `sha256(repair.diff) == evidence.edit.diff_sha256 == verifier_inputs.diff_digest == final evaluation.diff_digest`; the diff text inside the verifier `provider_task` equals `repair.diff`; `changed_files` ⊆ `write_paths` | `repair.diff`, ledger |
| test chain: `evidence.tests.output_sha256 == verifier_inputs.test_digest == evaluation.test_evidence_digest`; `command == job.test.argv` | ledger only; the output bytes are not kept (`delivery_gateway.py:657-660`) |
| baseline: `baseline.json` equals `evidence.baseline`; `regression_diff_sha256 == job.baseline.diff_sha256` | `baseline.json`, envelope |
| traces: `diagnostic_trace` and `event_trace` sha and bytes match the files | attempt-directory traces |
| events coherence: every `started`/`completed`/`unknown` action has `worker_dispatched`/`adapter_send_started`, every manager send has `manager_send_started`, every consumed expansion grant has `expansion_grant_consumed`; seq values are monotonic | ledger `events` |
| (new) token block: summed from the receipt rows, equal to the ledger sum, and within the sealed cap plus one call of overshoot | ledger, receipt |

**Impossible offline:**

- that the provider actually ran, what it billed, or its own token numbers beyond what the CLI reported;
- whether a provider session or transcript still exists (non-persistent and ephemeral);
- the outcome of an `unknown` send;
- test output bytes and a re-run (only a digest is kept, and re-running is excluded by decision);
- re-applying the diff (excluded) or checking that the worktree still equals `evidence.edit.files`; the worktree may have moved on, so at most this can be reported as drift;
- manager prompt text: only the digest is stored. It can be recovered only if MAF checkpoint JSON contains the messages, and Flow refuses to unpickle MAF internals (`execution_ledger.py:2030-2033`);
- the bytes of a replaced draft receipt;
- whether ledger timestamps are true.

---

## 4. Options and risks per piece

### Trace correlation

- **A (minimal):**
  - Keep `session_id`/`thread_id` and `input_sha256` in the manager observation at `delivery_gateway.py:1509`.
  - Add `action_id`/`call_id` to process-group lines (`process_identity.register`).
  - Add a per-call timings and correlation table to `inspect-delivery`.
  - Low risk. It changes the `manager_calls.result_json` bytes, so it changes the receipt shape.
- **B:** A plus storing manager request text, bounded at 32 KB (`delivery_gateway.py:499`), in a new `manager_requests` table or file, digest-bound to `prompt_digest`. This closes `manager-prompt-text-inspection`.
  - Risk: prompt text contains the charter and diff, so it needs the same 0600 handling. The ledger also grows.
- **C:** A plus a Flow-minted W3C traceparent passed to the MAF child.
  - Risk: unverified with API-only OTel, and it adds a dependency or experiment.
- **Also:** a grant-id history, either an event detail with `grant_id` or a grants table. Fix the `recover` actor default at `delivery_gateway.py:1132` and `flow.py:1079` by making it required, like `cancel`/`abandon`.

### Token cap

- **A (hard stop, no expansion):**
  - A new sealed `max_lineage_tokens`.
  - Refuse (hard) at `_v8_action_checks` and `decide_manager_call`.
  - Simplest; it cannot escalate.
- **B (tranche expansion):**
  - Add a `tokens` key whose unit is a sealed tranche, lineage-scoped.
  - It fits the existing one-unit expansion machinery with the fewest invariant changes.
  - Risk: the units are unintuitive, and headroom has to be expressed in tranches.
- **C (general amounts):**
  - `amount > 1` in expansion.
  - Most flexible, and the largest change to `_validate_expansion` and `decide_expansion`.
- **Risks:**
  - The token rule must pick one normalisation, because Codex's subset rule differs from Claude's disjoint cache.
  - Unknown or failed sends have no usage, so overshoot can exceed one call after an uncertain send unless unknown sends count as "cap reached". Recommend fail-closed.
  - The unchecked `reissue_recovered_manager_grant` path needs a decision.
  - The manager is likely the largest consumer [I], so a manager-call check is essential.

### Receipt verification

- **A:** `flow run verify-receipt <work_id> [attempt_id]` as a pure read-only module. It opens the ledger read-only, reuses `_snapshot_locked`, `_expansion_receipt`, `_manager_progress_receipt`, `_lineage_usage`, `build_recovery_block` and `validate_receipt`, and adds the file and chain checks from 3.5. It outputs a structured `{check, status: pass|fail|not_applicable|impossible_offline, detail}` list, where an empty list for a required block counts as a fail.
- **B:** A plus tightening `finish_attempt` to do the full-row comparison that `seal_terminal_uncertain` does by status. The seal and the verifier would then share one comparison function, so they cannot drift.
- **Risks:**
  - The verifier duplicating ledger logic and drifting from it. Mitigation: import the same private functions and make them public.
  - Vacuous passes over empty collections.
  - Checkpoint files moved to quarantine.
  - Legacy v8 receipts sealed before a column or block existed. There are no back-compat obligations, but decide whether to verify old runs or refuse with `unsupported`.

---

## 5. Open questions for the engineer

1. Can you supply `receipt_check.py` from `codex/v8-live-validation-3`, or its checklist? That tells verify-receipt what live review needed.
2. Token unit: which counts towards the cap? The choices are input + output only, or also cache writes and reads. Cache reads are cheap but dominate the Claude numbers.
3. Should an `unknown` or failed paid send, which has no observed usage, count as "cap reached" (fail-closed) or as zero?
4. Expansion for tokens: hard stop only (A), tranche units (B), or general amounts (C)?
5. Should the verifier's local Ollama tokens be recorded in the total but excluded from the cap? The current "paid" set excludes Ollama.
6. May manager request text be stored (B in trace correlation), or should manager inspection stay digest-only?
7. Should `finish_attempt` be tightened to full-row seal comparison in this run, or should only the offline verifier do it?
8. Is the W3C traceparent into MAF in scope, or is correlation Flow-side ids only?
9. Should verify-receipt walk the predecessor lineage by default, and should it fail or only warn on worktree drift?
