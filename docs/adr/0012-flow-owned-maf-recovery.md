# ADR 0012: Flow-owned recovery for supervised MAF attempts

Status: accepted for the recovery-first local worker slice, 2026-09-19.

## Decision

Flow reopens the original attempt and reads its durable ledger before starting a replacement MAF coordinator. The immutable envelope, action ID, charter snapshots, and manifest snapshot bind recovery to the original authorization. A transactional owner generation fences earlier parent processes. MAF checkpoint state is subordinate: it can restore coordination, but cannot grant or infer permission to call a provider.

A committed, validated worker result can be replayed to the same action without a second adapter send. A dispatch-start record without a complete durable response is uncertain and blocks automatic continuation. A missing response, timeout, or missing checkpoint never proves the provider was not called. A receipt written before the terminal ledger transaction may be repaired only after its identity and contents match the ledger. Earlier schema-v1 attempts remain readable and are not automatically resumable.

Operator resolution is append-only. Completion requires a Flow-owned durable response observation that validates against the original envelope. No-dispatch requires positive evidence from the fenced send boundary. Narrative claims and absent Ollama responses do not meet either threshold. Ambiguity retains its reservation under the six-delegation and three-concurrent-action limits.

## Consequences

Recovery is conservative: a physically successful call can remain blocked if its response was lost before Flow recorded it. The current local Ollama route cannot provide provider-side exactly-once proof. The local send counter measures attempts observed by Flow. This slice keeps one local specialist and zero paid-model budget; a multi-turn scheduler, paid providers, and Shaper expansion need separate contracts.

## Alternatives considered

Restoring MAF before reconciling Flow could repeat a provider call. Building a Flow scheduler would duplicate the candidate runtime's coordination machinery. The chosen Flow-first gate retains replaceability and makes uncertainty visible.
