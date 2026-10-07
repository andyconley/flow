# Local-agent resource observations

`cli/local_resources.py` observes resources without inference, model unloading or
system changes. On macOS it reads actual kernel pressure (normal/warning/critical),
raw VM compression/page-in/page-out/swap counters and interval rates, swap usage,
and Ollama `/api/ps` GPU/context residency and health latency. API health is a service
responsiveness proxy, not a GUI or inference speed measurement. Unsupported systems
and missing counters produce diagnostic unknown pressure, never fabricated distress.

The corrected POC's experimental controls are defaults, not user requirements:
critical kernel pressure or allocation failure stops immediately. Warning must last
30 seconds and accompany either at least 64 MiB of swapouts over 30 seconds across
three positive intervals with growth in the last 10 seconds, or three consecutive
API health losses/slowness exceeding max(2 seconds, 10 times baseline). Swap usage
alone and low availability percentages do not stop work. Unknown telemetry is visible
but is not classified as pressure. Thresholds remain explicitly configurable.

`ResourceMonitor` samples in a background thread, invokes `callback(sample, decision)`
and latches a stop reason. `check()` raises `ResourcePressureError` before subsequent
calls. The invoking adapter owns cancellation/backoff for an in-flight request;
monitoring never automatically retries an uncertain send. `record_error()` recognizes
allocation failures. Context-manager exit stops monitoring, without OS configuration
changes or writes outside the caller's normal artifact handling.
