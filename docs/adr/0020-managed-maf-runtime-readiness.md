# ADR 0020: Managed immutable MAF runtime and pre-attempt readiness boundary

- Status: accepted
- Date: 2026-09-27

## Context

The first real chartered Delivery Lead attempt created durable attempt state,
then failed before a manager or provider call because the CLI interpreter did
not have the optional Agent Framework packages. A terminal attempt is evidence
and must not be rewritten merely because the failure happened before work.

## Decision

Flow owns an optional managed MAF environment outside source checkouts. Its
selection is a small JSON pointer under `~/.flow/runtimes/maf/`; environments
are addressed by a digest of the requirements lock, base interpreter and
platform. Provisioning stages, probes, then atomically switches that pointer.

`FLOW_MAF_PYTHON` remains an explicit compatibility override. It is
authoritative and must pass the same credential-free package, runner and
protocol probe; it never falls back to the CLI Python or managed selection.

Chartered preparation performs this probe after its read-only authority and
worktree checks, but before creating an execution directory, ledger row,
attempt envelope, receipt, grant or process. A refusal has the stable reason
`maf_runtime_unready`. New envelopes and receipts bind the observed runtime
identity, and the child echoes its digest before the first manager callback.

Ordinary `flow doctor` reports unavailable MAF as a warning because base Flow
does not require it. `flow runtime readiness` and `flow runtime smoke --target
maf` are strict Delivery checks.

## Consequences

- A failed runtime check consumes no delivery authority and is safely repairable.
- A successful Delivery attempt has an auditable interpreter/package identity.
- Historical attempts remain readable; no receipt or ledger migration occurs.
- A real provider run remains a separately authorized acceptance exercise.

## Rejected alternatives

- Environment variable only: makes a machine's delivery capability implicit and
  cannot provide a managed repair path.
- Installing into Flow's CLI Python: makes an optional runtime a base import and
  couples upgrade safety to the launcher interpreter.
- One mutable virtual environment: cannot prove which package set an attempt used.
- Vendoring MAF: transfers an upstream package lifecycle into Flow.
