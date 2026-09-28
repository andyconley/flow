# Validation Results: step5-operational-handback

**Validated against:** the change itself.
- Every check ran against the real gateway, ledger and CLI code on this branch.
- Providers are stubs (hermetic).
- One lineage runs through the pinned stock Magentic runner (`agent-framework` 1.19.0 / 1.2.0) with `FLOW_MAF_PYTHON`.
- No paid or live calls were made.

## Full suite

`FLOW_MAF_PYTHON=~/.flow/venvs/maf/bin/python python3.12 -m unittest discover -s tests`, run after every commit:

| Point | Result |
|---|---|
| baseline (main at `715e2df`) | 1,643 OK, 0 skipped |
| C1 `a51f4f1` | 1,671, with 1 failure (the module roster) fixed before the commit |
| C2 `d629b59` | 1,679 OK, 0 skipped |
| C3 `f246839` | 1,699 OK, 0 skipped |
| C4 `e8d8af4` | 1,717 OK, 0 skipped |
| C5 `7ca8506` | 1,726 OK, 0 skipped |
| C6 `9e1d123` | 1,757 OK, 0 skipped |
| C7 `d1bcc5f` | docs only |
| review refinement | 1769 OK, 0 skipped |
| RS1 conservative charge | 1769 OK, 0 skipped |

`python3.12 scripts/regenerate-flow-help.py --check`: both files up to date.

## Acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | pass | `test_manager_requests`: `ManagerIdentityContractTests`, and `GatewayCorrelationTests` (identity on completed rows; a reply without identity stays `unknown`; the receipt validator rejects a row missing `session_id`). Codex `thread_id` is covered at the contract level only; the fixture manager is Claude. |
| AC2 | pass | `RequestFileTests`: canonical bytes, 0600/0700, reuse, conflict, a mid-write fault, a kill after the temporary file, FIFO, traversal, a world-readable directory. `GatewayCorrelationTests.test_the_file_is_durable_before_the_grant_is_consumed` (M7). The Claude `input_sha256` is the rendered prompt. |
| AC3 | pass | `test_grant_history`: an `ast` enumeration against `SITES` (a multiset, case-insensitive, non-static SQL allowlisted); every op site emits its op; the op scenarios; the history replay in the boundary-b recovery test. v5–v7 streams carry no `grant_changed`. |
| AC4 | pass | `ProcessGroupRowTests`: real child groups. The default adapters bind the row id, with a guard for `None`. |
| AC5 | pass | `CheckpointParentTests`; the quarantine recovery test asserts the parent after quarantine (TR1). |
| AC6 | pass | `RecoveryActorCliTests`: argparse refuses before any change; the actor is passed through; the default is gone (recursive search). `test_expansion_recovery` asserts the recorded actor. |
| AC7 | pass | `test_delivery_trace`: rows in seq order with every R7 field; durations; totals; the paused `token_cap` banner golden with absolute tokens; the terminal banner; the pinned JSON schema; read-only digests; `unsupported_protocol`; a pre-release `unsupported_contract`; a missing work id exits 2. |
| AC8 | pass | `test_token_contract.TokenContractTests`: each refusal, the exact projection, `DEFAULT_TOKEN_BUDGET` pinned to P10, a shared-projection identity assertion. `PreReleaseAttemptTests`: `create_attempt` and prepare refuse. |
| AC9 | pass | `test_token_charge`: the full charge table on the captured S1–S3 values; the 133,898 lineage golden; tolerance of a nested Codex key and a string manager key through the real parsers. |
| AC10 (amended) | pass | `test_token_gate.InitialGrantTests` (zero headroom pauses, for actions and managers; the verifier and an unpaid manager are granted); `RegrantAndReissueTests` (hard denials; `reissue_recovered_manager_grant` excludes its own row and enforces the round cap); `test_a_recovered_manager_reissue_denied_by_the_token_cap_fails_the_attempt` (gateway: never sent, the attempt fails, `op=deny`). |
| AC11 | pass | `JustUnderTests`: the reported overshoot. |
| AC12 | pass | `TrancheTests` (automatic tranche, cap raised by exactly T); `TokenEscalationRecoveryTests` (the pause, no send inside the pause window by seq, answer mode, the call sent once). |
| AC12b | pass | `MoreThanOneTrancheTests`: a hard refusal with headroom, without headroom, and past the absolute ceiling; no request is created. |
| AC12c | pass | `ConcurrentOvershootTests`: two outstanding grants; the overshoot is at most both calls, asserted exactly. |
| AC13 | pass | `LineageChargeTests`, `LineageGateTests`: an abandoned predecessor's unknown send is charged U. |
| AC14 | pass | `GatewayTokenBlockTests`: a field-by-field edit loop, and a missing block. `LedgerSealTests`: an edited block is refused. |
| AC15 | pass | `CleanPassTests` on the fixture lineage: all 17 checks pass with `compared ≥ 1`; the six unverifiable items; `--no-lineage`; the lineage shape (automatic tranche on manager call 4, replayed without a resend; engineer tranche on call 6; answer mode). `StockRunnerVerifyTests`: a stock-runner lineage verifies (real MAF checkpoint files under V9). |
| AC16 | pass | `TamperTests`: 17 cases, each asserting its exact failing set, the unchanged clean status of every other check, and a non-empty diagnosis. See the deviations below. |
| AC17 | pass | `NoVacuousPassTests`: no action rows; missing `repair.diff` and checkpoints; a missing `token_usage` fails rather than reading as unsupported; unsealed; pre-release; a ledger envelope edited to the legacy key set under a supported file fails V2; the generic compared-nothing rule (M6); malformed sources. `ReviewRefinementTests`: a truncated or deleted receipt fails V1. |
| AC18 | pass | `ReadOnlyOfflineTests`: the whole tree's digests are unchanged; one `_db` call; subprocess, socket and urlopen patched to raise; CLI exit codes 0, 1 and 2. |
| AC19 | pass | `AbandonedAndCancelledTests`; `CancelledTests`; `NonCompletedEditTests` (a failed attempt edited before any verifier; a cancelled attempt after its edit, QR1). |
| AC20 | pass | `LedgerSealTests` (both seals refuse content, key and row differences); the snapshot is taken under `send_lock` (a live flock probe); a single-function identity assertion across the ledger, compare and verify. |
| AC21 | pass | ADR 0020 covers every R17 item (including R12 and the P10 derivation, and adds the request-file sensitivity); the design doc's step 5 and proof status; the CLI reference (trace with the `jq` note, verify-receipt, token expansion, `recover-delivery-lead --actor`, `DEFAULT_TOKEN_BUDGET`); help regenerated. |
| AC22 | pass with named deviations | The full suite with 0 skipped; fixture changes listed below. |
| AC23 | pass | The mapping below, shown by real output in `evidence/`. |

### AC16 expected-set deviations (allowed by AC16; reasons recorded)

- **Charter file tamper: {V6, V7}, not {V7}.** The Delivery Charter is sealed once per run and shared by the lineage, so the recursive predecessor check fails too. With `--no-lineage` the set is exactly {V7}, and the test asserts both.
- **Ledger envelope limit: {V2, V7}.** The envelope.json-only edit is its own case, and fails exactly {V2}.
- **Added cases:**
  - an envelope-file-only edit;
  - a duplicated `grant_changed` issue ({V15}, the transition rule);
  - a deleted issue ({V15, V17}).

## Mutation checks

Each mutation was applied from a file backup and restored from it (never `git checkout`), using the harness at the scratchpad's `mutate.py`. Every one was re-run after the review refinements.

| # | Mutation | Caught by |
|---|---|---|
| M1 | drop `token_cap` from `_v8_action_checks` | `test_token_gate` Initial, JustUnder and Tranche tests |
| M2 | `_v8_manager_checks` counts the reissued row | `test_a_recovered_manager_reissue_checks_every_limit_and_excludes_its_own_row` |
| M3 | `charge` returns 0 for unknown rows | `ChargeTableTests`, `LineageGateTests`, `LineageChargeTests` |
| M4 | the token maximum multiplies by 1 | `TrancheTests`, `GateTests` |
| M5 | `compare_receipt_rows` compares status only | `LedgerSealTests`, `test_ledger_result_content_with_the_same_status` |
| M6 | verify accepts a pass with `compared == 0` | `test_a_pass_that_compared_nothing_fails` |
| M7 | request file written after `consume_manager_grant` | `test_the_file_is_durable_before_the_grant_is_consumed` |
| M8 | one `grant_changed` emission removed | `test_grant_history` (structural and scenario) |
| M9 | V15 transition check removed | `test_a_duplicated_grant_issue_event` (the first mapping to the deleted-issue tamper missed it; a dedicated case was added) |
| M10 | token check removed from `_v8_manager_checks` | `test_at_the_cap_a_paid_manager_call_pauses_and_an_unpaid_one_is_granted` |
| M11 | a hard `token_cap` at zero headroom | `test_at_the_cap_a_paid_action_pauses_for_a_decision_before_any_send` |
| M12 | V17 counts rows sent after the issue | `CleanPassTests` |
| M13 | the legacy refusal removed from `_v8_action_checks` | `test_a_pre_release_attempt_refuses_to_advance` |
| M14 | the conservative charge reverted to a flat U (RS1) | `ChargeTableTests` |

All 14 were caught.

## AC22 fixture changes, by category

**C1**
- **Manager-stub identity (A11).** `tests/manager_stub.py` provides `manager_reply`, used by the stubs in `test_maf_expansion`, `test_expansion_gateway`, `test_expansion_recovery`, `test_chartered_delivery_recovery` and `test_maf_progress_retry`. A paid v8 manager reply without session identity now stays `unknown`.
- **Actor argument.** `recover_delivery` callers pass `actor="andy"`.
- **Module roster.** `test_flow`'s release-staging roster gains `manager_requests`, `delivery_trace`, `receipt_compare` and `receipt_verify`.
- **Added assertions, none changed.** Grant history in boundary-b; the recovery actor; the checkpoint parent after quarantine.

**C3**
- **Token fields.** `TEST_TOKEN_BUDGET` in `shaper_intent_fixture`; `structured_verifier()` limits.
- **Legacy-version derivations strip the token keys.** v7 envelopes in five tests; the v1 and v2 contracts in `test_shaper_delivery_contracts`.
- **Exact expected dicts gain the new keys.** `tokens: 0` in headroom maps; `predecessor_charged` in `lineage_usage`; the envelope token limits; version 3 becomes 4.
- **Behaviour change (A4).** `test_claude_execution_contract` asserts that an unknown usage key is tolerated and a bad known counter is still rejected.
- **Runner limits.** The test gains the two token ceilings.

**C5**
- **Full-row seal (A11).** `SealedExpansionEvidenceTests` seals a full receipt built from `seal_view`.
- **Patch target moved.** The understated-lineage test patches `seal_view`'s blocks, consistently understating `lineage_usage` and `token_usage`, instead of `ExecutionLedger.lineage_usage`, which the gateway no longer calls.

**Review refinement**
- **Terminal seal test.** It gains a valid termination, because both seals now share one comparison helper that checks termination first.

## AC23: the hand check superseded

Evidence:
- `evidence/verify-fixture.txt`: the successor passes V1–V17; the abandoned predecessor passes, with V6, V11, V12 and V14 `not_applicable`.
- `evidence/trace-fixture.txt`: rows, grant histories, pgids, charges, the interleaved expansions, and the cap line "charged 16,000 of 20,000".
- `evidence/trace-fixture.json`.

| `receipt_check.py` check | Now covered by |
|---|---|
| `validate_receipt` | V2 |
| sealed digest matches | V1 |
| envelope headroom, roster, predecessors | V7 (limits projection), V6 |
| per-action provider and evidence level | V3; trace rows |
| manager (call, sequence, status) | V3; trace rows |
| manager sequences contiguous | V15(a) |
| send-start counts per row | V15(a) ("resent?") |
| expansion requests with authority | V4; trace expansion rows |
| `manager_progress` | V4 |
| recovery modes | V5; the trace header |
| sends before, during and after a pause | V15(e) by seq; the trace banner |
| automatic grant `consumed_by` | V4 and V15(b) |
| verifier evaluations present | V3, V11 and V12 under R14 |
| trace file size | V14 |

**Still run-specific** (`reconciliation.md` lists three; the approved success criteria name two):
- the stub scan;
- the D1 event-log content shape;
- the chartered-facts text search, which becomes a plain `grep` over `manager-requests/`.

## Manual checks against the real `v8-live-validation-3` run

The whole run tree hashed identically before and after each command.

- **`flow run trace v8-live-validation-3`** (`evidence/trace-vlv3.txt`): exit 0. It shows 7 rows with real timings, the Claude editor session, the automatic and engineer expansions interleaved, `unsupported_contract` and no token totals.
- **`flow run verify-receipt v8-live-validation-3`** (`evidence/verify-vlv3.txt`): exit 2, `unsupported_receipt`. This confirms I6 and P9 on a real pre-release run.
- **`flow run inspect-delivery` and `stuck`** still read the pre-release run.

## Not covered, or covered only in part

- Real Codex and Claude managers and editors under a v4 charter: not run live. That is `v8-live-validation-4`.
- The Codex manager `thread_id` through the gateway: covered at the contract level only.
- **RS1, resolved by the conservative charge (R9 and AC9 amended):** a usage block with no readable counter still charges U, and is reported as `unrecognised_usage`.
