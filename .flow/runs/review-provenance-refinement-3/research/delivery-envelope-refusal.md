# Delivery Envelope Refusal

No provider send occurred. After managed MAF activation succeeded, `execute-chartered-job` refused with `Magentic limits differ from approved envelope`.

The sealed Shaper/Delivery runtime allowance was 1,800 seconds. Protocol v8 accepts `max_runtime_seconds` only from 1 through 600. Definition approval, Delivery sealing, plan approval, and orchestration dispatch validation did not enforce that downstream runner bound.

Disposition: preserve this run, do not rewrite the sealed limit, and create a successor capped at 600 seconds. Add an early-gate regression so an unsupported Delivery envelope cannot reach execution preparation.

