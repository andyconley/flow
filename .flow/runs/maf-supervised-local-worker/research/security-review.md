# Security review: supervised local worker

## Summary

- Current findings: Critical 0; High 0; Medium 0; Low 0.
- Verdict: **approved for the bounded, local-only first slice.** All five findings from the first pass were addressed in code. This is a Flow-observed execution record, not proof that an arbitrary local Ollama service is honest or that the same-user MAF process is isolated.
- Recheck evidence: 13 `tests.test_execution` tests passed; a focused pipe check confirmed that a child emitting a partial line timed out in about 0.06 seconds against a 0.05-second deadline. Completed real Ollama attempt `f85ffff2ef074a0992a4c4f0e92336e2` reports the approved `llama3.1:8b` model, `flow_observed_local_http_response` evidence, and a result digest. No provider call was made during this security recheck.

## Original findings and disposition

### Resolved — Local execution records were world-readable

`cli/execution_gateway.py:70-75,87,147` now makes the execution, attempt, and checkpoint directories `0700` and writes envelope and receipt files `0600`. `cli/execution_ledger.py:23-31` creates/chmods the SQLite file to `0600`. The completed real attempt and ledger were observed with those modes. `tests/test_execution.py:190-198` checks them. The enclosing execution directory is now `0700`, also preventing other accounts from traversing to older attempt files beneath it. Users must still protect Git backups and other exports of these records.

### Resolved — Partial protocol output bypassed the deadline

`cli/maf_supervisor.py:38-65,134-141` now reads ready bytes with `os.read`, carries partial lines in a bounded buffer, and rechecks a monotonic deadline. `tests/test_maf_supervisor.py` permanently covers partial-line timeout.

### Resolved — Local HTTP could follow proxies or redirects

`cli/local_worker.py:18-20,39-49` fixes the endpoint to loopback, rejects overrides, uses `ProxyHandler({})`, and refuses redirects. `tests/test_execution.py:200-232` checks the handler configuration without external network access. This prevents those default `urllib` paths from sending task and specialist text outside the intended local service.

### Resolved — Completed results had weak model and digest validation

`cli/execution_contracts.py:92-110` now validates the versioned result, approved model/provider, physical-call and evidence labels, bounded nonempty output, recomputed output digest, and nonnegative integer usage. The gateway invokes that validator before recording completion (`cli/execution_gateway.py:114-118`). The Ollama adapter rejects a mismatched model and malformed message/usage (`cli/local_worker.py:58-76`). `tests/test_execution.py:177-188` exercises altered result fields. The evidence label accurately describes a Flow-observed local HTTP response; it does not independently attest to model internals.

### Resolved — Child completion ignored its exit status

`cli/maf_supervisor.py:157-176` now requires the child to exit within the deadline with status zero after `workflow_finished`. A nonzero or late exit raises, so the gateway can retain the completed action fact while marking the attempt failed. `tests/test_maf_supervisor.py` permanently covers nonzero exit.

## Positive controls

- The parent validates an envelope-bound action before it invokes the provider (`cli/execution_contracts.py:67-89`; `cli/maf_supervisor.py:142-155`; `cli/execution_gateway.py:107-118`).
- The SQLite policy decision and one-use grant are transactional. A duplicate action cannot cause a second dispatch within one attempt (`cli/execution_ledger.py:65-104`).
- The task source is confined to the run directory, and paid routes are excluded from this slice (`cli/execution_gateway.py:26-30,61-67`; `cli/execution_contracts.py:13,51-59`).
- An adapter exception marks a dispatched action `unknown`, without automatic retry (`cli/execution_gateway.py:119-135`).

## Remaining boundary for later slices

The child is an ordinary subprocess under the operator's user account. Its minimal environment reduces accidental credential inheritance but does not prevent filesystem or loopback access by malicious same-user code. Receipts are local Flow records, not cryptographically sealed attestations. Before paid providers, side-effecting tools, or multiworker execution, define process isolation and permissions, cross-attempt idempotency/reconciliation, and receipt integrity. These are adoption issues outside this first local-worker acceptance scope.
