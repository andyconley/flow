# Plan: step5-operational-handback

**Inputs:**
- approved `requirements.md` (revision 2: R1–R17, P1–P11, V1–V17);
- `acceptance-criteria.md` (AC1–AC23, AC12b, AC12c);
- `definition-dispositions.md`;
- `research/current-state.md` and `research/spikes.md` (S1–S3).

**Delivery:**
- One branch (`codex/step5-operational-handback`) and one PR.
- Seven Conventional Commits, C1–C7, in the order the requirements' Constraints fix.
- Each commit leaves the full suite green.
- The coordinator implements. Role agents review.

**Provenance.** The design below was drafted by a read-only planning subagent that read the definition and the code, citing file:line for each claim and tagging each [O] (observed) or [I] (inferred). The definition root then reviewed it and fixed the interpretations below. Line numbers refer to the tree at `6171c7d`.

## Interpretations fixed by this plan

- **I1. The default token budget is a constant, not a template.** No default Shaper intent template ships; intents are written per run.
  - `delivery_contracts.DEFAULT_TOKEN_BUDGET` pins the P10 values, and a unit test checks them.
  - ADR 0020 and the CLI reference cite the constant.
  - This is how AC8's "shipped default" is met.
- **I2. `tokens` follows the other expandable limits at 0 headroom** (R10 and AC10, amended by Andy on 2026-09-27).
  - Sealed headroom of 0, or headroom that is used up, pauses the attempt with a `pending` request for `decide-expansion`. This is the generic `_expand_locked` behaviour (`execution_ledger.py:491-500`), and there is no token-specific rule.
  - Only `units > 1` (AC12b) or the absolute tranche ceiling (D2) is a hard refusal.
- **I3. One recovery covers both.** The answer-mode resume after the engineer grant also replays the call that was granted automatically, from the ledger. That replay is the D5 regression. So the fixture lineage needs only one recovery, following `AutomaticGrantThenEscalationReplayTests`.
- **I4. "Unrecognised usage" is narrowly defined.** It means a shape the existing validators accept, but that has no usable token fields:
  - `input_tokens` or `output_tokens` is missing;
  - `usage: None`;
  - a Codex usage with `cached_input_tokens > input_tokens`.

  Negative or non-integer values stay rejected at record time. That is unchanged, and `tests/test_claude_worker.py` pins it.
- **I5. `grant_changed` is emitted for protocol 8 only.** v5–v7 event streams stay byte-identical. Grant-write sites that v8 can't reach are exempt in the AC3 table, and the reason given is the line that refuses them.
- **I6. Pre-release v8 attempts are read-compatible and write-refusing.**
  - What still works: `inspect-delivery`, `stuck`, `trace` and `abandon-delivery`. They keep working on the existing pre-release v8 envelopes in the repo.
  - What refuses: prepare refuses an older charter; the gate and seal builders refuse to advance a pre-release started attempt; verify-receipt reports `unsupported_receipt`.
  - Why: without this, `inspect-delivery` would raise on every old v8 attempt.

## Commits

| # | Commit | Design | ACs |
|---|---|---|---|
| C1 | `feat(delivery): correlate manager identity, request files, grant history and process groups` | D7–D12 | AC1–AC6 |
| C2 | `feat(delivery): add flow run trace` | D14, D15 | AC7 (stub-driven) |
| C3 | `feat(contracts): seal a lineage token budget and charge usage` | D1–D5 | AC8, AC9, AC13 (ledger) |
| C4 | `feat(ledger): check the token budget before every paid grant` | D6 | AC10–AC12c, AC13, AC7 (banner) |
| C5 | `feat(delivery): seal token usage with a full-row comparison` | D13 | AC14, AC20 |
| C6 | `feat(delivery): verify sealed receipts offline` | D16, fixture lineage | AC15–AC19, AC23, AC7 (fixture rows) |
| C7 | `docs(delivery): record ADR 0020 and operational handback` | R17 | AC21 |

AC22 (the full suite with 0 skipped) is checked after every commit. Section 6 gives rough sizes.

## 1. Design decisions

### D1. New constants and their homes

- **Token ceilings.**
  - `MAX_TOKEN_TRANCHES = 10` and `MAX_LINEAGE_TOKENS = 2_000_000` go in `runtime/maf_runner/limits.py`.
  - They are re-exported by the shim `cli/runner_limits.py:22-32` [O], which also gets its positive-int loop extended, alongside `MAX_ACTIONS` and friends.
  - Both contract modules already import from `runner_limits` (`delivery_contracts.py:13`, `execution_contracts.py:10` [O]).
  - Add the two names to `tests/test_runner_limits.py:19-21` [O].
- **Contract versions.**
  - `delivery_contracts.py:17-18`: `SHAPER_CONTRACT_VERSION = 4` and `DELIVERY_CHARTER_VERSION = 4`.
  - Add `EXPANSION_SHAPER_CONTRACT_VERSION = EXPANSION_DELIVERY_CHARTER_VERSION = 3`, so v3 stays readable, and add 3 to the version sets at `:25-26`.
- **Token contract (in `execution_contracts.py`).**
  - `TOKEN_LIMIT_KEYS = ("max_lineage_tokens", "token_tranche", "unobserved_send_tokens")`.
  - `CHARGED_UNIT = "charged_v1"`.
  - `MANAGER_IDENTITY_FIELDS = {"claude": ("session_id", "input_sha256", "num_turns"), "codex": ("thread_id",)}`.
- **Lineage-scoped limits.** `LINEAGE_SCOPED_LIMITS` moves from `execution_ledger.py:48` [O] to `execution_contracts.py`, becoming `{"paid_worker_calls", "verifier_calls", "tokens"}`. The ledger imports it. This removes the hard-coded copy at `execution_contracts.py:430` [O].

### D2. Tranches are an expandable counter with base 0 (F1, R8)

- **Registering the counter.**
  - `EXPANSION_LIMIT_KEYS` (`execution_contracts.py:351-357` [O]) gains `"tokens": (None, MAX_TOKEN_TRANCHES)`. `None` means the counter has no envelope limit key.
  - A new pure `expansion_base(envelope) -> dict[name, int]` returns `limits[key]` for each keyed name, and `tokens: 0`.
- **Every site that currently reads `envelope["limits"][key]` for all names must use `expansion_base`:**
  - `_effective_limits` (`execution_ledger.py:441-449` [O]);
  - `_validate_expansion` initialisation (`execution_contracts.py:415` [O]);
  - `_validate_expansion_headroom` (`:375-377` [O]).
- **Generic sites that pick `tokens` up unchanged, because they iterate `EXPANSION_LIMIT_KEYS`** [O]:
  - `_granted_units` (`:431`), `_outstanding_units` (`:460`), `_headroom_remaining` (`:467`);
  - `_expand_locked`'s automatic test (`:491`);
  - `decide_expansion`'s ceiling check (`:920`);
  - `expansion_headroom()` (`execution_contracts.py:363`);
  - `predecessor_headroom_spent` in `_expansion_receipt` (`execution_ledger.py:612-614`) and its validator (`execution_contracts.py:429`).
- **`predecessor_lineage_grants`** (`execution_ledger.py:622` [O]) is already built from `sorted(LINEAGE_SCOPED_LIMITS)`, so it gains `tokens`. The validator at `execution_contracts.py:430` switches to `set(LINEAGE_SCOPED_LIMITS)`.
- **Tokens-only ceiling** (a small protective extension; please confirm). The token "next unit fits" test also requires `max_lineage_tokens + (effective_tranches + outstanding + 1) × token_tranche ≤ MAX_LINEAGE_TOKENS`. It applies in:
  - the hard classification in `_v8_action_checks` (`:558-559`) and `_v8_manager_checks`;
  - `_expand_locked`'s automatic test (`:491`);
  - `decide_expansion` approval (`:920`, which raises `EXPANSION_CEILING_EXCEEDED`);
  - the receipt's final ceiling check (`execution_contracts.py:495`).

  Without it, engineer grants could push the absolute maximum past the charter rule's `MAX_LINEAGE_TOKENS`.
- **Amounts are unchanged.** `amount` stays 1 everywhere (`execution_ledger.py:495,504,926`; `execution_contracts.py:453,467` [O]).

### D3. Envelope versioning and P9 support (F7)

- **The marker is the ledger envelope's v8 limit key set.** There is no receipt-side marker. The envelope carries no charter version today (`delivery_gateway.py:455-477` [O]), and the limits projection is the envelope's image of charter v4.
- **`_validate_magentic_envelope`** (v8 branch, `execution_contracts.py:252-260` [O]) accepts exactly one of two sets:
  - `LEGACY_V8_LIMIT_KEYS`, the current eight keys;
  - `HANDBACK_V8_LIMIT_KEYS`, which adds the three token keys, with the R8 rules: each ≥ 1; `token_tranche ≥ unobserved_send_tokens`; `unobserved_send_tokens ≤ max_lineage_tokens ≤ MAX_LINEAGE_TOKENS`.
- **`_validate_expansion_headroom`** (`:366-379`) adds two checks:
  - `headroom.tokens ≤ MAX_TOKEN_TRANCHES`, via the base-0 ceiling;
  - `max_lineage_tokens + headroom.tokens × token_tranche ≤ MAX_LINEAGE_TOKENS`;
  - and it refuses `tokens` headroom on a legacy set.
- **New pure predicate:** `handback_supported(envelope) := protocol == 8 and set(limits) == HANDBACK_V8_LIMIT_KEYS`. It reads the raw JSON and is safe on legacy envelopes.
- **Write refusal.**
  - `create_attempt` (`execution_ledger.py:362-380` [O]) refuses a v8 envelope that is not `handback_supported`.
  - `_v8_action_checks`, `_v8_manager_checks` and the seal-block builder raise `ContractError("attempt predates the sealed token budget; abandon it")` for a legacy started attempt.
  - Abandon still works: legacy blocks give `token_usage=None`, and the validator requires `token_usage` absent for legacy envelopes.
- **Prepare** (`delivery_gateway.py:385-389` [O], next to the existing "requires … max_verifier_calls" refusal) adds: `canonical_charter["charter_version"] != DELIVERY_CHARTER_VERSION` gives `ContractError("protocol v8 requires a Delivery Charter that seals a token budget")`. The pattern follows `tests/test_chartered_delivery_gateway.py:806-827` [O].
- **verify-receipt** returns `unsupported_receipt` (exit 2) iff `not handback_supported(ledger envelope_json)`, read before any validating call. A supported receipt that lacks `token_usage` fails (V2 through `validate_receipt`, and V4).

### D4. Shaper, charter and envelope field sets (R8)

| Place | Change |
|---|---|
| `ENFORCEABLE_LIMIT_FIELDS`, `delivery_contracts.py:33-37` [O] | Add the 3 token fields. `validate_shaper_intent` requires the exact set (`:179`) and validates the R8 rules next to `:180-191`. |
| `EXPANSION_CEILINGS`, `:40-46` | Add `"tokens": MAX_TOKEN_TRANCHES`. |
| `_expansion_base`, `:124-126`, and `validate_expansion_headroom`, `:104-121` | Take a `names` parameter. v3 records validate without `tokens`; otherwise the full map `{…, tokens: 0}` would differ from a sealed v3 headroom map at `:321` and `:369-371` and break old contracts [I]. v4 includes `tokens` and adds the absolute rule. |
| `build_delivery_charter` limits, `:259-263` | Project the 3 token fields from `enforceable`. |
| `validate_shaper_contract`, `:315` | `if version == SHAPER_CONTRACT_VERSION` becomes `in {3, 4}` for headroom. v4 also requires `enforceable` keys == `ENFORCEABLE_LIMIT_FIELDS` plus the token rules. |
| `validate_delivery_charter`, `:357-372` | Add the 3 keys to `limit_keys` for v4, integers ≥ 1, the token rules and the absolute rule. Line `:360` `== DELIVERY_CHARTER_VERSION` becomes `in {3, 4}`. The "one version line" rule at `:367` still holds, with v4 on both sides. |
| Gateway envelope projection, `delivery_gateway.py:470-477` [O] | Add the 3 keys. The `expansion_headroom` projection at `:481` already copies non-zero `tokens`. |
| Test fixtures | `tests/shaper_intent_fixture.py:37-42` [O] defaults to **`max_lineage_tokens: 2_000_000, token_tranche: 1_000, unobserved_send_tokens: 1_000`**. Stub rows with `"usage": None` (`tests/test_chartered_delivery_gateway.py:151-158` [O]) and stub managers then cost 1,000 each and never hit the cap in legacy tests. With P10 values, two unobserved sends would exhaust 200k [I]. `tests/test_chartered_execution_contract.py:36-39` `structured_verifier()` [O] gets the same keys; it feeds `test_expansion_ledger`, `test_structured_verifier_ledger` and `test_runner_limits`. |

### D5. Charging (R9, P1, P2; pure functions in `execution_contracts.py`)

- **`charge(row, provider, unobserved_send_tokens) -> {"charged", "cache_read", "recognised"}`.** `row` has the snapshot or receipt shape `{status, result, …}`.
  - `status ∈ {allowed, denied, not_dispatched}`, or provider `ollama` or `local-stub`: `{0, 0, True}`.
  - `status ∈ {started, unknown}`: `{U, 0, False}`.
  - `status ∈ {completed, failed}`: normalise `result.get("usage")`:
    - **Claude.** Requires `input_tokens` and `output_tokens` as non-bool integers ≥ 0. `cache_creation_input_tokens` and `cache_read_input_tokens` are optional and default to 0. `charged = input + cache_creation + output`; `cache_read = cache_read_input_tokens`.
    - **Codex.** Requires `input_tokens` and `output_tokens`. `cached_input_tokens` is optional (default 0) and must be ≤ `input`. `charged = input − cached + output`; `cache_read = cached`. `reasoning_output_tokens` is included in `output_tokens` (S1), and `cache_write_input_tokens` is reported only (S1).
    - Extra keys are ignored. Anything else is `{U, 0, False}`.
- **`verifier_tokens(row) -> int`:** Ollama `prompt_eval_count + eval_count` (keys at `local_worker.py:111-117` [O]); reported only.
- **`attempt_token_charges(envelope, actions, manager_calls) -> {observed_charged, unobserved_sends, unobserved_charged, unrecognised_usage, cache_read_total, verifier_tokens, charged}`.**
  - It covers paid actions only (`request.provider ∈ {codex, claude}`), plus manager calls only when `envelope.manager.provider ∈ {codex, claude}`.
  - `unobserved_sends` counts the sent rows charged U. `unrecognised_usage` is the subset with status `completed` or `failed`.
- **`token_maximum(envelope, tranches) = max_lineage_tokens + tranches × token_tranche`.**
- **`token_gate(charged, envelope, tranches) -> (failing, units)`.**
  - `failing = charged ≥ max`.
  - `units = floor((charged − max) / tranche) + 1` when failing, else 0.
- **`token_usage_block(envelope, actions, manager_calls, *, predecessor_charged, tranches_granted)`** returns the R11 block with an exact key set: `{unit, maximum, tranches_granted, observed_charged, unobserved_sends, unobserved_charged, unrecognised_usage, charged_total, overshoot, cache_read_total, verifier_tokens}`.
  - `charged_total = observed_charged + unobserved_charged + predecessor_charged`.
  - `cache_read_total` and `verifier_tokens` cover the attempt's own rows only; ADR 0020 documents this.
- **Ledger wrapper:**
  - `ExecutionLedger._lineage_charged(db, envelope) -> {"predecessor_charged", "own", "total"}`. It loops `_lineage_attempts(envelope)` (`execution_ledger.py:424-425` [O]), reads each attempt's `envelope_json` (raw, not validated) plus its actions and manager rows, and calls `attempt_token_charges` with that attempt's own sealed U and manager provider.
  - Public wrapper: `lineage_charged(attempt_id)`.
  - Every lineage attempt shares the run's one charter, sealed once at `start-plan` (`delivery_control.py:120-205` [O], with the claim keeping `charter_digest` at `:333` [O]). So U is identical across the lineage, which keeps V6's cross-check exact [I].
- **`_lineage_usage`** (`execution_ledger.py:407-421` [O]) adds `predecessor_charged`. `_validate_lineage_usage`'s exact set (`execution_contracts.py:512` [O]) adds the key, a non-negative integer. `_assert_receipt_lineage` (`:563-577`) needs no change, because it compares the whole dict.

### D6. The gate (R10; commit 4)

- **`_v8_action_checks`** (`execution_ledger.py:510-560` [O]) adds one entry after `paid_call_cap` (`:548-549`):

  ```
  ("token_cap", action["provider"] in paid and failing, "tokens", units)
  ```

  Here `charged = _lineage_charged(db, envelope)["total"]`, computed with the own row excluded (`exclude`; an excluded row is unsent anyway), and `tranches = effective["tokens"]`.
  - The hard rule at `:558-559` adds `or (limit == "tokens" and absolute ceiling fails)` (D2). There is no headroom-0 special case (I2, amended).
  - `decide` (`:1250-1258`) is unchanged: expansion, automatic within headroom, else `pending`. Because units = 1 is required, one tranche always clears the cap (F1's last point) [I].
  - `regrant_recovered_action` (`:1062-1069`) picks it up through `_v8_limit_reason`. A token failure takes the existing state change: `denied` plus `policy_denied`, plus `grant_changed op=deny`.
  - `regrant_expanded_action` (`:1119-1121`) keeps its current behaviour, raise and roll back, now naming `token_cap`.
- **New `_v8_manager_checks(db, envelope, request, *, exclude="") -> (reason, hard, expandable)`.** It folds together:
  - the replan checks (`:1412-1426`);
  - the call count (`:1427-1431`, with `AND call_id<>?`);
  - call and round units (`:1435-1442`);
  - the new token check, applied when the manager is paid.

  Rules:
  - The historical reason order is kept: replan reasons, overwritten by `manager_call_cap`, then `manager_round_cap`, then `token_cap` (the comment at `:1432-1434`).
  - `hard` is non-None when a replan reason fails, when any failing unit ≠ 1, or when a ceiling fails, including the tokens absolute ceiling.
  - v5–v7 keep their current reason logic; the token check applies only to v8.
- **Call sites of `_v8_manager_checks`:**
  - **`decide_manager_call`** (`:1427-1452`) replaces its inline logic. It expands when `v8 and reason != allowed and hard is None and expandable`.
  - **`reissue_expanded_manager_grant`** (`:1142-1148`) replaces its duplicate logic and still raises on failure.
  - **`reissue_recovered_manager_grant`** (`:1154-1170`) gains the checks with `exclude=call_id`. On failure:

    ```sql
    UPDATE manager_calls SET status='denied', reason=?, grant_id=NULL
    ```

    followed by `manager_policy_denied`, plus `grant_changed op=deny` carrying the dropped grant. It returns `{"allowed": False, "reason": …, "replayed": False}`.
- **Gateway handling of a denied reissue** (`delivery_gateway.py:1476-1478` [O]). The returned decision is not replayed, so it falls through to `:1497-1498` (`"Magentic manager call denied: token_cap"`), and the attempt is sealed failed like other hard manager denials. No other gateway change is needed.
- **Unpaid calls.** An unpaid manager and the Ollama verifier are never checked (the `paid` guard).
- **Locks.** There is no new lock. Everything runs inside each method's existing `BEGIN IMMEDIATE`, and the lock order is unchanged.
- **Concurrency (P11).** `concurrency_cap` (`:552`) and `_unresolved_action` (`:1176-1185`) are unchanged. AC12c therefore needs a ledger-level test: two `decide` calls, then consume and complete both. Magentic issues actions serially, so a MAF run cannot produce two outstanding grants [I].

### D7. `grant_changed` (R3)

- **Helper.** `ExecutionLedger._grant_changed(db, attempt_id, row_id, kind, op, grant_id, reason)`. It:
  - reads `owner_generation` and `execution_protocol_version` from `attempts` within the same transaction;
  - returns without writing unless the protocol is 8;
  - otherwise calls `_event(db, attempt_id, row_id, "grant_changed", canonical({grant_id, row_id, kind, owner_generation, op, reason}))`.

  Here `kind ∈ {"action", "manager_call"}`.
- **Placement.** The event is written **immediately before** the legacy event in each path. That keeps assertions on the last one or two events intact: `tests/test_chartered_delivery_recovery.py:249-250` and `tests/test_delivery_termination.py:114` [O]. Existing `detail` strings are untouched (AC3).
- **Field semantics:**
  - `reason` is the row's `reason` column after the write, except `consume`, which uses `"grant_consumed"`.
  - `grant_id` for `issue`/`rotate` is the new grant; for `consume`/`expire`, the grant used; for `release`, the grant read *before* it is set to NULL; for `deny`, `None` (decide, or regrant of a released row) or the dropped grant (reissue deny).

The site table (all in `cli/execution_ledger.py`) also serves as AC3's enumeration table:

| Site | Transition | op |
|---|---|---|
| `seal_superseded_attempts` :729 | allowed → not_dispatched, NULL | release |
| `seal_terminal_uncertain` :781 | allowed → not_dispatched, NULL | release |
| `claim_chartered_recovery` :1010 | allowed → not_dispatched, NULL | release |
| `regrant_recovered_action` :1067 | not_dispatched → denied | deny |
| `regrant_recovered_action` :1071 | not_dispatched → allowed, new grant | issue |
| `regrant_expanded_action` :1123 | denied → allowed | issue |
| `reissue_expanded_manager_grant` :1150 | denied → allowed | issue |
| `reissue_recovered_manager_grant` :1168 | allowed, grant rotated | rotate |
| `reissue_recovered_manager_grant` (new UPDATE, C4) | allowed → denied | deny |
| `decide` :1327 | INSERT allowed or denied | issue or deny |
| `decide_manager_call` :1454 | INSERT allowed or denied | issue or deny |
| `consume_manager_grant` :1471 / :1474 | expired / consumed | expire / consume |
| `consume_grant` :1528 / :1531 | | expire / consume |
| `prepare_verifier_send` :1558 / :1567 | | expire / consume |
| `close_pre_send_failure` :1600 | allowed → not_dispatched | release |
| `_append_resolution_locked` :1960 | resolved_not_dispatched | release (helper present; exempt: v8 unreachable per :1819) |
| **Exempt, not a grant change** (from started or unknown only): :959, :963 `_claim_recovery_locked`; :1499 `observe_manager_response`; :1515 `mark_manager_unknown`; :1795 `complete`; :1805 `mark_unknown` | — | — |
| **Exempt, v8-unreachable:** :1958 (from `allowed` only through v5 `resolve_unknown`, refused at :1819); :1990 `regrant_not_dispatched` (refused at :1973) | — | — |

**AC3 structural test** (new `tests/test_grant_history.py`):

1. **Enumerate.** Use `ast.parse(cli/execution_ledger.py)` and walk every `Call` whose `func.attr == "execute"`. Build the first argument's string from `Constant`, `JoinedStr` or `BinOp` concatenations, and match `^\s*(UPDATE (actions|manager_calls) SET|INSERT INTO (actions|manager_calls))`. Record `(enclosing function, normalised SQL)`.
2. **Compare with the table.** Assert that the set equals the keys of a `SITES` table. Each entry is either `("op", scenario)` or `("exempt", reason)`. A new write site therefore fails the test until someone classifies it.
3. **Run the scenarios.** Each op scenario builds state on a fresh ledger, using the `CharteredFixture` and `RecoveryHarness` patterns. It records the maximum event seq, invokes the path, and asserts exactly one new `grant_changed` event with the right `op`, `row_id` and `grant_id` rule.

Also for AC3:
- **Replay.** For the boundary-b scenario (`tests/test_chartered_delivery_recovery.py:692-712` [O]: grant, kill at consume, recovery release, regrant, consume), fold the `grant_changed` events and assert the ordered history `issue → release → issue → consume`.
- **Exempt sites.** Assert the v8 refusals at `:1819` and `:1973`.

### D8. Manager identity (R1)

- **Worker.** `claude_worker._parse_result` returns `num_turns` too; it is validated at `cli/claude_worker.py:91-93` but not returned at `:94-100` [O]. That is a one-key addition.
- **Gateway** (`delivery_gateway.py:1509-1515` [O]). Only when `structured_verifier` (v8) and the manager provider is Claude or Codex:
  - copy `MANAGER_IDENTITY_FIELDS[provider]` from the adapter result into the observation;
  - if any field is missing or mistyped, raise `ContractError` *inside* the existing `try`. The call is then marked unknown, like the invalid-text precedent at `:1506-1508`.
- **Receipt validation.** `_validate_magentic_receipt`'s manager loop (`execution_contracts.py:1056-1065` [O]): for v8 completed rows, require `session_id` (non-empty str), `input_sha256` (hex) and `num_turns` (int ≥ 1) for Claude, and `thread_id` (non-empty str) for Codex.
- **Test churn.** Stub manager adapters must return these fields. Add a helper `manager_reply(message, text, *, usage=None, provider="claude")` in the new shared fixture module; it computes `input_sha256 = sha256(render_manager_prompt(message["messages"]).encode())`.

### D9. Manager request files and prompt rendering (R2) — new `cli/manager_requests.py`

- **`render_manager_prompt(messages) -> str`.** Moved verbatim from `_default_manager_adapter` (`delivery_gateway.py:1770-1782` [O]), raising `ContractError`. `_default_manager_adapter` calls it. Claude's `input_sha256` is `sha256(prompt.encode())` (`claude_worker.py:139-141,215` [O]), so it is recomputable offline.
- **`request_bytes(call_id, prompt_digest, messages) -> bytes`.** Returns `canonical({"call_id", "prompt_digest", "messages"}) + "\n"`, matching `envelope.json`'s convention (`delivery_gateway.py:486` [O]). It refuses if `digest(messages) != prompt_digest`; `_normalized_manager_request` already refuses at `:506` [O], and this re-check is defence in depth.
- **`write_request_file(attempt_dir, call_id, data)`:**
  - `attempt_dir/manager-requests/`, mode 0700; refuse a symlinked directory.
  - Write a temp file `.{call_id}.{uuid}.tmp` with `O_CREAT|O_EXCL|O_NOFOLLOW`, mode 0600; write, then fsync.
  - `os.link(tmp, final)`. On `FileExistsError`, read the existing file (`O_NOFOLLOW`, bounded). Equal bytes are reused; different bytes raise `ContractError("manager request file conflicts")`, leaving the file untouched.
  - Always unlink the temp file.
- **`read_request_file(run_attempt_dir, call_id) -> bytes | None`:** bounded to 64 KiB, `O_NOFOLLOW`.
- **Placement.** In `on_manager`, inside the existing `with authority_guard(), ledger.send_lock():` after `ledger.assert_owner` (`delivery_gateway.py:1499-1501` [O]) and **before** `consume_manager_grant` (`:1502`). It runs only for `allowed` decisions (the code path already guarantees this). The write runs before the `try` at `:1504`, so a refusal leaves the row `allowed` (AC2).
- **Replays.** A replayed never-sent grant (after `reissue_recovered_manager_grant`) produces identical bytes, because `call_id` is derived from `prompt_digest` (`execution_contracts.py:742-747` [O]).

### D10. Process groups name their call (R4)

- **Registrar.** `ControlScope.register(pgid, kind, row_id=None)` (`process_identity.py:190-199` [O]) writes `{pgid, leader_start, kind, at, row_id}`. `register_group(pgid, kind, row_id=None)` (`:231-235`) is used by stubs.
- **Default adapters bind the id per call.** `_default_manager_adapter` wraps `on_process_group` as `partial(on_process_group, row_id=message["call_id"])`, and `_default_worker_adapter` does the same with `action["action_id"]` (`delivery_gateway.py:1768-1833` [O]).
- **MAF and test groups stay null.** `maf_supervisor.py:478-479` and the test group at `delivery_gateway.py:643-644` are unchanged [O].
- **Readers.** `records()` (`process_identity.py:270-295` [O]) tolerates the extra key.

### D11. Checkpoint parent (R5)

- **Schema.** Migration in `ExecutionLedger.__init__`, next to `:213-215` [O]: `ALTER TABLE magentic_checkpoint_links ADD COLUMN previous_checkpoint_id TEXT`.
- **Bind.** `bind_magentic_checkpoint` (`:2139-2161` [O]) stores `value.get("previous_checkpoint_id")` read from the file it already parses. Real MAF files carry that key (seen as `None` for a root in `.flow/runs/maf-charter-job-launcher/execution/…/checkpoints/*.json` [O]).
- **Snapshot and receipt.** `_snapshot_locked` (`:2675,2692`) selects it (guarded by `PRAGMA`, for old read-only ledgers) and adds it to each `magentic_checkpoints` row. It therefore appears in the receipt's `checkpoints`.
- **Informational only.** No chain rule is enforced (F8).

### D12. Recovery actor (R6)

- `recover_delivery(…, actor: str, …)` becomes a required keyword with no default (`delivery_gateway.py:1131-1132` [O]).
- The CLI adds `--actor` (`required=True`) to `recover-delivery-lead` (`flow.py:617-622` [O]) and passes it at `:1079`.
- Callers: `tests/test_maf_expansion.py:77` and `tests/test_expansion_recovery.py:34` [O].
- The command strings gain `--actor NAME`:
  - `delivery_termination.next_command` (`:257` [O]);
  - `decide_expansion`'s `next_action` (`execution_ledger.py:934` [O]); the test at `test_expansion_decide.py:51` uses `assertIn`, so it survives.
- The structural test at `tests/test_chartered_delivery_recovery.py:1068-1123` [O] is unchanged, because `recover_delivery(` still appears once in `flow.py`.
- `_resume_chartered`'s own default `"flow-chartered-resume"` for resume-delivery-lead (`:716`) stays; it is not the recover default.

### D13. Seal comparison and snapshot timing (R16, P6) — new pure `cli/receipt_compare.py`

- **Block lists.**
  - `ROW_BLOCKS = ("actions", "manager_calls", "replans", "checkpoints", "verifier_inputs", "verifier_evaluations", "verifier_usage")`.
  - `DERIVED_BLOCKS = ("lineage_usage", "expansion", "manager_progress", "token_usage")`.
- **`expected_blocks(snapshot, blocks) -> dict`** maps receipt keys to expected values (`checkpoints ← snapshot["magentic_checkpoints"]`, as at `delivery_gateway.py:1312` [O]).
- **`compare_receipt_rows(receipt, expected, *, blocks) -> list[Mismatch]`**, where a mismatch is `{block, row_id, path, expected, found}`, or, for canonical values over 200 bytes, `{…, expected_sha256, found_sha256, path=first differing key path}`.
  - Lists are compared index by index. `row_id` comes from `action_id`, `call_id`, `replan_id` or `pending_id`, and a length difference is reported at path `[len]`.
  - Dicts compare exact key sets first, then values recursively.
  - For a derived block, an absent key is equivalent to an expected `None`.
  - The same function feeds V3 and V4 diagnostics (P-F5).
- **Ledger.** `_seal_blocks_locked(db, envelope) -> {lineage_usage (None without predecessors), expansion, manager_progress, token_usage (None for legacy)}`. The public `seal_view(attempt_id)` runs one read transaction and returns `{snapshot, blocks}`.
- **`finish_attempt`** (`execution_ledger.py:2259-2293` [O]). Move the receipt read *inside* `BEGIN IMMEDIATE` (it is currently at `:2262-2265`, before the transaction). Then for v8, compare in this order:
  1. lineage (keep the message "receipt lineage usage differs from the ledger"; `tests/test_chartered_delivery_recovery.py:567` [O]);
  2. expansion (keep its message);
  3. manager_progress (keep its message);
  4. token_usage;
  5. every row block, with the message `"receipt rows differ from the ledger: <block> <row_id> <path>"`.
- **`seal_terminal_uncertain`** (`:797-810` [O]) replaces the `listed` status comparison with `compare_receipt_rows`, keeping the message prefix "terminal receipt rows differ from the ledger" (`tests/test_delivery_termination.py:203,791` [O]). It adds `token_usage` to `blocks` (`:787-789`), and `build_terminal_receipt` adds it to the loop at `delivery_termination.py:102` [O].
- **Gateway `_seal_attempt`** (`delivery_gateway.py:1742-1765` [O]) is restructured into **one** hold:

  ```
  with authority_guard(), ledger.send_lock():
      ledger.close_expansions(...)
      view = ledger.seal_view(aid)
      receipt = _build_receipt(..., view["snapshot"], blocks=view["blocks"])
      validate_receipt(...)
      hook("after-receipt-draft")
      ledger.assert_owner(...)
      write_atomic(...)
      hook("before-finish-attempt")
      ledger.finish_attempt(...)
  ```

  `_build_receipt` (`:1318-1331` [O]) takes `blocks` instead of calling `ledger.lineage_usage`, `expansion_receipt` and `manager_progress_receipt`, and adds `receipt["token_usage"]` for supported envelopes. The v5 continuation path keeps its old behaviour. The stale snapshot from `:1692` is no longer used for sealing.
- **Identity test (AC20).** `execution_ledger.compare_receipt_rows is receipt_verify.compare_receipt_rows is receipt_compare.compare_receipt_rows`.
- **Receipt validation** (C5). `_validate_magentic_receipt` (`execution_contracts.py:1082-1167` [O]) recomputes `token_usage_block(envelope, receipt.actions, receipt.manager_calls, predecessor_charged=lineage["predecessor_charged"], tranches_granted=effective["tokens"])`, with `effective` from `_validate_expansion` (`:1089`). The block is required iff `handback_supported`, and must equal the recomputation exactly (AC14).

### D14. Read-only ledger view for trace and verify

- **API.** Public `ExecutionLedger.lineage_view(attempt_id) -> dict`. It requires `read_only=True`, opens one connection (`_db()`, `mode=ro` at `:240` [O]), runs `BEGIN` then all reads then `rollback()`, and closes.
- **Returned fields.**
  - For the target and each lineage attempt: the attempts row (status, reason, `receipt_path`, `sealed_receipt_sha256`, protocol, raw `envelope_json`), `_snapshot_locked`, and `_seal_blocks_locked` when supported.
  - `_v8_lineage_locked(work_id)`.
  - The full event rows.
- **Why it matters.** The private helpers stay private and are reused, not copied (current-state §4 risk). AC18's "one transaction" becomes testable by counting `_db` calls.
- **Callers.** verify must make exactly one `lineage_view` call and no other ledger call. The existing `snapshot()` opens a connection per call without a transaction (`:2652-2654` [O]), so it is unsuitable.

### D15. `flow run trace` — new `cli/delivery_trace.py`

- **API.** `trace(work_id, attempt_id=None, *, root) -> dict` (with `TRACE_SCHEMA_VERSION = 1`) and `render_text(view) -> str`.
- **Inputs:**
  - `lineage_view`;
  - `process_identity.records(attempt_dir)` for control records and pgids by `row_id`;
  - `manager_requests.read_request_file` for presence and digest match;
  - the events, for grant history (fold of `grant_changed`) and timings:
    - manager: `manager_send_started → manager_response_observed`;
    - producer: `worker_dispatched → response_observed`;
    - verifier: `verifier_send_claimed → response_observed`;
  - `charge()` and the block builder for usage.
- **Banner:**
  - For a started attempt: reason, since-seq/at, row and next command.
    - An `expansion_requested` pending request gives `expansion_paused: <denied row reason>`.
    - Other reasons come from the interruption or unknown events, the run.json lead status, or `control_view` (`delivery_termination.py:227` [O]).
    - The next command is `delivery_termination.next_command` (`:241-258` [O]), shared with `stuck`.
  - For a terminal attempt: status, cause and the ledger's receipt digest.
- **Supported protocols.** v5–v7 print `unsupported_protocol`, and pre-release v8 prints `unsupported_contract`; the lineage display continues past both.
- **Read-only.** Trace never writes or creates a lock file. The probe opens `O_RDONLY` without `O_CREAT` (`execution_ledger.py:307-332` [O]).
- **CLI.** `flow run trace <work-id> [--attempt ID] [--json]` goes next to `stuck` (`flow.py:671-673` [O]). Exit 0, or 2 if the run, attempt or ledger is unreadable.

### D16. `flow run verify-receipt` — new `cli/receipt_verify.py`

- **API.** `verify_receipt(work_id, attempt_id=None, *, root, lineage=True) -> {"exit_code", "attempt_id", "checks": [{check, status, compared, detail}], "unverifiable": [...], "informational": [...]}`.
- **Imports.** Only pure modules plus `ExecutionLedger(read_only=True).lineage_view`: `execution_contracts`, `receipt_compare`, `delivery_contracts` validators and digest, `delivery_recovery.build_recovery_block`, `verifier_contracts`, and `manager_requests`. It does **not** import `delivery_gateway`.
- **Moved helper.** `_verifier_provider_task` (`delivery_gateway.py:1213-1217` [O]) moves to `verifier_contracts.verifier_provider_task`, and the gateway keeps an alias.
- **Paths come from the run directory.** Every file is located under `run_dir`: `execution/<aid>/receipt.json`, `…/checkpoints/<basename(link.path)>` or `…/checkpoints-quarantine/*/<basename>`, `delivery/<charter digest>/…`, and `manager-requests/`.
  - Absolute paths recorded in the ledger (`receipt_path`, `link.path`, `checkpoint_dir`) are only checked for their trailing components, for example that `receipt_path` ends with `execution/<aid>/receipt.json`.
  - This satisfies "only files under the run directory", and makes AC16's copied-run-dir tampering work (the copy's absolute paths still point at the original) [I].
- **Target selection.** The default is the latest attempt of the work id, by rowid, with a sealed digest and a terminal status.
  - An explicit attempt that isn't sealed, or no sealed attempt at all, gives `attempt_not_sealed` (exit 2).
  - `not handback_supported(raw ledger envelope)` gives `unsupported_receipt` (exit 2).
  - An unreadable run or ledger gives exit 2.
- **Implementation per check.** "compared" counts the facts compared.

  | Check | Implementation |
  |---|---|
  | V1 | `sha256(file) == sealed`; the recorded `receipt_path` tail names this file; the attempt status is terminal and equals `receipt.status`. |
  | V2 | `envelope.json` bytes == `canonical(ledger envelope) + "\n"`; `validate_receipt(ledger envelope, receipt)`. |
  | V3 | `compare_receipt_rows(receipt, expected, blocks=ROW_BLOCKS)`. For `completed`, `ledger actions == []` is a fail ("required block empty"). |
  | V4 | `compare_receipt_rows(…, blocks=DERIVED_BLOCKS)` against `_seal_blocks_locked` values. A missing `token_usage` on a supported attempt is a fail. |
  | V5 | `recovery == build_recovery_block(snapshot, replaced_draft_sha256=receipt.recovery.replaced_draft_sha256)`. The replaced draft is R15-unverifiable; `validate_receipt` already cross-checks it with `evidence_damage` at `execution_contracts.py:1227-1231` [O]. `termination.{actor, cause, owner_generation}` equals `json.loads(attempts.reason)` (written at `execution_ledger.py:824` [O]), and `lead_generation` equals the envelope claim. `explanation` is receipt-only; the detail says so. |
  | V6 | Each predecessor: `envelope.predecessors[i].receipt_sha256 == ledger sealed == sha(file)`. Recurse (a nested failure rolls up as a V6 fail with nested detail) unless `--no-lineage`. A superseded predecessor is `not_applicable` ("superseded predecessor has no receipt; charged from the ledger"). The order equals the prefix of `_v8_lineage_locked` before the attempt. `Σ attempt_token_charges(pred receipt rows).charged` over sealed predecessors, plus ledger charges of superseded ones, equals `lineage_usage.predecessor_charged`. |
  | V7 | The shaper, charter and handoff files recompute their self-digests (as `_sealed_delivery_authority` does, `delivery_gateway.py:115-133` [O]) and equal the envelope's `shaper_contract_digest`, `delivery_charter_digest` and `handoff_digest`. The current claim path comes from `run.json` only. Walk `supersedes` from the current claim (files `lead-claim.json` for generation 1, then `lead-claim-g{n}-{status}.json`, `delivery_control.py:329-340` [O]) back to the claim whose digest equals the envelope's `delivery_lead_claim_digest`, recomputing each digest. `charter.limits` projected as at `delivery_gateway.py:470-484` must equal the ledger envelope's `limits` and `expansion_headroom`. |
  | V8 | sha of `requirements.snapshot.md`, `acceptance.snapshot.md` and `manifest.snapshot.json` (`delivery_gateway.py:445-447` [O]) equals `charter_sources` and `manifest_digest`; recompute `charter_digest` (`:456`). |
  | V9 | Per bound link: the file is found in either location; sha, size, `checkpoint_id`, `workflow_name == "flow-magentic-delivery-v8"`, the pending key `flow-magentic-action-{seq}` for worker links (the rule at `execution_ledger.py:2143-2150` [O]) and `previous_checkpoint_id` all match. |
  | V10 | For every call with an `op=issue` `grant_changed`: the file exists; its bytes are canonical plus `"\n"`; keys are exact; `call_id` and `prompt_digest` equal the row's; `digest(messages) == prompt_digest`; and for Claude completed rows, `sha256(render(messages)) == result.input_sha256`. Orphan files fail. The file mode goes in `informational` (F16). |
  | V11 | The final verifier input is `verifier_inputs[-1]`. `sha(repair.diff) ==` `evidence.edit.diff_sha256` `== final input.diff_digest == final evaluation.diff_digest`; `input.provider_task == verifier_provider_task(action.task, diff_text, sha, structured=True)`; the `diff --git` headers and `evidence.edit.changed_files` are ⊆ `write_paths`. |
  | V12 | `evidence.tests.output_sha256 ==` final `input.test_digest ==` final `evaluation.test_evidence_digest`; `command == job.test.argv`. |
  | V13 | parsed `baseline.json == evidence.baseline`; `regression_diff_sha256 == job.baseline.diff_sha256`. |
  | V14 | `diagnostic_trace` and `event_trace`: sha and byte counts of the files. |
  | V15 | (a) Each sent row has exactly one send-start event of its kind (`manager_send_started`, `worker_dispatched`, `verifier_send_claimed`), and manager sequences are contiguous from 1 (per `reconciliation.md`). (b) Each engineer-consumed expansion grant has `expansion_grant_consumed` with its `grant_id`; a `charter_headroom` grant has its `expansion_granted`. (c) Fold `grant_changed` per row: issue/rotate → (allowed, g); consume → (sent, g); expire → (denied, g); release → (not_dispatched, None); deny → (denied, None). The fold's end state must match the ledger row's status class and `grant_id`, and every row needs at least one event. (d) Each checkpoint link's `ledger_seq` is below the seq of its `magentic_checkpoint_bound` event. (e) No `manager_send_started`, paid `worker_dispatched` or `verifier_send_claimed` falls strictly between a pending `expansion_requested` and its `expansion_decided` or `expansion_cancelled` (matched by `request_id` in the detail). |
  | V16 | Every group line's `row_id` is null for `maf`/`test` and otherwise a receipt row id. Every sent Claude or Codex row has a line with its `row_id` in `control-g{gen}.groups.jsonl`, where `gen` is the `owner_generation` of its `op=consume` event. Ollama rows are `not_applicable`. |
  | V17 | Walk the lineage events in seq order. At each `grant_changed` issue or rotate on a paid row, compute `charged` = Σ `charge()` of lineage paid rows whose first send-start seq is below it, and `tranches` = consumed token grants whose `expansion_granted`/`expansion_grant_consumed` seq is below it. Require `charged < token_maximum`. Every sent paid row must have an issue event before its send-start, so a deleted event fails V17. Using final charges is exact, because `decide` refuses while any same-attempt row is started or unknown (`execution_ledger.py:1233-1235,1406-1407` [O]) [I]. |

- **Requiredness.** Encode R14's table as `REQUIREDNESS[check][status] ∈ {"R", "P", "-"}`, plus callables ("R if predecessors", "R if any manager call was allowed", "R if a Claude editor was sent").
  - `NA_REASONS[(check, status)]` holds fixed strings.
  - `pass` requires `compared ≥ 1`, except where a `LEGIT_EMPTY` set allows it.
  - The six R15 items are always `unverifiable_offline`, with fixed texts.
- **CLI.** `verify-receipt <work-id> [--attempt ID] [--no-lineage] [--json]`. Exit 0 when nothing fails, 1 on any fail, 2 when verification can't run.

---

## 2. R8 touch points (summary)

- **Key sets:**
  - `ENFORCEABLE_LIMIT_FIELDS` (`delivery_contracts.py:33-37`);
  - charter `limit_keys` (`:357-361`);
  - charter projection (`:259-263`);
  - envelope projection (`delivery_gateway.py:470-477`);
  - v8 envelope exact set (`execution_contracts.py:252-260`, now two sets per D3).
- **Expansion machinery:**
  - `EXPANSION_LIMIT_KEYS` (`execution_contracts.py:351`) and `EXPANSION_CEILINGS` (`delivery_contracts.py:40`);
  - `LINEAGE_SCOPED_LIMITS` (moved from `execution_ledger.py:48`);
  - `_expansion_receipt.predecessor_lineage_grants` (`:622`, automatic through the constant);
  - the `_validate_expansion` lineage set (`execution_contracts.py:430`);
  - base-0 handling (`_effective_limits` `:443`, `_validate_expansion` `:415`, `_validate_expansion_headroom` `:375`).
- **Gate integration.** Add the `("token_cap", …, "tokens", units)` entry to the `checks` list at `execution_ledger.py:542-553`, and the tokens clause to the hard rule at `:558-559`. `_v8_manager_checks` returns the same shape.
- **AC12b.**
  - `units > 1` is hard on the automatic path (`decide` sees `hard ≠ None`, so no `_expand_locked`, so no request row).
  - It is also hard on the engineer path (no pending request is created).
  - A test asserts `expansion_state(...)["requests"] == []` and the row is `denied/token_cap`, in both headroom configurations: 1 available, and exhausted.

---

## 3. Shared fixture builder (AC15; also AC7, AC16, AC19, AC23)

**New module `tests/delivery_handback_fixture.py`.** It builds on:
- `CharteredFixture` (`tests/test_chartered_delivery_gateway.py:36-185` [O]);
- `ExpansionGatewayFixture` (`tests/test_expansion_gateway.py:22-74` [O]);
- `MafExpansionFixture` and `real_runner` (`tests/test_maf_expansion.py:26-89` [O]), gated by `requires_maf` (`tests/maf_env.py`).

What it provides:

- **Manifest.** The editor is **Claude**, so the trace evidence (V14) exists; the stub writes `claude-implementer.debug.log` and `claude-implementer.events.ndjson` into the attempt directory. The manager is Claude. The verifier is Ollama.
- **Intent.**
  - `max_concurrent 1`.
  - `max_paid_worker_calls 2`, because the predecessor's unknown editor send counts toward the lineage paid cap (`execution_ledger.py:537-538` [O]).
  - Chosen values for `max_lineage_tokens` M, `token_tranche` T and `unobserved_send_tokens` U ≤ T, with `expansion_headroom {"tokens": 1}`.
- **Scripted manager.** It follows `MafExpansionFixture.manager`, but returns `manager_reply(...)` with S3-style usage and a correct `input_sha256`, and it registers a real `sleep` group through `process_identity.register_group(pid, "provider", row_id=call_id)`, then kills it.
  - It must be a real child process. Abandon reaps every recorded group (`delivery_termination.py:179-225` [O]), so registering the test's own pid would killpg the test process [I].
- **Stub workers.** They register groups the same way. The Claude editor returns S2 usage (charged 82,376), `session_id` and `num_turns`.
- **Step 1, the predecessor.** Run `real_runner`. The editor stub registers, then raises: the row becomes `unknown` and the attempt `interrupted` (reconciliation_required). Then call `abandon_delivery(actor="andy", …)`.
- **Step 2, reset.** Reset the worktree (`SuccessorLineageTests._reset_worktree`, `test_chartered_delivery_recovery.py:388` [O]).
- **Step 3, the successor.** Pick M, T, U and per-call usage so that:
  - the **auto tranche** triggers on a manager call *after* the verifier action (so that call replays from the ledger on resume, which is D5);
  - the **second hit** pauses on the `final` manager call (units = 1);
  - after `decide_expansion(approve)`, `recover_delivery(actor=…)` resumes in **answer** mode and completes.

  This mirrors `AutomaticGrantThenEscalationReplayTests` (`test_maf_expansion.py:182-203` [O]). The implementer computes concrete numbers in the builder, with an assertion that they satisfy these inequalities.
- **Build once.** Use a class-level cache built in `setUpClass`, into a temp root. `copy_run(dest)` does a `shutil.copytree` of the temp root for each tamper case.
- **Other fixtures.**
  - The abandoned fixture (AC19) is the lineage's predecessor, verified with `--attempt A`.
  - The cancelled fixture reuses `tests/delivery_cancel_harness.py` (`test_delivery_cancel.py`), whose stubs call `register_group` (`delivery_cancel_harness.py:49-54` [O]); add `row_id`.
  - The paused `token_cap` banner golden (AC7) uses the successor state just before `decide_expansion`; the builder exposes it.

---

## 4. AC16 tamper cases and their expected sets (record in `validation-plan.md`)

| Tamper | Exact change | Expected failing checks |
|---|---|---|
| Byte-only receipt change | append a space | {V1} |
| Receipt content change | the receipt's `manager_calls[0].observed_at` | {V1, V3} |
| Ledger action result, same status | (a) the editor row's `result.session_id` | {V3} |
| | (b) `result.usage.output_tokens += M` | {V3, V4, V17} |
| Envelope limit changed | `max_runtime_seconds` in the **ledger** `envelope_json` | {V2, V7}. V7 uses the ledger envelope; a change to the `envelope.json` file alone fails only V2. |
| Charter file byte changed | a content change (not whitespace: the digests are over canonical content) | {V7} |
| Requirements snapshot changed | | {V8} |
| Checkpoint byte changed | | {V9} |
| Request file message changed | | {V10} |
| `repair.diff` byte changed | | {V11} |
| Trace byte changed | | {V14} |
| `baseline.json` field changed | | {V13} |
| Duplicated `manager_send_started` | INSERT a copy into `events` | {V15}. V17 uses the first send-start. |
| Predecessor receipt byte changed | whitespace | {V6} |
| Group line row id changed | | {V16} |
| A `grant_changed` event deleted | the `op=issue` event of a paid row | {V15, V17} |

---

## 5. Tests likely to break (AC22 list)

| File | Why |
|---|---|
| `tests/shaper_intent_fixture.py` | Token defaults (D4). This is the central fix. |
| `tests/test_shaper_delivery_contracts.py` | Version 3→4 and the exact field sets. |
| `tests/test_chartered_execution_contract.py` | `structured_verifier()` limits; receipts need `token_usage` and manager identity. |
| `tests/test_runner_limits.py` | Constant names; headroom projection cases at `:40-60` [O]. |
| `tests/test_expansion_ledger.py` | Exact `headroom_remaining` dict at `:251` [O] now has a `tokens` key. |
| `tests/test_expansion_receipts.py` | `predecessor_*` blocks include `tokens`. `SealedExpansionEvidenceTests` (`:118-146` [O]) seals a bare `{"expansion": …}` receipt; the full-row seal now refuses it, so the fixture must use full rows. |
| `tests/test_expansion_gateway.py:156`, `tests/test_maf_expansion.py:45-57`, `tests/test_maf_progress_retry.py`, `tests/test_expansion_recovery.py`, `tests/test_chartered_delivery_recovery.py` (manager stub at the `:879` test), `tests/delivery_cancel_harness.py:108` | Manager stubs need identity (D8). |
| `tests/test_maf_expansion.py:77`, `tests/test_expansion_recovery.py:34` | The `actor` argument. |
| `tests/test_chartered_delivery_gateway.py:253` [O] | Exact `envelope["limits"]`. |
| `tests/test_chartered_delivery_recovery.py:566-578` [O] | It patches `ExecutionLedger.lineage_usage`, which the gateway no longer calls after R16, so it must patch `seal_view`'s blocks. The expected `lineage_usage` dict gains `predecessor_charged`. |
| `tests/test_delivery_termination.py` | Blocks include `token_usage`; the row comparison message; group lines. |
| `tests/test_delivery_projection.py`, `tests/test_structured_verifier_ledger.py` | Envelope limits. |
| `tests/test_claude_worker.py:134,175` [O] | Only if the result dict is compared exactly; `num_turns` is new. |
| `tests/test_process_identity.py:129` [O] | Unaffected (tuple projection); `register` gains a keyword. |

v5 and v7 tests should be unaffected because `grant_changed`, identity and tokens are v8-only [I].

---

## 6. Commits, sizes and the AC mapping

Each commit leaves the full suite green. The `flow.toml` and help entries land in the commit that introduces each command (precedent A14).

| # | Content | Production / test lines (rough) | ACs |
|---|---|---|---|
| **C1** `feat(delivery): correlate manager identity, request files, grant history and process groups` | D7 (all existing sites), D8, D9, D10, D11, D12; `flow.toml` entry for `recover-delivery-lead --actor`; regenerate help | ~420 / ~750 (`test_grant_history.py` ~350, request files ~180, identity ~80, pgid, checkpoint, actor ~140) | AC1–AC6 |
| **C2** `feat(delivery): add flow run trace` | D14 `lineage_view`, D15 (raw usage and timings; token columns filled in C3 and C4), CLI, `flow.toml` | ~420 / ~300 | AC7 (stub-driven; full fixture goldens in C4 and C6) |
| **C3** `feat(contracts): seal a lineage token budget and charge usage` | D1–D5, D3 prepare refusal and dual-read, fixture defaults, trace charged columns | ~380 / ~450, plus fixture churn | AC8, AC9, AC13 (ledger half) |
| **C4** `feat(ledger): check the token budget before every paid grant` | D6, the reissue deny site (update the AC3 table), the fixture builder (pause state), trace cap state and banner goldens | ~200 / ~550 | AC10–AC12c, AC13, AC7 paused banner |
| **C5** `feat(delivery): seal token usage with a full-row comparison` | D13, `token_usage` block and validator, `predecessor_charged` | ~330 / ~350 | AC14, AC20 |
| **C6** `feat(delivery): verify sealed receipts offline` | D16, the complete fixture lineage, tamper suite, cancelled and abandoned runs | ~750 / ~800 | AC15–AC19, AC23 (evidence), AC7 fixture rows |
| **C7** `docs(delivery): record ADR 0020 and operational handback` | `docs/adr/0020-…md` (every R17 item, the R12 bound, the P10 derivation, "not a cost proxy", "consistency check, not a signature"); `maf-adoption-design.md` rows `:12,20-33,79,88,101` [O]; `cli-reference.md` (trace with the `--json \| jq` note, verify-receipt, `--actor`); README; regenerate help (`--check`) | ~450 docs | AC21 |

---

## 7. Risks and remaining spikes

- **SP-A** (C6 first). Confirm that `mode=ro` with an explicit `BEGIN`/`rollback` creates no `-journal` or `-shm` file and changes no bytes. Also confirm the ledger's journal mode (not set, so `DELETE`) [I].
- **SP-B** (C4). Measure the MAF fixture build time (two runs plus a recovery). If it is slow, cache per class and copy per case.
- **SP-C** (C1, optional). A fake `claude` on `PATH`, following the AC1c harness pattern, to prove through the real `call_claude` that `input_sha256 == sha256(render_manager_prompt(messages))`.
- **Risk: fixture token numbers.** One mis-sized manager usage turns the auto tranche into a hard units > 1 stop. The builder asserts the inequalities up front.
- **Risk: seal restructure hooks.** Moving `after-receipt-draft` inside `send_lock` must keep the KillPoint tests in `test_chartered_delivery_recovery.py:791-834` [O] green. The receipt is still unwritten at that hook.
- **Risk: gateway size.** `delivery_gateway.py` is 1,834 lines [O]. The new logic lives in `manager_requests.py`, `receipt_compare.py`, `delivery_trace.py` and `receipt_verify.py`; the gateway gets only hooks.
- **Risk: open question S1.** Codex `cache_write_input_tokens` has only been observed as 0. It is reported only; ADR 0020 and the AC9 fixture say so.
- **Risk: the I1–I6 confirmations** in section 0.

## 8. Critical files
- /Users/andyconley/src/flow/cli/execution_ledger.py
- /Users/andyconley/src/flow/cli/execution_contracts.py
- /Users/andyconley/src/flow/cli/delivery_gateway.py
- /Users/andyconley/src/flow/cli/delivery_contracts.py
- /Users/andyconley/src/flow/tests/test_maf_expansion.py (the base for the new `tests/delivery_handback_fixture.py`)

New modules: `/Users/andyconley/src/flow/cli/receipt_compare.py`, `/Users/andyconley/src/flow/cli/receipt_verify.py`, `/Users/andyconley/src/flow/cli/delivery_trace.py`, `/Users/andyconley/src/flow/cli/manager_requests.py`, `/Users/andyconley/src/flow/tests/test_grant_history.py`.

## Amendments from plan review

These override the design text above wherever they conflict (`plan-dispositions.md` maps them to PR1–PR18).

- **A1. Legacy abandon (PR1).**
  - **Blocks never raise.** `_seal_blocks_locked` never raises. For `not handback_supported` it returns `token_usage=None` and the two-key legacy `lineage_usage`.
  - **Key sets.** `_validate_lineage_usage` chooses its key set by `handback_supported`. Its no-predecessor default includes `predecessor_charged: 0` only for supported attempts.
  - **Where "refuse to advance" lives.** Only in `_v8_action_checks`, `_v8_manager_checks`, the gateway's `_seal_attempt` and `finish_attempt`.
  - **Tests (C3).** A `tests/legacy_v8_rows.py` helper inserts rows by direct SQL. `abandon_delivery` then seals a legacy started attempt, with and without a legacy predecessor.
- **A2. V15 transition fold (PR2).** Legal transitions:
  - `issue`: from none, `not_dispatched` or `denied`;
  - `rotate`, `consume`, `expire`, `release`: from `(allowed, g)` with a matching `grant_id`;
  - `deny`: from none or `allowed`.

  An illegal transition fails V15, naming the row and the op.
- **A3. Escalation windows (PR3).** A window exists only for a request that no `charter_headroom` grant covered. It spans `expansion_requested` to the matching `expansion_decided` or `expansion_cancelled`, by `request_id`. A window still open at seal is a V15 fail.
- **A4. Tolerant record-time usage (PR4).** Change `codex_worker._parse_result` (`:58-63`), `validate_result` (`execution_contracts.py:846-849`) and `observe_manager_response` (`execution_ledger.py:1485`):
  - they validate only the known keys (non-bool int ≥ 0) and ignore extras;
  - known keys with bad values are still rejected.

  Add AC9 cases: a Codex nested extra key, and a manager string extra key. Each call completes, and is not marked unknown.
- **A5. Request-file durability (PR5).**
  - Fsync the `manager-requests/` directory fd after `os.link`, and on the reuse path.
  - V10 ignores `.*.tmp` for pass/fail and lists them under `informational`. Only `<hex call_id>.json` files take part in the orphan rule.
  - New AC2 case: kill after the temp file is created. V10 still passes.
- **A6. Checkpoint parent is v8-only (PR6).** `previous_checkpoint_id` is projected into snapshot and receipt rows only for protocol 8. v5–v7 receipts are unchanged.
- **A7. Shared limits projection and claim walk (PR7).**
  - C3 adds `delivery_contracts.project_envelope_limits(canonical_limits) -> (limits, expansion_headroom)`. The gateway's prepare and V7 both call it, with an identity assertion.
  - The V7 claim walk indexes every `lead-claim*.json` under `delivery/<charter digest>/` by recomputed digest, then follows `supersedes`.
- **A8. AC3 enumeration (PR8).**
  - It walks `execute`, `executemany` and `executescript` calls.
  - A first argument that can't be resolved statically fails the test, unless it is allowlisted. Today only the schema script is allowlisted.
  - The pattern is case-insensitive and unanchored: `(UPDATE|INSERT( OR \w+)? INTO|REPLACE INTO|DELETE FROM)\s+(actions|manager_calls)\b`.
  - It compares a `Counter` of `(function, normalised SQL)` against `SITES`.
- **A9. SITES reasons (PR9).** `:1958` becomes "exempt, not a grant change (from started or unknown only)". `:1960` stays v8-unreachable. `validation-results.md` notes that R3's `resolved_not_dispatched` emits nothing in v8.
- **A10. Confirmations and lapsed grants (PR10).** The D2 absolute ceiling and I3 go to Andy at plan approval. A lapsed engineer tranche stays counted as outstanding for the ceiling, which is conservative. ADR 0020 records this.
- **A11. AC22 deviations (PR11).** `validation-results.md` names each fixture-change category with its reason:
  - manager-stub identity;
  - full-row receipts in `SealedExpansionEvidenceTests`;
  - the `seal_view` patch target;
  - the `lineage_usage` shape;
  - `register_group(row_id=…)`.
- **A12. V13 on terminal-uncertain attempts (PR12).** V13 passes on cancelled and abandoned attempts, because the baseline is always written. Only V11 and V12 are `not_applicable` there.
- **A13. Verify is subprocess-free (PR13).**
  - verify uses only `process_identity.records()`.
  - trace may use a non-blocking liveness probe, but creates no lock file.
  - The subprocess and socket patch applies to verify (AC18).
- **A14. Small fixes (PR14).**
  - The v5 next-command at `execution_ledger.py:2453` gains `--actor`.
  - The D10 `partial` is applied only when `on_process_group` is not `None`.
- **A15. Request-file placement (PR15).**
  - The request file is written after `assert_owner` and before `stop_if_cancelled()` (`delivery_gateway.py:1500-1501`).
  - V10: every call with an `issue` or `rotate` event needs its file.
  - An `issue` with no `consume` and no file is `fail` for completed or failed attempts, and `not_applicable` for cancelled or abandoned ones.
- **A16. Sequencing (PR16).**
  - `tests/manager_stub.py` (`manager_reply`) lands in C1.
  - `predecessor_charged` lands in C3 only.
  - In C2, `lineage_view` returns the pre-C3 blocks.
- **A17. Mutations (PR17).** Add:
  - M9: drop the V15 transition check;
  - M10: drop the token check from `_v8_manager_checks`;
  - M11: reintroduce a hard `token_cap` refusal at 0 headroom, which must fail the amended AC10;
  - M12: V17 counts rows sent after the issue seq;
  - M13: remove the legacy refusal in `_v8_action_checks`.
- **A18. Validation gaps (PR18).**
  - A Codex manager `thread_id` case.
  - Trace outputs enumerated: `unsupported_protocol`, `unsupported_contract`, missing work id exits 2. Goldens normalise seq and time.
  - AC12c asserts the overshoot through `seal_view(...)["blocks"]["token_usage"]["overshoot"]`.
  - A supported `envelope.json` file whose ledger envelope is legacy fails V2 (exit 1), instead of `unsupported_receipt`.
  - Codex `cache_write_input_tokens` appears only in trace's raw usage.
