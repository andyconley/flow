# ADR 0013: Fenced continuation after an operator resolution

Status: accepted for the post-resolution action-3 slice, 2026-09-20.

## Decision

An evidence-backed resolution may authorize a separate, append-only continuation epoch attached to the original terminal attempt. The attempt status and original receipt bytes stay terminal and immutable. Flow records the epoch's owner generation, exact resolution and checkpoint lineage, grant history, send claim, MAF acknowledgment, and linked receipt. It applies delegation, concurrency, replan, provider, and budget limits across the full lineage.

Only two dispositions may continue. `resolved_completed` replays the validated durable response to the restored action-3 MAF request without another grant or provider send. `resolved_not_dispatched` may obtain one fresh policy grant for the same action ID only after the pinned runtime restores the Flow-verified checkpoint and reports that exact request pending. Flow claims the send once under its send lock before adapter I/O. A lost response after that claim becomes unknown and is not automatically retried.

Checkpoint metadata alone never authorizes a send. Flow verifies the original receipt, resolution, source/envelope, request, checkpoint bytes/runtime, and ledger barrier before the child starts and again at the send boundary. The archived live unknown action lacks a resolvable disposition and remains blocked. Historical v1 and v2 records remain readable without gaining continuation eligibility.

## Consequences

The continuation has its own receipt and inspection lineage; the original receipt is a historical snapshot, not a record to rewrite as the ledger advances. Repeated calls are idempotent or explicitly refused. If the actual Flow checkpoint cannot produce the pinned MAF pending request before regrant, the no-dispatch path halts without a send.

## Alternatives considered

A successor attempt would require translating MAF's attempt-derived action identity and aggregating policy across attempt rows. Reopening the terminal attempt would erase the original handback. The attached epoch keeps the original action identity and preserves both historical receipts.
