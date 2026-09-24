# Test strategy: first MAF adoption slice

- Owner role: test-engineer
- Date: 2026-09-19
- Scope: one supervised local `test-engineer` worker launched from an existing
  Flow run. Codex, Claude, MCP, multi-worker scheduling, and restart-safe
  recovery remain later work.

## Test Coverage Analysis

### Current coverage

- Existing CLI tests already establish an isolated repository and fake-home
  subprocess convention in `tests/test_flow.py`.
- The four spikes provide useful prototype evidence for Flow gating,
  interruption, duplicate replay, and replan limits. They do not cover a
  production CLI, supervised child protocol, sealed receipt, or optional
  runtime packaging.

### Coverage gaps

- No production execution-domain schema, attempt ledger, Flow gateway, runner
  protocol, local adapter, or CLI command exists.
- A deterministic local stub cannot establish that Ollama was reached; prior
  receipts correctly distinguish a stub from an observed provider call.
- The MAF multi-turn probe did not prove separate-process replan identity or
  recovery. Those must not become implied acceptance for this first slice.

## Recommended Tests

1. **Execution records round trip and reject incompatible input** — Unit test
   each versioned contract without MAF installed. A valid envelope, action,
   decision/grant, observed result, checkpoint reference, and receipt retain
   their canonical bytes/digests after readback. Unknown major version,
   altered digest, invalid enum, oversized task reference, and missing linked
   identifier fail before persistence.

2. **Policy ledger issues one grant for one exact action** — Unit/integration
   test the SQLite boundary. A matching allowlisted local action records
   intent, allow decision, one grant, and one consumed dispatch. Reusing the
   grant, changing its task/provider/role binding, duplicate action ID with a
   different payload, or a denied role/provider produces zero adapter calls.
   Include six delegation, three concurrent, two replan, and paid-budget-zero
   boundary examples even though the vertical path performs only one call.

3. **CLI only attaches an attempt to an eligible existing run** — CLI
   integration test with the established temporary project fixture. A valid
   implementing run and manifest assignment creates an execution attempt;
   missing run, wrong lifecycle, invalid manifest, absent/changed effective
   specialist definition, and unapproved assignment create no dispatch state.
   Assert `run.json` and `events.jsonl` are unchanged by worker status.

4. **Supervised protocol accepts only correlated, bounded records** — Use a
   fake child process at the process boundary. The oracle is a `start` request
   with the expected protocol/attempt/envelope identities followed by a
   correlated proposal and terminal event. Reject wrong protocol version,
   duplicate/non-monotonic message ID, mismatched attempt/action ID, malformed
   or oversized JSON line, unexpected EOF, and a terminal event before all
   actions are terminal. Assert subprocess cleanup and an explicit Flow state.

5. **Guarded construction rejects raw MAF participants** — Integration test
   the application factory, using a sentinel raw Agent/Executor object. The
   factory accepts only a resolved Flow `test-engineer` definition plus unique
   instance identity; it rejects the sentinel before child launch. A static or
   integration entrypoint test should also prove `execute-local` reaches that
   factory, rather than treating this factory-only test as global enforcement.

6. **A denied proposal reaches no worker transport** — Drive a fake runner to
   propose a forbidden role or provider. Assert no adapter invocation, no
   dispatch observation, a denial tied to the action ID, and a receipt/status
   that says `denied`. This is the principal oracle for Flow, rather than MAF,
   retaining dispatch authority.

7. **One allowed local-stub run produces a truthfully linked receipt** — Full
   CLI-to-child integration with a deterministic fake adapter. Given one
   allowlisted proposal, assert ordered intent → decision → grant → consumed
   grant → dispatch observation → normalized completed result, then validate a
   sealed receipt against ledger rows, charter/envelope, manifest, definition
   digest, checkpoint reference (or explicit absence), output hash, and
   attempt identity. Its provider state must be `local-stub`; it must never
   claim an observed Ollama request.

8. **Observed Ollama smoke produces evidence distinct from the stub** — Opt-in
   manual/runtime verification against a configured local Ollama server, using
   a bounded harmless task and the same CLI path. The oracle is a completed
   attempt whose Flow-observed provider/model/session fields and output hash
   appear in the validated receipt. Capture the command, environment/version,
   server/model identity, attempt ID, and receipt path. If Ollama is absent or
   unavailable, record `runtime_unavailable` with remediation; do not turn a
   fake result into local-provider evidence.

9. **Failure after grant stays unknown and never retries itself** — Process
   integration test with a fake adapter that blocks after the grant is
   atomically consumed, followed by child exit/timeout. Assert `unknown`, one
   consumed grant/dispatch observation, no automatic second adapter call, and
   a receipt/status that names reconciliation. Repeat for launch failure and
   worker-reported failure, which should have their own explicit states.

10. **Base Flow works with MAF unavailable; the opt-in path explains absence**
    — Fresh-install/subprocess smoke in an environment without the optional
    MAF package: ordinary `flow` help, run status/verify, and contract/policy
    tests work. `flow run execute-local` fails before attempt dispatch with
    precise install/remediation text. In the optional environment, test the
    pinned runner imports and protocol startup. Do not make network installation
    part of the ordinary test suite.

## Priority

- Critical: 2, 4, 6, 7, 9. These prove no bypass, duplicate physical call, or
  false receipt claim can hide behind the runner boundary.
- High: 1, 3, 5, 10. These protect schema evolution, lifecycle ownership,
  guarded construction, and dependency isolation.
- Medium: 8. It validates the configured local deployment after automated
  boundary tests pass; its model text is not a deterministic test oracle.

## Verification Notes

- **Automated checks:** Run new focused `unittest` modules in the base Python
  environment, the existing Flow suite, CLI help, `flow run verify`,
  `flow run validate-orchestration`, and `git diff --check`. Protocol and
  adapter tests use fakes only at the child-process and local-server boundaries;
  do not mock contract serialization, ledger, policy, or receipt validation.
- **Manual/runtime checks:** Run the one Ollama smoke only after its backend,
  model, timeout, and safe task are explicitly configured. Inspect the sealed
  receipt independently from runner stdout. No paid provider call belongs in
  this slice.
- **Mutation checks:** Deliberately remove grant validation, consume a grant
  twice, alter a receipt link, and make the child send a foreign attempt ID.
  The corresponding tests must fail. This is a focused way to validate the
  policy and provenance oracles, rather than a coverage percentage target.

## Inconsistencies to resolve before implementation

1. `plan-requirements.md` describes R6 as an isolated integration test that
   invokes an observed local worker, while `plan-integration.md` correctly
   places the real Ollama invocation in an opt-in manual smoke and uses a fake
   adapter for automated integration. Split R6 explicitly into automated
   `local-stub` acceptance and a required/optional deployment smoke criterion;
   otherwise the implementation team cannot tell whether CI must have Ollama.
2. The plan calls the gateway/factory the sole construction path but also says
   the child “constructs” a guarded participant. Define one ownership rule:
   the child may instantiate only a Flow-supplied guarded executor factory from
   the immutable envelope, while the parent gateway alone grants and invokes
   the adapter. The test in item 5 needs that exact seam.
3. Product success says a runner failure leaves a receipt/status response;
   requirements R8 promises an explicit attempt/result state but does not say
   whether a failed-to-start attempt receives a sealed receipt. Decide this
   before coding. The recommended behavior is a sealed terminal receipt with
   no dispatch/result and a machine-readable failure category.
