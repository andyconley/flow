# Business Analysis

- A provider response is not verification by itself. Successful handback requires a Flow-validated structured verdict bound to the exact observed diff and test evidence.
- A valid pass may complete the existing gate. A valid fail ends the attempt as failed and preserves findings. Missing, malformed, oversized, contradictory, or mismatched output is a known unusable verdict and fails before handback without automatic retry.
- Transport uncertainty remains `unknown`; a completed provider response whose verdict is unusable remains an observed completed call.
- `max_verifier_calls` must be separately sealed and enforced before provider send across all verifier identities.
- Direct planning would be sufficient only if protocol versioning were already settled.

