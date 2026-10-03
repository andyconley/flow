# V9 orchestration ownership correction

Baseline: v0.40.16, `ea55e55baab50580b5034645b60a2a5b68df4c3c`.
The initial clean checkout was `b3893de` on
`codex/cancel-wakeup-all-waits`; current refs were fetched and the local
`codex/v9-magentic-ownership` branch was created at the audited baseline.
No repository push, merge, release or installed-runtime update was performed.

## Responsibilities

| Owner | Responsibility |
| --- | --- |
| Shaper | Outcomes, scope, constraints, acceptance criteria |
| Flow | Sealed authority, permitted frontier, independent authorization, local-first provider binding, credentials/sends, generation fences, recovery and evidence-based acceptance |
| Stock MAF/Magentic | Delivery Lead facts/plan/progress loop, assignment/task proposals, bounded progress retries/replanning, checkpoints and completion proposal |
| Codex, Claude, local models | Workers reached only through Flow's gateway |

The v9 relay early return and parent-owned worker/repair scheduling loop are
removed. The separate v9 stock integration reuses the existing manager-proxy,
guarded-participant, request-info checkpoint and shared progress-parser design.
V8's concrete roster and checkpoint identities are not copied into v9.

## Verification types

`test_stock_v9_coordinates_edit_collect_verify_and_seals_real_evidence` runs the
pinned stock MAF packages in a real supervised process. It coordinates three
dependent assignments, applies a scoped fixture change, runs the chartered test,
selects local producer/collector and a disjoint hosted verifier, evaluates
structured verification, and seals/verifies the receipt. Provider responses are
mocked; the workflow, filesystem, test process, checkpoints, ledger and receipt
validation are real.

Gateway and ledger tests cover uncertain sends without fallback, positive
no-send/capacity evidence, restart/resume, exhausted candidates, malformed
manager responses, absent/invalid/non-passing verifier evidence, retained test
failure and bounded repair. Added adversarial tests cover stale completion,
cancellation at completion, artifact mutation after verification, and repeated
worker proposals. They use mocked coordinator callbacks to exercise Flow's
independent gates; they are not real-model claims.

A separate bounded real-provider smoke used the actual administrator catalog,
real sealed test authority and delivery guard, stock MAF, the durable send fence
and `llama3.1:8b`. It made seven observed local sends (five manager calls and two
dependent read workers). Flow rejected the next progress proposal because no
unfinished assignment remained and the manager had not proposed completion.
There was no retry, fallback or product acceptance. The retained evidence is
`/private/tmp/flow-v9-guarded-smoke-b2lforny/result.json`, with the ledger and
checkpoints under that isolated root. This is a read-only smoke, not proof of a
real-provider edit/test/independent-verifier acceptance. No hosted model was
called. The first smoke script was rejected before execution because it stubbed
the authority guard; the executed replacement has no guard stubs.

## Compatibility

V8 contracts, checkpoints and receipts retain their existing path. Existing
terminal v9 receipts are not rewritten. V9 clean-boundary continuation starts a
fresh stock coordination epoch, carries accepted assignments forward, and
retains original logical identities for pending no-send chains. Historical relay
chains are reconstructed only when the exact logical identity can be proved.
Unknown/started sends require explicit reconciliation. Historical budgets remain
sealed and can be too small for stock manager phases; they are never enlarged
silently. Arbitrary v9 MAF checkpoint restoration is not implemented: checkpoints
are retained as provenance while restart is from an observed clean boundary.

A healthy pinned MAF interpreter is now required by the default v9 route before
attempt preparation. Local source changes can make an installed managed-runtime
pointer stale; local checks use `FLOW_MAF_PYTHON` explicitly without changing that
pointer.

Flow also refuses a new v9 attempt while an earlier attempt for the same work
is still started. Token charges follow the sealed charter across attempts, so
abandoning an attempt does not reset its authority budget. Historical envelopes
with larger action budgets remain readable without rewriting their contracts.

## Checks and changed files

The full suite passed: 2,026 tests in 456.550 seconds using the pinned MAF
interpreter and hash-pinned wheelhouse. After the final recovery and budget
changes, the focused gateway, selection, receipt, ownership and migration suite
passed: 178 tests in 23.816 seconds. The selection suite separately passed 31
tests, and the ownership adversarial suite passed four tests.
`scripts/regenerate-flow-help.py --check` and `git diff --check` passed.
`flow doctor` reports the expected managed-runtime identity mismatch against
the modified local runner; the installed pointer was left unchanged.

Implementation files: `cli/delivery_gateway.py`, `cli/execution_contracts.py`,
`cli/execution_ledger.py`, `cli/maf_runtime.py`, `cli/maf_supervisor.py`, and
`runtime/maf_runner/delivery_lead.py`.

Tests: `tests/test_chartered_delivery_gateway.py`,
`tests/test_delivery_selection.py`, `tests/test_v9_orchestration_ownership.py`,
and `tests/v9_coordinator.py`.

Documentation: this report, `docs/adr/0022-deterministic-provider-selection.md`,
and `docs/maf-adoption-design.md`.

## Independent review and authorized recovery fixes (2026-10-03)

An independent local review reproduced two defects in the final restoration
tree. A positively observed `observed_not_executed` capacity refusal was reported
as not requiring reconciliation, but continuation rejected it as uncertain.
Also, a successor using the same logical action ID was refused at
`max_actions=1`, and that pre-send budget refusal was incorrectly wrapped as
`RecoveryRequired` even though the successor adapter never ran.

The authorized local correction changes these boundaries:

- continuation admits positively observed non-execution without counting it as
  accepted work; pending selection chains retain their original logical task,
  sequence, manager turn and refusal evidence;
- an exact refused chain is recovered from its journal or durable refusal row;
  ambiguous unfinished chains are refused;
- the action budget counts a successor under its existing logical ID, while a
  new logical action at the cap is refused before provider I/O;
- reusing the original sequence does not advance the next sequence slot again;
  new coordination calls still consume their own sealed budget;
- a failed ownership/budget check before the physical-send claim keeps its
  deterministic exception; a failure after the claim remains recovery-required.

Added regressions cover interruption immediately after the capacity refusal,
completion within the exact remaining action budget, interruption after the
successful successor, no resend on subsequent continuation, and rejection of
new work at the cap without calling its adapter. The existing unknown-send
restart and sealed-token-spend tests remain enforced. No implementation or
configuration from another session was reverted. The initial tracked diff
matched the reviewed snapshot exactly before editing.

Final focused gateway, selection, ownership, receipt, migration and v9 CLI
checks passed **180 tests in 26.200 seconds**. The verified pinned interpreter
is `/Users/andyconley/.flow/runtimes/maf/3ae9b98299261235de12e1c085c4ec8ca1b7881c37fc199595aa10ef8f3158c0/bin/python`
with `agent-framework-core==1.19.0` and
`agent-framework-orchestrations==1.2.0`. The final full suite passed
**2,031 tests in 488.507 seconds, with zero failures, errors or skips**, using
that interpreter in `FLOW_MAF_PYTHON`, `PYTHONDONTWRITEBYTECODE=1`, and
`/opt/homebrew/bin/python3.12 -m unittest discover -s tests -q`. The approved
test process ran outside the outer sandbox so disposable loopback sockets and
nested macOS confinement checks could execute. Its log is
`/tmp/flow-v9-fix-full-final.log`; focused output is
`/tmp/flow-v9-fix-focused-final.log`.

The final branch remains `codex/v9-magentic-ownership` at baseline HEAD
`ea55e55baab50580b5034645b60a2a5b68df4c3c`, with local uncommitted edits.
The tracked binary diff SHA-256 is
`2deb9558b81a8155be421fb71a6e7cad9a16129753db98e8269d043f959d9f22`.
Only `cli/delivery_gateway.py`, `cli/delivery_selection.py`,
`cli/execution_ledger.py`, `tests/test_delivery_selection.py`, and this report
were changed by this correction; all other restoration edits were preserved.
No commit, push, merge, release or branch switch was performed.
Logs and exact changed-file hashes are retained outside the checkout under
`/tmp/flow-v9-fix-*`; the final inventory is
`/tmp/flow-v9-fix-tree-identity.json`. `git diff --check` and generated help
`--check` pass.

The earlier review independently ran 2,029 tests in 464.827 seconds with zero
assertion failures, two outer-sandbox loopback errors and seven skips. Both
errored tests passed in an approved isolated seven-test socket run; six nested
macOS confinement skip events were covered by a separate six-test run that
passed outside the outer sandbox. The other skip was the offline upstream
refresh check. That is separate from the final correction's full-suite result.

The installed launcher invokes the released `~/.flow/source/cli/flow.py`, not
this checkout; its doctor reports the release runtime ready. The current
checkout's default managed-runtime probe reports `identity_mismatch`. Neither
the installed pointer nor installed runtime configuration was changed.

The retained smoke script, log and `result.json` are consistent with facts,
plan, initial progress, two dependent read workers and two later progress
checks: five manager calls plus two worker calls. The last progress response
requested work after the frontier became empty and was rejected. Its ledger
and checkpoints are no longer present at the reported smoke root, so the seven
sends cannot now be independently audited for replay or identity. Those calls
are not real-provider edit/test/independent-verifier acceptance proof.

That live acceptance proof remains missing. Flow-owned readiness in this
review executor reported `probe_failed` for local candidates and
`authentication_unavailable` for hosted candidates. No credentials, access,
credits or installed configuration were changed. Arbitrary checkpoint restore
remains unsupported; clean-boundary continuation does not imply arbitrary
checkpoint recovery or production readiness.

### Authorized verifier completion correction

A separate isolated mocked-provider probe found that a verifier's positively
observed capacity refusal followed by its successor's `valid_pass` still cannot
seal a completed receipt. `seal_v9_attempt` in `cli/execution_ledger.py` collects
all physical verifier action rows, including `observed_not_executed`, then
requires unique verifier assignment IDs. It therefore rejects the refused row
plus successful row with `protocol v9 terminal status contradicts verifier
evidence`. The probe called a Claude verifier that positively refused capacity,
then a Codex verifier that passed; neither was a real provider call.

The original reproduction and output are retained at
`/tmp/flow-v9-verifier-capacity-probe.py` and
`/tmp/flow-v9-verifier-capacity-probe.log`. This is separate from the two
recovery/budget corrections above. After explicit approval, the terminal gate
was corrected to count completed verifier executions, while retaining proven
non-execution in the receipt's refusal and successor lineage. The receipt
validator already makes this distinction and still checks the refusal's
positive evidence, successor chain and exact semantic evidence. No audit rows
are removed or rewritten. Duplicate actual verifier executions remain invalid,
every distinct required verifier must still pass, and an unknown send still
blocks completion before this gate.

Five new regressions passed. The positive case uses real pinned stock MAF to
coordinate an edit, evidence collection, a Claude capacity refusal and a Codex
`valid_pass`, then verifies the sealed receipt. Providers are mocked; the
workflow, filesystem, chartered test, ledger, refusal evidence and receipt
validation are real. Negative cases prove that duplicate actual passes,
missing durable evaluation, unusable successor evidence and unknown verifier
execution cannot complete. Removing semantic evidence from the successful
receipt is also rejected by offline validation.

The updated focused gateway, selection, ownership, receipt, migration and v9
CLI suite passed **185 tests in 27.342 seconds**. The latest full suite passed
**2,036 tests in 485.631 seconds, with zero failures, errors or skips**,
using the same verified pinned interpreter, full-suite command and approved
isolated socket/nested-sandbox test permissions described above. Logs are `/tmp/flow-v9-third-regressions.log`,
`/tmp/flow-v9-third-focused.log` and `/tmp/flow-v9-third-full.log`.
The latest exact tree inventory is `/tmp/flow-v9-third-tree-identity.json`.
The tracked diff SHA-256 is
`5bf87f20eb1628a84111f90791dfec2e682e4469c5000a1f895457ccc4321a07`.
This correction changes only `cli/execution_ledger.py`,
`tests/test_chartered_delivery_gateway.py` and this report; it preserves the
earlier corrections and restoration edits. The branch and baseline HEAD are
unchanged, with all edits local and uncommitted. The real-provider acceptance
and installed-runtime proof limitations above remain.
