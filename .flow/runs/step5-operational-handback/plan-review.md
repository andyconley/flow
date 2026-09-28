# Plan Review: step5-operational-handback

**Scope.** I reviewed `plan.md`, `validation-plan.md` and `implementation-handoff.md` against the approved `requirements.md`, `acceptance-criteria.md`, `definition-dispositions.md` and `research/spikes.md`. I checked the load-bearing citations in `cli/execution_ledger.py`, `cli/execution_contracts.py`, `cli/delivery_gateway.py`, `cli/delivery_termination.py`, `cli/delivery_control.py`, `cli/process_identity.py`, `cli/claude_worker.py`, `cli/codex_worker.py`, `tests/test_maf_expansion.py`, `tests/test_expansion_receipts.py`, `tests/test_chartered_delivery_recovery.py` and `tests/delivery_cancel_harness.py`. Almost every line reference is accurate (exceptions: PR9, and `_assert_receipt_lineage`, which is in `execution_ledger.py:563-577`, not `execution_contracts`).

**Verified sound; no finding needed.**
- **D2/D6 arithmetic.** `failing = charged ≥ M + k·T` and `units = floor((charged − max)/T) + 1` mean an expandable hit (units = 1) always clears with one tranche.
- **Headroom can't be spent twice.** `_headroom_remaining` counts lineage `charter_headroom` grants with `consumed_only=False` (`execution_ledger.py:463-467`). Automatic grants are inserted `consumed` (`:502-504`).
- **No double charge.** The own attempt is counted once, `predecessor_charged` covers predecessors only, and the excluded rows are `not_dispatched`/`allowed` and cost 0.
- **Effective tranches match on both sides.** The ledger's `_effective_limits` tranche count equals the validator's `_validate_expansion` `effective["tokens"]`: base 0, plus `predecessor_lineage_grants`, plus own consumed grants.
- **V17 "final charges are exact" holds.** Every grant-issuing path refuses or raises while a same-attempt row is started or unknown: `decide` `:1233`, `decide_manager_call` `:1406`, `regrant_recovered_action` `:1062`, `regrant_expanded_action` `:1112`, both reissues `:1137,:1164`. So every same-attempt row sent before an issue event is already final. Predecessor rows are frozen, because terminal attempts fence `assert_owner`. Unknown→completed only happens by late observation or `resolve_observed_v8` in the same started attempt, and no gate runs in between.
- **D13 lock ordering is unchanged.** The order stays `authority_guard` → `send_lock` → SQLite. None of `close_expansions`, `seal_view`, `_build_receipt` or `validate_receipt` takes `send_lock`. A `KillPoint` raised at `after-receipt-draft` unwinds the flock, and `test_boundary_i` (`test_chartered_delivery_recovery.py:791-812`) still sees no draft at that point.
- **Fixture numbers are feasible.** The real-runner call order is facts(1), plan(2), progress→editor(3), progress→verifier(4), progress(5), final(6) (`test_maf_expansion.py:120,186-189`). The Ollama verifier is never gated. Scripted usage can therefore make call 4 cross M, call 5 hit and auto-grant (charged in [M, M+T)), and call 6 hit with units = 1.

## Findings

### PR1 — Critical — D3 / D5 / D13 / I6: a pre-release v8 attempt can no longer be abandoned
- **The contradiction.**
  - D3 says the "seal-block builder" raises for a legacy started attempt.
  - D13 makes `seal_terminal_uncertain` build its blocks through the same `_seal_blocks_locked`.
  - Abandon is `seal_terminal_uncertain` (`delivery_termination.py:218-223`), and I6 promises abandon keeps working.
- **A second break, even if the raise is moved.** D5 adds `predecessor_charged` to `_lineage_usage` (`execution_ledger.py:407-421`), and the `_validate_lineage_usage` exact set (`execution_contracts.py:512`) grows. Computing it calls `attempt_token_charges` with each predecessor's `unobserved_send_tokens`. Legacy envelopes don't have that key, so abandoning a legacy attempt that has predecessors raises `KeyError` [I].
- **Smaller gap.** The no-predecessor default returned at `execution_contracts.py:511` also lacks `predecessor_charged`, and D13's `validate_receipt` recomputation reads it [O].
- **Why Critical.** Prepare, the gate, recover and seal all refuse legacy attempts by design, so abandon is their only way to become terminal.
- **Amendment.**
  1. `_seal_blocks_locked` never raises. For `not handback_supported` it returns `token_usage=None` and the legacy two-key `lineage_usage`.
  2. The "refuse to advance" raise lives only in `_v8_action_checks`, `_v8_manager_checks`, the gateway `_seal_attempt`, and `finish_attempt`.
  3. `_validate_lineage_usage` picks its key set by `handback_supported`, and its default return includes `predecessor_charged: 0`.
  4. Add a C3 test: abandon a legacy started attempt, both with and without a legacy predecessor. The attempt row is inserted directly, because `create_attempt` now refuses it.

### PR2 — Important — D16 V15(c) and the AC16 "grant_changed deleted" tamper: V15 would not fail
- **The problem.** The fold as written maps consume → (sent, g) and checks only the end state and "at least one event".
- **Why the tamper passes V15.** Deleting a paid row's `op=issue` event leaves `[consume]`. That folds to (sent, g), which matches the ledger row, so V15 passes. The declared set {V15, V17} is then wrong, and the test either fails or gets weakened [I].
- **Amendment.** The fold validates each transition:
  - `issue`: only from none, `not_dispatched` or `denied`;
  - `rotate`, `consume`, `expire`, `release`: only from (allowed, g), with `grant_id` equal to g;
  - `deny`: from none (decide) or allowed (reissue).

  An illegal transition fails V15 with the row id and the offending op. Add mutation M9: drop the transition check, and the tamper case must fail.

### PR3 — Important — D16 V15(e): automatic grants would open escalation windows that never close
- **The problem.** Every automatic tranche writes `expansion_requested` then `expansion_granted` (`execution_ledger.py:497-506`), and never `expansion_decided` or `expansion_cancelled`.
- **Consequence.** If a window opens on any `expansion_requested`, the fixture's automatic tranche opens one that never closes. The later sends (calls 6+) then fail V15 on the clean fixture, and AC15 fails.
- **Amendment.** A window exists only for a request whose `expansion_requested` has no `expansion_granted` with the same `request_id`, or equivalently whose `expansion_requests` row wasn't granted by `charter_headroom`. It spans from `expansion_requested.seq` to the matching `expansion_decided` or `expansion_cancelled` seq. A window still open at seal is itself a V15 fail.

### PR4 — Important — I4 deviates from R9/F3 and AC9 without being flagged
- **What the definition says.**
  - R9: "Extra keys are ignored. A missing or unrecognised shape is never an error at record time."
  - AC9: a completed paid row with an unrecognised shape "completes and is not marked unknown".
- **What the code does.** Three record-time validators reject *any* non-integer usage value, including unknown extra keys:
  - `codex_worker._parse_result`, `codex_worker.py:58-63`;
  - `validate_result`, `execution_contracts.py:846-849`;
  - `observe_manager_response`, `execution_ledger.py:1485`.
- **Consequence.** A future Codex usage key holding a nested object makes the call `unknown`, which blocks the attempt for reconciliation. I4 declares this unchanged, but only I2 is flagged for Andy.
- **Amendment (either).**
  - (a) Relax the three validators to check only the known keys, with type and ≥ 0 rules, and ignore extras. Add AC9 cases for a Codex usage with a nested extra key and a manager usage with a string extra key.
  - (b) Flag I4 to Andy as an amendment to R9 and AC9.

  Option (a) matches the approved text.

### PR5 — Important — D9 request-file crash windows: durability and orphan temp files
- **Durability.** `os.link` is never followed by an fsync of `manager-requests/`. `consume_manager_grant` then commits durably to SQLite. A crash can lose the directory entry while the consume survives, so V10 later fails a clean sent call [I].
- **Orphans.** A SIGKILL between creating `.{call_id}.{uuid}.tmp` and the `finally` unlink leaves a temp file behind. D16 V10 says "orphan files fail", so a crashed-but-clean lineage fails V10.
- **Amendment.**
  1. fsync the directory fd after `os.link`, and on the reuse path, before returning to `on_manager`.
  2. V10 ignores `.*.tmp` names for pass/fail, and lists them under `informational`. Only `<hex call_id>.json` files take part in the orphan rule.
  3. Add an AC2 case: kill after the temp file is created; V10 must still pass.

### PR6 — Important — D11 `previous_checkpoint_id` leaks into v5–v7 receipts
- **The problem.** `_snapshot_locked`'s `magentic_checkpoints` feeds receipts for every Magentic protocol:
  - `delivery_gateway.py:1312`;
  - `delivery_termination.py:96`;
  - v5 continuation receipts through the same `_build_receipt`.
- **Consequence.** Adding the key for every row changes v5–v7 receipt shape and snapshots. That contradicts the handoff rule "Protocols 5–7 keep their … receipts … unchanged" and §5's "v5 and v7 tests should be unaffected" [O/I].
- **Amendment.** Project the column only for protocol-8 attempts in `_snapshot_locked` (and in `bind_magentic_checkpoint`'s return), or explicitly accept and list the v5–v7 shape change. The first matches I5's v8-only rule.

### PR7 — Important — D16 V7 duplicates the gateway's limits projection
- **The problem.** V7 recomputes "`charter.limits` projected as at `delivery_gateway.py:470-484`", but verify must not import the gateway. That means a second copy of the projection, which breaks the handoff's "one pure function per concept". The copy drifts silently when the envelope shape changes (C3 changes it).
- **Amendment.** Factor `project_envelope_limits(canonical_limits) -> (limits, expansion_headroom)` into `delivery_contracts.py` in C3. The gateway `prepare` and V7 both call it, and `receipt_verify` imports the same object (an identity assertion, as in AC20).
- **Also, for V7's claim walk.** `supersedes` is a digest, not a file name (`delivery_control.py:335-338`). Index every `lead-claim*.json` in `delivery/<charter digest>/` by its recomputed digest, then walk `supersedes`, rather than assuming a `g{n}` naming sequence.

### PR8 — Important — D7 AC3 `ast` enumeration can silently under-count
- **The problem.** The matcher only sees `.execute` calls whose first argument is a `Constant`, `JoinedStr` or `BinOp`, with an anchored upper-case regex, and it records a *set* of (function, SQL) pairs. It would miss:
  - SQL held in a variable (`q = "UPDATE …"; db.execute(q)`);
  - `executemany` and `executescript`;
  - lower-case SQL, `INSERT OR REPLACE`, `REPLACE INTO` and `DELETE FROM`;
  - two identical statements in one function, which collapse into one entry.

  A future unclassified write would pass the test.
- **Amendment.**
  1. Walk every `execute`, `executemany` and `executescript` call in `execution_ledger.py`.
  2. Any first argument that isn't statically resolvable fails the test unless it is in a small named allowlist; today that is the schema `executescript` at `:74`.
  3. Match case-insensitively on `(UPDATE|INSERT( OR \w+)? INTO|REPLACE INTO|DELETE FROM)\s+(actions|manager_calls)\b`, anywhere in the string.
  4. Compare a multiset (`Counter`) of (function, normalised SQL) against `SITES`.

### PR9 — Suggestion — D7 SITES table: the :1958 exemption reason is wrong
- **What the plan says.** `:1958` (`_append_resolution_locked`, resolved_completed) is "v8-unreachable (from `allowed` only through v5 `resolve_unknown`)".
- **What the code does.** It is reachable in v8 through `resolve_observed_v8` → `_append_resolution_locked` (`execution_ledger.py:1946-1947`), from `started` or `unknown` only (`:1922`).
- **Amendment.** Reclassify it as "exempt, not a grant change (from started/unknown only)", alongside `complete`. Keep `:1960` as v8-unreachable. Note in the ADR or results that R3's listed `resolved_not_dispatched` path emits nothing under I5, because v8 can't reach it.

### PR10 — Suggestion — The D2 absolute ceiling and I3 need Andy's explicit confirmation too
- **D2.** The tokens-only absolute ceiling (`M + (eff + outstanding + 1)·T ≤ MAX_LINEAGE_TOKENS`, applied to engineer grants) is new behaviour that R8 doesn't state. The plan says "please confirm" but doesn't list it with I2.
- **I3.** I3 merges the success criterion's separate "D5-style recovery" into the escalation recovery.
- **Also.** Because `_granted_units(consumed_only=False)` counts lapsed `approve` grants (`execution_ledger.py:433-434`), `_outstanding_units` treats a lapsed predecessor engineer tranche as outstanding forever. That makes the new ceiling tighter than intended (conservative, not unsafe).
- **Amendment.** Flag I3 and the D2 ceiling alongside I2 at plan approval. Document the lapsed-grant behaviour in ADR 0020, or exclude `status='lapsed'` from the tokens outstanding count.

### PR11 — Suggestion — AC22 fixture-change list
- **What AC22 allows.** Fixture edits limited to adding "token fields, the actor argument".
- **What the plan also changes:**
  - manager-stub identity (D8), across about six test files;
  - `SealedExpansionEvidenceTests` switching to full-row receipts (`test_expansion_receipts.py:132-135`);
  - `test_chartered_delivery_recovery.py:565` re-targeting its patch from `lineage_usage` to `seal_view`;
  - the `lineage_usage` shape in `:541,573,578`;
  - the harness `register_group(row_id=…)`.
- **Amendment.** Record these in `validation-results.md` as named AC22 deviations with reasons, per category, rather than implying AC22 is met verbatim.

### PR12 — Suggestion — AC19 vs R14 on V13
- **The conflict.**
  - AC19: "V11–V13 are `not_applicable` … where no edit ran."
  - R14: V13 is P for cancelled and abandoned.
  - `baseline.json` is always written at prepare (`delivery_gateway.py:487`), and `build_terminal_receipt` carries it (`delivery_termination.py:65-75`). So V13 will be *present* and `pass` on those fixtures.
- **Amendment.** In `validation-plan.md`, state that V13 passes on cancelled and abandoned attempts per R14, and that only V11 and V12 are `not_applicable`. Record why.

### PR13 — Suggestion — Trace/verify locks and subprocess use vs the handoff and AC18
- **Trace.** The banner uses `control_view` → `probe_recovery_lock`, which briefly takes `flock(LOCK_EX|LOCK_NB)` (`execution_ledger.py:326-329`), and `parent_live` → `machine_id()`, which runs `subprocess.run(["ioreg", …])` on macOS (`process_identity.py:121-125`).
- **The rules.** The handoff says trace and verify "take no lock", and the validation plan patches `Popen` to raise.
- **Amendment.**
  - Verify uses `process_identity.records()` only (it is subprocess-free), never `control_view` or `parent_live`.
  - The subprocess and socket patch applies to verify, per AC18.
  - The handoff wording for trace becomes "creates no lock file; a non-blocking liveness probe is allowed".

### PR14 — Suggestion — D12 and D10 gaps
- **D12.** `execution_ledger.py:2453` also builds a `flow run recover-delivery-lead` next-command (v5) without `--actor`. Update it.
- **D10.** `partial(on_process_group, row_id=…)` must guard `on_process_group is None`. Adapters get `register=None` outside a v8 scope (`delivery_gateway.py:1433-1439`).

### PR15 — Suggestion — D9 placement and V10 requiredness detail
- **Placement.** Place `write_request_file` after `assert_owner` and *before* `stop_if_cancelled()` (`delivery_gateway.py:1500-1501`). Then a cancelled attempt's allowed-but-unsent call still has its file.
- **V10 rule.** State it precisely: every call with an `op=issue` or `rotate` event that reached the send section needs its file. An `issue` with no `consume` and no file is `fail` for completed/failed and `not_applicable` for cancelled/abandoned (P).

### PR16 — Suggestion — Commit sequencing details
- **C1:** `manager_reply()` needs a home in C1, for example `tests/manager_stub.py`. The plan puts it in the "new shared fixture module", which otherwise lands in C4/C6.
- **C3 vs C5:** `predecessor_charged` is assigned to both C3 (D5) and C5. Pick C3, so the validator and seal key sets move together.
- **C3:** I6 read-compat tests need legacy v8 rows inserted by direct SQL, because `create_attempt` now refuses them. Name that helper.
- **C2:** `lineage_view`'s "blocks when supported" predates `handback_supported` (C3). In C2 it should always return the pre-C3 blocks.

### PR17 — Suggestion — Mutation coverage
M1–M8 miss the new safety-critical branches. Add:
- M9: the V15 transition check (PR2);
- M10: drop the token check from `_v8_manager_checks` (AC10, manager path);
- M11: the I2 zero-headroom hard rule (AC10/AC12b);
- M12: V17 counts rows sent *after* the issue seq (the clean fixture must then fail);
- M13: remove the legacy refusal in `_v8_action_checks`.

### PR18 — Suggestion — Validation-plan gaps
- **AC1:** add a Codex manager `thread_id` case (the fixture's manager is Claude).
- **AC7:** enumerate the `unsupported_protocol` and `unsupported_contract` output, the missing-work-id exit, and how banner goldens normalise seq and time.
- **AC12c:** state how "the receipt's overshoot" is asserted at ledger level, for example `seal_view(...)["blocks"]["token_usage"]["overshoot"]`, since no gateway receipt exists.
- **Tamper hole:** a ledger `envelope_json` edited to the legacy key set yields exit 2 `unsupported_receipt` rather than a fail. Consider reporting `fail` when `envelope.json` on disk is handback-shaped but the ledger's isn't.
- **Codex cache writes:** say where `cache_write_input_tokens` is "reported" (trace raw only), since R11's block has no field for it.

## Verdict

**Approve after amendments.**
- **PR1** (legacy abandon) and **PR2, PR3** (V15 fold and window) must be fixed in the plan before C1 starts. As written they would, respectively, dead-end pre-release attempts and make AC15 and AC16 unattainable.
- **PR4** needs either the validator relaxation or Andy's explicit sign-off.
- **PR5–PR8** should be folded into D9, D11, D16 and D7.
- The rest can be handled during implementation and recorded in `validation-results.md`.
