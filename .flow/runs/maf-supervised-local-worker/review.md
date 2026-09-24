# Quality review: supervised local MAF worker

## Review Summary

**Verdict:** APPROVE

**Overview:** The approved first slice is implemented and verifiable: Flow controls the execution envelope, policy grant, local provider call, ledger, and receipt while an optional supervised MAF child proposes one bounded action. The final code passed focused and full tests, three mutation checks, and a physical Ollama run whose receipt independently reconciles with the ledger and exact source snapshots.

### Critical Issues

- None found.

### Important Issues

- None open. The initial review findings were resolved: grants now expire after 60 seconds with a recorded `grant_expired` reason; the envelope and receipt retain approved source paths, hashes, and run revision; checkpoint IDs must resolve to a file under the attempt before inclusion in a receipt; and the required protocol, denial, expiry, checkpoint, and receipt-link tests were added.

### Suggestions

- `runtime/maf_runner/__main__.py`: The child selects `checkpoints[0]`; document the ordering guarantee or describe this as a returned checkpoint reference. Acceptance needs a valid linked checkpoint, which the final run provides.
- `docs/cli-reference.md`: Keep “sealed receipt” scoped to an owner-only atomic Flow record. It is not a cryptographic signature or independent Ollama attestation. The security review and handback state this limit.

### What's Done Well

- The parent validates the envelope-bound action before adapter invocation. `ExecutionLedger` commits the decision, enforces run-wide delegation/concurrency caps, and consumes a grant once within a transaction. Adapter uncertainty is recorded as `unknown` without automatic replay.
- The optional MAF child uses a fixed process command, minimal environment, bounded protocol reader, deadline, and clean-exit check. Local HTTP is fixed to loopback with proxies and redirects disabled. Test doubles are labeled `local-stub`.
- Each attempt retains exact owner-only snapshots of the manifest, requirements, and acceptance criteria. The final receipt includes source and execution digests, a matching action/result, and a validated checkpoint reference.

### Verification Story

- Tests reviewed: **yes.** Focused execution/supervisor suite passed 25/25; final post-change full repository suite passed 1,120 tests with one skipped. Fake-child tests cover malformed and oversized messages, wrong version/identity, EOF/crash, duplicate proposal, timeout, and nonzero exit. Three temporary mutation checks made the relevant grant, attempt-binding, and receipt-link tests fail, then the restored suite passed. Details are in `validation-results.md`.
- Build/runtime checks reviewed: **yes.** `flow run verify` and handback orchestration validation passed; generated help check and `git diff --check` passed. The installed develop launcher exposes `execute-local`; Claude/Codex sync checks and static runtime smoke were clean. I independently reconciled physical attempt `44d98b9e0beb4d0d9a59c682b30af299`: completed ledger attempt/action and receipt, one-use grant, normalized Ollama result, envelope digest, all three owner-only snapshot hashes, and checkpoint file match.
- Remaining risks: The MAF child shares the operator's user account and is not an OS sandbox. The receipt records Flow's local HTTP observation, not model internals or answer quality. Four live client checks remain manual, but are outside this CLI execution slice. Paid providers, multiple workers, and restart/reconciliation remain later slices.

## Evidence inventory

- Approved intent: `.flow/runs/maf-adoption-design/plan.md` and `validation-plan.md`; this run's `requirements.md`, `acceptance-criteria.md`, and `plan.md`.
- Changed surface: `cli/execution_contracts.py`, `execution_ledger.py`, `execution_gateway.py`, `local_worker.py`, `maf_supervisor.py`, `cli/flow.py`, `runtime/maf_runner/`, `tests/test_execution.py`, `tests/test_maf_supervisor.py`, README, CLI reference, generated help, architecture design, and ADR.
- Runtime proof: `execution/44d98b9e0beb4d0d9a59c682b30af299/receipt.json`, its envelope and three source snapshots, `execution/ledger.sqlite`, and the referenced checkpoint; checks and mutations in `validation-results.md`; independent security recheck in `research/security-review.md`.
- Review dimensions: Correctness, clarity, structural fit, safety, and verifiability apply and were reviewed. Implementation was committed as `3503354 feat: add supervised local MAF execution through Flow`, following the Conventional Commit format.
