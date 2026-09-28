# Adversarial Architecture Review: step5-operational-handback (revision 1)

- **Reviewer:** `adversarial-architecture` (architect subagent, read-only). The coordinator saved this from the subagent's hand-back; the findings are unchanged.
- **Advisory expertise:** `no_match` (request `341fa582-a0fb-43c6-bbf7-3f96175cdbb9`).
- **Scope:** `requirements.md` (R1–R17, P1–P9) and `acceptance-criteria.md` (AC1–AC23), checked against `intake.md`, `research/current-state.md` and the current code.
- **Tags:** **[O]** read in the cited code; **[I]** inferred, not run.
- **Not checked:** the reviewer had no shell, so it could not read `receipt_check.py` (see F20).

## F1. Tranche expansion does not fit the one-unit machinery as written
**Severity:** Critical. **Hits:** P3, R8, R10, AC12, AC8.

**Evidence**
- Expansion adds grant units directly to a limit's value [O]:
  - `_effective_limits` returns `value + granted_units` (`cli/execution_ledger.py:443-449`);
  - `_granted_units` sums `amount`, which is always 1 (`:428-438`, `:504`);
  - `_validate_expansion` adds 1 per consumed grant (`cli/execution_contracts.py:490-491`).
- **So a tranche raises the cap by 1 token.** If `tokens` is an `EXPANSION_LIMIT_KEYS` entry whose base is `max_lineage_tokens`, a granted tranche raises the effective cap by one token, not by `token_tranche`.
- Every ceiling check assumes the limit's own unit and a step of +1 [O]:
  - `_expand_locked` (`:491`);
  - the `_v8_action_checks` hard predicate (`:559`);
  - `decide_manager_call` (`:1447`);
  - `validate_expansion_headroom` (`cli/delivery_contracts.py:117`) and `_validate_expansion_headroom` (`cli/execution_contracts.py:375-377`).
- **R8's bound can't be expressed** through these generic checks.
- **A multi-tranche shortfall is a hard refusal.** A limit expands only when `units == 1` (`:558-559`; `call_units in {0,1}` at `:1446`) [O]. One call that overshoots by more than one tranche makes the check a hard refusal, which contradicts E2's "escalates".
- **The automatic path doesn't re-check after granting.** `decide` sets `expansion_granted` right after `_expand_locked` (`:1257-1258`) [O]. One tranche has to clear the cap, or the automatic path allows a send the engineer path would refuse (`regrant_expanded_action`, `:1119-1121`).

**Recommended change**
- **Count tranches in the expansion machinery.** `tokens` becomes an expandable counter, sealed at a base of 0 tranches, with ceiling `MAX_TOKEN_TRANCHES`. Only the token predicate computes `max_lineage_tokens + effective["tokens"] × token_tranche`.
- **Bound the absolute total separately.** A separate charter check bounds the absolute total by `MAX_LINEAGE_TOKENS`.
- **Define units precisely.** `units = floor((charged − effective)/token_tranche) + 1`. When units > 1, refuse hard with `token_cap`, and document it.
- **Add a charter rule:** `token_tranche ≥ unobserved_send_tokens`.
- **Name every touch point:**
  - `LINEAGE_SCOPED_LIMITS` (`:48`);
  - `_expansion_receipt.predecessor_lineage_grants` (`:622`);
  - the hard-coded lineage key set (`execution_contracts.py:430`).
- **Add an AC** for an overshoot larger than one tranche, on both the automatic and the engineer paths.

## F2. `token_usage` cannot be recomputed purely if R9 charges from `response_observations`
**Severity:** Critical. **Hits:** R9, R11, AC14, open question 3.

**Evidence**
- The receipt doesn't carry `response_observations` (`cli/delivery_gateway.py:1307-1321`; `execution_ledger.py:2695`) [O]. So the R9 ledger sum and R11's pure recomputation diverge for `started` or `unknown` rows that have an observation.
- **At gate time, `started` never matters.** `decide` and `decide_manager_call` return `reconciliation_required` while any row is `started` or `unknown` (`:1233-1235`, `:1406-1407`) [O].
- **The resolution source is redundant.** A `resolved_completed` resolution already rewrites the row (`:1958`) [O].

**Recommended change.** Charge by row status only:

| Row | Charge |
|---|---|
| `completed` or `failed`, with usage that is recognised | its observed usage |
| any sent row (`started`, `unknown`, or `completed`/`failed` without recognised usage) | `unobserved_send_tokens` |
| `allowed`, `denied`, `not_dispatched` | 0 |

- "Sent" means the same set `_lineage_usage` uses (`execution_ledger.py:419`, `execution_contracts.py:520`).
- The per-row function goes in the pure contracts module, and the ledger sum wraps it.

## F3. Refusing an unrecognised usage shape at record time turns paid calls into abandon-only unknowns
**Severity:** Important. **Hits:** R9, AC9.

**Evidence**
- **An observe error becomes unknown.** Any exception during observe becomes `mark_manager_unknown` (`delivery_gateway.py:1515-1519`) or `mark_unknown` (`:1646-1648`) [O].
- **That unknown can only be abandoned.** An unknown manager call is `UNRESOLVABLE_ABANDON_ONLY` (`execution_ledger.py:1897-1900`) [O].
- **The shapes aren't stable.** Codex usage is any integer keys (`codex_worker.py:57-63`), and Claude usage may be `None` (`claude_worker.py:65`) [O].

**Recommended change**
- Never refuse at record time. Normalise tolerantly.
- Charge an unrecognised shape `unobserved_send_tokens`, and report it as `token_usage.unrecognised_usage` and in trace.

## F4. V7 checks the lead claim against `run.json`, which is mutable and moves on
**Severity:** Important. **Hits:** V7, AC15, AC16.

**Evidence**
- `run.json` delivery fields are rewritten on every lead change (`cli/delivery_control.py:338-347`) [O].
- The claim files `lead-claim-g{n}-{status}.json` are immutable and carry `supersedes` (`:329-340`) [O].

**Recommended change.** Check V7 against the sealed files, never against `run.json`:
- the envelope claim equals a claim file whose digest recomputes;
- the `supersedes` chain from the current claim back to that file is unbroken;
- the shaper, charter and handoff files recompute their own digests, as `_sealed_delivery_authority` does (`delivery_gateway.py:115-133`).

## F5. The overshoot bound depends on serial dispatch the ledger does not enforce
**Severity:** Important. **Hits:** R12, E2, Assumptions.

**Evidence**
- **Only unresolved rows block.** `_unresolved_action` blocks only while a row is `started` or `unknown` (`:1176-1185`) [O].
- **Allowed grants don't block.** `concurrency_cap` allows `max_concurrent` rows in `allowed`, `started` or `unknown` (`:528`, `:552`) [O].
- **The manager ignores outstanding action grants.** `decide_manager_call` doesn't count them [O].
- **Consume doesn't re-check.** Neither consume path checks any limit (`:1518-1533`, `:1460-1476`) [O].
- **So the worst case is several calls.** Up to `max_concurrent` action grants plus one manager grant can be outstanding when the cap is crossed.

**Recommended change**
- In v8, refuse a paid grant while any other paid row of the attempt is `allowed`. Use the hard reason `paid_grant_outstanding`, which is never expandable.
- Then state R12 as: the overshoot is at most the charged usage of the single paid call granted last before the cap was reached.

## F6. "Follows ADR 0017 exactly" is false on the regrant and reissue paths
**Severity:** Important. **Hits:** R10, AC10.

**Evidence**
- **`regrant_recovered_action`** denies on any limit, and never expands (`:1065-1069`) [O].
- **`regrant_expanded_action`** raises "still denied" and rolls back (`:1119-1121`) [O].
- **Only one expansion request per row.** Each row allows one request: `request_id = hash(attempt, kind, row_id)` (`:485`) [O].
- **`reissue_recovered_manager_grant`** rotates an `allowed` row, so a naive cap check would count the row itself (`:1427-1431`). It needs `call_id<>?`, as in `:1144`. The gateway also assumes this path always succeeds (`delivery_gateway.py:1476-1478`) [O].

**Recommended change**
- Per path:
  - **`decide` / `decide_manager_call`:** ADR 0017 expansion;
  - **regrant and reissue:** a hard `token_cap` denial;
  - **a manager hard `token_cap`:** fails the attempt (`delivery_gateway.py:1497-1498`).
- Exclude the reissued row from its own cap count.
- Add an AC for a failed reissue.
- **Suggestion:** fold the manager checks into one `_v8_manager_checks`.

## F7. Detecting pre-release receipts must not depend on the receipt's own contents
**Severity:** Important. **Hits:** P9, R13, AC17.

**Evidence**
- If `unsupported_receipt` is inferred from a missing `token_usage`, then deleting that block downgrades a tamper to "can't run".
- The receipt `schema_version` is fixed at 1 (`delivery_gateway.py:1307`) [O].

**Recommended change**
- Decide supported or unsupported from the ledger: the sealed envelope's contract version.
- For a supported attempt, a missing block is `fail`.
- Add this case to AC17.

## F8. V9's "the chain is unbroken" is not well defined for MAF checkpoints
**Severity:** Important. **Hits:** R5, V9, AC5.

**Evidence**
- **MAF checkpoints every superstep.** Each checkpoint is parented to the previous one (`agent_framework/_workflows/_runner.py:256-270`) [O].
- **Restore forks the chain.** A restore resets the parent (`:500`) [O].
- **Only pending-worker checkpoints are bound.** Flow binds only those (`delivery_gateway.py:1563,1578,1595`), so a bound checkpoint's parent is usually an unbound file [O].

**Recommended change**
- Record `previous_checkpoint_id` at bind time and show it in trace.
- V9 checks only bound links: file sha, size, id, workflow, pending key and the recorded parent, against a file in either location.
- Drop "the chain is unbroken" as a pass/fail criterion. The ancestry walk is informational at most.

## F9. V15 has a tautology, uses timestamps where it should use seq, and leaves "sent" undefined
**Severity:** Important. **Hits:** V15, R15, AC16.

**Evidence and recommended changes**
- **"seq increasing" is vacuous.** The snapshot orders events by seq (`:2667`) [O]. Replace it with:
  - each checkpoint link's `ledger_seq` precedes its bound event;
  - interruption seqs fall within the attempt's range.
- **Use seq, not timestamps, for escalation windows.** Define each window from `expansion_requested` to the decision or cancellation event.
- **Define the send-start event per row kind:**
  - manager: `manager_send_started`;
  - producer: `worker_dispatched`;
  - verifier: `verifier_send_claimed`.

  A producer row can legitimately have `worker_dispatched` without `adapter_send_started`, after a crash between consume and observe (`delivery_gateway.py:1598-1626`) [O].
- **The grant-history end state has two special cases:**
  - release, where `grant_id` becomes NULL;
  - `grant_expired`, where the row is `denied` and `grant_id` is kept (`:1528`, `:1471`) [O].

## F10. AC16's "one tamper, one failure" is not achievable as worded
**Severity:** Important. **Hits:** AC16, success criteria.

**Evidence.** Failures overlap by design [I]:
- a receipt edit fails V1 plus the matching block check;
- a usage edit fails V3 and V4;
- a predecessor edit fails V6 and the successor's V4;
- a charter edit may fail V7 and V8.

**Recommended change**
- Each tamper case declares its exact expected set of failing checks, and the test asserts that set exactly.
- Tampering with a file other than the receipt expects exactly one failing check.
- Add a byte-only receipt tamper that fails V1 alone.

## F11. R2 request files: write order, partial writes and determinism
**Severity:** Important. **Hits:** R2, V10, AC2.

**Evidence**
- **The consume step.** Consume is `consume_manager_grant` under `send_lock` (`delivery_gateway.py:1499-1503`) [O].
- **No resend after consume.** A consumed manager call is never resent: an unknown is abandon-only, and reissue refuses once `manager_send_started` exists (`:1165`) [O].
- **The only reuse is a never-sent grant.** Its `call_id` is deterministic from `prompt_digest`.
- **An in-place O_EXCL write can wedge.** A crash mid-write leaves a truncated file, so every replay would refuse [I].
- **Writing after consume can lose the file.** A crash between consume and write leaves a sent row with no file [I].

**Recommended change**
- **Where:** write only for `allowed` calls, inside `send_lock`, after `assert_owner`, and before `consume_manager_grant`.
- **How:** write a temp file, then `os.link` it into place, so no file is ever overwritten.
- **What:** the canonical `{call_id, prompt_digest, messages}` only, with no timestamps.
- **Bind the Claude identity.** Factor the prompt rendering (`delivery_gateway.py:1770-1780`) into a pure function. V10 then also checks `sha256(render(messages)) == result.input_sha256` for Claude (`claude_worker.py:136-141,215`) [O].
- **Scope of V10:**
  - it accepts files for calls that were allowed but not sent;
  - it flags any file that matches no row.

## F12. R3 grant events: AC3 misses paths, and rewriting event details breaks existing tests
**Severity:** Important. **Hits:** R3, AC3, AC22.

**Evidence**
- **AC3 misses these paths** [O]:
  - the release in `close_pre_send_failure` (`:1600`);
  - expiry (`:1528`, `:1471`);
  - the superseded release (`:729`);
  - the terminal-seal release (`:781`);
  - the recovery release (`:1010`);
  - verifier consumption (`:1567-1569`);
  - `resolved_not_dispatched` (`:1960`).
- **Existing tests match exact event details.** Examples are `tests/test_chartered_delivery_recovery.py:710,930` and `tests/test_expansion_recovery.py:77-79` [O].

**Recommended change**
- Add a new `grant_changed` event with the canonical detail `{grant_id, row_id, kind, owner_generation, reason, op}`, written in the same transaction as the change. Leave the existing events untouched.
- Make AC3 structural: enumerate every `grant_id` write and every transition away from `allowed`.

## F13. R16's full-row seal is feasible, but the snapshot timing must be pinned
**Severity:** Important. **Hits:** R16, P6, AC20.

**Evidence**
- **The snapshot is taken early.** The receipt rows come from a snapshot taken at `delivery_gateway.py:1692`. That is before `record_runtime_outcome` (`:1716`), before `close_expansions` (`:1751`), and outside `send_lock` [O].
- **`finish_attempt` reads early and compares little.** It reads the receipt before `BEGIN IMMEDIATE` and compares three blocks (`execution_ledger.py:2263-2288`) [O].

**Recommended change**
- The gateway re-snapshots under the sealing `send_lock` hold, after `close_expansions`.
- `finish_attempt` compares against `_snapshot_locked` inside its transaction.
- The comparison checks each row's exact key set.
- The function is pure and shared by both seals and V3.

## F14. `not_applicable` needs a requiredness table per terminal status
**Severity:** Important. **Hits:** R13, V11–V13, AC17, AC19.

**Evidence**
- An unrestricted `not_applicable` is itself a vacuous-pass escape.
- The evidence a receipt carries differs by status (`delivery_gateway.py:1305,1314-1317`) [O].

**Recommended change**
- Add a status × check table whose cells are `required`, `if-present` or `n/a`. A required check with missing input is `fail`.
- Pin V11 to the final verifier input only, by recomputing `_verifier_provider_task(...)`. Earlier inputs legitimately bind older diffs (`delivery_gateway.py:1583-1586`) [O].

## F15. Add a check that replays the token gate
**Severity:** Suggestion. **Hits:** R11, R14.

- `validate_receipt` can't replay the gate, but verify-receipt has `events`.
- **Add V17.** Walk the lineage events in seq order. At each paid grant, require charged < effective, both recomputed from the rows before it.

## F16. V10's 0600 check is brittle outside the original host
**Severity:** Suggestion. **Hits:** V10, AC2.

- Git doesn't preserve 0600, and live runs are reviewed from branch checkouts [I].
- Report the file mode as a separate item, outside the exit code.

## F17. V16 is weak
**Severity:** Suggestion. **Hits:** R4, V16, AC4.

- Group lines aren't digest-bound, so a swapped id still passes [I].
- Add the reverse check: every sent Claude or Codex row has a group line in its generation's control file. It is `not_applicable` for injected adapters and for Ollama.
- State that V16 is a consistency check only.

## F18. Where `predecessor_charged` lives, and superseded predecessors
**Severity:** Suggestion. **Hits:** R11, V6, AC13.

**Evidence**
- `lineage_usage` is absent when there are no predecessors, and its keys are exact (`execution_ledger.py:571`; `execution_contracts.py:508-512`) [O].
- A superseded predecessor has `receipt_sha256 = None` (`:397`) [O].

**Recommended change**
- `predecessor_charged` lives in `lineage_usage`, and `token_usage` references it.
- For a superseded predecessor, V6 reports `not_applicable`, and its charge is checked from the ledger only.
- Cross-check sealed predecessor receipts' charges against the successor's `predecessor_charged`.

## F19. P1's unit still needs checking against real usage fixtures
**Severity:** Suggestion. **Hits:** P1, AC9.

**Evidence** [I]:
- whether Codex `reasoning_output_tokens` is separate from or inside `output_tokens` is unknown;
- whether a multi-turn Claude editor's usage covers the whole session or only the last turn is unknown.

**Recommended change**
- Make both blocking planning items, each backed by a captured fixture.
- ADR 0020 states that `charged_v1` is not a cost proxy.

## F20. AC23 depends on a file that no review has read
**Severity:** Important (process). **Hits:** success criteria, AC23.

- **Before approval,** read the script from its branch.
- **Reconcile its checks** with V1–V17 in `research/`.

## F21. Scope, commit order and smaller points
**Severity:** Suggestion. **Hits:** E1.

**Commit order**
1. The actor, identity, group ids, grant events and request files.
2. Trace.
3. The token contract and the charge function.
4. The gate.
5. The receipt block and the shared seal comparison.
6. verify-receipt.
7. Docs.

**Candidate cuts:**
- V9's chain walk;
- V16;
- trace's per-lineage totals.

**Smaller points:**
- **verify-receipt reads:** read the ledger in one read transaction, and take no locks.
- **trace scope:** state that trace is v8-only.
- **R6:** list every caller of `recover_delivery`.

## Verdict

**Needs revision.** F1 and F2 are design errors. F4–F14 are specification gaps, each with a concrete fix. F20 must be closed before AC23 can be judged. Once they are dispositioned, and P3, P9 and R12 are amended, the definition should be ready for approval.
