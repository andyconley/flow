# Validation plan: first supervised MAF execution slice

Plan approved by Andy on 2026-09-19. Test targets are the new Flow-owned contracts, ledger, CLI gateway, supervised child protocol, local adapter and receipt. The prior run-local spikes are background evidence, not substitutes for production-path tests.

## Automated proof

1. **Contracts without MAF:** round-trip canonical versioned envelope, action, decision/grant, result and receipt. Reject unsupported versions, altered digests, missing links, invalid states, unsafe paths and oversized task/protocol data. Ordinary Flow CLI commands must import and run without the optional MAF package.
2. **Gate and ledger:** transactions enforce the allowlist, six-delegation, three-concurrent, two-replan and zero-paid envelope. A duplicate action with changed payload, expired/reused grant, denied role/provider/model, and missing definition produce zero local-adapter calls. One grant maps to at most one observed physical dispatch. `unknown` blocks automatic retry.
3. **CLI and lifecycle:** use the existing temporary-repository harness. `execute-local` requires an existing `implementing` run, valid revision-2 manifest and approved assignment/task artifact. Absent/invalid run, wrong state or changed source digest stops before provider work. Verify `run.json` and `events.jsonl` change only through lifecycle transitions.
4. **Supervision and protocol:** run a fake child to test start/proposal/decision/result/finish correlation. Reject wrong protocol version, foreign attempt/action, duplicate or non-monotonic message ID, malformed/oversized JSON, premature finish, EOF, timeout and child crash. The parent closes the process and records a terminal attempt. A failure before dispatch has a sealed no-dispatch receipt; post-dispatch uncertainty is `unknown` with reconciliation needed.
5. **Guarded construction:** prove the Flow CLI route reaches the guarded factory. A raw MAF Agent/Executor or an envelope requesting a disallowed participant is rejected before launch or adapter invocation. The MAF child has no provider credentials or raw-participant input path.
6. **Full stub path:** run the CLI with an optional MAF child and deterministic `local-stub` adapter. Inspect ledger and sealed receipt independently: action intent, decision, grant, dispatch observation, normalized result, definition/envelope digests, checkpoint reference or explicit absence, and output hash must agree. Stubbed work is labeled `local-stub` and makes no Ollama claim.
7. **Mutation checks:** deliberately disable grant validation, reuse a consumed grant, change a receipt link, and send a foreign attempt ID. The covering tests must fail, then pass when restored.

## Required runtime acceptance

Run one bounded `test-engineer` task through the real Flow CLI, optional supervised MAF child and configured local Ollama server. Record the installed MAF package versions, model/server identity, CLI command, attempt ID, policy/adapter observation, receipt path, output hash and source digests. Independently compare receipt to the ledger and source files. Model prose quality is not the test oracle. If Ollama is unavailable, record `runtime_unavailable` and leave the physical-worker acceptance criterion open; a stub run cannot satisfy it. No paid provider call is part of this plan.

## Regression and operational checks

Run `/opt/homebrew/bin/python3.12 -m unittest discover -s tests`, focused execution tests, `flow run verify`, `flow run validate-orchestration` at the required stages, CLI `--help`, `flow doctor`, `git diff --check`, and a fresh install smoke with and without the optional runtime. Review the deny path, receipt provenance, process cleanup and install isolation independently before handback. Document per-check transfer limits if a disposable fixture stands in for a real project run.
