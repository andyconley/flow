# Plan: Chartered v8 Delivery Recovery, chunk 2

Source: `solution.md` (Option A) and the approved `requirements.md` with its amendments. The plan-engagement decisions of 2026-09-24 are P1–P4 below. Anchors are at `b38989b`; see `research/plan-architecture.md` for evidence.

## Engagement decisions (engineer, 2026-09-24)

- **P1.** A v8 `resolve-execution` **refuses** `--evidence-file` (`v8_evidence_file_refused`).
- **P2.** A v8 call **requires** `--expected-generation N` (`expected_generation_required`). The value is the ledger owner generation, which `inspect-delivery` shows.
- **P3.** A v8 call refuses `resolved_not_dispatched` and `still_unknown` (`v8_disposition_unsupported`).
- **P4.** The worktree guard applies to v8 chartered delivery only.

## Desired outcome

An operator can take an interrupted v8 attempt whose producer or verifier response Flow already stored and complete it with three commands:

1. `inspect-delivery` reports the blocker and the owner generation;
2. `resolve-execution … --disposition resolved_completed --expected-generation N` records the resolution;
3. `recover-delivery-lead` continues.

There are zero resends and the receipt is truthful. Every other uncertain row is reported "unresolvable; abandon only". For those, the operator uses the existing, unchanged `release` (or the lifecycle `block`). Nothing new is built for abandonment.

## Scope

**In scope:**
- the v8 resolve route and its CLI contract (P1–P4);
- the ledger reconcile method;
- the binding check at continuation;
- inspection guidance, and a refusal that points to inspection;
- the receipt;
- lead changes after resolution;
- the worktree guard, the v8 no-dispatch guard, `send_lock` O_NOFOLLOW, and a MAF interpreter taken from `FLOW_MAF_PYTHON`;
- the ADR 0016 amendment.

**Out of scope:**
- manager-call resolution;
- trace-backed resolution;
- operator-authored import;
- automatic reconcile;
- the v8 no-dispatch regrant;
- any change to v5–v7 semantics other than the text of the missing-`--evidence-file` error;
- guarding recovery itself with the worktree check;
- schema changes.

## Contracts

- **CLI (`cli/flow.py:604-612`).**
  - `--evidence-file` becomes optional in argparse, and `--expected-generation` is added (`int`).
  - `resolve_execution` routes the call before any I/O:
    - **v8:** P1–P3 refusals.
    - **v5–v7:** `evidence_file_required` if the file is missing, and `expected_generation_v8_only` if the flag is given. Otherwise the call goes byte-identical to `execution_gateway.resolve_attempt`.
  - Refusal JSON carries `code`.
- **Route (`delivery_gateway._resolve_chartered`).** In order:
  1. validate the arguments;
  2. take `recovery_lock("recovery")` (non-blocking: `attempt_running` or `recovery_in_progress`);
  3. re-peek and check `envelope_changed`, `attempt_terminal`, and an active lead claim (otherwise `lead_generation_inactive`);
  4. apply the worktree guard to `envelope["worktree"]`;
  5. check that the owner generation equals the expected one (otherwise `owner_generation_stale`);
  6. under `delivery_authority_guard`, call `ExecutionLedger.resolve_observed_v8`.
- **Ledger (`ExecutionLedger.resolve_observed_v8`).** Under `send_lock` and `BEGIN IMMEDIATE`, it re-checks:
  - protocol 8, `recovery_version` 2, and attempt `started`;
  - the owner generation and the event high-water mark;
  - replay: the same digest is a replay; any other prior resolution refuses (`item_not_unresolved`);
  - the row status is `started` or `unknown` (otherwise `item_not_unresolved`);
  - the role is producer or verifier (otherwise `unresolvable_abandon_only`);
  - an observation exists (otherwise `evidence_insufficient`);
  - the digest matches and the result revalidates with `validate_result` or `validate_structured_verifier_result` (otherwise `evidence_invalid`);
  - dispatch evidence exists.

  It then appends through the shared `_append_resolution_locked`, which is extracted from `resolve_unknown` with identical v5 behavior. The evidence is `[{"kind":"flow_response_observation","path":"ledger:response_observations/<action_id>","sha256":<result_digest>}]` at `generation=expected_generation`. There is **no generation bump**.
- **Binding (`delivery_recovery.unbound_resolutions`).**
  - `recovery_eligibility` calls it after the uncertainty check and refuses with `resolution_unbound` unless every `operator_resolved_*` action has exactly one resolution with:
    - the same `action_id`;
    - disposition `resolved_completed`;
    - a result equal to the action's result;
    - `owner_generation` in the chain.
  - The chain is `{envelope.delivery_lead_claim.generation} ∪ {recoveries[].generation}`, each at or below the current owner generation.
- **Inspection.**
  - `EVIDENCE_NEEDED`: `"resolve-execution (stored response)"` for a producer or verifier with an observation; `"unresolvable; abandon only"` otherwise and for every manager call.
  - The projection gains `resolutions` (`resolution_id`, `action_id`, `disposition`, `owner_generation`).
  - The text output shows the resolutions and the owner generation.
  - The refusal detail appends `; see flow run inspect-delivery <work> --attempt-id <id>`.
- **Guards.**
  - **Worktree:** `_refuse_project_flow_in_worktree` raises `worktree_contains_project_flow` when the project `.flow` is at or under the worktree, or the worktree is under `.flow`. It runs in prepare (after `delivery_gateway.py:352`, commit 4) and in the route (commit 10).
  - **No-dispatch:** `regrant_not_dispatched` raises `v8_no_dispatch_regrant_unsupported` before any write.
  - **`send_lock`:** opens with `O_NOFOLLOW`.
  - **MAF:** a new `tests/maf_env.py` provides `MAF_PYTHON = os.environ.get("FLOW_MAF_PYTHON")` and a skip decorator whose reason names the variable. It replaces every hardcoded path and fallback.
- **Reason constants** are defined in `cli/delivery_recovery.py`.

## Commit sequence (Conventional Commits; full suite green after each)

**Group 1: guards and hardening** (commit 5 locks in existing guard behavior, and is a test only)
1. `fix(ledger): open send_lock without following symlinks`
2. `test: resolve the MAF interpreter only from FLOW_MAF_PYTHON`
3. `feat(ledger): refuse the no-dispatch regrant for protocol v8`
4. `feat(delivery): refuse a chartered worktree that contains the project .flow`: the prepare side only, with the prepare subtest. The route side lands in commit 10.
5. `test(delivery): an unknown manager call alone blocks a lead change`

**Group 2: reconcile**
6. `refactor(ledger): extract the resolution append shared by resolve_unknown`
7. `feat(ledger): resolve a v8 action from its stored response observation`
8. `feat(delivery): bind resolutions at continuation`: `unbound_resolutions` in eligibility, with the AC2 subtests.
9. `feat(delivery): guide each blocker in inspection and point refusals to it`: `EVIDENCE_NEEDED`, projection `resolutions`, the text output, and the refusal pointer. Updates `test_chartered_delivery_recovery.py:1106`.
10. `feat(cli): route v8 resolve-execution through a fenced chartered route`: the route, the CLI contract, the route-side worktree guard and its subtest, and the entry-point reachability test.
11. `test(delivery): recover boundaries (a), (c), and (e) after operator reconcile`
12. `docs(adr): amend ADR 0016 for v8 operator reconcile`
13. Validation evidence.

## Risks

- **R1** (a resolution outside the chain). Resolution happens at the current generation, which is always in the chain. A mutation that bumps the generation must fail the resolve-recover-seal-validate test.
- **R2** (a pre-guard attempt). The route applies the guard to `envelope["worktree"]`. Recovery itself stays unguarded (out of scope).
- **R3** (an orphaned child after resolution). `attempt_running` covers the live run, and the drift check runs after resolution. **Residual:** a resolved producer with no verifier input is checked for scope only, and its diff is then judged by the verifier.
- `solution.md` R4 (permanently blocked manager-call and unobserved rows, accepted under ADR 0012) and R5 (`resolve_unknown` rejecting `started` rows, answered by the separate `resolve_observed_v8`) are requirement-level risks, settled in `requirements.md` and in the ledger contract above.
- **R6** (v5–v7 CLI). Only the text of the missing `--evidence-file` error changes. The exit code stays 2.
